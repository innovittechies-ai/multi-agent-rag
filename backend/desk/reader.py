"""Reader agent. Extracts claims from written passages only."""

import generator
from desk.state import clean_claims, emit, passages_block

READER_SYSTEM = (
    "You are the reader on a document desk. You only read written passages "
    "(PDF, Word, or text). You do not use spreadsheet rows and you do not "
    "answer the user directly. Extract claims that the passages explicitly "
    "support. Reply with one JSON object and no other text: "
    '{"claims": [{"text": "one claim", "filename": "exact file name", '
    '"location": "exact location"}]}'
)


def reader_node(state):
    """Extract prose claims, or record that this agent was skipped.

    Parameters
    ----------
    state : dict
        Uses ``need_reader``, ``passages``, ``question``, and ``top_k``.

    Returns
    -------
    dict
        ``claims`` when the agent ran, plus one trace event.
        Skipped when the lead did not ask for prose, or no prose passage
        was retrieved. A skip returns no claims.
    """
    emit(state, "reader", "running", "Reading written passages.")
    if not state.get("need_reader"):
        record = emit(state, "reader", "skipped", "Not needed for this question.")
        return {"trace": [record]}
    limit = max(int(state.get("top_k") or 4), 1)
    prose = [item for item in state.get("passages") or [] if item.get("kind") == "prose"]
    prose = prose[:limit]
    if not prose:
        record = emit(state, "reader", "skipped", "No written passages were retrieved.")
        return {"trace": [record]}
    user = "Question: {0}\n\nPassages:\n{1}".format(
        state["question"], passages_block(prose)
    )
    parsed = generator.complete_json(READER_SYSTEM, user)
    claims = clean_claims(parsed.get("claims"), prose)
    summary = "Extracted {0} claims from written passages.".format(len(claims))
    record = emit(state, "reader", "done", summary)
    return {"claims": claims, "trace": [record]}
