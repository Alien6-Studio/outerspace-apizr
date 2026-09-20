"""Image entrypoint: clear image-injected environment before the shared worker."""

import os
import sys


def main() -> None:
    names = sys.argv[1:]
    allowed = {name: os.environ[name] for name in names if name in os.environ}
    os.environ.clear()
    os.environ.update(allowed)
    os.chdir("/bundle")
    from apizr.execution.worker import main as worker_main

    worker_main()


if __name__ == "__main__":
    main()
