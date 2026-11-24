"""SQLite vector store. This file is the vector database.

Chroma would do the same three jobs: save chunk vectors, find the nearest
ones, and delete a document. Here those jobs are visible:

* ``add_document`` writes rows
* ``cosine_similarity`` measures the angle between two vectors
* ``search`` scores every stored chunk and keeps the top ones

Vectors are JSON text in the ``chunks`` table. A few hundred chunks is enough
for a live demo. Search reads them all and ranks them in Python. There is no
NumPy and no Chroma dependency.

To swap in Chroma later, keep ``add_document``, ``search``,
``list_documents``, and ``delete_document`` and replace the bodies. Callers
in ``rag.py`` would not change.
"""

import json
import math
import sqlite3
import uuid
from datetime import datetime, timezone

import config


def init_db():
    """Create the data folder and the two tables if they do not exist."""
    config.DATA_DIR.mkdir(parents=True, exist_ok=True)
    with connect() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS documents (
                id TEXT PRIMARY KEY,
                filename TEXT NOT NULL,
                filetype TEXT NOT NULL,
                uploaded_at TEXT NOT NULL,
                chunk_count INTEGER NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS chunks (
                id TEXT PRIMARY KEY,
                document_id TEXT NOT NULL,
                chunk_index INTEGER NOT NULL,
                location TEXT,
                text TEXT NOT NULL,
                embedding_json TEXT NOT NULL,
                FOREIGN KEY (document_id) REFERENCES documents(id)
            )
            """
        )


def connect():
    """Open a short-lived SQLite connection.

    Returns
    -------
    sqlite3.Connection
        Rows can be read by column name. Foreign keys are on.
    """
    config.DATA_DIR.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(config.SQLITE_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def cosine_similarity(left, right):
    """Score how similar two embedding vectors are.

    Cosine similarity is the dot product divided by the product of the
    lengths. The result is between -1 and 1. For these normalized Gemini
    vectors it is usually between 0 and 1. Closer to 1 means more similar.
    A zero-length vector scores 0 so bad data cannot divide by zero.

    Parameters
    ----------
    left : sequence of float
        Usually the question embedding.
    right : sequence of float
        Usually one stored chunk embedding.

    Returns
    -------
    float
    """
    dot = 0.0
    left_norm = 0.0
    right_norm = 0.0
    for a, b in zip(left, right):
        dot += a * b
        left_norm += a * a
        right_norm += b * b
    if left_norm == 0.0 or right_norm == 0.0:
        return 0.0
    return dot / (math.sqrt(left_norm) * math.sqrt(right_norm))


def add_document(filename, filetype, chunks):
    """Store one uploaded file and its embedded chunks.

    Parameters
    ----------
    filename : str
        Original file name shown in the UI and in citations.
    filetype : str
        Lowercase extension, including the dot. Example: ``.pdf``.
    chunks : list of dict
        Each dict needs ``text``, ``location``, ``chunk_index``, and
        ``embedding`` (a list of floats).

    Returns
    -------
    dict
        ``id``, ``filename``, ``filetype``, ``uploaded_at``, ``chunk_count``.
    """
    document_id = uuid.uuid4().hex
    uploaded_at = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    init_db()
    with connect() as conn:
        conn.execute(
            """
            INSERT INTO documents (id, filename, filetype, uploaded_at, chunk_count)
            VALUES (?, ?, ?, ?, ?)
            """,
            (document_id, filename, filetype, uploaded_at, len(chunks)),
        )
        conn.executemany(
            """
            INSERT INTO chunks (
                id, document_id, chunk_index, location, text, embedding_json
            )
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            [
                (
                    uuid.uuid4().hex,
                    document_id,
                    chunk["chunk_index"],
                    chunk.get("location") or "",
                    chunk["text"],
                    json.dumps(chunk["embedding"]),
                )
                for chunk in chunks
            ],
        )
    return {
        "id": document_id,
        "filename": filename,
        "filetype": filetype,
        "uploaded_at": uploaded_at,
        "chunk_count": len(chunks),
    }


def search(query_embedding, top_k):
    """Return the ``top_k`` chunks closest to ``query_embedding``.

    Parameters
    ----------
    query_embedding : list of float
        Vector for the user's question.
    top_k : int
        How many chunks to keep. Values below 1 become 1.

    Returns
    -------
    list of dict
        Each dict has ``document_id``, ``filename``, ``chunk_index``,
        ``location``, ``text``, ``score``, and ``excerpt``. Highest score
        first. Embeddings are not included.
    """
    top_k = max(int(top_k), 1)
    init_db()
    with connect() as conn:
        rows = conn.execute(
            """
            SELECT
                chunks.document_id,
                chunks.chunk_index,
                chunks.location,
                chunks.text,
                chunks.embedding_json,
                documents.filename
            FROM chunks
            JOIN documents ON documents.id = chunks.document_id
            """
        ).fetchall()
    ranked = []
    for row in rows:
        vector = json.loads(row["embedding_json"])
        ranked.append(
            {
                "document_id": row["document_id"],
                "filename": row["filename"],
                "chunk_index": row["chunk_index"],
                "location": row["location"],
                "text": row["text"],
                "score": cosine_similarity(query_embedding, vector),
                "excerpt": _excerpt(row["text"]),
            }
        )
    ranked.sort(key=lambda item: item["score"], reverse=True)
    return ranked[:top_k]


def list_documents():
    """Return every uploaded document, newest first.

    Returns
    -------
    list of dict
        ``id``, ``filename``, ``filetype``, ``uploaded_at``, ``chunk_count``.
    """
    init_db()
    with connect() as conn:
        rows = conn.execute(
            """
            SELECT id, filename, filetype, uploaded_at, chunk_count
            FROM documents
            ORDER BY uploaded_at DESC
            """
        ).fetchall()
    return [dict(row) for row in rows]


def delete_document(document_id):
    """Delete one document and every chunk that belongs to it.

    Parameters
    ----------
    document_id : str
        The ``id`` returned by ``add_document`` or ``list_documents``.

    Returns
    -------
    bool
        True when a document row was removed, False when the id is unknown.
    """
    init_db()
    with connect() as conn:
        conn.execute("DELETE FROM chunks WHERE document_id = ?", (document_id,))
        cursor = conn.execute("DELETE FROM documents WHERE id = ?", (document_id,))
        return cursor.rowcount > 0


def _excerpt(text, limit=None):
    """Shorten ``text`` for the API response and the demo screen.

    Parameters
    ----------
    text : str
    limit : int or None
        Defaults to ``config.EXCERPT_CHARS`` (400).

    Returns
    -------
    str
    """
    if limit is None:
        limit = config.EXCERPT_CHARS
    collapsed = " ".join((text or "").split())
    if len(collapsed) <= limit:
        return collapsed
    return collapsed[: limit - 3].rstrip() + "..."
