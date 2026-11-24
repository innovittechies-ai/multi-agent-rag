"""Shared graph state, the trace queue, and small claim helpers.

``RUNS`` maps a ``run_id`` to a ``queue.Queue``. Nodes call ``emit`` as they
start and finish. The HTTP handler reads that queue so the browser can show
each agent while the graph is still running. The queue is not stored on the
graph state, because LangGraph keeps that state as plain data.
"""

import queue
from pathlib import Path
from typing import Annotated, TypedDict


RUNS = {}

PROSE_SUFFIXES = {".pdf", ".docx", ".txt"}
SHEET_SUFFIX = ".xlsx"


def merge_trace(left, right):
    """Append trace events. ``right`` is the list a node just returned.

    Parameters
    ----------
    left : list or None
        Trace already on the graph state.
    right : list or None
        New events from the node that just finished.

    Returns
    -------
    list
    """
    return list(left or []) + list(right or [])


def merge_claims(left, right):
    """Append claims, or clear them when ``right`` is a reset marker.

    The librarian returns ``{"__reset__": True}`` before a specialist runs,
    so a second pass does not keep claims the reviewer already rejected.

    Parameters
    ----------
    left : list or None
    right : list or dict or None
        A dict with ``__reset__`` true replaces the list with ``[]``.
        Any other dict is ignored. A list is appended.

    Returns
    -------
    list
    """
    if isinstance(right, dict):
        if right.get("__reset__"):
            return []
        return list(left or [])
    return list(left or []) + list(right or [])


class DeskState(TypedDict):
    """Fields passed between LangGraph nodes.

    ``trace`` and ``claims`` use reducers so the reader and the analyst can
    both write in the same step. Every other field is replaced by the node
    that returns it.
    """

    question: str
    top_k: int
    search_query: str
    need_reader: bool
    need_analyst: bool
    passages: list
    claims: Annotated[list, merge_claims]
    approved: list
    rejected: list
    revision: int
    revise: bool
    answer: str
    sources: list
    trace: Annotated[list, merge_trace]
    run_id: str


def emit(state, name, status, summary):
    """Push one agent event to the run queue, if this run has one.

    Parameters
    ----------
    state : dict
        Must contain ``run_id`` when the call is part of a streamed ask.
    name : str
        ``lead``, ``librarian``, ``reader``, ``analyst``, or ``reviewer``.
    status : str
        ``running``, ``done``, or ``skipped``.
    summary : str
        One line for the trace pane. Clipped to 180 characters.

    Returns
    -------
    dict
        The trace record stored on the graph: ``agent``, ``status``, ``summary``.
        Running events are not stored. The node returns only the terminal record.
    """
    summary = " ".join((summary or "").split())
    if len(summary) > 180:
        summary = summary[:177].rstrip() + "..."
    box = RUNS.get(state.get("run_id"))
    if box is not None:
        box.put(
            {
                "type": "agent",
                "name": name,
                "status": status,
                "summary": summary,
            }
        )
    return {"agent": name, "status": status, "summary": summary}


def open_run():
    """Create a queue for one question and return ``(run_id, queue)``."""
    import uuid

    run_id = uuid.uuid4().hex
    box = queue.Queue()
    RUNS[run_id] = box
    return run_id, box


def close_run(run_id):
    """Drop the queue for ``run_id``. Safe to call more than once."""
    RUNS.pop(run_id, None)


def passage_kind(filename):
    """Return ``sheet`` for Excel and ``prose`` for every other stored file.

    Parameters
    ----------
    filename : str

    Returns
    -------
    str
    """
    if Path(filename or "").suffix.lower() == SHEET_SUFFIX:
        return "sheet"
    return "prose"


def passages_block(passages):
    """Format passages the way the specialists and the reviewer read them.

    Parameters
    ----------
    passages : list of dict
        Each dict needs ``filename``, ``location``, and ``text``.

    Returns
    -------
    str
    """
    blocks = []
    for index, passage in enumerate(passages, start=1):
        blocks.append(
            "[{0}] file: {1} | {2}\n{3}".format(
                index,
                passage.get("filename") or "",
                passage.get("location") or "",
                passage.get("text") or "",
            )
        )
    return "\n\n".join(blocks)


def clean_claims(raw, passages):
    """Keep claims that name a file actually present in ``passages``.

    Parameters
    ----------
    raw : list
        Model output. Items that are not objects, or have no text, are dropped.
    passages : list of dict
        The passages this agent was allowed to read.

    Returns
    -------
    list of dict
        Each dict has ``text``, ``filename``, and ``location``. A location
        the model invented is replaced with the location of the first passage
        from that file.
    """
    by_file = {}
    allowed = set()
    for passage in passages:
        filename = passage.get("filename") or ""
        location = passage.get("location") or ""
        allowed.add((filename, location))
        by_file.setdefault(filename, location)
    cleaned = []
    for item in raw or []:
        if not isinstance(item, dict):
            continue
        text = " ".join(str(item.get("text") or "").split())
        filename = str(item.get("filename") or "").strip()
        location = str(item.get("location") or "").strip()
        if not text or filename not in by_file:
            continue
        if (filename, location) not in allowed:
            location = by_file[filename]
        cleaned.append(
            {"text": text, "filename": filename, "location": location}
        )
    return cleaned
