# Product Validation

## Product boundary
Lease-based resource coordination service demonstrating atomic acquisition, expiry, idempotency, authorization, auditability, and concurrency behavior.

## Real-world validation ladder
1. Unit/control-plane tests.
2. PostgreSQL integration test.
3. Concurrent acquisition stress test proving at-most-one active holder for an exclusive resource.
4. Expiry/reacquisition and idempotent retry tests.
5. Fencing-token tests proving each new holder receives a strictly larger token while idempotent retries preserve the original token.
6. Process restart/recovery validation against persistent state.

## Evidence rules
A local concurrency test is not a distributed-consensus claim. The service must not be described as a replacement for Kubernetes/etcd/Consul. Fencing tokens are emitted for downstream stale-holder protection, but external resources must actually enforce those tokens for that protection to be effective.
