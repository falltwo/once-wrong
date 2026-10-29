"""Prevent removed source documents, private access links, or corpus reintroduction."""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

DATASET_ROOT = Path(__file__).resolve().parents[1]
REPOSITORY_ROOT = DATASET_ROOT.parents[2]
REMOVED_CORPUS_FILES = {
    "AI_HANDOFF.md", "PREPARED_SCHEMA.md", "build_catalog.py", "prepare_ai_data.py",
    "clause_examples.jsonl", "clause_examples_cancer_accident.jsonl",
    "clause_examples_life_annuity.jsonl", "comparison_pairs.json",
    "source_annotations_cancer_accident.json", "source_annotations_life_annuity.json",
    "source_index.json", "source_candidates.json", "excluded_sources.json",
    "source_manifest.json", "fetch_sources.py", "test_fetch_sources.py",
}
PRIVATE_LINK = re.compile(r"https?://(?:drive|docs)\.google\.com(?:[/:?#]|$)", re.IGNORECASE)
TEXT_SUFFIXES = {".md", ".json", ".jsonl", ".py", ".yml", ".yaml", ".txt"}


def _publication_files():
    # Include new files before staging, but exclude ignored local downloads and
    # generated artifacts. Deleted tracked paths are absent from the new tree.
    result = subprocess.run(
        ["git", "ls-files", "--cached", "--others", "--exclude-standard", "-z"],
        cwd=REPOSITORY_ROOT, check=True, capture_output=True,
    )
    return [
        path
        for name in result.stdout.decode("utf-8").split("\0")
        if name and (path := REPOSITORY_ROOT / name).is_file()
    ]


def test_public_tree_has_no_documents_or_organizer_download_links():
    files = _publication_files()
    assert files
    for path in files:
        relative = path.relative_to(REPOSITORY_ROOT)
        assert path.suffix.lower() not in {".pdf", ".docx"}, str(relative)
        assert "originals" not in relative.parts, str(relative)
        if path.suffix.lower() in TEXT_SUFFIXES:
            assert not PRIVATE_LINK.search(path.read_text(encoding="utf-8-sig")), str(relative)


def test_contract_corpus_and_training_preparation_are_outside_this_pr():
    published_dataset_files = {
        path.name for path in _publication_files() if path.is_relative_to(DATASET_ROOT)
    }
    assert not published_dataset_files.intersection(REMOVED_CORPUS_FILES)


def test_private_manual_index_carries_only_offline_provenance(manual_references):
    assert len(manual_references) == 5
    for source_id, source in manual_references.items():
        assert re.fullmatch(r"(?:MANUAL|RULES)-[A-Z0-9-]+", source_id)
        assert source["bundled"] is False
        assert re.fullmatch(r"[0-9a-f]{64}", source["sha256"])
        assert source["local_file"].startswith("official-materials/")
        assert not any("url" in key.lower() for key in source)
