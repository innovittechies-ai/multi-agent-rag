"""HTTP routes. This file does not embed or search. It calls ``rag.py``.

Routes
------
GET    /api/health
POST   /api/upload
GET    /api/documents
DELETE /api/documents/<id>
POST   /api/ask
"""

import json
import os
import tempfile
from pathlib import Path

from flask import Flask, Response, jsonify, request
from flask_cors import CORS
from werkzeug.exceptions import RequestEntityTooLarge

import config
import rag
import vector_store

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = config.MAX_UPLOAD_MB * 1024 * 1024

_origins = [item.strip() for item in config.CORS_ORIGINS.split(",") if item.strip()]
if not _origins or _origins == ["*"]:
    CORS(app, resources={r"/api/*": {"origins": "*"}})
else:
    CORS(app, resources={r"/api/*": {"origins": _origins}})


def _error(message, status):
    """Return ``{"error": message}`` with an HTTP status code."""
    return jsonify({"error": message}), status


@app.errorhandler(RequestEntityTooLarge)
def file_too_large(_error):
    """Reject uploads over ``MAX_UPLOAD_MB``."""
    return _error(
        "File is larger than {0} MB.".format(config.MAX_UPLOAD_MB),
        413,
    )


@app.get("/")
def root():
    """A one-line pointer so a browser visit to the host is not a blank 404."""
    return jsonify(
        {
            "service": "document-desk",
            "health": "/api/health",
        }
    )


@app.get("/api/health")
def health():
    """Report which provider is selected and whether keys are present.

    The response never includes the key values. ``google_key_set`` and
    ``groq_key_set`` are booleans.
    """
    vector_store.init_db()
    chat_model = (
        config.GROQ_CHAT_MODEL
        if config.LLM_PROVIDER == "groq"
        else config.GEMINI_CHAT_MODEL
    )
    return jsonify(
        {
            "status": "ok",
            "llm_provider": config.LLM_PROVIDER,
            "google_key_set": bool(config.GOOGLE_API_KEY),
            "groq_key_set": bool(config.GROQ_API_KEY),
            "embed_model": config.GEMINI_EMBED_MODEL,
            "chat_model": chat_model,
            "embed_dim": config.EMBED_DIM,
            "chunk_size": config.CHUNK_SIZE,
            "chunk_overlap": config.CHUNK_OVERLAP,
            "top_k": config.TOP_K,
        }
    )


@app.post("/api/upload")
def upload():
    """Accept one or more files in the multipart field ``file``.

    Each file is written to a temporary path, passed to ``rag.ingest_file``,
    then deleted. The original file is not kept on disk. The text lives in
    SQLite.

    Success returns HTTP 201 and ``{"documents": [...], "errors": [...]}``.
    If every file fails, the status is 400 and ``documents`` is empty.
    """
    incoming = request.files.getlist("file")
    named = [item for item in incoming if item and item.filename]
    if not named:
        return _error("Choose a file to upload. Use the form field name 'file'.", 400)

    documents = []
    errors = []
    for storage in named:
        filename = Path(storage.filename).name
        suffix = Path(filename).suffix.lower()
        if suffix not in config.ALLOWED_EXTENSIONS:
            errors.append(
                {
                    "filename": filename,
                    "error": "Unsupported file type. Use .pdf, .docx, .xlsx, or .txt.",
                }
            )
            continue
        temp_path = None
        try:
            with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as handle:
                storage.save(handle)
                temp_path = handle.name
            documents.append(rag.ingest_file(temp_path, filename))
        except Exception as exc:
            errors.append({"filename": filename, "error": str(exc)})
        finally:
            if temp_path and os.path.exists(temp_path):
                os.remove(temp_path)

    if not documents:
        summary = errors[0]["error"] if len(errors) == 1 else "No files were saved."
        return jsonify({"error": summary, "documents": [], "errors": errors}), 400
    return jsonify({"documents": documents, "errors": errors}), 201


@app.get("/api/documents")
def documents():
    """List uploaded documents, newest first."""
    return jsonify({"documents": vector_store.list_documents()})


@app.delete("/api/documents/<document_id>")
def delete_document(document_id):
    """Delete one document and its chunks.

    Parameters
    ----------
    document_id : str
        Path parameter. The id from the document list.
    """
    if not vector_store.delete_document(document_id):
        return _error("Document not found.", 404)
    return jsonify({"deleted": document_id})


@app.post("/api/ask")
def ask():
    """Stream the desk as server-sent events.

    JSON body: ``{"question": "...", "top_k": 4}``. ``top_k`` is optional.

    Each event is one ``data:`` line. Agent events use ``type`` ``agent``
    with ``name``, ``status``, and ``summary``. The last event is ``result``
    (``answer``, ``sources``, ``trace``) or ``error``.

    A blank question or a bad ``top_k`` is still a normal JSON error, before
    the stream starts. Provider failures that happen after the stream has
    started are an ``error`` event, not an HTTP 502, because the status was
    already sent.
    """
    payload = request.get_json(silent=True) or {}
    question = payload.get("question", "")
    top_k = payload.get("top_k", None)
    if not str(question or "").strip():
        return _error("Question is empty.", 400)
    if top_k is not None:
        try:
            top_k = int(top_k)
        except (TypeError, ValueError):
            return _error("top_k must be an integer.", 400)
        if top_k < 1 or top_k > 20:
            return _error("top_k must be from 1 to 20.", 400)

    def generate():
        try:
            for event in rag.ask_stream(question, top_k=top_k):
                yield "data: " + json.dumps(event) + "\n\n"
        except Exception as exc:
            yield "data: " + json.dumps({"type": "error", "error": str(exc)}) + "\n\n"

    return Response(
        generate(),
        mimetype="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )
