from __future__ import annotations

import json
import logging
import time
from uuid import uuid4

from flask import Flask, Response, g, jsonify, render_template, request
from prometheus_client import CONTENT_TYPE_LATEST, Counter, Gauge, Histogram, generate_latest
from sqlalchemy import create_engine, text
from werkzeug.middleware.proxy_fix import ProxyFix

from .config import Settings
from .models import metadata
from .security import SlidingWindowLimiter, authenticate, parse_api_keys, role_allows
from .service import ResourceService, ServiceError

HTTP_REQUESTS = Counter(
    "resource_control_http_requests_total",
    "HTTP requests handled by the service",
    ["method", "route", "status"],
)
HTTP_LATENCY = Histogram(
    "resource_control_http_request_duration_seconds",
    "HTTP request latency",
    ["method", "route"],
)
LEASE_OPERATIONS = Counter(
    "resource_control_lease_operations_total",
    "Lease lifecycle operations",
    ["operation", "result"],
)
ACTIVE_LEASES = Gauge("resource_control_active_leases", "Current active lease count")


def _payload() -> dict:
    if not request.is_json:
        raise ServiceError(415, "json_required", "request body must be application/json")
    value = request.get_json(silent=True)
    if not isinstance(value, dict):
        raise ServiceError(400, "invalid_json", "request body must be a JSON object")
    return value


def create_app(test_config: dict | None = None) -> Flask:
    settings = Settings.from_env()
    app = Flask(__name__, template_folder="../templates", static_folder="../static")
    app.config.update(
        DATABASE_URL=settings.database_url,
        RESOURCE_API_KEYS=settings.api_keys,
        DEFAULT_LEASE_TTL_SECONDS=settings.default_ttl_seconds,
        MAX_LEASE_TTL_SECONDS=settings.max_ttl_seconds,
        RATE_LIMIT_PER_MINUTE=settings.rate_limit_per_minute,
        MAX_CONTENT_LENGTH=settings.request_max_bytes,
        TRUSTED_PROXY_HOPS=settings.trusted_proxy_hops,
        TESTING=False,
        AUTO_CREATE_SCHEMA=False,
    )
    if test_config:
        app.config.update(test_config)

    if not logging.getLogger().handlers:
        logging.basicConfig(level=logging.INFO, format="%(message)s")

    if app.config["TRUSTED_PROXY_HOPS"] > 0:
        hops = app.config["TRUSTED_PROXY_HOPS"]
        app.wsgi_app = ProxyFix(app.wsgi_app, x_for=hops, x_proto=hops, x_host=hops)

    connect_args = {}
    if str(app.config["DATABASE_URL"]).startswith("sqlite"):
        connect_args["check_same_thread"] = False
    engine = create_engine(
        app.config["DATABASE_URL"],
        pool_pre_ping=True,
        connect_args=connect_args,
    )
    if app.config["AUTO_CREATE_SCHEMA"]:
        metadata.create_all(engine)

    actors = parse_api_keys(app.config["RESOURCE_API_KEYS"])
    if not actors and not app.config["TESTING"]:
        raise RuntimeError("RESOURCE_API_KEYS must configure at least one credential")

    limiter = SlidingWindowLimiter(app.config["RATE_LIMIT_PER_MINUTE"])
    service = ResourceService(
        engine,
        app.config["DEFAULT_LEASE_TTL_SECONDS"],
        app.config["MAX_LEASE_TTL_SECONDS"],
    )
    app.extensions["resource_engine"] = engine
    app.extensions["resource_service"] = service

    @app.before_request
    def before_request() -> Response | None:
        g.request_started = time.perf_counter()
        incoming = request.headers.get("X-Request-ID", "")
        g.request_id = incoming[:64] if incoming and incoming.isascii() else str(uuid4())

        if request.path.startswith("/api/") or request.path == "/metrics":
            actor = authenticate(request.headers.get("Authorization"), actors)
            if actor is None:
                return jsonify(
                    error={"code": "unauthorized", "message": "valid bearer token required"}
                ), 401
            g.actor = actor
            allowed, remaining = limiter.allow(actor.key_hash)
            g.rate_limit_remaining = remaining
            if not allowed:
                return jsonify(
                    error={"code": "rate_limited", "message": "request rate exceeded"}
                ), 429
        return None

    @app.after_request
    def after_request(response: Response) -> Response:
        response.headers["X-Request-ID"] = getattr(g, "request_id", str(uuid4()))
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("Referrer-Policy", "no-referrer")
        response.headers.setdefault("X-Frame-Options", "DENY")
        response.headers.setdefault(
            "Content-Security-Policy",
            "default-src 'self'; style-src 'self'; frame-ancestors 'none'; base-uri 'none'",
        )
        if hasattr(g, "rate_limit_remaining"):
            response.headers["X-RateLimit-Remaining"] = str(g.rate_limit_remaining)

        route = request.url_rule.rule if request.url_rule else "unmatched"
        HTTP_REQUESTS.labels(request.method, route, str(response.status_code)).inc()
        if hasattr(g, "request_started"):
            HTTP_LATENCY.labels(request.method, route).observe(
                time.perf_counter() - g.request_started
            )
        logging.getLogger("resource_control").info(
            json.dumps(
                {
                    "event": "http_request",
                    "request_id": response.headers["X-Request-ID"],
                    "method": request.method,
                    "route": route,
                    "status": response.status_code,
                    "actor": getattr(getattr(g, "actor", None), "name", None),
                },
                separators=(",", ":"),
            )
        )
        return response

    def require(required_role: str):
        actor = getattr(g, "actor", None)
        if actor is None or not role_allows(actor, required_role):
            raise ServiceError(403, "forbidden", f"{required_role} role required")
        return actor

    @app.errorhandler(ServiceError)
    def handle_service_error(error: ServiceError):
        return jsonify(error={"code": error.code, "message": error.message}), error.status

    @app.errorhandler(404)
    def not_found(_error):
        return jsonify(error={"code": "not_found", "message": "route not found"}), 404

    @app.errorhandler(405)
    def method_not_allowed(_error):
        return jsonify(error={"code": "method_not_allowed", "message": "method not allowed"}), 405

    @app.get("/")
    def index():
        return render_template("index.html")

    @app.get("/healthz")
    def healthz():
        return jsonify(status="ok")

    @app.get("/readyz")
    def readyz():
        try:
            with engine.connect() as conn:
                conn.execute(text("SELECT 1"))
            return jsonify(status="ready")
        except Exception:
            return jsonify(status="not_ready"), 503

    @app.get("/metrics")
    def metrics():
        require("reader")
        ACTIVE_LEASES.set(service.active_count())
        return Response(generate_latest(), mimetype=CONTENT_TYPE_LATEST)

    @app.get("/api/v1/resources")
    def list_resources():
        require("reader")
        return jsonify(items=service.list_resources())

    @app.get("/api/v1/resources/<resource_id>")
    def get_resource(resource_id: str):
        require("reader")
        return jsonify(service.get_resource(resource_id))

    @app.post("/api/v1/resources")
    def create_resource():
        actor = require("admin")
        body = _payload()
        resource = service.create_resource(
            str(body.get("id", "")),
            str(body.get("name", "")),
            str(body.get("kind", "")),
            body.get("metadata") if isinstance(body.get("metadata"), dict) else {},
            actor.name,
        )
        return jsonify(resource), 201

    @app.delete("/api/v1/resources/<resource_id>")
    def remove_resource(resource_id: str):
        actor = require("admin")
        service.remove_resource(resource_id, actor.name)
        return "", 204

    @app.post("/api/v1/resources/<resource_id>/leases")
    def acquire_lease(resource_id: str):
        actor = require("operator")
        body = _payload()
        try:
            lease, replayed = service.acquire(
                resource_id=resource_id,
                owner=str(body.get("owner", "")),
                purpose=str(body.get("purpose", "")),
                ttl_value=body.get("ttl_seconds"),
                actor=actor.name,
                idempotency_key=request.headers.get("Idempotency-Key"),
            )
        except ServiceError as error:
            if error.code == "resource_busy":
                LEASE_OPERATIONS.labels("acquire", "conflict").inc()
            raise
        LEASE_OPERATIONS.labels("acquire", "replay" if replayed else "success").inc()
        response = jsonify(lease)
        response.status_code = 200 if replayed else 201
        if replayed:
            response.headers["Idempotency-Replayed"] = "true"
        return response

    @app.get("/api/v1/leases")
    def list_leases():
        require("reader")
        return jsonify(
            items=service.list_leases(request.args.get("status"), request.args.get("owner"))
        )

    @app.post("/api/v1/leases/<lease_id>/renew")
    def renew_lease(lease_id: str):
        actor = require("operator")
        body = _payload()
        lease = service.renew(lease_id, body.get("ttl_seconds"), actor.name)
        LEASE_OPERATIONS.labels("renew", "success").inc()
        return jsonify(lease)

    @app.delete("/api/v1/leases/<lease_id>")
    def release_lease(lease_id: str):
        actor = require("operator")
        lease = service.release(lease_id, actor.name)
        LEASE_OPERATIONS.labels("release", "success").inc()
        return jsonify(lease)

    @app.get("/api/v1/audit")
    def audit():
        require("admin")
        try:
            limit = int(request.args.get("limit", "100"))
        except ValueError as exc:
            raise ServiceError(400, "invalid_limit", "limit must be an integer") from exc
        return jsonify(items=service.audit(limit))

    return app
