# pipeline_utils/pipeline_utils.py

import os
import json
import datetime
import time
import traceback
import logging
from .redis_utils import redis_client
from .notification_utils import notify_all
from .logging_utils import setup_logger

# Create a logger for this module
logger = setup_logger("pipeline_utils")

# -------- REDIS STREAM KEYS --------
STREAM_QUEUED = "stream:queued"
STREAM_METADATA_DONE = "stream:metadata_done"
STREAM_SPLIT_DONE = "stream:split_done"
STREAM_PACKAGED = "stream:packaged"

# -------- UTILITIES --------
def clean_string(s):
    """Sanitize input for safe filesystem usage."""
    if not isinstance(s, str):
        s = str(s)
    return (
        s.replace("\x00", "")
         .replace("/", "-")
         .replace("\\", "-")
         .strip()
    )

# -------- STATUS & ERROR MANAGEMENT --------
def set_file_status(filename, status, error=None, extra=None):
    """Set the status of a file in Redis."""
    key = f"file:{filename}"
    value = {"status": status}
    if error:
        value["error"] = error
    if extra:
        value.update(extra)
    try:
        redis_client.hset(key, mapping=value)
    except Exception as e:
        logger.error(f"Redis set_file_status error: {e}", exc_info=True)

def get_files_by_status(status):
    """Get all files with a specific status."""
    try:
        keys = redis_client.keys("file:*")
    except Exception as e:
        logger.error(f"Redis get_files_by_status error: {e}", exc_info=True)
        return []
    out = []
    for key in keys:
        try:
            data = redis_client.hgetall(key)
            if data.get("status") == status:
                out.append(key.replace("file:", ""))
        except Exception:
            continue
    return out

def set_file_error(filename, error):
    """Set a file status to error with an error message."""
    set_file_status(filename, "error", error=error)

def get_file_status(filename):
    """Get the status of a file."""
    key = f"file:{filename}"
    try:
        data = redis_client.hgetall(key)
        return {
            "filename": filename,
            "status": data.get("status", "unknown"),
            "last_error": data.get("error", ""),
        }
    except Exception as e:
        return {"filename": filename, "status": "unknown", "last_error": str(e)}

# -------- RETRY UTILITIES --------
def get_retry_count(stage, filename):
    """Get the retry count for a specific stage and file."""
    try:
        return int(redis_client.get(f"{stage}_retries:{filename}") or 0)
    except Exception:
        return 0

def increment_retry(stage, filename):
    """Increment the retry count for a specific stage and file."""
    cnt = get_retry_count(stage, filename) + 1
    try:
        redis_client.set(f"{stage}_retries:{filename}", cnt)
    except Exception:
        pass
    return cnt

def reset_retry(stage, filename):
    """Reset the retry count for a specific stage and file."""
    try:
        redis_client.delete(f"{stage}_retries:{filename}")
    except Exception:
        pass

def handle_auto_retry(stage, filename, func, max_retries=3, retry_delay=5, notify_fail=True):
    """Handle automatic retries for a function with proper logging and notifications."""
    for attempt in range(1, max_retries + 1):
        try:
            result = func()
            reset_retry(stage, filename)
            return result
        except Exception as e:
            retries = increment_retry(stage, filename)
            tb = traceback.format_exc()
            timestamp = datetime.datetime.now().isoformat()
            set_file_error(filename, f"{timestamp}\n{e}\n{tb}")
            logger.error(f"[{stage}] error on {filename} (attempt {retries}): {e}", exc_info=True)
            if attempt < max_retries:
                time.sleep(retry_delay)
            elif notify_fail:
                notify_all(f"Pipeline Error [{stage}]", f"{stage} FAILED: {filename}\n{e}\n{tb}")
            if attempt == max_retries:
                raise
