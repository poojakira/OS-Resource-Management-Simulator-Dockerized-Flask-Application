from __future__ import annotations

from threading import Lock

from flask import Flask, abort, jsonify, redirect, render_template, url_for

RESOURCE_NAMES = ("Stove", "Oven", "Mixer", "Knife")


def create_app() -> Flask:
    app = Flask(__name__)
    app.config["MAX_CONTENT_LENGTH"] = 16 * 1024
    app.config["RESOURCE_STATE"] = {name: "Available" for name in RESOURCE_NAMES}
    app.config["RESOURCE_LOCK"] = Lock()

    @app.after_request
    def add_security_headers(response):
        response.headers.setdefault(
            "Content-Security-Policy",
            "default-src 'self'; style-src 'self'; "
            "form-action 'self'; frame-ancestors 'none'; base-uri 'self'",
        )
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("Referrer-Policy", "no-referrer")
        return response

    @app.get("/")
    def index():
        return render_template("index.html", resources=app.config["RESOURCE_STATE"])

    @app.get("/health")
    def health():
        return jsonify(status="ok"), 200

    @app.post("/resource/<tool>/allocate")
    def allocate_resource(tool: str):
        if tool not in RESOURCE_NAMES:
            abort(404)

        with app.config["RESOURCE_LOCK"]:
            app.config["RESOURCE_STATE"][tool] = "Occupied"

        return redirect(url_for("index"), code=303)

    @app.post("/resource/<tool>/release")
    def release_resource(tool: str):
        if tool not in RESOURCE_NAMES:
            abort(404)

        with app.config["RESOURCE_LOCK"]:
            app.config["RESOURCE_STATE"][tool] = "Available"

        return redirect(url_for("index"), code=303)

    @app.post("/reset")
    def reset_resources():
        with app.config["RESOURCE_LOCK"]:
            app.config["RESOURCE_STATE"].update(
                {name: "Available" for name in RESOURCE_NAMES}
            )

        return redirect(url_for("index"), code=303)

    return app


app = create_app()

if __name__ == "__main__":
    app.run(host="127.0.0.1", port=8000, debug=False)
