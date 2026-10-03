from __future__ import annotations

import hashlib
import hmac
import re
import threading
import time
from collections import defaultdict, deque
from dataclasses import dataclass

ROLE_LEVEL = {"reader": 10, "operator": 20, "admin": 30}
BEARER_RE = re.compile(r"^Bearer\s+(.+)$", re.IGNORECASE)


@dataclass(frozen=True)
class Actor:
    name: str
    role: str
    key_hash: str


def parse_api_keys(raw: str) -> dict[str, Actor]:
    actors: dict[str, Actor] = {}
    if not raw.strip():
        return actors
    for entry in raw.split(","):
        parts = entry.strip().split(":", 2)
        if len(parts) != 3:
            raise ValueError("RESOURCE_API_KEYS entries must be name:role:key")
        name, role, key = parts
        if not name or role not in ROLE_LEVEL:
            raise ValueError("invalid RESOURCE_API_KEYS identity or role")
        if len(key) < 24:
            raise ValueError("API keys must be at least 24 characters")
        digest = hashlib.sha256(key.encode()).hexdigest()
        if digest in actors:
            raise ValueError("duplicate API key")
        actors[digest] = Actor(name=name, role=role, key_hash=digest)
    return actors


def authenticate(header: str | None, actors: dict[str, Actor]) -> Actor | None:
    if not header:
        return None
    match = BEARER_RE.match(header.strip())
    if not match:
        return None
    digest = hashlib.sha256(match.group(1).encode()).hexdigest()
    for known_digest, actor in actors.items():
        if hmac.compare_digest(digest, known_digest):
            return actor
    return None


def role_allows(actor: Actor, required: str) -> bool:
    return ROLE_LEVEL[actor.role] >= ROLE_LEVEL[required]


class SlidingWindowLimiter:
    def __init__(self, requests_per_minute: int) -> None:
        self.limit = requests_per_minute
        self._events: dict[str, deque[float]] = defaultdict(deque)
        self._lock = threading.Lock()

    def allow(self, key: str) -> tuple[bool, int]:
        if self.limit == 0:
            return True, 0
        now = time.monotonic()
        cutoff = now - 60
        with self._lock:
            events = self._events[key]
            while events and events[0] <= cutoff:
                events.popleft()
            if len(events) >= self.limit:
                return False, 0
            events.append(now)
            return True, self.limit - len(events)
