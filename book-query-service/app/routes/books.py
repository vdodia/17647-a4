"""
Book query – reads from MongoDB; related-books from external service.
GET /books?keyword=, GET /books/isbn/<ISBN>, GET /books/<ISBN>, GET /books/<ISBN>/related-books
"""
import logging
import re
import requests as http_requests
from flask import Blueprint, request, jsonify, Response

from app.circuit_breaker import recommendation_cb
from app.mongo_client import get_collection, doc_to_book_dict
from app import config

logger = logging.getLogger(__name__)

books_bp = Blueprint("books", __name__)

KEYWORD_RE = re.compile(r"^[A-Za-z]+$")


def _get_book_by_isbn(isbn: str):
    try:
        coll = get_collection()
        doc = coll.find_one({"ISBN": isbn})
    except Exception:
        logger.exception("Mongo error on GET book by ISBN %s", isbn)
        return jsonify({"message": "Internal server error"}), 500

    if doc is None:
        return jsonify({"message": "ISBN not found"}), 404

    return jsonify(doc_to_book_dict(doc)), 200


@books_bp.get("/books")
def search_books_by_keyword():
    """
    GET /books?keyword={single word}
    200 + array if any match; 204 empty body if none; 400 invalid keyword.
    """
    raw = request.args.get("keyword")
    if raw is None:
        return jsonify({"message": "query parameter 'keyword' is required"}), 400
    if not KEYWORD_RE.match(raw):
        return jsonify({"message": "keyword must be a single word (letters a-z and A-Z only)"}), 400

    try:
        coll = get_collection()
    except Exception:
        logger.exception("Mongo connection failed for keyword search")
        return jsonify({"message": "Internal server error"}), 500

    try:
        pat = re.compile(re.escape(raw), re.IGNORECASE)
        query = {
            "$or": [
                {"title": pat},
                {"Author": pat},
                {"description": pat},
                {"genre": pat},
                {"summary": pat},
            ]
        }
        results = [doc_to_book_dict(d) for d in coll.find(query)]
    except Exception:
        logger.exception("Mongo query failed for keyword=%s", raw)
        return jsonify({"message": "Internal server error"}), 500

    if not results:
        return Response(status=204)

    return jsonify(results), 200


@books_bp.get("/books/isbn/<string:isbn>")
def get_book_by_isbn_path(isbn: str):
    return _get_book_by_isbn(isbn)


@books_bp.get("/books/<string:isbn>/related-books")
def get_related_books(isbn: str):
    was_half_open = recommendation_cb.state == "half_open"

    if not recommendation_cb.allow_request():
        return "", 503

    try:
        url = f"{config.RECOMMENDATION_SERVICE_URL}/recommended-titles/isbn/{isbn}"
        resp = http_requests.get(url, timeout=3)
    except (
        http_requests.exceptions.Timeout,
        http_requests.exceptions.ConnectionError,
    ):
        recommendation_cb.record_failure()
        if was_half_open:
            return "", 503
        return "", 504

    recommendation_cb.record_success()

    if resp.status_code == 204 or not resp.content:
        return "", 204

    raw = resp.json()
    result = [
        {
            "ISBN": item.get("isbn", ""),
            "title": item.get("title", ""),
            "Author": item.get("authors", ""),
        }
        for item in raw
    ]
    return jsonify(result), 200


@books_bp.get("/books/<string:isbn>")
def get_book(isbn: str):
    return _get_book_by_isbn(isbn)
