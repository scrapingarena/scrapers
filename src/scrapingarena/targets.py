from __future__ import annotations

import hashlib
import json
from pathlib import Path

from pydantic import TypeAdapter

from scrapingarena.models import Target

TARGETS_ADAPTER = TypeAdapter(list[Target])


def default_targets_path() -> Path:
    return Path(__file__).resolve().parents[2] / "targets" / "targets.json"


def load_targets(path: Path | None = None) -> list[Target]:
    target_path = path or default_targets_path()
    raw = json.loads(target_path.read_text(encoding="utf-8"))
    targets = TARGETS_ADAPTER.validate_python(raw)
    validate_corpus(targets)
    return targets


def validate_corpus(targets: list[Target], *, require_full_corpus: bool = True) -> None:
    if require_full_corpus and len(targets) != 100:
        raise ValueError(
            f"target corpus must contain exactly 100 URLs, got {len(targets)}"
        )

    if require_full_corpus:
        unprotected = [target.id for target in targets if target.protection == "none"]
        if unprotected:
            raise ValueError(f"canonical targets cannot be unprotected: {unprotected}")

        editorial = [
            target.id
            for target in targets
            if "news" in target.category or target.category == "publishing"
        ]
        if editorial:
            raise ValueError(f"canonical targets cannot be editorial: {editorial}")

        plain = [
            target.id
            for target in targets
            if not target.url.query and not (target.url.path or "").rstrip("/")
        ]
        if plain:
            raise ValueError(f"canonical targets must use deep routes: {plain}")

    ids = [target.id for target in targets]
    if len(ids) != len(set(ids)):
        raise ValueError("target IDs must be unique")

    domains = [target.url.host.lower() for target in targets if target.url.host]
    if len(domains) != len(set(domains)):
        raise ValueError("target domains must be unique")


def corpus_sha256(path: Path | None = None) -> str:
    target_path = path or default_targets_path()
    return hashlib.sha256(target_path.read_bytes()).hexdigest()
