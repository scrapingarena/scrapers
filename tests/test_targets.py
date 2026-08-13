from pathlib import Path

import pytest

from scrapingarena.models import Target
from scrapingarena.targets import load_targets, validate_corpus


def test_versioned_corpus_has_100_unique_domains() -> None:
    targets = load_targets()

    assert len(targets) == 100
    assert len({target.url.host for target in targets}) == 100
    assert len({target.id for target in targets}) == 100
    assert all(target.protection != "none" for target in targets)
    assert all("news" not in target.category for target in targets)
    assert all(target.category != "publishing" for target in targets)


def test_versioned_corpus_includes_deep_dynamic_routes() -> None:
    targets = load_targets()
    dynamic_targets = [
        target
        for target in targets
        if target.url.query or (target.url.path or "").rstrip("/")
    ]

    assert len(dynamic_targets) == 100


def test_custom_corpus_can_skip_full_size_requirement() -> None:
    target = Target.model_validate(
        {
            "id": "example",
            "name": "Example",
            "url": "https://example.com",
            "category": "test",
        }
    )

    validate_corpus([target], require_full_corpus=False)


def test_duplicate_domain_is_rejected() -> None:
    first = Target.model_validate(
        {
            "id": "first",
            "name": "First",
            "url": "https://example.com/a",
            "category": "test",
        }
    )
    second = Target.model_validate(
        {
            "id": "second",
            "name": "Second",
            "url": "https://example.com/b",
            "category": "test",
        }
    )

    with pytest.raises(ValueError, match="domains"):
        validate_corpus([first, second], require_full_corpus=False)


def test_default_target_path_exists() -> None:
    # Guards package layout changes that could silently break Actions.
    assert Path("targets/targets.json").is_file()
