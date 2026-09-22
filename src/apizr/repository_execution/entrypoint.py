"""Fixed repository OCI entrypoint; image environment is not invocation authority."""

import os
import sys


def main() -> None:
    allowed = {name: os.environ[name] for name in sys.argv[1:] if name in os.environ}
    os.environ.clear()
    os.environ.update(allowed)
    os.chdir("/bundle")
    from apizr.repository_execution.worker import main as worker_main

    worker_main()


if __name__ == "__main__":
    main()
