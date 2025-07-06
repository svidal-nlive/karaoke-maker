#!/usr/bin/env python3
# packager/packager.py

import os
import json
import time
import signal
import threading
import shutil
import tempfile
import subprocess
from pathlib import Path
from pydub import AudioSegment
from mutagen.mp3 import MP3
from mutagen.id3 import ID3, APIC, TPE1, TALB, TIT2, TRCK, TYER

# Import pipeline utilities
import sys
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from pipeline_utils.file_lock import FileLock
from pipeline_utils import (
    setup_logger,
    redis_client,
    create_consumer_group,
    read_from_group,
    acknowledge_message,
    add_to_stream,
    set_file_status,
    handle_auto_retry,
    notify_all,
    is_file_processed,
    get_processing_status,
    set_processing_step,
    mark_file_processed,
    log_processed_file,
    STREAM_SPLIT_DONE,
    STREAM_PACKAGED,
    STEP_PACKAGED
)

# --- Config ---
GROUP_NAME = os.environ.get("PACKAGER_GROUP", "packager-group")
CONSUMER_NAME = os.environ.get("PACKAGER_CONSUMER", "packager-consumer")
QUEUE_DIR = os.environ.get("QUEUE_DIR", "/queue")
STEMS_DIR = os.environ.get("STEMS_DIR", "/stems")
METADATA_DIR = os.environ.get("METADATA_DIR", "/metadata")
OUTPUT_DIR = os.environ.get("OUTPUT_DIR", "/output")
ARCHIVE_DIR = os.environ.get("ARCHIVE_DIR", "/archive")
LOG_DIR = os.environ.get("LOG_DIR", "/logs")
MAX_RETRIES = int(os.environ.get("MAX_RETRIES", 3))
RETRY_DELAY = int(os.environ.get("RETRY_DELAY", 10))
# Always clean intermediate files regardless of environment variable
CLEAN_INTERMEDIATE = True

# Setup logger
logger = setup_logger("packager")

def merge_stems(filename, stems_dir, selected_stems=None):
    """Merge selected stems into one audio file."""
    # Get all available stems
    available_stems = []
    for file in os.listdir(stems_dir):
        if file.endswith(".mp3"):
            stem_name = os.path.splitext(file)[0]
            available_stems.append(stem_name)
    
    logger.info(f"Available stems: {available_stems}")
    
    # Read settings from Redis to see which stems to include by default
    settings_key = "karaoke:settings"
    settings = redis_client.hgetall(settings_key)
    
    # By default, remove vocals stem if settings specify that
    default_remove_vocals = settings.get("default_remove_vocals", "true").lower() == "true"
    
    # If no selected stems provided, use all available stems except vocals if default_remove_vocals is true
    if not selected_stems:
        selected_stems = [s for s in available_stems if not (s == "vocals" and default_remove_vocals)]
    else:
        # Filter selected stems to only include available ones
        selected_stems = [s for s in selected_stems if s in available_stems]
    
    logger.info(f"Selected stems to merge: {selected_stems}")
    
    if not selected_stems:
        raise ValueError("No stems selected for merging")
    
    # Merge stems
    merged = None
    stems_actually_used = []  # Track which stems were actually successfully merged
    
    for stem in selected_stems:
        stem_path = os.path.join(stems_dir, f"{stem}.mp3")
        if os.path.exists(stem_path):
            audio = AudioSegment.from_file(stem_path)
            if merged is None:
                merged = audio
            else:
                merged = merged.overlay(audio, position=0)
            stems_actually_used.append(stem)  # Only add to used stems if successful
    
    if merged is None:
        raise ValueError("Failed to merge stems")
    
    # Create temporary file for merged audio
    with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as tmp:
        merged.export(tmp.name, format="mp3", bitrate="320k")
        return tmp.name, stems_actually_used

def apply_metadata(input_path, output_path, metadata, cover_art_path=None):
    """Apply metadata and cover art to the output file."""
    # Use file locking when copying and modifying the output file
    with FileLock(output_path):
        # Copy file first
        shutil.copy2(input_path, output_path)
        
        try:
            # Get original tags
            tags = metadata.get("tags", {})
            
            # Add ID3 tags
            audio = MP3(output_path)
            
            # If the file doesn't have ID3 tags, add them
            if not audio.tags:
                audio.tags = ID3()
            
            # Add basic tags
            if "title" in tags:
                audio.tags.add(TIT2(encoding=3, text=tags["title"][0]))
            
            if "artist" in tags:
                audio.tags.add(TPE1(encoding=3, text=tags["artist"][0]))
            
            if "album" in tags:
                audio.tags.add(TALB(encoding=3, text=tags["album"][0]))
            
            if "tracknumber" in tags:
                audio.tags.add(TRCK(encoding=3, text=tags["tracknumber"][0]))
            
            if "date" in tags:
                audio.tags.add(TYER(encoding=3, text=tags["date"][0]))
            
            # Add cover art if available
            if cover_art_path and os.path.exists(cover_art_path):
                with open(cover_art_path, "rb") as f:
                    cover_art = f.read()
                
                audio.tags.add(
                    APIC(
                        encoding=3,  # UTF-8
                        mime="image/jpeg",
                        type=3,  # Cover image
                        desc="Cover",
                        data=cover_art
                    )
                )
            
            # Save changes
            audio.save()
            return True
        
        except Exception as e:
            logger.error(f"Error applying metadata: {e}")
            raise

def organize_output(filename, metadata):
    """Organize output file using Beets-like structure: Artist/Album/Song."""
    tags = metadata.get("tags", {})
    
    # Get artist, album, and title
    artist = tags.get("artist", ["Unknown Artist"])[0]
    album = tags.get("album", ["Unknown Album"])[0]
    title = tags.get("title", [os.path.splitext(filename)[0]])[0]
    
    # Handle compilations
    if "," in artist or "&" in artist:
        artist = "Various Artists"
    
    # Replace invalid characters
    for char in ['/', '\\', ':', '*', '?', '"', '<', '>', '|']:
        artist = artist.replace(char, '_')
        album = album.replace(char, '_')
        title = title.replace(char, '_')
    
    # Create path
    rel_path = os.path.join(artist, album)
    full_path = os.path.join(OUTPUT_DIR, rel_path)
    
    # Create directory
    os.makedirs(full_path, exist_ok=True)
    
    # First check if there's an album-named cover in assets
    album_named_cover = f"/assets/covers/{artist}-{album}.jpg"
    cover_art_path = metadata.get("cover_art_path", "/assets/covers/default.jpg")
    album_cover_path = os.path.join(full_path, "cover.jpg")
    
    # Prefer album-named cover art if available
    if os.path.exists(album_named_cover):
        logger.info(f"Found album-named cover art: {album_named_cover}")
        cover_art_path = album_named_cover
    
    # Only copy cover art if it doesn't already exist in the album directory
    if cover_art_path and os.path.exists(cover_art_path) and not os.path.exists(album_cover_path):
        try:
            with FileLock(album_cover_path):
                # Double check after acquiring lock to prevent race conditions
                if not os.path.exists(album_cover_path):
                    shutil.copy2(cover_art_path, album_cover_path)
                    logger.info(f"Copied cover art to {album_cover_path}")
        except Exception as e:
            logger.error(f"Error copying cover art: {e}")
    else:
        logger.info(f"Album cover already exists at {album_cover_path}, skipping copy")
    
    # Get file extension
    _, ext = os.path.splitext(filename)
    
    # Create output path
    output_file = f"{title}{ext}"
    output_path = os.path.join(full_path, output_file)
    
    return output_path, album_cover_path

def process_file(filename, data=None):
    """Process a file to merge stems, apply metadata, and organize output."""
    if data is None:
        data = {}
    
    # Get file_id from the filename (traditional way)
    file_id = os.path.splitext(filename)[0]
    
    # Check if we have a stable_id in the message data
    stable_id = data.get('tracking_id') or data.get('stable_id')
    
    # If we have a stable_id, use it for tracking instead of the filename-based id
    tracking_id = stable_id if stable_id else file_id

    # Check if file was already processed using the stable ID if available
    if is_file_processed(tracking_id):
        logger.info(f"File {filename} already processed (tracking ID: {tracking_id}), skipping")
        log_processed_file(tracking_id)
        return True
    
    # Check if already packaged
    status = get_processing_status(tracking_id)
    if status and int(status.get(STEP_PACKAGED, 0)):
        logger.info(f"Already packaged {filename} (tracking ID: {tracking_id}), skipping")
        return True

    def _process():
        # Get paths
        queue_path = os.path.join(QUEUE_DIR, filename)
        stems_dir = os.path.join(STEMS_DIR, file_id)
        metadata_path = os.path.join(METADATA_DIR, f"{filename}.json")
        
        # Check if files exist
        if not os.path.exists(stems_dir):
            # Look for alternative stems directory with the same base name
            base_name, ext = os.path.splitext(filename)
            parts = base_name.split('_')
            if len(parts) > 1 and len(parts[-1]) == 14 and parts[-1].isdigit():
                # Remove timestamp suffix
                original_base = '_'.join(parts[:-1])
                
                # Look for matching stems directories
                matching_dirs = []
                for dir_name in os.listdir(STEMS_DIR):
                    if dir_name.startswith(original_base):
                        matching_dirs.append(dir_name)
                
                if matching_dirs:
                    # Use the most recent directory
                    matching_dirs.sort(reverse=True)
                    alt_stems_dir = os.path.join(STEMS_DIR, matching_dirs[0])
                    
                    logger.warning(f"Original stems directory not found: {stems_dir}")
                    logger.warning(f"Using alternative stems directory: {alt_stems_dir}")
                    
                    # Update stems directory
                    stems_dir = alt_stems_dir
                else:
                    raise FileNotFoundError(f"Stems directory not found: {stems_dir}")
            else:
                raise FileNotFoundError(f"Stems directory not found: {stems_dir}")
        
        if not os.path.exists(metadata_path):
            # Look for alternative metadata file with the same base name
            base_name, ext = os.path.splitext(filename)
            parts = base_name.split('_')
            if len(parts) > 1 and len(parts[-1]) == 14 and parts[-1].isdigit():
                # Remove timestamp suffix
                original_base = '_'.join(parts[:-1])
                
                # Look for matching metadata files
                matching_files = []
                for file_name in os.listdir(METADATA_DIR):
                    if file_name.startswith(original_base) and file_name.endswith(".json"):
                        matching_files.append(file_name)
                
                if matching_files:
                    # Use the most recent file
                    matching_files.sort(reverse=True)
                    alt_metadata_path = os.path.join(METADATA_DIR, matching_files[0])
                    
                    logger.warning(f"Original metadata file not found: {metadata_path}")
                    logger.warning(f"Using alternative metadata file: {alt_metadata_path}")
                    
                    # Update metadata path
                    metadata_path = alt_metadata_path
                else:
                    raise FileNotFoundError(f"Metadata file not found: {metadata_path}")
            else:
                raise FileNotFoundError(f"Metadata file not found: {metadata_path}")
        
        # Load metadata
        with open(metadata_path, "r") as f:
            metadata = json.load(f)
        
        # Get all available stems
        available_stems = []
        for stem_file in os.listdir(stems_dir):
            if stem_file.endswith(".mp3"):
                stem_name = os.path.splitext(stem_file)[0]
                available_stems.append(stem_name)
        
        # Determine which stems to merge
        settings_key = "karaoke:settings"
        settings = redis_client.hgetall(settings_key)
        default_remove_vocals = settings.get("default_remove_vocals", "true").lower() == "true"
        selected_stems = [s for s in available_stems if not (s == "vocals" and default_remove_vocals)]
        
        # Merge stems using the selected stems
        merged_file, stems_actually_used = merge_stems(filename, stems_dir, selected_stems)
        
        # Record the stems actually used in the metadata - this will match what was logged in merge_stems
        metadata["stems_used"] = stems_actually_used
        logger.info(f"Stems used: {stems_actually_used}")
        
        # Get output path and organize files
        output_path, album_cover_path = organize_output(filename, metadata)
        
        # Apply metadata and cover art
        apply_metadata(merged_file, output_path, metadata, album_cover_path)
        
        # Clean up temporary merged file
        if os.path.exists(merged_file):
            os.unlink(merged_file)
        
        # Mark as packaged and fully processed - use tracking_id for consistent tracking
        set_processing_step(tracking_id, STEP_PACKAGED)
        mark_file_processed(tracking_id, metadata)
        log_processed_file(tracking_id)
        
        # Add to packaged stream
        add_to_stream(STREAM_PACKAGED, {
            "filename": filename,
            "file_id": file_id,
            "tracking_id": tracking_id,  # Include the stable tracking ID
            "timestamp": time.time(),
            "output_path": output_path
        })
        
        # Always clean up residual files
        # We're ignoring the CLEAN_INTERMEDIATE setting to always clean up
        logger.info(f"Cleaning up residual files for {filename}")
        cleanup_result = cleanup_residual_files(file_id, filename)
        if cleanup_result:
            logger.info(f"Successfully cleaned up residual files for {filename}")
        else:
            logger.warning(f"Failed to clean up some residual files for {filename}")
        
        return output_path
    
    return handle_auto_retry("packager", filename, _process, MAX_RETRIES, RETRY_DELAY)

def cleanup_residual_files(file_id, filename):
    """Clean up residual files after processing."""
    try:
        # Clean up paths
        queue_path = os.path.join(QUEUE_DIR, filename)
        queue_jobstate_path = f"{queue_path}.jobstate.json"
        stems_dir = os.path.join(STEMS_DIR, file_id)
        metadata_path = os.path.join(METADATA_DIR, f"{filename}.json")
        
        # List of paths to remove
        paths_to_remove = [
            queue_path,
            queue_jobstate_path,
            metadata_path
        ]
        
        # Remove individual files
        for path in paths_to_remove:
            if os.path.exists(path):
                try:
                    with FileLock(path):
                        os.unlink(path)
                    logger.debug(f"Removed residual file: {path}")
                except Exception as e:
                    logger.warning(f"Failed to remove file {path}: {e}")
        
        # Remove stems directory
        if os.path.exists(stems_dir) and os.path.isdir(stems_dir):
            try:
                shutil.rmtree(stems_dir)
                logger.debug(f"Removed stems directory: {stems_dir}")
            except Exception as e:
                logger.warning(f"Failed to remove stems directory {stems_dir}: {e}")
        
        # Remove file-specific cover art, but keep album covers
        file_cover_path = f"/assets/covers/{file_id}.jpg"
        if os.path.exists(file_cover_path):
            try:
                os.unlink(file_cover_path)
                logger.debug(f"Removed file cover art: {file_cover_path}")
            except Exception as e:
                logger.warning(f"Failed to remove file cover art {file_cover_path}: {e}")
        
        # Check if there are any leftover files with this file_id pattern
        for directory in [QUEUE_DIR, METADATA_DIR]:
            if os.path.exists(directory):
                for leftover in os.listdir(directory):
                    if file_id in leftover:
                        leftover_path = os.path.join(directory, leftover)
                        try:
                            if os.path.isfile(leftover_path):
                                os.unlink(leftover_path)
                                logger.debug(f"Removed leftover file: {leftover_path}")
                            elif os.path.isdir(leftover_path):
                                shutil.rmtree(leftover_path)
                                logger.debug(f"Removed leftover directory: {leftover_path}")
                        except Exception as e:
                            logger.warning(f"Failed to remove leftover {leftover_path}: {e}")
                
        logger.info(f"Completed cleanup for {filename}")
        return True
    except Exception as e:
        logger.error(f"Error during cleanup: {e}")
        return False

def main():
    """Main function to continuously process files from the queue with graceful shutdown."""
    shutdown_event = threading.Event()
    
    def signal_handler(signum, frame):
        logger.info("Received shutdown signal, finishing current tasks...")
        shutdown_event.set()
    
    # Register signal handlers
    signal.signal(signal.SIGTERM, signal_handler)
    signal.signal(signal.SIGINT, signal_handler)
    
    try:
        # Create consumer group if it doesn't exist
        create_consumer_group(STREAM_SPLIT_DONE, GROUP_NAME)
        
        # Create output directories if they don't exist
        for directory in [OUTPUT_DIR, ARCHIVE_DIR, LOG_DIR]:
            os.makedirs(directory, exist_ok=True)
        
        logger.info(f"Packager started. Consumer group: {GROUP_NAME}, Consumer: {CONSUMER_NAME}")
        
        while not shutdown_event.is_set():
            try:
                # Read messages from the stream - no need to decode manually since redis_utils handles it
                messages = read_from_group(STREAM_SPLIT_DONE, GROUP_NAME, CONSUMER_NAME, count=1, block=5000)
                
                if not messages:
                    continue
                
                # Process each message
                for message in messages:
                    if shutdown_event.is_set():
                        break
                    
                    stream_name = message[0]  # Already decoded by redis_utils
                    for message_id, data in message[1]:
                        try:
                            filename = data.get('filename', '')  # Already decoded
                            
                            if not filename:
                                logger.warning(f"Invalid message, no filename: {data}")
                                acknowledge_message(stream_name, GROUP_NAME, message_id)
                                continue
                            
                            logger.info(f"Processing file: {filename}")
                            
                            # Process the file with the data that includes tracking_id
                            process_file(filename, data)
                            
                            # Acknowledge the message
                            acknowledge_message(stream_name, GROUP_NAME, message_id)
                        
                        except Exception as e:
                            logger.error(f"Error processing message: {e}", exc_info=True)
                            # Don't acknowledge to allow reprocessing
            
            except Exception as e:
                logger.error(f"Error in main loop: {e}", exc_info=True)
                if not shutdown_event.is_set():
                    time.sleep(5)  # Wait a bit before retrying
        
        logger.info("Shutting down gracefully...")
        
    except Exception as e:
        logger.error(f"Fatal error in packager service: {e}", exc_info=True)
        raise

if __name__ == "__main__":
    main()
