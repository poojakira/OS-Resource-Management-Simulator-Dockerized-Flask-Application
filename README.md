# OS Resource Management Simulator & Dockerized Flask Application

A small Flask application that demonstrates operating-system resource allocation concepts through a kitchen-tool metaphor. The original coursework was completed for **IFT 510: Principles of Computer & Information Technology Architecture, Fall 2024**. Lab 1 implemented the Flask/Jinja2 resource-allocation interface; Lab 2 containerized the application with Docker.

> **Coursework date:** Nov. 30-Dec. 1, 2024  
> **Public repository:** published and cleaned for portfolio use in 2026  
> **Scope:** educational systems/web-development project, not a production resource scheduler

## What the simulator does

The application tracks four shared resources:

- Stove
- Oven
- Mixer
- Knife

Each resource is either **Available** or **Occupied**. Users can allocate an available resource, release an occupied resource, or reset the simulator. The interface is rendered with Jinja2 and the state is managed by Flask.

This mirrors the basic idea of an operating system coordinating access to shared resources, but it is intentionally a simplified teaching model. It does not implement real CPU scheduling, deadlock detection, persistence, distributed locking, or kernel-level resource management.

## 2024 coursework vs. maintained public version

The original Fall 2024 submission used:

- Flask
- Jinja2
- an in-memory Python dictionary for resource state
- GET requests that changed resource state
- Flask debug mode
- a basic Python 3.9 Docker image

The maintained public version preserves the assignment concept while correcting issues that should not remain in a public repository:

- state-changing actions use **POST**
- resources can be both allocated and released
- unknown resources return **404**
- in-process state changes are protected with a lock
- Flask debug mode is disabled
- a health endpoint is provided
- basic security headers are added
- Docker runs as a non-root user
- dependencies are pinned
- virtual environments and local environment files are ignored
- automated tests, linting, dependency auditing, and a Docker build check run in GitHub Actions
- student identifiers and bundled virtual environments from the original submission are not published in the maintained source tree

See [docs/COURSEWORK_PROVENANCE.md](docs/COURSEWORK_PROVENANCE.md) for the evidence boundary and modernization notes.

## Architecture

```text
Browser
   |
   v
Flask / Jinja2
   |
   +--> GET  /                         render current state
   +--> POST /resource/<name>/allocate
   +--> POST /resource/<name>/release
   +--> POST /reset
   +--> GET  /health
   |
   v
In-memory resource state
(single Gunicorn worker, thread-safe updates)
```

## Run locally

### Python

```bash
python -m venv .venv
source .venv/bin/activate
# Windows PowerShell: .\.venv\Scripts\Activate.ps1

python -m pip install --upgrade pip
python -m pip install -r requirements.txt
python app.py
```

Open:

```text
http://127.0.0.1:8000
```

The development entry point binds to `127.0.0.1:8000` with debug mode disabled. The Docker image uses Gunicorn inside the container and should be published only to the interface you intend. This project has no authentication and is not intended as an Internet-facing service.

### Docker

```bash
docker build -t os-resource-simulator .
docker run --rm -p 127.0.0.1:8000:8000 os-resource-simulator
```

Then open `http://127.0.0.1:8000`.

The container uses one Gunicorn worker because the simulator intentionally keeps state in process memory. Multiple workers would each maintain separate state.

## Test and verify

```bash
python -m pip install -r requirements-dev.txt
python -m ruff check .
python -m pytest
python -m bandit -q -r app.py
python -m pip_audit -r requirements.txt
docker build -t os-resource-simulator .
```

GitHub Actions runs the same quality/security checks on public repository changes.

## Security and limitations

This project is intentionally small, but the maintained version avoids several unsafe defaults from the classroom prototype:

- no Flask debug server in the container
- no state mutation through GET requests
- no arbitrary resource names
- non-root container user
- pinned runtime dependencies
- response headers that restrict framing, MIME sniffing, referrer leakage, and off-origin content loading
- no committed `.env`, virtual environment, credentials, or student identifier

Remaining limitations:

- state is in memory and resets when the process restarts
- one process owns the authoritative state
- there is no authentication or authorization
- the lock protects threads in one process only
- the project is an educational simulation, not a production scheduler or inventory platform

## Resume-safe description

**OS Resource Management Simulator & Dockerized Flask Application | Python, Flask, Jinja2, Docker | Dec. 2024**

Built a Flask/Jinja2 educational simulator for shared-resource allocation and containerized it with Docker, demonstrating resource-state management, request handling, and portable application deployment.

## Repository structure

```text
.
├── .github/workflows/ci.yml
├── docs/COURSEWORK_PROVENANCE.md
├── static/style.css
├── templates/index.html
├── tests/test_app.py
├── app.py
├── Dockerfile
├── requirements.txt
├── requirements-dev.txt
├── pyproject.toml
└── SECURITY.md
```

## License

MIT. See [LICENSE](LICENSE).
