# Security Policy

## Implemented controls

- bearer credentials with reader/operator/admin roles
- no credentials written to the database or request logs
- bounded request bodies
- state changes restricted to POST/DELETE
- atomic database-backed lease claims
- lease expiration, renewal, and release
- transaction-scoped idempotency records
- structured audit events and request IDs
- authenticated Prometheus metrics
- per-process abuse throttling
- non-root read-only application container
- dropped Linux capabilities and no-new-privileges
- dependency, static-analysis, migration, PostgreSQL concurrency, Docker, and Compose CI gates

## Production requirements

Terminate TLS at a controlled ingress, store credentials in a secret manager, keep PostgreSQL private and backed up, configure trusted proxy hops only for a known proxy chain, apply a distributed rate limit for multi-replica deployments, and test database restore procedures.

Do not place credentials, private infrastructure data, database URLs, or other secrets in public issues. Use private vulnerability reporting when available.
