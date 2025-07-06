#!/usr/bin/env python3
# splitter/splitter.py

import os
import time
import json
import shutil
import signal
import threading
import logging
import tempfile
import subprocess
import traceback
from pathlib import Path
from pydub import AudioSegment
from pydub.utils import make_chunks
import redis

# Import pipeline utilities
import sys
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from pipeline_utils.file_lock import FileLock
import sys
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
    clean_string,
    is_file_processed,
    get_processing_status,
    set_processing_step,
    log_processed_file,
    STREAM_METADATA_DONE,
    STREAM_SPLIT_DONE,
    STEP_STEMS
)

# --- Config ---
GROUP_NAME = os.environ.get("SPLITTER_GROUP", "splitter-group")
CONSUMER_NAME = os.environ.get("SPLITTER_CONSUMER", "splitter-consumer")
QUEUE_DIR = os.environ.get("QUEUE_DIR", "/queue")
STEMS_DIR = os.environ.get("STEMS_DIR", "/stems")
MAX_RETRIES = int(os.environ.get("MAX_RETRIES", 3))
RETRY_DELAY = int(os.environ.get("RETRY_DELAY", 10))
REDIS_RETRY_DELAY = int(os.environ.get("REDIS_RETRY_DELAY", 5))
CHUNKING_ENABLED = os.environ.get("CHUNKING_ENABLED", "false").lower() == "true"
CHUNK_LENGTH_MS = int(os.environ.get("CHUNK_LENGTH_MS", 240000))
MIN_CHUNK_LENGTH_MS = int(os.environ.get("MIN_CHUNK_LENGTH_MS", CHUNK_LENGTH_MS // 2))
CHUNK_MAX_ATTEMPTS = int(os.environ.get("CHUNK_MAX_ATTEMPTS", 4))

# --- Stem configuration ---
# Default values (can be overridden by settings)
SPLITTER_TYPE = os.environ.get("SPLITTER_TYPE", "SPLEETER").upper()
STEMS = int(os.environ.get("STEMS", 4))
STEM_TYPE = [
    s.strip().lower()
    for s in os.environ.get("STEM_TYPE", "vocals,drums,bass,other").split(",")
    if s.strip()
]

# Setup logger
logger = setup_logger("splitter")

# --- Stem model configurations ---
SPLEETER_MODELS = {
    2: ["vocals", "accompaniment"],
    4: ["vocals", "drums", "bass", "other"],
    5: ["vocals", "drums", "bass", "piano", "other"],
}

def get_supported_stems(splitter_type, stems_num):
    """Get the supported stems for the given splitter type and number of stems."""
    if splitter_type == "SPLEETER":
        return SPLEETER_MODELS.get(stems_num, [])
    return []

def run_spleeter(input_path, output_dir, stems_num):
    """Run Spleeter to separate stems."""
    model = f"spleeter:{stems_num}stems"
    cmd = ["spleeter", "separate", "-p", model, "-o", output_dir, input_path]
    logger.info(f"Running Spleeter: {' '.join(cmd)}")
    
    proc = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    logger.info(proc.stdout)
    logger.info(proc.stderr)
    
    if proc.returncode != 0:
        raise RuntimeError(f"Spleeter error: {proc.stderr}")
    
    return os.path.join(output_dir, os.path.splitext(os.path.basename(input_path))[0])

def find_raw_folder(stems_folder):
    """Find the folder containing the raw stem files."""
    for root, _, files in os.walk(stems_folder):
        if any(f.lower().endswith((".wav", ".mp3", ".flac")) for f in files):
            return root
    return stems_folder

def filter_and_export_stems(stems_folder, keep, dest_dir):
    """Filter and export stems to MP3 format."""
    os.makedirs(dest_dir, exist_ok=True)
    exported = []
    
    raw_folder = find_raw_folder(stems_folder)
    
    for stem in keep:
        for ext in ("wav", "mp3", "flac"):
            src = os.path.join(raw_folder, f"{stem}.{ext}")
            if os.path.exists(src):
                tgt = os.path.join(dest_dir, f"{stem}.mp3")
                AudioSegment.from_file(src).export(
                    tgt, format="mp3", bitrate="192k"
                )
                exported.append(stem)
                break
    
    # Clean up intermediate files if requested
    if os.environ.get("CLEAN_INTERMEDIATE_STEMS", "false").lower() == "true":
        try:
            shutil.rmtree(raw_folder)
            logger.info(f"Removed raw stems at {raw_folder}")
        except FileNotFoundError:
            pass
        except Exception as e:
            logger.warning(f"Could not remove raw folder: {e}", exc_info=True)
        
        # Try to remove empty parent directories
        parent = os.path.dirname(raw_folder)
        if os.path.isdir(parent):
            for entry in os.listdir(parent):
                path = os.path.join(parent, entry)
                if os.path.isdir(path):
                    try:
                        os.rmdir(path)
                        logger.info(f"Removed empty dir {path}")
                    except OSError:
                        pass
    
    return exported

def process_file(filename, data=None):
    """Process file for stem splitting."""
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
    
    # Check if stems were already extracted
    status = get_processing_status(tracking_id)
    if status and int(status.get(STEP_STEMS, 0)):
        logger.info(f"Stems already extracted for {filename} (tracking ID: {tracking_id}), skipping")
        return True

    def _process():
        # Get file paths
        queue_path = os.path.join(QUEUE_DIR, filename)
        stems_dir = os.path.join(STEMS_DIR, file_id)
        
        # Enhanced file not found handling
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
                else:
                    raise FileNotFoundError(f"Input file not found: {queue_path}")
            else:
                raise FileNotFoundError(f"Input file not found: {queue_path}")
        
        # Create stems directory
        os.makedirs(stems_dir, exist_ok=True)
        
        # Split stems
        split_stems(queue_path, stems_dir)
        
        # Mark stems step as complete - use tracking_id for consistent tracking
        set_processing_step(tracking_id, STEP_STEMS)
        
        # Add to split done stream
        add_to_stream(STREAM_SPLIT_DONE, {
            "filename": filename,
            "file_id": file_id,
            "tracking_id": tracking_id,  # Include the stable tracking ID
            "timestamp": time.time()
        })
        
        return stems_dir
    
    return handle_auto_retry("splitter", filename, _process, MAX_RETRIES, RETRY_DELAY)

def ensure_redis_connection():
    """Ensure Redis connection is available, retry if not."""
    while True:
        try:
            redis_client.ping()
            break
        except (redis.ConnectionError, redis.TimeoutError) as e:
            logger.error(f"Redis connection error: {e}. Retrying in {REDIS_RETRY_DELAY} seconds...")
            time.sleep(REDIS_RETRY_DELAY)
        except Exception as e:
            logger.error(f"Unexpected Redis error: {e}")
            raise

def run():
    """Run the splitter service."""
    # Create output directory if it doesn't exist
    os.makedirs(STEMS_DIR, exist_ok=True)
    
    while True:
        try:
            # Ensure Redis connection
            ensure_redis_connection()
            
            # Create consumer group if it doesn't exist
            create_consumer_group(STREAM_METADATA_DONE, GROUP_NAME)
            
            logger.info(f"Splitter started. Consumer group: {GROUP_NAME}, Consumer: {CONSUMER_NAME}")
            
            while True:
                try:
                    # Read messages from the stream
                    messages = read_from_group(STREAM_METADATA_DONE, GROUP_NAME, CONSUMER_NAME, count=1, block=5000)
                    
                    if not messages:
                        continue
                    
                    # Process each message
                    for message in messages:
                        stream_name = message[0]  # Already decoded by redis_utils
                        for message_id, data in message[1]:
                            try:
                                filename = data.get('filename', '')
                                
                                if not filename:
                                    logger.warning(f"Invalid message, no filename: {data}")
                                    acknowledge_message(stream_name, GROUP_NAME, message_id)
                                    continue
                                
                                logger.info(f"Processing file: {filename}")
                                
                                if process_file(filename):
                                    logger.info(f"Successfully processed {filename}")
                                    acknowledge_message(stream_name, GROUP_NAME, message_id)
                                else:
                                    logger.error(f"Failed to process {filename}")
                            
                            except Exception as e:
                                logger.error(f"Error processing message: {e}", exc_info=True)
                                # Don't acknowledge to allow reprocessing
                
                except redis.ConnectionError as e:
                    logger.error(f"Redis connection lost: {e}")
                    break  # Break inner loop to reconnect
                
                except Exception as e:
                    logger.error(f"Error in processing loop: {e}", exc_info=True)
                    time.sleep(1)  # Avoid tight loop on persistent errors
        
        except Exception as e:
            logger.error(f"Fatal error: {e}", exc_info=True)
            time.sleep(REDIS_RETRY_DELAY)  # Wait before retrying

def signal_handler(sig, frame):
    """Handle termination signals."""
    logger.info("Received shutdown signal, exiting gracefully...")
    sys.exit(0)

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
        create_consumer_group(STREAM_METADATA_DONE, GROUP_NAME)
        
        # Create stems directory if it doesn't exist
        os.makedirs(STEMS_DIR, exist_ok=True)
        
        logger.info(f"Splitter started. Consumer group: {GROUP_NAME}, Consumer: {CONSUMER_NAME}")
        
        while not shutdown_event.is_set():
            try:
                # Read messages from the stream
                messages = read_from_group(STREAM_METADATA_DONE, GROUP_NAME, CONSUMER_NAME, count=1, block=5000)
                
                if not messages:
                    continue
                
                # Process each message
                for message in messages:
                    if shutdown_event.is_set():
                        break
                    
                    stream_name = message[0]
                    for message_id, data in message[1]:
                        try:
                            filename = data.get('filename', '')
                            
                            if not filename:
                                logger.warning(f"Invalid message, no filename: {data}")
                                acknowledge_message(stream_name, GROUP_NAME, message_id)
                                continue
                            
                            logger.info(f"Processing file: {filename}")
                            
                            # Process the file with the data that includes stable_id
                            process_file(filename, data)
                            
                            # Acknowledge the message
                            acknowledge_message(stream_name, GROUP_NAME, message_id)
                        
                        except Exception as e:
                            logger.error(f"Error processing message: {e}", exc_info=True)
                            # Don't acknowledge to allow reprocessing
            
            except Exception as e:
                logger.error(f"Error in main loop: {e}", exc_info=True)
                if not shutdown_event.is_set():
                    time.sleep(REDIS_RETRY_DELAY)  # Wait before retrying
        
        logger.info("Shutting down gracefully...")
        
    except Exception as e:
        logger.error(f"Fatal error in splitter service: {e}", exc_info=True)
        raise

def split_stems(input_path, output_dir):
    """Split audio file into stems."""
    logger.info(f"Splitting stems for {input_path} to {output_dir}")
    
    # Default to 4 stems (vocals, drums, bass, other)
    stems_num = int(os.environ.get("STEMS_NUM", 4))
    
    # Use spleeter by default
    splitter_type = os.environ.get("SPLITTER_TYPE", "SPLEETER")
    
    if splitter_type == "SPLEETER":
        # Create temp dir for initial output
        with tempfile.TemporaryDirectory() as temp_dir:
            # Run spleeter
            stems_folder = run_spleeter(input_path, temp_dir, stems_num)
            
            # Get supported stems
            keep = get_supported_stems(splitter_type, stems_num)
            
            # Export and convert stems
            exported = filter_and_export_stems(stems_folder, keep, output_dir)
            
            logger.info(f"Exported stems: {exported}")
            return exported
    else:
        raise ValueError(f"Unsupported splitter type: {splitter_type}")

if __name__ == "__main__":
    main()
