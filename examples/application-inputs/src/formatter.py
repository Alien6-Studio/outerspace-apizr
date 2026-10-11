from pathlib import Path


def message() -> str:
    """Return packaged text with the pinned application dependency installed."""
    return _message()


def _message() -> str:
    from importlib.metadata import version

    if version("six") != "1.17.0":
        raise RuntimeError("Application dependency version does not match")
    content = (Path(__file__).parent.parent / "data/message.txt").read_bytes()
    return content.decode("utf-8").strip().upper()
