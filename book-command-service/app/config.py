"""
config.py – Load all configuration from environment variables.
"""
import os

DB_HOST = os.environ.get("DATABASE_HOST", "db")
DB_PORT = int(os.environ.get("DATABASE_PORT", 3306))
DB_USER = os.environ.get("MYSQL_USER", "bookuser")
DB_PASSWORD = os.environ.get("MYSQL_PASSWORD", "")
DB_NAME = os.environ.get("MYSQL_DATABASE", "books_db")

GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")
