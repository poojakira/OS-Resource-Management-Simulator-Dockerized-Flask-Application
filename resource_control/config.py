from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class Settings:
    database_url: str
    api_keys: str
    default_ttl_seconds: int
    max_ttl_seconds: int
    rate_limit_per_minute: int
    request_max_bytes: int
    trusted_proxy_hops: int

    @classmethod
    def from_env(cls) -> Settings:
        default_ttl = int(os.getenv("DEFAULT_LEASE_TTL_SECONDS", "1800"))
        max_ttl = int(os.getenv("MAX_LEASE_TTL_SECONDS", "86400"))
        rate_limit = int(os.getenv("RATE_LIMIT_PER_MINUTE", "120"))
        request_max = int(os.getenv("REQUEST_MAX_BYTES", "65536"))
        proxy_hops = int(os.getenv("TRUSTED_PROXY_HOPS", "0"))
        if default_ttl < 30 or max_ttl < default_ttl:
            raise ValueError("invalid lease TTL configuration")
        if rate_limit < 0 or request_max < 1024 or proxy_hops < 0:
            raise ValueError("invalid runtime limits")
        return cls(
            database_url=os.getenv("DATABASE_URL", "sqlite:///resource_control.db"),
            api_keys=os.getenv("RESOURCE_API_KEYS", ""),
            default_ttl_seconds=default_ttl,
            max_ttl_seconds=max_ttl,
            rate_limit_per_minute=rate_limit,
            request_max_bytes=request_max,
            trusted_proxy_hops=proxy_hops,
        )
