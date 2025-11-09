import os
import json
import redis

REDIS_HOST = os.getenv("REDIS_HOST", "redis")
REDIS_PORT = int(os.getenv("REDIS_PORT", "6379"))

r = redis.Redis(host=REDIS_HOST, port=REDIS_PORT, decode_responses=True)

def append_message(session_id: str, role: str, content: str):
    key = f"session:{session_id}:history"
    r.rpush(key, json.dumps({"role": role, "content": content}))
    r.expire(key, 60 * 60 * 24)  # keep 24h by default

def get_history(session_id: str):
    key = f"session:{session_id}:history"
    items = r.lrange(key, 0, -1)
    return [json.loads(i) for i in items]

def clear_history(session_id: str):
    key = f"session:{session_id}:history"
    r.delete(key)
