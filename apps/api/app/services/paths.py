"""Safe filesystem helpers — every user-influenced path must go through safe_join."""
from __future__ import annotations

import re
from pathlib import Path

_SLUG_RE = re.compile(r"[^a-z0-9-]+")


def slugify(text: str, fallback: str = "untitled") -> str:
    slug = _SLUG_RE.sub("-", text.strip().lower()).strip("-")
    slug = re.sub(r"-{2,}", "-", slug)[:64]
    return slug or fallback


def safe_join(root: Path, *parts: str) -> Path:
    """Join and verify the result stays inside root. Raises ValueError otherwise."""
    root = root.resolve()
    target = root.joinpath(*parts).resolve()
    if target != root and root not in target.parents:
        raise ValueError(f"Path escapes storage root: {parts!r}")
    return target


def is_safe_doc_name(name: str) -> bool:
    return bool(re.fullmatch(r"[a-z0-9][a-z0-9-]*\.md", name))
