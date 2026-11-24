"""The LangGraph that runs the document desk.

Reader and analyst are started together with ``Send`` after the librarian.
The reviewer waits until both of those branches finish. It may send the
graph back to the librarian once.
"""

import threading

import vector_store
from langgraph.graph import END, START, StateGraph

try:
    from langgraph.types import Send
except ImportError:  # older LangGraph builds
    from langgraph.constants import Send

from desk.analyst import analyst_node
from desk.lead import lead_node
from desk.librarian import librarian_node
from desk.reader import reader_node
from desk.reviewer import reviewer_node
from desk.state import DeskState, close_run, open_run


def fan_out(state):
    """Start the reader and the analyst on the state the librarian just wrote.

    Parameters
    ----------
    state : dict
        Graph state after ``librarian_node``.

    Returns
    -------
    list of Send
        Always both agents. Each one records ``skipped`` when it has no work,
        so the trace still shows the whole team and the reviewer is not left
        waiting for a branch that never started.
    """
    payload = {
        "question": state["question"],
        "top_k": state["top_k"],
        "search_query": state.get("search_query") or state["question"],
        "need_reader": state.get("need_reader", True),
        "need_analyst": state.get("need_analyst", True),
        "passages": state.get("passages") or [],
        "revision": state.get("revision", 0),
        "revise": False,
        "run_id": state.get("run_id", ""),
    }
    return [Send("reader", payload), Send("analyst", payload)]


def after_reviewer(state):
    """Loop back to the librarian once, or end.

    Parameters
    ----------
    state : dict
        Uses ``revise`` and ``revision``. ``revision`` stays 0 until the
        librarian begins the retry, so this function still sees 0 on the
        first rejection.

    Returns
    -------
    str
        ``librarian`` or ``END``.
    """
    if state.get("revise") and state.get("revision", 0) < 1:
        return "librarian"
    return END


def build_graph():
    """Compile the desk graph.

    Returns
    -------
    CompiledStateGraph
        The object returned by ``StateGraph.compile``.
    """
    builder = StateGraph(DeskState)
    builder.add_node("lead", lead_node)
    builder.add_node("librarian", librarian_node)
    builder.add_node("reader", reader_node)
    builder.add_node("analyst", analyst_node)
    try:
        builder.add_node("reviewer", reviewer_node, defer=True)
    except TypeError:
        builder.add_node("reviewer", reviewer_node)
    builder.add_edge(START, "lead")
    builder.add_edge("lead", "librarian")
    builder.add_conditional_edges("librarian", fan_out, ["reader", "analyst"])
    builder.add_edge("reader", "reviewer")
    builder.add_edge("analyst", "reviewer")
    builder.add_conditional_edges("reviewer", after_reviewer, ["librarian", END])
    return builder.compile()


graph = build_graph()


def stream_question(question, top_k):
    """Run the desk and yield events as each agent finishes a step.

    Parameters
    ----------
    question : str
        Blank input raises ``ValueError``.
    top_k : int
        Passed through to the librarian. The pool it searches is larger than
        this so one file type does not crowd out the other. Each specialist
        then keeps at most ``top_k`` passages of its own kind.

    Yields
    ------
    dict
        ``type: agent`` while the graph runs, then one ``type: result`` with
        ``answer``, ``sources``, and ``trace``. If the library is empty, only
        the result event is yielded and the graph is not started. Provider
        failures become ``type: error`` after any agent events already sent.
    """
    question = (question or "").strip()
    if not question:
        raise ValueError("Question is empty.")
    if not vector_store.list_documents():
        yield {
            "type": "result",
            "answer": "No documents have been uploaded yet.",
            "sources": [],
            "trace": [],
        }
        return

    run_id, box = open_run()
    holder = {}

    def worker():
        try:
            holder["final"] = graph.invoke(
                _initial_state(question, top_k, run_id),
                {"recursion_limit": 20},
            )
        except Exception as exc:
            holder["error"] = exc
        finally:
            box.put(None)

    thread = threading.Thread(target=worker, daemon=True)
    thread.start()
    try:
        while True:
            event = box.get()
            if event is None:
                break
            yield event
    finally:
        thread.join()
        close_run(run_id)

    if holder.get("error") is not None:
        yield {"type": "error", "error": str(holder["error"])}
        return
    final = holder.get("final") or {}
    yield {
        "type": "result",
        "answer": final.get("answer") or "I do not know based on the uploaded documents.",
        "sources": final.get("sources") or [],
        "trace": final.get("trace") or [],
    }


def _initial_state(question, top_k, run_id):
    """The state passed into ``graph.invoke``.

    Parameters
    ----------
    question : str
    top_k : int
    run_id : str

    Returns
    -------
    dict
    """
    return {
        "question": question,
        "top_k": int(top_k),
        "search_query": question,
        "need_reader": True,
        "need_analyst": True,
        "passages": [],
        "claims": [],
        "approved": [],
        "rejected": [],
        "revision": 0,
        "revise": False,
        "answer": "",
        "sources": [],
        "trace": [],
        "run_id": run_id,
    }
