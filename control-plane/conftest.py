import os
from pathlib import Path

# Load deploy/.env and set environment variables for all pytest runs under control-plane/
env_path = Path(__file__).resolve().parent / "../deploy" / ".env"
if env_path.exists():
    values = {}
    for line in env_path.read_text(encoding="utf-8").splitlines():
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key] = value
    
    # Set REDIS_URL so tests connecting to Redis are automatically authenticated
    if "REDIS_PASSWORD" in values:
        port = values.get("REDIS_PORT") or "6379"
        password = values["REDIS_PASSWORD"]
        url = f"redis://:{password}@127.0.0.1:{port}/0"
        os.environ.setdefault("REDIS_URL", url)
