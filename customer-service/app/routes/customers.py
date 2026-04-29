"""
routes/customers.py – Customer endpoints.

Endpoints:
    POST /customers
    GET  /customers/<id>        (numeric ID)
    GET  /customers?userId=...  (email / userId)
"""
import logging
from flask import Blueprint, request, jsonify
import mysql.connector

from app.db import get_connection
from app.validation import validate_email, validate_state, check_required_fields
from app.kafka_producer import publish_customer_event

logger = logging.getLogger(__name__)

customers_bp = Blueprint("customers", __name__)

# address2 is intentionally excluded — it is optional
REQUIRED_CUSTOMER_FIELDS = ["userId", "name", "phone", "address", "city", "state", "zipcode"]


def _row_to_dict(row: tuple) -> dict:
    """Convert a DB row (id, userId, name, phone, address, address2, city, state, zipcode) to dict."""
    return {
        "id":       row[0],
        "userId":   row[1],
        "name":     row[2],
        "phone":    row[3],
        "address":  row[4],
        "address2": row[5],
        "city":     row[6],
        "state":    row[7],
        "zipcode":  row[8],
    }


def _validate_customer_payload(data: dict) -> str | None:
    """Return error message string if invalid, else None."""
    missing = check_required_fields(data, REQUIRED_CUSTOMER_FIELDS)
    if missing:
        return f"Missing required fields: {', '.join(missing)}"
    if not validate_email(data["userId"]):
        return "userId must be a valid email address"
    if not validate_state(data["state"]):
        return "state must be a valid 2-letter US state abbreviation"
    return None


# ---------------------------------------------------------------------------
# POST /customers
# ---------------------------------------------------------------------------
@customers_bp.post("/customers")
def add_customer():
    data = request.get_json(silent=True)
    if data is None:
        return jsonify({"message": "Request body must be valid JSON"}), 400

    error = _validate_customer_payload(data)
    if error:
        return jsonify({"message": error}), 400

    try:
        with get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT INTO customers (userId, name, phone, address, address2, city, state, zipcode)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                """,
                (
                    data["userId"],
                    data["name"],
                    data["phone"],
                    data["address"],
                    data.get("address2"),   # optional field
                    data["city"],
                    data["state"],
                    data["zipcode"],
                ),
            )
            conn.commit()
            new_id = cursor.lastrowid
            cursor.close()
    except mysql.connector.IntegrityError:
        return jsonify({"message": "This user ID already exists in the system."}), 422
    except Exception:
        logger.exception("DB error on POST /customers")
        return jsonify({"message": "Internal server error"}), 500

    response_body = {
        "id":       new_id,
        "userId":   data["userId"],
        "name":     data["name"],
        "phone":    data["phone"],
        "address":  data["address"],
        "address2": data.get("address2"),
        "city":     data["city"],
        "state":    data["state"],
        "zipcode":  data["zipcode"],
    }

    try:
        publish_customer_event(response_body)
    except Exception:  # noqa: BLE001
        logger.exception("Kafka publish failed after customer insert; response still 201")
    location = request.host_url.rstrip("/") + f"/customers/{new_id}"
    response = jsonify(response_body)
    response.status_code = 201
    response.headers["Location"] = location
    return response


# ---------------------------------------------------------------------------
# GET /customers/<id>  (numeric)
# ---------------------------------------------------------------------------
@customers_bp.get("/customers/<string:customer_id>")
def get_customer_by_id(customer_id: str):
    if not customer_id.isdigit():
        return jsonify({"message": "Customer ID must be a numeric value"}), 400

    try:
        with get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT id, userId, name, phone, address, address2, city, state, zipcode "
                "FROM customers WHERE id = %s",
                (int(customer_id),),
            )
            row = cursor.fetchone()
            cursor.close()
    except Exception:
        logger.exception("DB error on GET /customers/%s", customer_id)
        return jsonify({"message": "Internal server error"}), 500

    if row is None:
        return jsonify({"message": "Customer not found"}), 404

    return jsonify(_row_to_dict(row)), 200


# ---------------------------------------------------------------------------
# GET /customers?userId=<email>
# ---------------------------------------------------------------------------
@customers_bp.get("/customers")
def get_customer_by_user_id():
    user_id = request.args.get("userId", "").strip()
    if not user_id:
        return jsonify({"message": "userId query parameter is required"}), 400
    if not validate_email(user_id):
        return jsonify({"message": "userId must be a valid email address"}), 400

    try:
        with get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT id, userId, name, phone, address, address2, city, state, zipcode "
                "FROM customers WHERE userId = %s",
                (user_id,),
            )
            row = cursor.fetchone()
            cursor.close()
    except Exception:
        logger.exception("DB error on GET /customers?userId=%s", user_id)
        return jsonify({"message": "Internal server error"}), 500

    if row is None:
        return jsonify({"message": "Customer not found"}), 404

    return jsonify(_row_to_dict(row)), 200
