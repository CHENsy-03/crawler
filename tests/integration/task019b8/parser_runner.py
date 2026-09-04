"""B8 test-only launcher for the formal Python parser worker."""

import os
import sys


def main() -> int:
    repo_root = os.environ.get("TASK019B8_REPO_ROOT", "")
    redis_addr = os.environ.get("TASK019B8_REDIS_ADDR", "")
    if not repo_root or not redis_addr:
        print("TASK019B8_REPO_ROOT and TASK019B8_REDIS_ADDR are required", file=sys.stderr)
        return 2
    sys.path.insert(0, repo_root)
    from workers.parser_worker import run_worker

    run_worker(redis_addr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())