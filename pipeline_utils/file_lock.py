"""
File locking utilities for preventing race conditions in the karaoke pipeline.

This is a universal implementation used by all pipeline services.
"""

import os
import time
import fcntl
from contextlib import contextmanager
from typing import Optional
import logging

logger = logging.getLogger(__name__)

class FileLockException(Exception):
    """Exception raised when file locking fails."""
    pass

class FileLock:
    """
    File locking class to prevent race conditions.
    
    Usage:
        with FileLock(file_path):
            # do operations on file_path
    """
    
    def __init__(self, file_path: str, timeout: Optional[int] = 30):
        """
        Initialize the file lock.
        
        Args:
            file_path: Path to the file to lock
            timeout: Maximum time to wait for lock in seconds
        """
        self.file_path = file_path
        self.timeout = timeout
        self.lock_path = f"{file_path}.lock"
        self.lock_file = None
    
    def __enter__(self):
        try:
            start_time = time.time()
            while True:
                try:
                    self.lock_file = open(self.lock_path, 'w')
                    # Try to acquire an exclusive lock
                    fcntl.flock(self.lock_file.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                    break
                except (IOError, OSError) as e:
                    if self.timeout and (time.time() - start_time) > self.timeout:
                        raise FileLockException(f"Timeout waiting for lock on {self.file_path}")
                    logger.debug(f"Waiting for lock on {self.file_path}")
                    time.sleep(1)
            return self
        except Exception as e:
            self.__exit__(None, None, None)
            raise e
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        if self.lock_file:
            try:
                fcntl.flock(self.lock_file.fileno(), fcntl.LOCK_UN)
                self.lock_file.close()
                try:
                    os.unlink(self.lock_path)
                except FileNotFoundError:
                    pass  # Lock file might have been deleted by another process
            except (IOError, OSError) as e:
                logger.error(f"Error releasing lock: {e}")

# For backwards compatibility
@contextmanager
def file_lock(file_path: str, timeout: Optional[int] = 30):
    """
    File locking context manager to prevent race conditions.
    
    Args:
        file_path: Path to the file to lock
        timeout: Maximum time to wait for lock in seconds
    """
    with FileLock(file_path, timeout) as lock:
        yield
