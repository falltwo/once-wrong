"""Keep the backend and AI imports owned by separate installed distributions."""

import importlib.metadata as metadata
import importlib.util
import re
import tomllib
from pathlib import Path

from packaging.requirements import Requirement

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
PACKAGES = (
    ("once-wrong", "once_wrong_ai", REPOSITORY_ROOT / "src" / "once_wrong_ai"),
    ("once-wrong-backend", "once_wrong", REPOSITORY_ROOT / "backend" / "once_wrong"),
)


def normalized_name(value: str) -> str:
    return re.sub(r"[-_.]+", "-", value).lower()


def test_installed_packages_have_unique_owners_and_the_expected_import_sources():
    owners = metadata.packages_distributions()
    for distribution_name, import_name, directory in PACKAGES:
        distribution = metadata.distribution(distribution_name)
        top_levels = set((distribution.read_text("top_level.txt") or "").split())
        assert top_levels == {import_name}
        assert {normalized_name(owner) for owner in owners.get(import_name, [])} == {
            distribution_name
        }
        spec = importlib.util.find_spec(import_name)
        assert spec is not None and spec.origin is not None
        assert Path(spec.origin).resolve() == (directory / "__init__.py").resolve()

    cli = [
        entry for entry in metadata.distribution("once-wrong").entry_points
        if entry.group == "console_scripts" and entry.name == "once-wrong-review"
    ]
    assert len(cli) == 1
    assert cli[0].value == "once_wrong_ai.ai_review.cli:main"


def test_source_roots_do_not_contain_a_second_or_repeatedly_renamed_package():
    for source_root, expected in (
        (REPOSITORY_ROOT / "src", {"once_wrong_ai"}),
        (REPOSITORY_ROOT / "backend", {"once_wrong"}),
    ):
        actual = {
            path.name for path in source_root.glob("once_wrong*")
            if path.is_dir() and (path / "__init__.py").is_file()
        }
        assert actual == expected
    assert not (REPOSITORY_ROOT / "src" / "once_wrong").exists()
    assert not (REPOSITORY_ROOT / "backend" / "once_wrong_ai").exists()


def test_backend_dependency_matches_the_ai_distribution_without_renaming_it():
    ai_project = tomllib.loads((REPOSITORY_ROOT / "pyproject.toml").read_text("utf-8"))
    backend_project = tomllib.loads(
        (REPOSITORY_ROOT / "backend" / "pyproject.toml").read_text("utf-8")
    )
    ai_name = normalized_name(ai_project["project"]["name"])
    assert ai_name == "once-wrong"
    assert normalized_name(backend_project["project"]["name"]) == "once-wrong-backend"

    for requirements in (
        backend_project["project"]["dependencies"],
        metadata.distribution("once-wrong-backend").requires or [],
    ):
        ai_requirements = [
            Requirement(value) for value in requirements
            if normalized_name(Requirement(value).name).startswith("once-wrong")
        ]
        assert len(ai_requirements) == 1
        requirement = ai_requirements[0]
        assert normalized_name(requirement.name) == ai_name
        assert metadata.version(ai_name) in requirement.specifier
