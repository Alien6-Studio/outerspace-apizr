from pathlib import Path


def message() -> str:
    """Return the packaged message decoded with the application's dependency."""
    return _message()


def _message() -> str:
    from six import ensure_text

    content = (Path(__file__).parent.parent / "data/message.txt").read_bytes()
    return ensure_text(content).strip().upper()
