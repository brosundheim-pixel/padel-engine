"""Disk cache for paid Google Maps API responses.

First line of defense against runaway spend: if the answer is on disk, never
hit the network. Keys are stable hashes of (endpoint, query_dict) so the same
logical query always lands on the same path regardless of dict iteration
order or whitespace.

Cache root is `data/raw/google_places/` per spec. When other Google APIs are
added (Routes, Geocoding) the root can be parameterized; for now scope is
limited to Places.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Dict, Optional

REPO_ROOT = Path(__file__).resolve().parents[2]
CACHE_DIR = REPO_ROOT / "data" / "raw" / "google_places"


def _canonical(query_dict: Dict[str, Any]) -> str:
    """Deterministic JSON for hashing — sorted keys, no whitespace."""
    return json.dumps(query_dict, sort_keys=True, separators=(",", ":"))


def _key(endpoint: str, query_dict: Dict[str, Any]) -> str:
    """16-hex-char SHA256 prefix of (endpoint, canonical query). Includes
    endpoint in the hash so the same query against different endpoints
    cannot collide."""
    payload = json.dumps(
        {"endpoint": endpoint, "query": query_dict},
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(payload.encode()).hexdigest()[:16]


def cache_path(endpoint: str, query_dict: Dict[str, Any]) -> Path:
    """Stable path for the (endpoint, query) pair. Does NOT create the file."""
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    return CACHE_DIR / f"{_key(endpoint, query_dict)}.json"


def is_cached(endpoint: str, query_dict: Dict[str, Any]) -> bool:
    return cache_path(endpoint, query_dict).exists()


def get(endpoint: str, query_dict: Dict[str, Any]) -> Optional[Any]:
    """Return cached response if present, else None."""
    path = cache_path(endpoint, query_dict)
    if not path.exists():
        return None
    return json.loads(path.read_text())


def set(endpoint: str, query_dict: Dict[str, Any], response: Any) -> Path:
    """Write response JSON to cache_path. Returns the path written."""
    path = cache_path(endpoint, query_dict)
    path.write_text(json.dumps(response, indent=2, sort_keys=True))
    return path
