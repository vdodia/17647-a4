"""Config from environment – no RDS; Mongo + recommendation URL only."""
import os

MONGO_URI = os.environ.get("MONGO_URI", "")
MONGO_DATABASE = os.environ.get("MONGO_DATABASE", "BooksDB")
MONGO_COLLECTION = os.environ.get("MONGO_COLLECTION", "books_vdodia")

RECOMMENDATION_SERVICE_URL = os.environ.get(
    "RECOMMENDATION_SERVICE_URL", "http://54.221.160.63"
)
