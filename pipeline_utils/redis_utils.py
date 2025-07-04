# pipeline_utils/redis_utils.py

import os
import logging
import redis

# -------- ENV VARS --------
REDIS_HOST = os.environ.get("REDIS_HOST", "redis")
REDIS_PORT = int(os.environ.get("REDIS_PORT", 6379))

# Configure logging
logger = logging.getLogger("redis_utils")

# -------- REDIS CLIENT (singleton) --------
# Use two clients - one for decoded responses and one for raw responses
redis_client = redis.Redis(host=REDIS_HOST, port=REDIS_PORT, decode_responses=True)
redis_raw_client = redis.Redis(host=REDIS_HOST, port=REDIS_PORT, decode_responses=False)

def get_redis_client(raw=False):
    """Get the Redis client singleton instance."""
    return redis_raw_client if raw else redis_client

def add_to_stream(stream_name, data):
    """Add an item to a Redis stream."""
    try:
        # Ensure all values are strings
        clean_data = {str(k): str(v) for k, v in data.items()}
        return redis_client.xadd(stream_name, clean_data)
    except Exception as e:
        logger.error(f"Failed to add to stream {stream_name}: {e}", exc_info=True)
        return None

def create_consumer_group(stream_name, group_name):
    """Create a consumer group for a stream, handling the case where it already exists."""
    try:
        redis_client.xgroup_create(stream_name, group_name, id="0", mkstream=True)
        logger.info(f"Created consumer group {group_name} for stream {stream_name}")
    except redis.exceptions.ResponseError as e:
        if "BUSYGROUP" in str(e):
            # Group already exists, which is fine
            logger.debug(f"Consumer group {group_name} already exists for stream {stream_name}")
        else:
            logger.error(f"Failed to create consumer group: {e}", exc_info=True)
            raise

def read_from_group(stream_name, group_name, consumer_name, count=1, block=0, id=">", raw=False):
    """Read messages from a consumer group.
    
    Args:
        stream_name: Name of the stream to read from
        group_name: Name of the consumer group
        consumer_name: Name of the consumer
        count: Number of messages to read
        block: Milliseconds to block for
        id: Message ID to start from
        raw: Whether to return raw bytes (False for decoded strings)
    """
    try:
        client = redis_raw_client if raw else redis_client
        return client.xreadgroup(group_name, consumer_name, {stream_name: id}, count=count, block=block)
    except Exception as e:
        logger.error(f"Failed to read from group {group_name}: {e}", exc_info=True)
        return []

def acknowledge_message(stream_name, group_name, id):
    """Acknowledge a message in a consumer group."""
    try:
        redis_client.xack(stream_name, group_name, id)
    except Exception as e:
        logger.error(f"Failed to acknowledge message {id}: {e}", exc_info=True)

def claim_pending_messages(stream_name, group_name, consumer_name, min_idle_time=60000, count=10):
    """Claim pending messages that have been idle for too long."""
    try:
        # Get pending messages
        pending = redis_client.xpending(stream_name, group_name, count=count)
        if not pending:
            return []
        
        # Claim messages that have been idle for too long
        message_ids = [p[0] for p in pending]
        return redis_client.xclaim(
            stream_name, 
            group_name, 
            consumer_name, 
            min_idle_time, 
            message_ids
        )
    except Exception as e:
        logger.error(f"Failed to claim pending messages: {e}", exc_info=True)
        return []
