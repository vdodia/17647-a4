"""
db.py – MySQL connection pool using mysql-connector-python.
Provides get_connection() as a context manager for safe auto-close.
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

    # 1. Connect without DB selected to ensure the DB itself exists
    # Wait for DB to be accessible (retry loop for AWS Aurora initial availability)
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
                logger.info(f"Waiting for database to be ready (attempt {attempt + 1}/{max_retries}): {err}")
                time.sleep(5)
            else:
                raise

    cursor = conn.cursor()
    
    # Acquire a named lock to prevent concurrent initialization race conditions
    cursor.execute("SELECT GET_LOCK('bookstore_init', 30)")
    cursor.fetchone()  # Consume the lock result
    
    try:
        cursor.execute(f"CREATE DATABASE IF NOT EXISTS {config.DB_NAME}")
        cursor.execute(f"USE {config.DB_NAME}")
        
        # Apply schema definition within the lock
        init_file_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "sql", "init.sql")
        if os.path.exists(init_file_path):
            with open(init_file_path, 'r') as f:
                sql_script = f.read()
                statements = [s.strip() for s in sql_script.split(';') if s.strip()]
                for stmt in statements:
                    cursor.execute(stmt)
                    if cursor.with_rows:
                        cursor.fetchall()
            conn.commit()
    finally:
        # Clear any remaining results
        try:
            cursor.fetchall()
        except:
            pass
        cursor.execute("SELECT RELEASE_LOCK('bookstore_init')")
        cursor.fetchone()
        conn.close()

    # 2. Setup the global pool
    _pool = pooling.MySQLConnectionPool(
        pool_name="bookstore_pool",
        pool_size=10,
        host=config.DB_HOST,
        port=config.DB_PORT,
        user=config.DB_USER,
        password=config.DB_PASSWORD,
        database=config.DB_NAME,
    )



@contextmanager
def get_connection():
    """Yield a pooled DB connection; auto-returns it to the pool on exit."""
    if _pool is None:
        init_db()
    conn = _pool.get_connection()
    try:
        yield conn
    finally:
        conn.close()
