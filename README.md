> **READ THIS LICENSE BEFORE USING THIS REPOSITORY.** Owner-controlled new releases are subject to the [proprietary All Rights Reserved LICENSE](LICENSE): copying, modification, and redistribution require written authorization except where law or GitHub's Terms allow. Previously granted MIT rights remain valid for versions covered by that license; see the [historical license](docs/license-history/LICENSE-BEFORE-2026-10-13.txt). Third-party rights remain unaffected.

# Resource Control Plane

A production-oriented lease service for coordinating exclusive shared resources such as GPU nodes, lab equipment, mobile test devices, staging environments, or other scarce assets.

This project began as an IFT 510 Fall 2024 Flask/Docker resource-management lab. The maintained implementation evolves that idea into a durable control plane with PostgreSQL state, authenticated roles, expiring leases, atomic acquisition, idempotent retries, audit history, metrics, migrations, and hardened containers.

## Real-world use cases

- reserve a GPU before an automated benchmark
- claim a physical iOS/Android test device for CI
- coordinate a hardware-security lab bench
- lease a staging environment to one deployment job at a time
- reserve specialized shared equipment for an automated workflow

## Implemented controls

- one active lease per resource through an atomic conditional database update
- lease TTLs so abandoned clients cannot hold a resource indefinitely
- explicit renew and release operations
- retry-safe acquisition with Idempotency-Key
- monotonically increasing fencing tokens on successful acquisitions so downstream resource adapters can reject stale lease holders
- reader, operator, and admin bearer-token roles
- durable PostgreSQL resource, lease, idempotency, and audit records
- request IDs, JSON request logs, liveness, readiness, and Prometheus metrics
- bounded request bodies and per-process abuse throttling
- Alembic schema migrations
- non-root, read-only application container with Linux capabilities dropped
- PostgreSQL concurrency tests, lint, Bandit, pip-audit, migrations, Docker, and Compose gates in CI

See docs/ARCHITECTURE.md for the design and failure model.

## Quick start

Copy .env.example to .env, replace every placeholder with strong random values, and do not commit .env.

```bash
docker compose up -d --build
```

The API binds only to localhost using HOST_PORT, defaulting to 18080. Set HOST_PORT locally if that port is already in use.

## API roles

| Role | Capabilities |
| --- | --- |
| reader | list resources and leases, read metrics |
| operator | reader + acquire, renew, release |
| admin | operator + create/delete resources, read audit history |

A competing acquisition receives HTTP 409 until the lease is released or expires. Every successful acquisition returns a `fencing_token`; a newer holder always receives a larger token. Downstream systems that perform work on the leased resource should persist/compare that token and reject stale holders. The control plane emits the token but cannot enforce it inside an unrelated external device or service.

## Verification

```bash
python -m ruff check .
python -m pytest
python -m bandit -q -r resource_control wsgi.py
python -m pip_audit -r requirements.txt
alembic upgrade head
docker build -t resource-control-plane .
docker compose config --quiet
```

CI runs tests against PostgreSQL and includes a two-client concurrency test proving that only one contender can win a lease.

## Zero-cost development and validation

This repository requires no paid external service for local development or validation. The reference stack uses local Docker, PostgreSQL, open-source Python tooling, and no managed cloud database, paid API, SaaS monitoring service, or paid security scanner. Repository CI uses the standard public-repository Ubuntu runner and does not upload build artifacts or use workflow caches.

Optional production infrastructure is deliberately left to the deployer; nothing in this repository automatically provisions or purchases cloud resources.

## Deployment boundaries

The included Compose stack is a hardened single-host reference deployment. An Internet-facing deployment should additionally provide TLS, a controlled ingress, global rate limiting, secret-manager-backed credentials, PostgreSQL backups, monitoring, and tested restore procedures.

## 2024 provenance

The original coursework was completed Nov. 30-Dec. 1, 2024. The production control-plane architecture was added later and is documented separately from the original lab in docs/COURSEWORK_PROVENANCE.md.

## License

Proprietary / All Rights Reserved. See [LICENSE](LICENSE) and the [previous MIT license](docs/license-history/LICENSE-BEFORE-2026-10-13.txt).

## Product validation

This repository separates **implementation evidence**, **public/external interoperability checks**, and **real deployment or customer evidence**. See [PRODUCT_VALIDATION.md](PRODUCT_VALIDATION.md) for the current validation ladder, reproducible checks, and the claims that are deliberately out of scope. A passing test or public-data canary is not presented as customer adoption or universal production efficacy.


### Maintained Python quality checks

Use Ruff 0.16.10 to match the repository's CI tool version. Run `ruff check .`
and `ruff format --check .` from the repository root. These checks include maintained
source, tests, scripts, examples, benchmarks, validation helpers, and poster generators
where present. Ruff's standard exclusions omit version-control metadata, virtual
environments, and build/cache directories; generated poster HTML/PDF/PNG assets are
not Python source. Passing these static checks does not establish runtime behavior or product effectiveness.

## Current local verification

2026-10-13 UTC, Python 3.12.14; baseline `6777d6676c353e14d16d41d31a11bfd14575cc17` plus readiness regression fix. `python -m pytest -rA --cov=resource_control --cov-report=term`: **15 passed, 3 skipped**, 394/472 statements (83.47%). PostgreSQL integration and concurrency checks were skipped because `TEST_DATABASE_URL` was unavailable. Docker and Compose checks were blocked because Docker is not installed. Ruff 0.16.8 lint/format and Bandit 1.9.4 passed; the pinned Ruff 0.16.10 binary failed locally, so its exact CI check remains pending. `/readyz` checks database connectivity and required table presence; it does not certify migration revision or deployment reliability.
