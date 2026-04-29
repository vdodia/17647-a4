import base64
import json
import logging
import os
import time

import requests
from flask import Flask, Response, jsonify, request

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def _book_service_url(path: str, method: str) -> str:
    """
    A4: book writes -> command service /cmd/...; reads -> query service.
    path: e.g. 'books', 'books/123', 'books/isbn/123', 'books/123/related-books'
    """
    cmd = os.environ.get("URL_BOOK_COMMAND_SERVICE", "").rstrip("/")
    qry = os.environ.get("URL_BOOK_QUERY_SERVICE", "").rstrip("/")
    legacy = os.environ.get("URL_BOOK_SERVICE", "").rstrip("/")
    if (not cmd or not qry) and legacy:
        return f"{legacy}/{path}" if path else legacy
    if not cmd or not qry:
        return "http://localhost:3000"
    if method == "POST" and path == "books":
        return f"{cmd}/cmd/books"
    if method == "PUT" and path.startswith("books/"):
        rest = path[len("books/") :]
        if "/" in rest or not rest:
            return f"{qry}/{path}"
        return f"{cmd}/cmd/books/{rest}"
    return f"{qry}/{path}" if path else qry


def _customer_url(path: str) -> str:
    base = os.environ.get("URL_CUSTOMER_SERVICE", "") or os.environ.get(
        "URL_BASE_BACKEND_SERVICES", ""
    )
    base = (base or "http://localhost:3000").rstrip("/")
    if not path:
        return base
    return f"{base}/{path}"


def _default_backend_url(path: str) -> str:
    base = (os.environ.get("URL_BASE_BACKEND_SERVICES") or "http://localhost:3000").rstrip(
        "/"
    )
    if not path:
        return base
    return f"{base}/{path}"


def _resolve_upstream_url(path: str, method: str) -> str:
    if path.startswith("customers"):
        return _customer_url(path)
    if path == "books" or path.startswith("books"):
        return _book_service_url(path, method)
    return _default_backend_url(path)


def create_app() -> Flask:
    app = Flask(__name__)

    def validate_jwt(auth_header):
        if not auth_header or not auth_header.startswith("Bearer "):
            return False, "Missing or invalid Authorization header"
        token = auth_header.split(" ")[1]
        try:
            parts = token.split(".")
            if len(parts) != 3:
                return False, "Invalid JWT format"
            payload_b64 = parts[1]
            payload_b64 += "=" * ((4 - len(payload_b64) % 4) % 4)
            payload_json = base64.urlsafe_b64decode(payload_b64).decode("utf-8")
            payload = json.loads(payload_json)
            if payload.get("sub") not in [
                "starlord",
                "gamora",
                "drax",
                "rocket",
                "groot",
            ]:
                return False, "Invalid sub"
            exp = payload.get("exp")
            if not exp or int(time.time()) >= int(exp):
                return False, "Token expired"
            if payload.get("iss") != "cmu.edu":
                return False, "Invalid iss"
            return True, None
        except Exception as e:  # noqa: BLE001
            return False, str(e)

    @app.get("/status")
    def status():
        return {"status": "ok", "service": "web-bff"}, 200

    @app.route("/", defaults={"path": ""}, methods=["GET", "POST", "PUT", "DELETE", "PATCH"])
    @app.route("/<path:path>", methods=["GET", "POST", "PUT", "DELETE", "PATCH"])
    def proxy(path: str):
        if not request.headers.get("X-Client-Type"):
            return jsonify({"error": "Missing X-Client-Type header"}), 400
        ok, err = validate_jwt(request.headers.get("Authorization"))
        if not ok:
            return jsonify({"error": err}), 401

        route_path = path
        if not route_path and request.path not in ("/", ""):
            route_path = request.path.lstrip("/")

        url = _resolve_upstream_url(route_path, request.method)

        headers = {k: v for k, v in request.headers if k.lower() != "host"}
        try:
            resp = requests.request(
                method=request.method,
                url=url,
                headers=headers,
                data=request.get_data(),
                params=request.args,
                allow_redirects=False,
                timeout=30,
            )
        except requests.exceptions.RequestException as e:
            logger.error("Error proxying request: %s", e)
            return jsonify({"error": "Backend service unavailable"}), 502

        excluded = ["content-encoding", "content-length", "transfer-encoding", "connection"]
        h = [(k, v) for k, v in resp.headers.items() if k.lower() not in excluded]
        return Response(resp.content, resp.status_code, h)

    return app


app = create_app()

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=80)
