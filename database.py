import os
import sqlite3
from datetime import datetime

from huffman import format_symbol


DB_PATH = os.path.join(os.path.dirname(__file__), "history", "huffman.db")


def get_connection():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def _ensure_column(cursor: sqlite3.Cursor, table: str, column: str, definition: str):
    cursor.execute(f"PRAGMA table_info({table})")
    columns = {row["name"] for row in cursor.fetchall()}
    if column not in columns:
        cursor.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")


def init_db():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = get_connection()
    cursor = conn.cursor()

    cursor.executescript("""
        CREATE TABLE IF NOT EXISTS compression_history (
            id                    INTEGER PRIMARY KEY AUTOINCREMENT,
            original_filename     TEXT NOT NULL,
            compressed_filename   TEXT NOT NULL,
            file_type             TEXT NOT NULL DEFAULT 'text',
            quality_level         TEXT,
            original_size         INTEGER NOT NULL,
            compressed_size       INTEGER NOT NULL,
            space_saved_percent   REAL NOT NULL,
            total_chars           INTEGER NOT NULL,
            total_bits            INTEGER NOT NULL,
            compression_ratio     REAL NOT NULL,
            pdf_page_count        INTEGER,
            pdf_image_count       INTEGER,
            pdf_dpi_used          INTEGER,
            docx_paragraph_count  INTEGER,
            docx_image_count      INTEGER,
            docx_table_count      INTEGER,
            created_at            TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS huffman_codes (
            id            INTEGER PRIMARY KEY AUTOINCREMENT,
            history_id    INTEGER NOT NULL,
            character     TEXT NOT NULL,
            frequency     INTEGER NOT NULL,
            binary_code   TEXT NOT NULL,
            code_length   INTEGER NOT NULL,
            FOREIGN KEY (history_id) REFERENCES compression_history(id)
                ON DELETE CASCADE
        );

        CREATE INDEX IF NOT EXISTS idx_history_created
            ON compression_history(created_at DESC);

        CREATE INDEX IF NOT EXISTS idx_history_filetype
            ON compression_history(file_type);

        CREATE INDEX IF NOT EXISTS idx_codes_history
            ON huffman_codes(history_id);
    """)

    _ensure_column(cursor, "compression_history", "quality_level", "TEXT")

    conn.commit()
    conn.close()


def insert_compression_record(data: dict) -> int:
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO compression_history
        (original_filename, compressed_filename, file_type, quality_level,
         original_size, compressed_size, space_saved_percent,
         total_chars, total_bits, compression_ratio,
         pdf_page_count, pdf_image_count, pdf_dpi_used,
         docx_paragraph_count, docx_image_count, docx_table_count,
         created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        data["original_filename"],
        data["compressed_filename"],
        data.get("file_type", "text"),
        data.get("quality_level"),
        data["original_size"],
        data["compressed_size"],
        data["space_saved_percent"],
        data["total_chars"],
        data["total_bits"],
        data["compression_ratio"],
        data.get("pdf_page_count"),
        data.get("pdf_image_count"),
        data.get("pdf_dpi_used"),
        data.get("docx_paragraph_count"),
        data.get("docx_image_count"),
        data.get("docx_table_count"),
        datetime.utcnow().isoformat(timespec="seconds"),
    ))
    history_id = cursor.lastrowid
    conn.commit()
    conn.close()
    return history_id


def insert_huffman_codes(history_id: int, codes: dict, freq_table: dict):
    if not codes:
        return

    conn = get_connection()
    cursor = conn.cursor()
    rows = []
    for symbol, code in codes.items():
        if isinstance(symbol, int):
            display = format_symbol(symbol)
        else:
            display = str(symbol)
        rows.append((history_id, display, int(freq_table.get(symbol, 0)), code, len(code)))

    cursor.executemany("""
        INSERT INTO huffman_codes
        (history_id, character, frequency, binary_code, code_length)
        VALUES (?, ?, ?, ?, ?)
    """, rows)
    conn.commit()
    conn.close()


def get_all_history(limit: int = 100, file_type: str | None = None) -> list[dict]:
    conn = get_connection()
    cursor = conn.cursor()
    if file_type:
        cursor.execute("""
            SELECT * FROM compression_history
            WHERE file_type = ?
            ORDER BY created_at DESC
            LIMIT ?
        """, (file_type, limit))
    else:
        cursor.execute("""
            SELECT * FROM compression_history
            ORDER BY created_at DESC
            LIMIT ?
        """, (limit,))
    rows = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return rows


def get_codes_for_job(history_id: int) -> list[dict]:
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT character, frequency, binary_code, code_length
        FROM huffman_codes
        WHERE history_id = ?
        ORDER BY frequency DESC, character ASC
    """, (history_id,))
    rows = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return rows


def get_job_detail(history_id: int) -> dict | None:
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM compression_history WHERE id = ?", (history_id,))
    row = cursor.fetchone()
    conn.close()
    return dict(row) if row else None


def get_stats_summary() -> dict:
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT
            COUNT(*) AS total_jobs,
            SUM(CASE WHEN file_type='text' THEN 1 ELSE 0 END) AS text_jobs,
            SUM(CASE WHEN file_type='pdf' THEN 1 ELSE 0 END) AS pdf_jobs,
            SUM(CASE WHEN file_type='docx' THEN 1 ELSE 0 END) AS docx_jobs,
            ROUND(AVG(compression_ratio), 2) AS avg_ratio,
            SUM(original_size - compressed_size) AS total_bytes_saved
        FROM compression_history
    """)
    row = dict(cursor.fetchone())
    conn.close()

    return {
        "total_jobs": row.get("total_jobs") or 0,
        "text_jobs": row.get("text_jobs") or 0,
        "pdf_jobs": row.get("pdf_jobs") or 0,
        "docx_jobs": row.get("docx_jobs") or 0,
        "avg_ratio": row.get("avg_ratio") or 0.0,
        "total_bytes_saved": row.get("total_bytes_saved") or 0,
    }


def clear_history():
    conn = get_connection()
    conn.execute("DELETE FROM compression_history")
    conn.commit()
    conn.close()


def delete_job(history_id: int):
    conn = get_connection()
    conn.execute("DELETE FROM compression_history WHERE id = ?", (history_id,))
    conn.commit()
    conn.close()
