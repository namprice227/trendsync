from __future__ import annotations

import os
from pathlib import Path

from tripstory_logging import configure_logging, get_logger, log_event, redacted_snippet


def _load_dotenv(path: Path = Path(".env")) -> None:
    if not path.exists():
        return
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return
    for raw_line in lines:
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        if line.startswith("export "):
            line = line.removeprefix("export ").strip()
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip("\"'")
        if key and key not in os.environ:
            os.environ[key] = value


_load_dotenv()
configure_logging()
logger = get_logger("worker")


def run_tripstory_job(job_id: str) -> None:
    import api_server

    log_event(logger, 20, "worker_job_received", job_id=job_id)
    api_server.run_queued_job(job_id)


def main() -> None:
    try:
        from redis import Redis
        from rq import Queue, Worker
    except ImportError as exc:
        raise SystemExit("Install queue dependencies with: python -m pip install -r requirements.txt") from exc

    redis_url = os.environ.get("TRIPSTORY_REDIS_URL", "redis://localhost:6379/0")
    queue_name = os.environ.get("TRIPSTORY_QUEUE_NAME", "tripstory")
    connection = Redis.from_url(redis_url)
    queue = Queue(queue_name, connection=connection)
    log_event(logger, 20, "worker_start", queue_name=queue_name, redis_url=redacted_snippet(redis_url, 120))
    Worker([queue], connection=connection).work()


if __name__ == "__main__":
    main()
