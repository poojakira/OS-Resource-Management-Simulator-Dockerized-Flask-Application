# Production Architecture

## Purpose

The service coordinates scarce resources that must not be owned by two clients at the same time, including GPU nodes, lab instruments, mobile test devices, and shared staging environments.

## Guarantees

- acquisition uses a conditional database update so only one transaction can claim an idle resource
- every lease expires, preventing abandoned clients from holding a resource indefinitely
- active leases can be renewed or explicitly released
- Idempotency-Key is scoped to the authenticated actor, hashed before storage, and reserved transactionally
- resource and lease state changes write durable audit events in the same database transaction
- request logs include request ID, route, actor, and status but never bearer tokens or request bodies

## Authorization

Credentials use name:role:key entries. Keys are SHA-256 hashed in memory before lookup and are never written to the application database.

reader can inspect state and metrics. operator can acquire, renew, and release leases. admin can create/delete resources and read audit history.

## Deployment

TLS and a global rate limiter belong at the controlled ingress. Gunicorn replicas use PostgreSQL as the shared source of truth. The application limiter is intentionally per process, so multi-replica deployments require a distributed ingress/API-gateway limit.

## Metrics and failure model

The authenticated Prometheus endpoint exposes request volume, request latency, active lease count, and lease-operation outcomes without resource IDs or owner names as labels.

Database failure returns readiness 503. Duplicate claims return 409. Invalid credentials return 401. Insufficient roles return 403. Invalid request bodies or TTLs return 400/415.
