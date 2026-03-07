from __future__ import annotations

import re
from typing import Iterable, List, Set


def parse_detected_classes(raw) -> Set[str]:
    if raw is None:
        return set()
    if isinstance(raw, (list, tuple, set)):
        return {str(x).strip().lower() for x in raw if str(x).strip()}
    text = str(raw).lower()
    parts = re.split(r"[,:;|\s]+", text)
    return {p.strip() for p in parts if p.strip()}


def has_any(classes: Set[str], candidates: Iterable[str]) -> bool:
    cands = {x.lower() for x in candidates}
    return any(c in classes for c in cands)


def has_all(classes: Set[str], candidates: Iterable[str]) -> bool:
    cands = {x.lower() for x in candidates}
    return cands.issubset(classes)


def safe_upper_tokens(text: str) -> List[str]:
    tokens = re.split(r"[^A-Za-z0-9\-]+", (text or "").upper())
    return [x for x in tokens if x]
