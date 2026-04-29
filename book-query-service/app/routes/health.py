from flask import Blueprint, Response

health_bp = Blueprint("health", __name__)


@health_bp.get("/status")
def status():
    return Response("OK", status=200, mimetype="text/plain")
