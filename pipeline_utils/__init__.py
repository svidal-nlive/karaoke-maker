# pipeline_utils/__init__.py

import time
import logging

logger = logging.getLogger(__name__)

from .pipeline_utils import (
    clean_string, 
    set_file_status, 
    get_files_by_status, 
    set_file_error, 
    get_file_status, 
    get_retry_count, 
    increment_retry, 
    reset_retry, 
    handle_auto_retry,
    STREAM_QUEUED,
    STREAM_METADATA_DONE,
    STREAM_SPLIT_DONE,
    STREAM_PACKAGED
)

from .redis_utils import (
    redis_client,
    get_redis_client,
    add_to_stream,
    create_consumer_group,
    read_from_group,
    acknowledge_message,
    claim_pending_messages
)

from .notification_utils import (
    send_telegram_message,
    send_slack_message,
    send_email,
    notify_all
)

from .logging_utils import (
    setup_logger,
    get_file_logger
)

def get_processing_key(file_id):
    """Get Redis key for processing status."""
    return f"processing:{file_id}"

def get_processed_key(file_id):
    """Get Redis key for processed status."""
    return f"processed:{file_id}"

def is_file_processed(file_id):
    """Check if a file has been fully processed."""
    return redis_client.exists(get_processed_key(file_id))

def get_processing_status(file_id):
    """Get current processing status for a file."""
    return redis_client.hgetall(get_processing_key(file_id))

def set_processing_step(file_id, step, status=True):
    """Set status for a processing step."""
    redis_client.hset(get_processing_key(file_id), step, int(status))

def mark_file_processed(file_id, metadata):
    """Mark a file as fully processed and store its metadata."""
    processed_key = get_processed_key(file_id)
    redis_client.hmset(processed_key, {
        'title': metadata.get('tags', {}).get('title', ['Unknown'])[0],
        'artist': metadata.get('tags', {}).get('artist', ['Unknown'])[0],
        'album': metadata.get('tags', {}).get('album', ['Unknown'])[0],
        'bitrate': str(metadata.get('bitrate', 0)),
        'duration': str(metadata.get('duration', 0)),
        'stems_used': ','.join(metadata.get('stems_used', [])),
        'timestamp': time.time()
    })

def log_processed_file(file_id):
    """Log information about a processed file."""
    processed_key = get_processed_key(file_id)
    if not redis_client.exists(processed_key):
        return False
    
    info = redis_client.hgetall(processed_key)
    logger.info(f"Instrumental created for {info['title']}")
    logger.info("Metadata:")
    logger.info(f"  Title: {info['title']}")
    logger.info(f"  Artist: {info['artist']}")
    logger.info(f"  Album: {info['album']}")
    logger.info(f"  Duration: {float(info['duration']):.2f}s")
    logger.info(f"  Bitrate: {int(info['bitrate'])/1000:.0f}kbps")
    logger.info(f"  Stems used: {info['stems_used']}")
    return True

# Processing steps
STEP_QUEUED = "queued"
STEP_METADATA = "metadata"
STEP_COVER_ART = "cover_art"
STEP_STEMS = "stems"
STEP_PACKAGED = "packaged"

PROCESSING_STEPS = [STEP_QUEUED, STEP_METADATA, STEP_COVER_ART, STEP_STEMS, STEP_PACKAGED]
