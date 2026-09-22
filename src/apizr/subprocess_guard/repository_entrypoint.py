"""Strict repository worker entrypoint; installation precedes all project imports."""

from .filter import install


def main() -> None:
    install()
    from apizr.repository_execution.entrypoint import main as worker

    worker()


if __name__ == "__main__":
    main()
