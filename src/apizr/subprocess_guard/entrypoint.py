"""Strict single-source worker entrypoint; installation failure stops startup."""

from .filter import install


def main() -> None:
    install()
    from apizr.oci.entrypoint import main as worker

    worker()


if __name__ == "__main__":
    main()
