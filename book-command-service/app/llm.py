"""
llm.py – Gemini summary stored in RDS books table.
"""
import logging
import google.generativeai as genai
from app import config

logger = logging.getLogger(__name__)


def fetch_and_store_summary(isbn: str, title: str, author: str) -> None:
    try:
        if not config.GEMINI_API_KEY:
            logger.warning("GEMINI_API_KEY not set; skipping LLM for ISBN=%s", isbn)
            return

        genai.configure(api_key=config.GEMINI_API_KEY)
        model = genai.GenerativeModel("gemini-2.5-flash-lite")
        prompt = (
            f"Write a 500-word summary of the book titled '{title}' by {author}. "
            "Include key themes, target audience, and why it is significant."
        )
        response = model.generate_content(prompt)
        summary = response.text

        from app.db import get_connection

        with get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "UPDATE books SET summary = %s WHERE ISBN = %s",
                (summary, isbn),
            )
            conn.commit()
            cursor.close()
        logger.info("Summary stored for ISBN=%s", isbn)

    except Exception:
        logger.exception("LLM summary fetch failed for ISBN=%s", isbn)


def trigger_summary(isbn: str, title: str, author: str) -> None:
    fetch_and_store_summary(isbn, title, author)
