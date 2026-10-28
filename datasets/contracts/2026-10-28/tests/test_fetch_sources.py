"""Optional downloads are pinned and never overwrite files; no live networking."""

import hashlib
import importlib.util
import io
import json
import urllib.error
import urllib.request
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[1] / "fetch_sources.py"
SPEC = importlib.util.spec_from_file_location("rule_dataset_fetch_sources", SCRIPT)
fetcher = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(fetcher)
PDF = b"%PDF-1.7\nSynthetic offline test document\n%%EOF\n"


def source(**changes):
    item = {
        "source_id": "SYNTHETIC-PDF",
        "source_page_url": "https://example.test/source",
        "download_url": "https://example.test/source.pdf",
        "sha256": hashlib.sha256(PDF).hexdigest(),
        "local_file": "originals/SYNTHETIC-PDF.pdf",
    }
    return {**item, **changes}


class Response(io.BytesIO):
    def __init__(self, content=PDF, *, url="https://example.test/source.pdf", headers=None):
        super().__init__(content)
        self.url = url
        self.status = 200
        self.headers = headers or {}

    def geturl(self):
        return self.url


class Opener:
    def __init__(self, response=None, error=None):
        self.response = response
        self.error = error
        self.calls = []

    def open(self, request, *, timeout):
        self.calls.append((request.full_url, timeout))
        if self.error:
            raise self.error
        return self.response or Response()


def manifest(tmp_path, sources=None):
    path = tmp_path / "source_manifest.json"
    path.write_text(json.dumps({"sources": sources or [source()]}), encoding="utf-8")
    return path


def assert_failed(result):
    assert result["download_status"] == "failed", result
    assert result["download_error"]


def test_pinned_download_succeeds_and_cached_copy_needs_no_network(tmp_path):
    path = manifest(tmp_path)
    before = path.read_bytes()
    [item] = fetcher.load_manifest(path)
    opener = Opener()
    result = fetcher.fetch(item, root=tmp_path, opener=opener)
    assert result["download_status"] == "downloaded_verified_pdf"
    assert opener.calls == [(item["download_url"], 30.0)]
    target = tmp_path / item["local_file"]
    assert target.read_bytes() == PDF
    cached_opener = Opener(error=AssertionError("cache must not use the network"))
    cached = fetcher.fetch(item, root=tmp_path, opener=cached_opener)
    assert cached["download_status"] == "cached_verified_pdf"
    assert cached_opener.calls == []
    assert path.read_bytes() == before


def test_existing_hash_mismatch_is_not_overwritten_or_refetched(tmp_path):
    item = source()
    target = tmp_path / item["local_file"]
    target.parent.mkdir()
    target.write_bytes(b"%PDF-1.7\nexisting other revision")
    before = target.read_bytes()
    opener = Opener()
    assert_failed(fetcher.fetch(item, root=tmp_path, opener=opener))
    assert target.read_bytes() == before
    assert opener.calls == []


@pytest.mark.parametrize("content", [b"<html>not a PDF</html>", b"%PDF-1.7\nnew unpinned revision"])
def test_invalid_or_new_revision_download_is_not_saved(tmp_path, content):
    path = manifest(tmp_path)
    before = path.read_bytes()
    result = fetcher.fetch(source(), root=tmp_path, opener=Opener(Response(content)))
    assert_failed(result)
    assert not (tmp_path / source()["local_file"]).exists()
    assert path.read_bytes() == before


def test_missing_remote_document_fails_without_creating_file(tmp_path):
    error = urllib.error.HTTPError("https://example.test/missing", 404, "missing", {}, None)
    assert_failed(fetcher.fetch(source(), root=tmp_path, opener=Opener(error=error)))
    assert not (tmp_path / "originals").exists()


@pytest.mark.parametrize("path", [
    "../escape.pdf", "/escape.pdf", "C:/escape.pdf", "originals/../escape.pdf",
    "originals/subdir/file.pdf", "originals\\escape.pdf", "originals/file.txt",
    "originals/CON.pdf",
])
def test_only_direct_safe_pdf_paths_are_allowed(tmp_path, path):
    opener = Opener()
    assert_failed(fetcher.fetch(source(local_file=path), root=tmp_path, opener=opener))
    assert opener.calls == []
    assert not (tmp_path / "originals").exists()


@pytest.mark.parametrize("url", [
    "http://example.test/a.pdf", "file:///etc/passwd", "https://u:p@example.test/a.pdf"
])
def test_only_https_source_urls_without_credentials_are_allowed(tmp_path, url):
    opener = Opener()
    assert_failed(fetcher.fetch(source(download_url=url), root=tmp_path, opener=opener))
    assert opener.calls == []


def test_final_redirect_url_must_remain_https(tmp_path):
    response = Response(url="http://example.test/source.pdf")
    assert_failed(fetcher.fetch(source(), root=tmp_path, opener=Opener(response)))
    assert not (tmp_path / "originals").exists()


def test_redirect_handler_refuses_http_before_following_it():
    handler = fetcher.HTTPSOnlyRedirectHandler()
    request = urllib.request.Request("https://example.test/source.pdf")
    with pytest.raises(ValueError, match="HTTPS"):
        handler.redirect_request(request, None, 302, "redirect", {}, "http://example.test/source.pdf")


@pytest.mark.parametrize("advertised", [False, True])
def test_streaming_and_advertised_size_limits(tmp_path, monkeypatch, advertised):
    monkeypatch.setattr(fetcher, "MAX_FILE_BYTES", len(PDF) - 1)
    response = Response(headers={"Content-Length": str(len(PDF))} if advertised else {})
    assert_failed(fetcher.fetch(source(), root=tmp_path, opener=Opener(response)))
    assert not (tmp_path / "originals").exists()


def test_symlinked_originals_directory_cannot_escape_manifest_root(tmp_path):
    outside = tmp_path / "outside"
    outside.mkdir()
    root = tmp_path / "package"
    root.mkdir()
    try:
        (root / "originals").symlink_to(outside, target_is_directory=True)
    except OSError:
        pytest.skip("This environment cannot create directory symlinks")
    opener = Opener()
    assert_failed(fetcher.fetch(source(), root=root, opener=opener))
    assert opener.calls == []
    assert list(outside.iterdir()) == []


def test_exclusive_creation_does_not_replace_a_concurrent_file(tmp_path):
    item = source()
    target = tmp_path / item["local_file"]

    class ConcurrentOpener(Opener):
        def open(self, request, *, timeout):
            target.parent.mkdir()
            target.write_bytes(b"other process owns this file")
            return Response()

    assert_failed(fetcher.fetch(item, root=tmp_path, opener=ConcurrentOpener()))
    assert target.read_bytes() == b"other process owns this file"


def test_failure_after_creating_own_file_removes_incomplete_output(tmp_path, monkeypatch):
    def fail_flush(descriptor):
        raise OSError("simulated disk failure")

    monkeypatch.setattr(fetcher.os, "fsync", fail_flush)
    assert_failed(fetcher.fetch(source(), root=tmp_path, opener=Opener()))
    assert not (tmp_path / source()["local_file"]).exists()


def test_cli_source_selection_and_immutable_manifest(tmp_path, monkeypatch, capsys):
    path = manifest(tmp_path, [
        source(), source(source_id="SECOND", local_file="originals/SECOND.pdf")
    ])
    before = path.read_bytes()
    monkeypatch.setattr(fetcher.urllib.request, "build_opener", lambda *args: Opener())
    assert fetcher.main(["--manifest", str(path), "--source-id", "SECOND"]) == 0
    [result] = [json.loads(line) for line in capsys.readouterr().out.splitlines()]
    assert result["source_id"] == "SECOND"
    assert not (tmp_path / source()["local_file"]).exists()
    assert (tmp_path / "originals/SECOND.pdf").read_bytes() == PDF
    assert path.read_bytes() == before


def test_cli_unknown_source_or_missing_manifest_returns_nonzero(tmp_path):
    path = manifest(tmp_path)
    assert fetcher.main(["--manifest", str(path), "--source-id", "MISSING"]) == 1
    assert fetcher.main(["--manifest", str(tmp_path / "missing.json")]) == 1
    assert not (tmp_path / "originals").exists()


def test_cli_repeated_selection_fetches_only_selected_sources(tmp_path, monkeypatch, capsys):
    path = manifest(tmp_path, [
        source(),
        source(source_id="SECOND", local_file="originals/SECOND.pdf"),
        source(source_id="THIRD", local_file="originals/THIRD.pdf"),
    ])
    monkeypatch.setattr(fetcher.urllib.request, "build_opener", lambda *args: Opener())
    args = ["--manifest", str(path), "--source-id", "SECOND", "--source-id", "THIRD"]
    assert fetcher.main(args) == 0
    results = [json.loads(line) for line in capsys.readouterr().out.splitlines()]
    assert [item["source_id"] for item in results] == ["SECOND", "THIRD"]
    assert not (tmp_path / source()["local_file"]).exists()


@pytest.mark.parametrize("changes", [{"sha256": "missing-hash"}, {"download_url": ""}])
def test_invalid_manifest_source_fields_fail_before_network(tmp_path, changes):
    opener = Opener()
    assert_failed(fetcher.fetch(source(**changes), root=tmp_path, opener=opener))
    assert opener.calls == []


def test_missing_manifest_source_field_is_rejected(tmp_path):
    item = source()
    del item["sha256"]
    path = manifest(tmp_path, [item])
    with pytest.raises(ValueError, match="five"):
        fetcher.load_manifest(path)


def test_duplicate_manifest_sources_are_rejected(tmp_path):
    path = manifest(tmp_path, [source(), source()])
    with pytest.raises(ValueError, match="unique"):
        fetcher.load_manifest(path)
