"""Analyst agent. Extracts claims from spreadsheet rows only."""

import generator
from desk.state import clean_claims, emit, passages_block

ANALYST_SYSTEM = (
    "You are the analyst on a document desk. You only read spreadsheet rows. "
    "You do not use PDF or Word passages and you do not answer the user directly. "
    "State figures and comparisons that are present in the rows. Do not invent "
    "a total, average, or difference that is not written in a row. "
    "Reply with one JSON object and no other text: "
    '{"claims": [{"text": "one claim", "filename": "exact file name", '
    '"location": "exact location"}]}'
)


def analyst_node(state):
    """Extract sheet claims, or record that this agent was skipped.

    Parameters
    ----------
    state : dict
        Uses ``need_analyst``, ``passages``, ``question``, and ``top_k``.

    Returns
    -------
    dict
        ``claims`` when the agent ran, plus one trace event.
    """
    emit(state, "analyst", "running", "Reading spreadsheet rows.")
    if not state.get("need_analyst"):
        record = emit(state, "analyst", "skipped", "Not needed for this question.")
        return {"trace": [record]}
    limit = max(int(state.get("top_k") or 4), 1)
    sheets = [item for item in state.get("passages") or [] if item.get("kind") == "sheet"]
    sheets = sheets[:limit]
    if not sheets:
        record = emit(state, "analyst", "skipped", "No spreadsheet rows were retrieved.")
        return {"trace": [record]}
    user = "Question: {0}\n\nRows:\n{1}".format(
        state["question"], passages_block(sheets)
    )
    parsed = generator.complete_json(ANALYST_SYSTEM, user)
    claims = clean_claims(parsed.get("claims"), sheets)
    summary = "Extracted {0} claims from spreadsheet rows.".format(len(claims))
    record = emit(state, "analyst", "done", summary)
    return {"claims": claims, "trace": [record]}
