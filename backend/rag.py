"""The two operations the rest of the app calls: ingest a file, ask a question.

``ingest_file`` runs extract, chunk, embed, store.
``ask_stream`` runs the LangGraph document desk and yields events.
``ask`` collects that stream into one result.
"""

from pathlib import Path

import config
import embeddings
import extractors
import vector_store
from chunker import chunk_sections
from desk.graph import stream_question


def ingest_file(path, filename):
    """Read one file from disk and store its chunks.

    Parameters
    ----------
    path : path-like
        Temporary path of the upload.
    filename : str
        Original file name. The extension selects the extractor and is stored
        for the document list.

    Returns
    -------
    dict
        The document record from ``vector_store.add_document``, including
        ``id``, ``filename``, ``filetype``, ``uploaded_at``, and
        ``chunk_count``.

    Raises
    ------
    extractors.ExtractError
        Unsupported type, or the file contained no readable text.
    embeddings.EmbeddingError
        The embedding API failed.
    """
    sections = extractors.extract_file(path, filename)
    if not sections:
        raise extractors.ExtractError(
            "No readable text was found in {0}. Scanned PDFs and empty files cannot be indexed.".format(
                filename
            )
        )
    chunks = chunk_sections(sections, config.CHUNK_SIZE, config.CHUNK_OVERLAP)
    if not chunks:
        raise extractors.ExtractError(
            "No readable text was found in {0}.".format(filename)
        )
    vectors = embeddings.embed_documents(chunks, filename)
    for chunk, vector in zip(chunks, vectors):
        chunk["embedding"] = vector
    filetype = Path(filename).suffix.lower()
    return vector_store.add_document(filename, filetype, chunks)


def ask_stream(question, top_k=None):
    """Yield desk events for one question.

    Parameters
    ----------
    question : str
        Blank questions raise ``ValueError`` inside ``stream_question``.
    top_k : int or None
        How many passages of each kind a specialist may read. ``None`` uses
        ``config.TOP_K``.

    Yields
    ------
    dict
        See ``desk.graph.stream_question``.
    """
    if top_k is None:
        top_k = config.TOP_K
    for event in stream_question(question, top_k):
        yield event


def ask(question, top_k=None):
    """Run the desk and return the final result.

    Parameters
    ----------
    question : str
    top_k : int or None
        Passed to ``ask_stream``.

    Returns
    -------
    dict
        ``answer``, ``sources``, and ``trace``.

    Raises
    ------
    ValueError
        The question is blank.
    RuntimeError
        The desk emitted ``type: error``, or it ended without a result.
        ``ask_stream`` yields that error instead of raising, which is what
        the HTTP stream uses.
    """
    result = None
    for event in ask_stream(question, top_k=top_k):
        if event.get("type") == "error":
            raise RuntimeError(event.get("error") or "The desk failed.")
        if event.get("type") == "result":
            result = event
    if result is None:
        raise RuntimeError("The desk ended without an answer.")
    return {
        "answer": result.get("answer") or "",
        "sources": result.get("sources") or [],
        "trace": result.get("trace") or [],
    }
