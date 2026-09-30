"""Download only the checksum-pinned official Inso qualification binary."""

import argparse
import hashlib
import io
import platform
import tarfile
import urllib.request
import zipfile


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output")
    args = parser.parse_args()
    from pathlib import Path

    root = Path(args.output)
    root.mkdir(parents=True, exist_ok=False)
    if platform.system() == "Darwin":
        name = "inso-macos-13.3.0.zip"
        digest = "c63043015fd1ef129f614b5eb146a34f1b1585ded9b186eb2494b420980139e6"
    elif platform.system() == "Linux" and platform.machine() == "x86_64":
        name = "inso-linux-x64-13.3.0.tar.xz"
        digest = "b9cc5f827d510048a9e259e2a1687ca78fb57c21020b832d4630f96740a90864"
    else:
        raise SystemExit("Unsupported qualification platform")
    url = "https://github.com/Kong/insomnia/releases/download/core%4013.3.0/" + name
    with urllib.request.urlopen(url, timeout=90) as response:
        data = response.read()
    if hashlib.sha256(data).hexdigest() != digest:
        raise SystemExit("Inso archive digest mismatch")
    if name.endswith(".zip"):
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            # Only the executable is extracted, never arbitrary archive members.
            (root / "inso").write_bytes(archive.read("inso"))
    else:
        with tarfile.open(fileobj=io.BytesIO(data), mode="r:xz") as archive:
            member = next(
                m
                for m in archive.getmembers()
                if m.name.rsplit("/", 1)[-1] == "inso" and m.isfile()
            )
            stream = archive.extractfile(member)
            if stream is None:
                raise SystemExit("Inso archive has no executable")
            (root / "inso").write_bytes(stream.read())
    (root / "inso").chmod(0o755)


if __name__ == "__main__":
    main()
