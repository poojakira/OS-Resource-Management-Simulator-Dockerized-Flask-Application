# Coursework Provenance

## Source material

This repository is based on two original Fall 2024 coursework submissions:

1. **Module 8: Lab 1 - Creating a Web Interface for Simulating OS Resource Management**
2. **Module 8: Lab 2 - Virtualization - Docker**

The submitted reports identify the course as **IFT 510: Principles of Computer & Information Technology Architecture (2024 Fall C)** and are dated **December 1, 2024**. The source-file headers are dated **November 30, 2024**.

The original implementation used Flask and Jinja2 to represent four kitchen tools as shared resources with `Available` / `Occupied` states. Lab 2 copied the same application into a basic Docker image.

## What is original to the 2024 coursework

The following concepts are directly supported by the original submissions:

- Flask web application
- Jinja2-rendered resource list
- four simulated resources: Stove, Oven, Mixer, Knife
- in-memory resource state
- resource request/allocation behavior
- `Available` and `Occupied` states
- Dockerfile-based containerization
- local service on port 8000

The maintained repository does **not** claim that the 2024 lab implemented a real OS scheduler, distributed resource manager, production locking system, authentication layer, or durable storage.

## Public-repository modernization

The public repository was cleaned and modernized in 2026. These changes are maintenance improvements, not claims about what was present in the original lab:

- removed student identifiers from published source
- removed bundled virtual environments and bytecode
- changed state mutation from GET to POST
- added release and reset operations
- added explicit 404 behavior for unknown resources
- added an in-process lock for thread-safe state updates
- disabled Flask debug mode
- added a liveness endpoint
- added security response headers
- pinned dependencies
- moved the container to Python 3.12
- added a non-root container user and health check
- added tests, linting, Bandit, pip-audit, and Docker build verification in CI

## Evidence boundary

The coursework reports contain explanatory prose that occasionally describes operating-system concepts more broadly than the code implements. This repository treats the code as an **educational simulation** and does not repeat unsupported claims such as deadlock prevention, fairness guarantees, distributed locking, or production-scale resource coordination.

The original reports also described `127.0.0.1:8000` as reachable from other devices on the network. That address is loopback-only. A service bound to `0.0.0.0` may be reachable through the host's actual network address if local firewall/network policy permits it.
