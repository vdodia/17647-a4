#!/usr/bin/env python3
"""
Book data sync: RDS (books table) -> MongoDB collection (upsert by ISBN).
Runs as a one-shot job (K8s CronJob invokes the container on a schedule).
"""
import logging
import os
import sys
from decimal import Decimal

import mysql.connector
from pymongo import MongoClient

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
logger = logging.getLogger("book-sync")


def row_to_doc(row: tuple) -> dict:
    """(ISBN, title, Author, description, genre, price, quantity, summary) -> Mongo document."""
    isbn, title, author, desc, genre, price, quantity, summary = row
    p = price
    if isinstance(p, Decimal):
        p = float(p)
    elif p is not None:
        p = float(p)
    else:
        p = 0.0
    doc: dict = {
        "ISBN": isbn,
        "title": title,
        "Author": author,
        "description": desc,
        "genre": genre,
        "price": p,
        "quantity": int(quantity) if quantity is not None else 0,
    }
    if summary is not None:
        doc["summary"] = summary
    return doc


def main() -> int:
    host = os.environ.get("DATABASE_HOST", "")
    port = int(os.environ.get("DATABASE_PORT", "3306"))
    user = os.environ.get("MYSQL_USER", "")
    password = os.environ.get("MYSQL_PASSWORD", "")
    db_name = os.environ.get("MYSQL_DATABASE", "books_db")
    mongo_uri = os.environ.get("MONGO_URI", "")
    mongo_db = os.environ.get("MONGO_DATABASE", "BooksDB")
    mongo_coll = os.environ.get("MONGO_COLLECTION", "books_vdodia")

    if not all([host, user, password, mongo_uri]):
        logger.error("Missing DATABASE_HOST, MYSQL_USER, MYSQL_PASSWORD, or MONGO_URI")
        return 1

    logger.info("Connecting to MySQL %s:%s / %s", host, port, db_name)
    mconn = mysql.connector.connect(
        host=host,
        port=port,
        user=user,
        password=password,
        database=db_name,
    )
    logger.info("Connecting to Mongo %s / %s.%s", "(uri hidden)", mongo_db, mongo_coll)
    mclient = MongoClient(mongo_uri, serverSelectionTimeoutMS=20000)
    collection = mclient[mongo_db][mongo_coll]

    try:
        cur = mconn.cursor()
        cur.execute(
            "SELECT ISBN, title, Author, description, genre, price, quantity, summary FROM books"
        )
        rows = cur.fetchall()
        cur.close()
    except Exception:
        logger.exception("Failed to read from RDS")
        mconn.close()
        mclient.close()
        return 1

    synced = 0
    errors = 0
    for row in rows:
        try:
            doc = row_to_doc(row)
            isbn = doc["ISBN"]
            collection.replace_one({"ISBN": isbn}, doc, upsert=True)
            synced += 1
        except Exception:
            logger.exception("Failed to upsert ISBN=%s", row[0] if row else "?")
            errors += 1

    mconn.close()
    mclient.close()
    logger.info("Sync complete: %d rows upserted, %d errors", synced, errors)
    return 0 if errors == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
