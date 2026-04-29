"""
Book command service – POST /cmd/books, PUT /cmd/books/<ISBN>
"""
import logging
from flask import Blueprint, request, jsonify
import mysql.connector

from app.db import get_connection
from app.validation import validate_price, check_required_fields
from app.llm import trigger_summary

logger = logging.getLogger(__name__)

books_bp = Blueprint("books", __name__)

BOOK_FIELDS = ["ISBN", "title", "Author", "description", "genre", "price", "quantity"]


def _validate_book_payload(data: dict) -> str | None:
    missing = check_required_fields(data, BOOK_FIELDS)
    if missing:
        return f"Missing required fields: {', '.join(missing)}"
    if not validate_price(data["price"]):
        return "price must be a valid number with 0-2 decimal places"
    return None


@books_bp.post("/cmd/books")
def add_book():
    data = request.get_json(silent=True)
    if data is None:
        return jsonify({"message": "Request body must be valid JSON"}), 400

    error = _validate_book_payload(data)
    if error:
        return jsonify({"message": error}), 400

    isbn = data["ISBN"]
    title = data["title"]
    author = data["Author"]
    desc = data["description"]
    genre = data["genre"]
    price = data["price"]
    quantity = data["quantity"]

    try:
        with get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT INTO books (ISBN, title, Author, description, genre, price, quantity)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
                """,
                (isbn, title, author, desc, genre, price, quantity),
            )
            conn.commit()
            cursor.close()
    except mysql.connector.IntegrityError:
        return jsonify({"message": "This ISBN already exists in the system."}), 422
    except Exception:
        logger.exception("DB error on POST /cmd/books")
        return jsonify({"message": "Internal server error"}), 500

    trigger_summary(isbn, title, author)

    response_body = {
        "ISBN": isbn,
        "title": title,
        "Author": author,
        "description": desc,
        "genre": genre,
        "price": float(price),
        "quantity": quantity,
    }
    # Public BFF path (proxied to this service) — do not use /cmd in Location
    response = jsonify(response_body)
    response.status_code = 201
    response.headers["Location"] = f"/books/{isbn}"
    return response


@books_bp.put("/cmd/books/<string:isbn>")
def update_book(isbn: str):
    data = request.get_json(silent=True)
    if data is None:
        return jsonify({"message": "Request body must be valid JSON"}), 400

    error = _validate_book_payload(data)
    if error:
        return jsonify({"message": error}), 400

    if data["ISBN"] != isbn:
        return jsonify({"message": "ISBN mismatch between URL and payload"}), 400

    try:
        with get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT ISBN FROM books WHERE ISBN = %s", (isbn,))
            if cursor.fetchone() is None:
                cursor.close()
                return jsonify({"message": "ISBN not found"}), 404

            cursor.execute(
                """
                UPDATE books
                SET title=%s, Author=%s, description=%s, genre=%s, price=%s, quantity=%s
                WHERE ISBN=%s
                """,
                (
                    data["title"],
                    data["Author"],
                    data["description"],
                    data["genre"],
                    data["price"],
                    data["quantity"],
                    isbn,
                ),
            )
            conn.commit()
            cursor.close()
    except Exception:
        logger.exception("DB error on PUT /cmd/books/%s", isbn)
        return jsonify({"message": "Internal server error"}), 500

    response_body = {
        "ISBN": isbn,
        "title": data["title"],
        "Author": data["Author"],
        "description": data["description"],
        "genre": data["genre"],
        "price": float(data["price"]),
        "quantity": data["quantity"],
    }
    return jsonify(response_body), 200
