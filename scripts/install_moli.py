"""Install the pinned official Moli binary without executing a remote installer."""

from __future__ import annotations

import hashlib
import io
import platform
import tarfile
import urllib.request
from pathlib import Path

VERSION = "1.1.9"
SHA256 = {
    "moli-aarch64-apple-darwin.tar.gz": (
        "6acf1b2dc54dc9d90902608b449edd4ca1aa1a95d54b67087a9be6d495f32e9d"
    ),
    "moli-aarch64-unknown-linux-gnu.tar.gz": (
        "e0100a651b1efdcbaa2f00e4e78aa86c30acbb7deac417a241ad5f7aee55513c"
    ),
    "moli-x86_64-apple-darwin.tar.gz": (
        "e07f2db104333142f5157bbd523f23ec57bf8fd698a9774dc8eae8760a69db52"
    ),
    "moli-x86_64-unknown-linux-gnu.tar.gz": (
        "34d00b75a6ca59119ac9ec09e6fc0c9ee264c215e9c482440d159fa63a589ba5"
    ),
}


def install() -> Path:
    system = {"Linux": "unknown-linux-gnu", "Darwin": "apple-darwin"}.get(
        platform.system()
    )
    arch = {"arm64": "aarch64", "aarch64": "aarch64", "x86_64": "x86_64"}.get(
        platform.machine()
    )
    if system is None or arch is None:
        raise SystemExit("Moli installer supports Linux/macOS on x86_64 and ARM64")
    destination = Path.home() / ".cache/scrapingarena/moli" / VERSION / "moli"
    if destination.is_file():
        return destination
    url = (
        f"https://github.com/lexmount/moli/releases/download/v{VERSION}/"
        f"moli-{arch}-{system}.tar.gz"
    )
    with urllib.request.urlopen(url, timeout=120) as response:
        archive = response.read()
    asset = f"moli-{arch}-{system}.tar.gz"
    if hashlib.sha256(archive).hexdigest() != SHA256[asset]:
        raise RuntimeError("Moli archive checksum mismatch")
    with tarfile.open(fileobj=io.BytesIO(archive), mode="r:gz") as package:
        candidates = [
            m
            for m in package.getmembers()
            if m.isfile() and Path(m.name).name == "moli"
        ]
        if len(candidates) != 1:
            raise RuntimeError("Moli release must contain exactly one executable")
        binary = package.extractfile(candidates[0])
        assert binary is not None
        destination.parent.mkdir(parents=True, exist_ok=True)
        temporary = destination.with_suffix(".tmp")
        temporary.write_bytes(binary.read())
        temporary.chmod(0o755)
        temporary.replace(destination)
    return destination


if __name__ == "__main__":
    print(install())
