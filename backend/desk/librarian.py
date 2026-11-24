"""Librarian agent. Retrieval only. This node does not call a chat model."""

import embeddings
import vector_store
from desk.state import emit, passage_kind

RESET_CLAIMS = {"__reset__": True}


def librarian_node(state):
    """Embed ``search_query`` and store the nearest passages.

    Parameters
    ----------
    state : dict
        Uses ``search_query``, ``top_k``, ``revise``, ``revision``, and ``run_id``.

    Returns
    -------
    dict
        ``passages`` tagged ``prose`` or ``sheet``, ``claims`` reset so the
        next specialists start clean, and ``revision`` incremented when this
        visit is the one allowed retry. ``revise`` is cleared.
    """
    retry = bool(state.get("revise")) and state.get("revision", 0) < 1
    if retry:
        emit(state, "librarian", "running", "Searching again with a tighter query.")
    else:
        emit(state, "librarian", "running", "Searching the library.")
    pool = min(max(int(state.get("top_k") or 4) * 2, 8), 12)
    vector = embeddings.embed_question(state.get("search_query") or state["question"])
    matches = vector_store.search(vector, pool)
    passages = []
    for item in matches:
        kind = passage_kind(item["filename"])
        passages.append(
            {
                "document_id": item["document_id"],
                "filename": item["filename"],
                "chunk_index": item["chunk_index"],
                "location": item["location"],
                "text": item["text"],
                "score": item["score"],
                "excerpt": item["excerpt"],
                "kind": kind,
            }
        )
    prose = sum(1 for item in passages if item["kind"] == "prose")
    sheets = sum(1 for item in passages if item["kind"] == "sheet")
    if not passages:
        summary = "No passages matched."
    else:
        summary = "Retrieved {0} passages, {1} written and {2} from sheets.".format(
            len(passages), prose, sheets
        )
    record = emit(state, "librarian", "done", summary)
    revision = state.get("revision", 0)
    if retry:
        revision = revision + 1
    return {
        "passages": passages,
        "claims": RESET_CLAIMS,
        "revision": revision,
        "revise": False,
        "trace": [record],
    }
