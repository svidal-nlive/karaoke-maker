#!/usr/bin/env python3
# metadata/metadata.py

import os
import json
import time
import signal
import threading
import tempfile
import traceback
import requests
from datetime import datetime
from pathlib import Path
from mutagen.mp3 import MP3
from mutagen.id3 import ID3
from mutagen.easyid3 import EasyID3
# Import pipeline utilities
import sys
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from pipeline_utils.file_lock import FileLock, FileLockException
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from pipeline_utils import (
    setup_logger,
    redis_client,
    create_consumer_group,
    read_from_group,
    acknowledge_message,
    add_to_stream,
    set_file_status,
    handle_auto_retry,
    is_file_processed,
    get_processing_status,
    set_processing_step,
    log_processed_file,
    STREAM_QUEUED,
    STREAM_METADATA_DONE,
    STEP_QUEUED,
    STEP_METADATA,
    STEP_COVER_ART
)

# --- Config ---
GROUP_NAME = os.environ.get("METADATA_GROUP", "metadata-group")
CONSUMER_NAME = os.environ.get("METADATA_CONSUMER", "metadata-consumer")
QUEUE_DIR = os.environ.get("QUEUE_DIR", "/queue")
METADATA_DIR = os.environ.get("METADATA_DIR", "/metadata")
MAX_RETRIES = int(os.environ.get("MAX_RETRIES", 3))
RETRY_DELAY = int(os.environ.get("RETRY_DELAY", 10))
FETCH_COVER_ART = os.environ.get("FETCH_COVER_ART", "true").lower() == "true"
COVER_ART_API = os.environ.get("COVER_ART_API", "https://musicbrainz.org/ws/2/")

# Setup logger
logger = setup_logger("metadata")

def extract_and_save_cover_art(id3, file_id, metadata=None):
    """Extract cover art from ID3 tags and save it to the covers directory."""
    cover_art_path = None
    try:
        # Get album name for cover art if available
        album_name = None
        if metadata and metadata.get("tags", {}).get("album"):
            artist = metadata.get("tags", {}).get("artist", ["Unknown"])[0]
            album = metadata.get("tags", {}).get("album", ["Unknown"])[0]
            
            # Sanitize album name for file system
            for char in ['/', '\\', ':', '*', '?', '"', '<', '>', '|']:
                artist = artist.replace(char, '_')
                album = album.replace(char, '_')
            
            album_name = f"{artist}-{album}"
        
        for key in id3:
            if key.startswith("APIC"):
                apic = id3[key]
                # Create output path
                cover_art_dir = "/assets/covers"
                os.makedirs(cover_art_dir, exist_ok=True)
                
                # Always try to use album name for the cover art filename if available
                if album_name:
                    cover_art_path = os.path.join(cover_art_dir, f"{album_name}.jpg")
                    # Check if this album cover already exists
                    if os.path.exists(cover_art_path):
                        logger.info(f"Album cover already exists at {cover_art_path}, skipping extraction")
                        break
                else:
                    # Otherwise use the file_id
                    cover_art_path = os.path.join(cover_art_dir, f"{file_id}.jpg")
                
                # Save cover art with file locking to prevent race conditions
                with FileLock(cover_art_path):
                    # Double check after acquiring lock to prevent race conditions
                    if album_name and os.path.exists(cover_art_path):
                        logger.info(f"Album cover already exists at {cover_art_path} (verified after lock), skipping extraction")
                        break
                        
                    with open(cover_art_path, "wb") as f:
                        f.write(apic.data)
                
                logger.info(f"Saved cover art to {cover_art_path}")
                break
    except Exception as e:
        logger.error(f"Error saving cover art: {e}")
        cover_art_path = None
    
    return cover_art_path

def extract_metadata(file_path):
    """Extract metadata from an MP3 file."""
    try:
        audio = MP3(file_path)
        id3 = ID3(file_path)
        
        # Generate a unique ID for the file
        file_id = Path(file_path).stem
        
        metadata = {
            "duration": audio.info.length,
            "bitrate": audio.info.bitrate,
            "sample_rate": audio.info.sample_rate,
            "channels": audio.info.channels,
            "tags": {},
            "file_id": file_id
        }
        
        # Extract ID3 tags
        if hasattr(audio, "tags") and audio.tags:
            # Use EasyID3 for easier tag access
            easy = EasyID3(file_path)
            for key in easy:
                metadata["tags"][key] = easy[key]
        
        # Extract and save cover art if present
        cover_art_path = extract_and_save_cover_art(id3, file_id, metadata)
        metadata["cover_art_path"] = cover_art_path or "/assets/covers/default.jpg"
        metadata["has_cover_art"] = bool(cover_art_path)
        
        return metadata
    
    except Exception as e:
        logger.error(f"Error extracting metadata: {e}")
        raise

def fetch_cover_art(artist, album, title):
    """Fetch cover art from MusicBrainz API if not found in file."""
    if not artist or not album:
        logger.warning("Missing artist or album info, skipping cover art fetch")
        return None
    
    try:
        # First, search for the release
        query = f"release:{album} AND artist:{artist}"
        if title:
            query += f" AND recording:{title}"
        
        search_url = f"{COVER_ART_API}release"
        params = {
            "query": query,
            "fmt": "json"
        }
        
        response = requests.get(search_url, params=params, timeout=10)
        
        if not response.ok:
            logger.warning(f"Error searching MusicBrainz: {response.status_code}")
            return None
        
        data = response.json()
        
        if not data.get("releases"):
            logger.warning("No releases found")
            return None
        
        # Get the first release ID
        release_id = data["releases"][0]["id"]
        
        # Now fetch the cover art
        cover_art_url = f"https://coverartarchive.org/release/{release_id}/front"
        
        response = requests.get(cover_art_url, timeout=10)
        
        if not response.ok:
            logger.warning(f"Error fetching cover art: {response.status_code}")
            return None
        
        # Return the image data
        return response.content
    
    except Exception as e:
        logger.error(f"Error fetching cover art: {e}")
        return None

def save_cover_art(cover_art_data, output_path):
    """Save cover art to a file."""
    if not cover_art_data:
        return False
    
    try:
        with open(output_path, "wb") as f:
            f.write(cover_art_data)
        return True
    except Exception as e:
        logger.error(f"Error saving cover art: {e}")
        return False

def process_file(filename, data=None):
    """Process file metadata."""
    if data is None:
        data = {}
    
    # Get file_id from the filename (traditional way)
    file_id = os.path.splitext(filename)[0]
    
    # Check if we have a stable_id in the message data (from watcher)
    stable_id = data.get('stable_id')
    
    # If we have a stable_id, use it for tracking instead of the filename-based id
    tracking_id = stable_id if stable_id else file_id

    # Check if file was already processed using the stable ID if available
    if is_file_processed(tracking_id):
        logger.info(f"File {filename} already processed (tracking ID: {tracking_id}), skipping")
        log_processed_file(tracking_id)
        return True
    
    # Check if metadata was already extracted
    status = get_processing_status(tracking_id)
    if status and int(status.get(STEP_METADATA, 0)):
        logger.info(f"Metadata already extracted for {filename} (tracking ID: {tracking_id}), skipping")
        return True

    def _process():
        # Get file paths
        queue_path = os.path.join(QUEUE_DIR, filename)
        metadata_path = os.path.join(METADATA_DIR, f"{filename}.json")
        
        # Enhanced file not found handling:
        # If the exact filename doesn't exist, look for files with the same base name but different timestamp
        if not os.path.exists(queue_path):
            # Get base name without extension and timestamp
            base_name, ext = os.path.splitext(filename)
            
            # Try to find a file with the same base part but potentially different timestamp
            # Extract the base part (before the timestamp)
            parts = base_name.split('_')
            if len(parts) > 1 and len(parts[-1]) == 14 and parts[-1].isdigit():
                # Remove timestamp suffix
                original_base = '_'.join(parts[:-1])
                
                # Look for files in queue directory with matching pattern
                matching_files = []
                for file in os.listdir(QUEUE_DIR):
                    if file.startswith(original_base) and file.endswith(ext):
                        matching_files.append(file)
                
                if matching_files:
                    # Use the most recent file based on timestamp in filename
                    matching_files.sort(reverse=True)
                    alt_filename = matching_files[0]
                    alt_path = os.path.join(QUEUE_DIR, alt_filename)
                    
                    logger.warning(f"Original file not found: {queue_path}")
                    logger.warning(f"Using alternative file with same base name: {alt_path}")
                    
                    # Update filename and paths
                    queue_path = alt_path
                    metadata_path = os.path.join(METADATA_DIR, f"{alt_filename}.json")
                else:
                    raise FileNotFoundError(f"Input file not found: {queue_path}")
            else:
                raise FileNotFoundError(f"Input file not found: {queue_path}")
        
        # Create metadata directory if it doesn't exist
        os.makedirs(METADATA_DIR, exist_ok=True)
        
        # Extract metadata
        metadata = extract_metadata(queue_path)
        metadata["file_id"] = file_id
        metadata["tracking_id"] = tracking_id  # Add the stable tracking ID
        metadata["original_filename"] = data.get("original_filename")
        metadata["original_path"] = data.get("original_path")
        metadata["job_id"] = data.get("job_id")
        
        # Save metadata atomically using a temporary file
        temp_metadata_path = f"{metadata_path}.tmp"
        try:
            with open(temp_metadata_path, "w") as f:
                json.dump(metadata, f, indent=2)
            os.replace(temp_metadata_path, metadata_path)  # Atomic operation
        except Exception as e:
            if os.path.exists(temp_metadata_path):
                os.unlink(temp_metadata_path)
            raise e
        
        # Mark metadata step as complete - use tracking_id for consistent tracking
        set_processing_step(tracking_id, STEP_METADATA)
        
        # If cover art was handled, mark that step too
        if metadata.get("has_cover_art"):
            set_processing_step(tracking_id, STEP_COVER_ART)
        
        # Add to metadata done stream
        add_to_stream(STREAM_METADATA_DONE, {
            "filename": filename,
            "file_id": file_id,
            "tracking_id": tracking_id,  # Include the stable tracking ID
            "timestamp": time.time(),
            "metadata": {
                "title": metadata.get("tags", {}).get("title", ["Unknown"])[0],
                "artist": metadata.get("tags", {}).get("artist", ["Unknown"])[0],
                "album": metadata.get("tags", {}).get("album", ["Unknown"])[0],
                "has_cover_art": metadata.get("has_cover_art", False),
                "cover_art_path": metadata.get("cover_art_path")
            },
            "original_data": data  # Pass through original data from watcher
        })
        
        return metadata_path
    
    return handle_auto_retry("metadata", filename, _process, MAX_RETRIES, RETRY_DELAY)

def main():
    """Main function to continuously process files from the queue with graceful shutdown."""
    shutdown_event = threading.Event()
    
    def signal_handler(signum, frame):
        logger.info("Received shutdown signal, finishing current tasks...")
        shutdown_event.set()
    
    # Register signal handlers
    signal.signal(signal.SIGTERM, signal_handler)
    signal.signal(signal.SIGINT, signal_handler)
    
    # Initialize system
    try:
        # Create consumer group if it doesn't exist
        create_consumer_group(STREAM_QUEUED, GROUP_NAME)
        
        # Create output directory if it doesn't exist
        os.makedirs(METADATA_DIR, exist_ok=True)
        
        logger.info(f"Metadata extractor started. Consumer group: {GROUP_NAME}, Consumer: {CONSUMER_NAME}")
        
        # Track consecutive errors for backoff
        error_count = 0
        last_error_time = None
        
        while not shutdown_event.is_set():
            try:
                # Implement exponential backoff for errors
                if error_count > 0:
                    wait_time = min(30, 2 ** error_count)  # Max 30 seconds
                    logger.warning(f"Backing off for {wait_time} seconds after {error_count} errors")
                    if shutdown_event.wait(wait_time):
                        break
                
                # Read messages from the stream
                messages = read_from_group(STREAM_QUEUED, GROUP_NAME, CONSUMER_NAME, count=1, block=5000)
                
                if not messages:
                    error_count = 0  # Reset error count on successful read
                    continue
                
                # Process each message
                for message in messages:
                    if shutdown_event.is_set():
                        break
                        
                    stream_name = message[0]  # Already decoded by Redis client
                    
                    for message_id, data in message[1]:
                        try:
                            # Validate message data
                            if not isinstance(data, dict):
                                logger.error(f"Unexpected message data format: {type(data)}")
                                acknowledge_message(stream_name, GROUP_NAME, message_id)
                                continue
                            
                            filename = data.get('filename', '')
                            if not filename:
                                logger.warning(f"Invalid message, no filename: {data}")
                                acknowledge_message(stream_name, GROUP_NAME, message_id)
                                continue
                            
                            logger.info(f"Processing file: {filename}")
                            start_time = time.time()
                            
                            # Process the file with timeout
                            try:
                                success = process_file(filename, data)
                                processing_time = time.time() - start_time
                                logger.info(f"Processed {filename} in {processing_time:.2f} seconds")
                                
                                if success:
                                    error_count = 0  # Reset error count on success
                            except Exception as e:
                                logger.error(f"Error processing {filename}: {e}", exc_info=True)
                                error_count += 1
                                raise
                            
                            # Acknowledge the message
                            acknowledge_message(stream_name, GROUP_NAME, message_id)
                            
                        except Exception as e:
                            logger.error(f"Error processing message: {e}", exc_info=True)
                            logger.error(f"Message data: {data}")
                            error_count += 1
                            
                            # Record error time for rate limiting
                            current_time = datetime.now()
                            if last_error_time:
                                error_rate = (current_time - last_error_time).total_seconds()
                                if error_rate < 1:  # More than 1 error per second
                                    logger.warning("Error rate too high, backing off...")
                                    time.sleep(5)
                            last_error_time = current_time
            
            except Exception as e:
                logger.error(f"Error in main loop: {e}", exc_info=True)
                error_count += 1
                time.sleep(min(30, 2 ** error_count))  # Exponential backoff
        
        logger.info("Gracefully shutting down...")
        
    except Exception as e:
        logger.error(f"Fatal error in metadata service: {e}", exc_info=True)
        raise

if __name__ == "__main__":
    main()
