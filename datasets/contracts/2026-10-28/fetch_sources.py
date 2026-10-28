"""Optionally download public reference PDFs without changing their pinned hashes.

With no arguments, read source_manifest.json next to this script and download
into its ignored originals/ directory. --manifest is resolved against the
current working directory; local_file is relative to that manifest's directory.
Rule fixtures do not require these optional public contract downloads.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import urllib.request
from pathlib import Path, PureWindowsPath
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parent
MAX_FILE_BYTES = 25 * 1024 * 1024
REQUEST_TIMEOUT = 30.0
SOURCE_FIELDS = {"source_id", "source_page_url", "download_url", "sha256", "local_file"}


def _https_url(value: str) -> str:
    parsed = urlsplit(value)
    if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password:
        raise ValueError("Source and redirect URLs must use HTTPS without credentials")
    return value


def _validate_source(item: dict) -> None:
    if not isinstance(item, dict) or set(item) != SOURCE_FIELDS:
        raise ValueError("Every source must contain exactly the five manifest source fields")
    if any(not isinstance(value, str) or not value for value in item.values()):
        raise ValueError("Manifest source fields must be nonempty strings")
    if not re.fullmatch(r"[0-9a-fA-F]{64}", item["sha256"]):
        raise ValueError("Source SHA-256 must be a 64-character hexadecimal digest")
    _https_url(item["source_page_url"])
    _https_url(item["download_url"])
    path = item["local_file"]
    if not re.fullmatch(r"originals/[A-Za-z0-9][A-Za-z0-9._-]*\.pdf", path):
        raise ValueError("local_file must be a direct originals/*.pdf path")
    if PureWindowsPath(path).is_reserved():
        raise ValueError("local_file cannot use a Windows reserved filename")


def load_manifest(path: str | Path = ROOT / "source_manifest.json") -> list[dict]:
    """Read a pinned manifest; do not rewrite it during download or verification."""
    payload = json.loads(Path(path).read_text(encoding="utf-8-sig"))
    if not isinstance(payload, dict) or not isinstance(payload.get("sources"), list):
        raise ValueError("Manifest must be an object with a sources list")
    sources = payload["sources"]
    ids, files = set(), set()
    for item in sources:
        _validate_source(item)
        if item["source_id"] in ids or item["local_file"].casefold() in files:
            raise ValueError("Manifest source IDs and local paths must be unique")
        ids.add(item["source_id"])
        files.add(item["local_file"].casefold())
    return sources


def _target(root: Path, item: dict) -> Path:
    root = root.resolve()
    directory = root / "originals"
    target = root / item["local_file"]
    # Reject even in-tree symlinks: ignored downloads must not follow a link
    # into a tracked directory or replace a different document through a link.
    if directory.is_symlink() or target.is_symlink():
        raise ValueError("Download paths cannot be symlinks")
    if not target.resolve().is_relative_to(root):
        raise ValueError("Download path escapes the manifest directory")
    if target.parent.resolve() != directory.resolve():
        raise ValueError("Download must be directly inside originals/")
    return target


def _verified(content: bytes, expected_hash: str) -> None:
    if len(content) > MAX_FILE_BYTES:
        raise ValueError("PDF exceeds the 25 MiB download limit")
    if not content.lstrip().startswith(b"%PDF-"):
        raise ValueError("Response does not have a PDF signature")
    if hashlib.sha256(content).hexdigest() != expected_hash.lower():
        raise ValueError("SHA-256 mismatch; pinned manifest and existing files were not changed")


class HTTPSOnlyRedirectHandler(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, request, fp, code, msg, headers, newurl):
        _https_url(newurl)
        return super().redirect_request(request, fp, code, msg, headers, newurl)


def _download(url: str, opener) -> bytes:
    request = urllib.request.Request(
        _https_url(url), headers={"User-Agent": "Once-Wrong-Optional-Reference-Downloader/1.0"}
    )
    # The default HTTPS handler verifies certificates using platform trust.
    # No insecure SSL context is supplied.
    with opener.open(request, timeout=REQUEST_TIMEOUT) as response:
        _https_url(response.geturl())
        if not 200 <= response.status < 300:
            raise ValueError(f"Unexpected HTTP status: {response.status}")
        length = response.headers.get("Content-Length")
        if length is not None and int(length) > MAX_FILE_BYTES:
            raise ValueError("PDF exceeds the 25 MiB download limit")
        chunks, total = [], 0
        while True:
            chunk = response.read(min(64 * 1024, MAX_FILE_BYTES - total + 1))
            if not chunk:
                break
            total += len(chunk)
            if total > MAX_FILE_BYTES:
                raise ValueError("PDF exceeds the 25 MiB download limit")
            chunks.append(chunk)
        return b"".join(chunks)


def _write_exclusive(target: Path, content: bytes) -> None:
    identity = None
    try:
        with target.open("xb") as stream:
            stat = os.fstat(stream.fileno())
            identity = (stat.st_dev, stat.st_ino)
            if stream.write(content) != len(content):
                raise OSError("Incomplete PDF write")
            stream.flush()
            os.fsync(stream.fileno())
    except BaseException:
        if identity is not None:
            try:
                current = target.stat(follow_symlinks=False)
                if (current.st_dev, current.st_ino) == identity:
                    target.unlink()
            except FileNotFoundError:
                pass
        raise


def fetch(item: dict, *, root: str | Path = ROOT, opener=None) -> dict:
    """Return a status object; failures leave the manifest and prior files intact."""
    source_id = item.get("source_id") if isinstance(item, dict) else None
    result = {"source_id": source_id}
    try:
        _validate_source(item)
        root = Path(root)
        target = _target(root, item)
        if target.exists():
            with target.open("rb") as stream:
                content = stream.read(MAX_FILE_BYTES + 1)
            _verified(content, item["sha256"])
            status = "cached_verified_pdf"
        else:
            if opener is None:
                opener = urllib.request.build_opener(HTTPSOnlyRedirectHandler())
            content = _download(item["download_url"], opener)
            _verified(content, item["sha256"])
            target.parent.mkdir(parents=True, exist_ok=True)
            target = _target(root, item)
            _write_exclusive(target, content)
            status = "downloaded_verified_pdf"
        result.update(
            download_status=status,
            local_file=item["local_file"],
            sha256=item["sha256"],
            size_bytes=len(content),
        )
    except Exception as error:
        result.update(download_status="failed", download_error=str(error))
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--manifest", type=Path, default=ROOT / "source_manifest.json",
        help="Manifest path; explicit relative paths are resolved against the current directory",
    )
    parser.add_argument(
        "--source-id", action="append",
        help="Download only this source; repeat the option to select multiple sources",
    )
    args = parser.parse_args(argv)
    try:
        manifest = args.manifest.resolve()
        sources = load_manifest(manifest)
        if args.source_id:
            requested = set(args.source_id)
            unknown = requested - {item["source_id"] for item in sources}
            if unknown:
                raise ValueError(f"Unknown source IDs: {', '.join(sorted(unknown))}")
            sources = [item for item in sources if item["source_id"] in requested]
    except (OSError, ValueError) as error:
        print(json.dumps({"download_status": "failed", "download_error": str(error)}))
        return 1
    results = [fetch(item, root=manifest.parent) for item in sources]
    for result in results:
        print(json.dumps(result, ensure_ascii=False))
    return int(any(item["download_status"] == "failed" for item in results))


if __name__ == "__main__":
    raise SystemExit(main())
