"""Lead agent. Decides who should work, and what to search for.

This node does not answer the question.
"""

import generator
from desk.state import emit

LEAD_SYSTEM = (
    "You are the lead of a document desk. You do not answer the question. "
    "Decide whether the question needs written prose (policy, contract, report) "
    "and whether it needs spreadsheet rows (numbers, tables, dates in a sheet). "
    "Reply with one JSON object and no other text: "
    '{"need_reader": true, "need_analyst": true, "search_query": "short search query", '
    '"intent": "one sentence"}'
)


def lead_node(state):
    """Plan the question.

    Parameters
    ----------
    state : dict
        Uses ``question`` and ``run_id``.

    Returns
    -------
    dict
        ``need_reader``, ``need_analyst``, ``search_query``, and one trace event.
        If the model sets both flags false, both are turned on so the desk
        still searches.
    """
    emit(state, "lead", "running", "Reading the question.")
    plan = generator.complete_json(
        LEAD_SYSTEM,
        "Question: {0}".format(state["question"]),
    )
    need_reader = bool(plan.get("need_reader"))
    need_analyst = bool(plan.get("need_analyst"))
    if not need_reader and not need_analyst:
        need_reader = True
        need_analyst = True
    search_query = " ".join(str(plan.get("search_query") or "").split())
    if not search_query:
        search_query = state["question"]
    intent = " ".join(str(plan.get("intent") or "").split())
    if not intent:
        parts = []
        if need_reader:
            parts.append("written files")
        if need_analyst:
            parts.append("spreadsheet rows")
        intent = "Needs " + " and ".join(parts) + "."
    record = emit(state, "lead", "done", intent)
    return {
        "need_reader": need_reader,
        "need_analyst": need_analyst,
        "search_query": search_query,
        "trace": [record],
    }
