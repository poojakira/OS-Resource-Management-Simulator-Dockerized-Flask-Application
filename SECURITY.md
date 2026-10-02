# Security Policy

## Supported scope

This repository is an educational Flask/Docker project. It is maintained to avoid unsafe defaults and to keep the public source clean, but it is not an authenticated production service.

## Reporting a problem

Use the repository's GitHub Issues for non-sensitive bugs. For a security issue that should not be public, use GitHub's private vulnerability reporting feature if it is enabled for the repository.

Do not include credentials, access tokens, private keys, personal identifiers, or other secrets in an issue.

## Security expectations

- Do not commit populated `.env` files or virtual environments.
- Keep runtime dependencies pinned and review dependency-audit failures.
- Keep Flask debug mode disabled in shared or containerized environments.
- Use the Docker image as a non-root user.
- Treat the in-memory state model as single-process educational state, not durable or distributed state.
- Do not expose the application directly to the public Internet without adding authentication, authorization, CSRF protection, TLS termination, and production monitoring.
