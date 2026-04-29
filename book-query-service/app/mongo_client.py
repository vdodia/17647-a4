"""Lazy MongoDB client (pymongo)."""

from pymongo import MongoClient
from pymongo.database import Database
from pymongo.collection import Collection

from app import config

_client: MongoClient | None = None
_db: Database | None = None
_collection: Collection | None = None


def get_collection() -> Collection:
    global _client, _db, _collection
    if not config.MONGO_URI:
        raise RuntimeError("MONGO_URI is not set")
    if _collection is not None:
        return _collection
    _client = MongoClient(config.MONGO_URI, serverSelectionTimeoutMS=10000)
    _db = _client[config.MONGO_DATABASE]
    _collection = _db[config.MONGO_COLLECTION]
    return _collection


def doc_to_book_dict(doc: dict) -> dict:
    """Map Mongo document to API shape (same keys as A3 JSON)."""
    if not doc:
        return {}
    out = {
        "ISBN": doc.get("ISBN"),
        "title": doc.get("title"),
        "Author": doc.get("Author"),
        "description": doc.get("description"),
        "genre": doc.get("genre"),
        "price": float(doc["price"]) if doc.get("price") is not None else None,
        "quantity": doc.get("quantity"),
    }
    if "summary" in doc and doc["summary"] is not None:
        out["summary"] = doc["summary"]
    return out
