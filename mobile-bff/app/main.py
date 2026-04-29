import base64
import json
import logging
import os
import re
import time

import requests
from flask import Flask, Response, jsonify, request

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def _book_read_url(path: str) -> str:
    qry = os.environ.get("URL_BOOK_QUERY_SERVICE", "").rstrip("/")
    legacy = os.environ.get("URL_BOOK_SERVICE", "").rstrip("/")
    if not qry and legacy:
        return f"{legacy}/{path}" if path else legacy
    if not qry:
        return "http://localhost:3000"
    return f"{qry}/{path}" if path else qry


def _book_command_url(path: str) -> str:
    cmd = os.environ.get("URL_BOOK_COMMAND_SERVICE", "").rstrip("/")
    if not cmd:
        return "http://localhost:3000"
    return f"{cmd}/{path}" if path else cmd


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
    if path.startswith("cmd/"):
        return _book_command_url(path)
    if path == "books" or path.startswith("books"):
        return _book_read_url(path)
    return _default_backend_url(path)


def _forbidden_legacy_book_write(path: str, method: str) -> tuple[bool, str]:
    if method == "POST" and path == "books":
        return True, "Book creation must use POST /cmd/books"
    if method == "PUT" and re.match(r"^books/[^/]+$", path or ""):
        return True, "Book updates must use PUT /cmd/books/{ISBN}"
    return False, ""


def _apply_nonfiction_to_book_payload(data) -> None:
    if isinstance(data, dict) and data.get("genre") == "non-fiction":
        data["genre"] = 3
    elif isinstance(data, list):
        for b in data:
            if isinstance(b, dict) and b.get("genre") == "non-fiction":
                b["genre"] = 3


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
        return {"status": "ok", "service": "mobile-bff"}, 200

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

        block, msg = _forbidden_legacy_book_write(route_path, request.method)
        if block:
            return jsonify({"message": msg}), 405

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

        content = resp.content
        if request.method == "GET" and resp.status_code == 200:
            p = request.path
            if p == "/books" and "keyword" in request.args:
                try:
                    data = json.loads(content.decode("utf-8"))
                    _apply_nonfiction_to_book_payload(data)
                    content = json.dumps(data).encode("utf-8")
                except (ValueError, OSError, UnicodeError):
                    pass
            if p.startswith("/books/isbn/") or (p.startswith("/books/") and p != "/books"):
                if "/related-books" not in p and "keyword" not in (request.args or {}):
                    try:
                        data = json.loads(content.decode("utf-8"))
                        _apply_nonfiction_to_book_payload(data)
                        content = json.dumps(data).encode("utf-8")
                    except (ValueError, OSError, UnicodeError):
                        pass
            if p.startswith("/customers"):
                try:
                    data = json.loads(content.decode("utf-8"))
                    keys = ["address", "address2", "city", "state", "zipcode"]
                    if isinstance(data, list):
                        for c in data:
                            for k in keys:
                                c.pop(k, None)
                    elif isinstance(data, dict):
                        for k in keys:
                            data.pop(k, None)
                    content = json.dumps(data).encode("utf-8")
                except (ValueError, OSError, UnicodeError):
                    pass

        excluded = ["content-encoding", "content-length", "transfer-encoding", "connection"]
        h = [(k, v) for k, v in resp.headers.items() if k.lower() not in excluded]
        return Response(content, resp.status_code, h)

    return app


app = create_app()

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=80)
