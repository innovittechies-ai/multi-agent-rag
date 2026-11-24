"""Call the Gemini embedding API and return one vector per string.

Documents and questions are prefixed differently. Gemini Embedding 2 has no
``task_type`` parameter. Google asks callers to put the task in the text:

* a stored chunk: ``title: report.pdf | text: ...``
* a question: ``task: question answering | query: ...``

Each string is one HTTP request. Sending a list in one request makes
Embedding 2 collapse that list into a single vector, which would break search.
"""

import time

import requests

import config


class EmbeddingError(RuntimeError):
    """The embedding API refused the request or returned no vector."""


def prepare_document(content, title):
    """Prefix a chunk the way Embedding 2 expects a document.

    Parameters
    ----------
    content : str
        The chunk text.
    title : str
        File name. ``none`` is used when the title is blank.

    Returns
    -------
    str
    """
    title = (title or "").strip() or "none"
    return "title: {0} | text: {1}".format(title, content)


def prepare_query(question):
    """Prefix a user question for question-answering retrieval.

    Parameters
    ----------
    question : str

    Returns
    -------
    str
    """
    return "task: question answering | query: {0}".format(question.strip())


def embed_text(text):
    """Embed one string. Retries once when Google responds with HTTP 429.

    Parameters
    ----------
    text : str
        Already prefixed with ``prepare_document`` or ``prepare_query``.

    Returns
    -------
    list of float
        Length is ``config.EMBED_DIM`` (768 by default).
    """
    if not config.GOOGLE_API_KEY:
        raise EmbeddingError(
            "GOOGLE_API_KEY is not set. Add it to backend/.env on the server."
        )
    last_error = None
    for attempt in range(2):
        try:
            return _post_embed(text)
        except EmbeddingError as exc:
            last_error = exc
            if "429" not in str(exc) or attempt == 1:
                raise
            time.sleep(2)
    raise last_error


def embed_documents(chunks, title):
    """Embed every chunk of one uploaded file.

    Parameters
    ----------
    chunks : list of dict
        Each dict must contain ``text``.
    title : str
        Original file name, passed to ``prepare_document``.

    Returns
    -------
    list of list of float
        One vector per chunk, same order as ``chunks``.
    """
    vectors = []
    for chunk in chunks:
        vectors.append(embed_text(prepare_document(chunk["text"], title)))
    return vectors


def embed_question(question):
    """Embed a user question for search.

    Parameters
    ----------
    question : str

    Returns
    -------
    list of float
    """
    return embed_text(prepare_query(question))


def _post_embed(text):
    """POST one ``embedContent`` request and return the value list.

    The JSON field ``output_dimensionality`` asks for a 768-number vector.
    Embedding 2 normalizes that shorter vector itself.
    """
    url = (
        "https://generativelanguage.googleapis.com/v1beta/models/{0}:embedContent"
    ).format(config.GEMINI_EMBED_MODEL)
    response = requests.post(
        url,
        headers={
            "Content-Type": "application/json",
            "x-goog-api-key": config.GOOGLE_API_KEY,
        },
        json={
            "content": {"parts": [{"text": text}]},
            "output_dimensionality": config.EMBED_DIM,
        },
        timeout=config.REQUEST_TIMEOUT_SECONDS,
    )
    if response.status_code != 200:
        detail = response.text.strip().replace("\n", " ")
        if len(detail) > 300:
            detail = detail[:300] + "..."
        raise EmbeddingError(
            "Gemini embeddings returned HTTP {0}: {1}".format(
                response.status_code, detail
            )
        )
    payload = response.json()
    values = _read_values(payload)
    if not values:
        raise EmbeddingError("Gemini embeddings returned an empty vector.")
    if len(values) != config.EMBED_DIM:
        raise EmbeddingError(
            "Expected {0} dimensions, got {1}. Check EMBED_DIM.".format(
                config.EMBED_DIM, len(values)
            )
        )
    return values


def _read_values(payload):
    """Pull the float list out of either response shape Google has used."""
    embedding = payload.get("embedding") or {}
    if embedding.get("values"):
        return embedding["values"]
    embeddings = payload.get("embeddings") or []
    if embeddings and embeddings[0].get("values"):
        return embeddings[0]["values"]
    return []
