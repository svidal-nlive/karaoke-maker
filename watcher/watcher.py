#!/usr/bin/env python3
# watcher/watcher.py

import os
import time
import json
import shutil
import datetime
import uuid
from pathlib import Path
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler

# Import pipeline utilities
import sys
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from pipeline_utils.file_lock import FileLock
from pipeline_utils import (
    setup_logger,
    add_to_stream,
    set_file_status,
    clean_string,
    is_file_processed,
    get_processing_status,
    set_processing_step,
    log_processed_file,
    STREAM_QUEUED,
    STEP_QUEUED
)

# --- Config ---
INPUT_DIR = os.environ.get("INPUT_DIR", "/input")
QUEUE_DIR = os.environ.get("QUEUE_DIR", "/queue")
CHECK_INTERVAL = int(os.environ.get("CHECK_INTERVAL", 5))  # seconds
ALLOWED_EXTENSIONS = [".mp3"]
PLAYLIST_INFO_FILE = "playlist.json"
ALBUM_INFO_FILE = "album.json"

# Setup logger
logger = setup_logger("watcher")

class InputFolderHandler(FileSystemEventHandler):
    def on_created(self, event):
        if event.is_directory:
            # When a new directory is created, scan it for any existing files
            logger.info(f"New directory created: {event.src_path}")
            self.scan_directory(event.src_path)
            return
        
        file_path = event.src_path
        self.process_file(file_path)
    
    def scan_directory(self, directory_path):
        """Scan a directory for audio files and metadata."""
        logger.info(f"Scanning directory: {directory_path}")
        
        # Keep track of processed files in this scan to avoid duplicates
        processed_files = set()
        
        # Check for playlist or album metadata
        playlist_file = os.path.join(directory_path, PLAYLIST_INFO_FILE)
        album_file = os.path.join(directory_path, ALBUM_INFO_FILE)
        collection_info = None
        collection_type = None
        
        if os.path.exists(playlist_file):
            try:
                with open(playlist_file, 'r') as f:
                    collection_info = json.load(f)
                collection_type = "playlist"
            except Exception as e:
                logger.error(f"Error reading playlist info: {e}")
        
        elif os.path.exists(album_file):
            try:
                with open(album_file, 'r') as f:
                    collection_info = json.load(f)
                collection_type = "album"
            except Exception as e:
                logger.error(f"Error reading album info: {e}")
        
        # Process all audio files in the directory
        for root, _, files in os.walk(directory_path):
            for file in files:
                if any(file.lower().endswith(ext) for ext in ALLOWED_EXTENSIONS):
                    file_path = os.path.join(root, file)
                    
                    # Skip if we've already processed this file
                    if file_path in processed_files:
                        continue
                        
                    processed_files.add(file_path)
                    self.process_file(file_path, collection_info, collection_type)
    
    def process_file(self, file_path, collection_info=None, collection_type=None):
        """Process a new file in the input directory."""
        filename = os.path.basename(file_path)
        file_id = os.path.splitext(filename)[0]

        # Generate a unique ID based on file path to prevent duplicate processing
        unique_id = clean_string(os.path.relpath(file_path, INPUT_DIR))
        
        # Check if file was already processed or is being processed
        if is_file_processed(unique_id):
            logger.debug(f"File {filename} already processed, skipping")
            return
        
        # Check if file is already being processed
        status = get_processing_status(unique_id)
        if status:
            logger.debug(f"File {filename} is already being processed, skipping")
            return

        # Skip files that don't have allowed extensions
        if not any(file_path.lower().endswith(ext) for ext in ALLOWED_EXTENSIONS):
            logger.debug(f"Skipping non-audio file: {file_path}")
            return
        
        # Wait for the file to be fully written and acquire lock
        with FileLock(file_path):
            if not self._wait_for_file_ready(file_path):
                logger.error(f"File not ready after timeout: {file_path}")
                return
            
            # Get filename and relative path from input directory
            rel_path = os.path.relpath(file_path, INPUT_DIR)
            filename = os.path.basename(file_path)
            
            # Add timestamp to ensure uniqueness
            timestamp = datetime.datetime.now().strftime("%Y%m%d%H%M%S")
            base, ext = os.path.splitext(filename)
            unique_filename = f"{base}_{timestamp}{ext}"
            
            # Create a job state file in the queue directory
            job_id = str(uuid.uuid4())
            job_state = {
                "filename": unique_filename,
                "original_filename": filename,
                "original_path": rel_path,
                "job_id": job_id,
                "timestamp": timestamp,
                "status": "queued",
                "unique_id": unique_id  # Add unique ID to track this specific file
            }
            
            # Add collection info if available
            if collection_info and collection_type:
                job_state["collection_type"] = collection_type
                job_state["collection_info"] = collection_info
                # If it's an album, try to get track number from the filename
                if collection_type == "album":
                    try:
                        # Try to extract track number from the start of filename (e.g., "01 - Song.mp3")
                        track_num = int(base.split(" ")[0])
                        job_state["track_number"] = track_num
                    except (ValueError, IndexError):
                        pass
            
            # Create queue directory if it doesn't exist
            os.makedirs(QUEUE_DIR, exist_ok=True)
            
            # Write job state to queue directory with file locking and atomic write
            job_state_path = os.path.join(QUEUE_DIR, f"{unique_filename}.jobstate.json")
            tmp_job_state_path = f"{job_state_path}.tmp"
            
            with FileLock(job_state_path):
                with open(tmp_job_state_path, 'w') as f:
                    json.dump(job_state, f, indent=2)
                os.replace(tmp_job_state_path, job_state_path)
            
            # Copy the file to queue directory with file locking
            output_path = os.path.join(QUEUE_DIR, unique_filename)
            tmp_output_path = f"{output_path}.tmp"
            
            try:
                with FileLock(output_path):
                    # Copy to temporary file first
                    shutil.copy2(file_path, tmp_output_path)
                    # Then atomically move it to final location
                    os.replace(tmp_output_path, output_path)
                logger.info(f"Copied file to queue: {output_path}")
            except Exception as e:
                logger.error(f"Error copying file to queue: {e}")
                # Clean up temporary file if it exists
                try:
                    if os.path.exists(tmp_output_path):
                        os.unlink(tmp_output_path)
                except Exception:
                    pass
                return
            
            # Set initial file status
            set_file_status(unique_filename, "queued")
            
            # Add to processing queue stream with collection info
            stream_data = {
                "filename": unique_filename,
                "original_filename": filename,
                "original_path": rel_path,
                "job_id": job_id,
                "timestamp": timestamp
            }
            
            if collection_info and collection_type:
                stream_data["collection_type"] = collection_type
                stream_data["collection_name"] = collection_info.get("name", "")
            
            add_to_stream(STREAM_QUEUED, stream_data)
            
            # Log with collection context if available
            if collection_info and collection_type:
                logger.info(f"Added file to queue: {unique_filename}, Job ID: {job_id}, {collection_type}: {collection_info.get('name', '')}")
            else:
                logger.info(f"Added file to queue: {unique_filename}, Job ID: {job_id}")
    
    def _wait_for_file_ready(self, file_path, timeout=60):
        """Wait until the file size stops changing, indicating it's fully written."""
        start_time = time.time()
        last_size = -1
        
        while time.time() - start_time < timeout:
            try:
                current_size = os.path.getsize(file_path)
                if current_size == last_size and current_size > 0:
                    # File size hasn't changed, it's probably fully written
                    return True
                last_size = current_size
            except Exception as e:
                logger.warning(f"Error checking file size: {e}")
            
            time.sleep(1)  # Wait a second before checking again
        
        logger.warning(f"Timeout waiting for file to be ready: {file_path}")
        return False

def scan_existing_files():
    """Scan the input directory recursively for existing files and folders."""
    logger.info(f"Scanning input directory: {INPUT_DIR}")
    
    # Process existing files and folders
    handler = InputFolderHandler()
    
    # Keep track of processed directories to avoid duplicate scans
    processed_dirs = set()
    
    for root, dirs, files in os.walk(INPUT_DIR):
        # Check if this directory has an album or playlist info file
        if PLAYLIST_INFO_FILE in files or ALBUM_INFO_FILE in files:
            # Skip if we've already processed this directory
            if root in processed_dirs:
                continue
                
            processed_dirs.add(root)
            handler.scan_directory(root)
        else:
            # Process individual files if no collection metadata
            for file in files:
                if any(file.lower().endswith(ext) for ext in ALLOWED_EXTENSIONS):
                    file_path = os.path.join(root, file)
                    logger.info(f"Found existing file: {file_path}")
                    handler.process_file(file_path)

def main():
    # Create input directory if it doesn't exist
    os.makedirs(INPUT_DIR, exist_ok=True)
    
    # Scan for existing files
    scan_existing_files()
    
    # Set up the observer with recursive watching
    event_handler = InputFolderHandler()
    observer = Observer()
    observer.schedule(event_handler, INPUT_DIR, recursive=True)  # Enable recursive watching
    observer.start()
    
    logger.info(f"Watching directory recursively: {INPUT_DIR}")
    
    try:
        while True:
            time.sleep(CHECK_INTERVAL)
    except KeyboardInterrupt:
        observer.stop()
    
    observer.join()

if __name__ == "__main__":
    main()
