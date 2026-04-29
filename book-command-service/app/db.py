"""
db.py – MySQL connection pool using mysql-connector-python.
"""
import mysql.connector
from mysql.connector import pooling
from contextlib import contextmanager
from app import config

import os
import time
import logging

logger = logging.getLogger(__name__)

_pool = None

def init_db():
    global _pool
    if _pool is not None:
        return

    max_retries = 30
    conn = None
    for attempt in range(max_retries):
        try:
            conn = mysql.connector.connect(
                host=config.DB_HOST,
                port=config.DB_PORT,
                user=config.DB_USER,
                password=config.DB_PASSWORD,
            )
            break
        except mysql.connector.Error as err:
            if attempt < max_retries - 1:
                logger.info(
                    "Waiting for database to be ready (attempt %s/%s): %s",
                    attempt + 1,
                    max_retries,
                    err,
                )
                time.sleep(5)
            else:
                raise

    cursor = conn.cursor()
    cursor.execute("SELECT GET_LOCK('bookstore_init', 30)")
    cursor.fetchone()

    try:
        cursor.execute(f"CREATE DATABASE IF NOT EXISTS {config.DB_NAME}")
        cursor.execute(f"USE {config.DB_NAME}")

        # __file__ = /app/app/db.py -> two dirnames -> /app (project root in container)
        init_file_path = os.path.join(
            os.path.dirname(os.path.dirname(__file__)), "sql", "init.sql"
        )
        if os.path.exists(init_file_path):
            with open(init_file_path, "r", encoding="utf-8") as f:
                sql_script = f.read()
                statements = [s.strip() for s in sql_script.split(";") if s.strip()]
                for stmt in statements:
                    cursor.execute(stmt)
                    if cursor.with_rows:
                        cursor.fetchall()
            conn.commit()
    finally:
        try:
            cursor.fetchall()
        except Exception:
            pass
        cursor.execute("SELECT RELEASE_LOCK('bookstore_init')")
        cursor.fetchone()
        conn.close()

    _pool = pooling.MySQLConnectionPool(
        pool_name="bookstore_cmd_pool",
        pool_size=10,
        host=config.DB_HOST,
        port=config.DB_PORT,
        user=config.DB_USER,
        password=config.DB_PASSWORD,
        database=config.DB_NAME,
    )


@contextmanager
def get_connection():
    if _pool is None:
        init_db()
    conn = _pool.get_connection()
    try:
        yield conn
    finally:
        conn.close()
