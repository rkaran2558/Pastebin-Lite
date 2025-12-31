import os
from upstash_redis import Redis
from dotenv import load_dotenv

load_dotenv()

# Connect to Upstash Redis using REST API
redis_client = Redis.from_env()

def get_current_time(test_now_ms: str = None):
    """Get current time in milliseconds, respecting TEST_MODE"""
    if os.getenv("TEST_MODE") == "1" and test_now_ms:
        return int(test_now_ms)
    
    import time
    return int(time.time() * 1000)
