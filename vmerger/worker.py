import argparse
import json
import time

from . import jobs
from .pipeline import process


def run_once(queues=("io", "ai", "render")):
    job = jobs.claim(queues)
    if not job:
        return False
    started = time.monotonic()
    try:
        process(job)
        print(
            json.dumps({"event": "job_completed", "job_id": str(job["id"]), "kind": job["kind"]}), flush=True
        )
    except Exception as error:
        # Provider bodies, media names and prompts must not enter telemetry.
        jobs.fail(job, error, retry=isinstance(error, (ConnectionError, TimeoutError)))
        print(
            json.dumps(
                {
                    "event": "job_failed",
                    "job_id": str(job["id"]),
                    "kind": job["kind"],
                    "error_type": type(error).__name__,
                }
            ),
            flush=True,
        )
    finally:
        jobs.observe(job, "system", "processing_seconds", time.monotonic() - started)
    return True


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--queues", default="io,ai,render")
    parser.add_argument("--once", action="store_true")
    args = parser.parse_args()
    while True:
        busy = run_once(tuple(args.queues.split(",")))
        if args.once:
            return
        if not busy:
            time.sleep(1)


if __name__ == "__main__":
    main()
