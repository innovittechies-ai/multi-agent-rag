"""Reviewer agent. Drops unsupported claims, may search once more, then writes."""

import generator
from desk.state import clean_claims, emit, passages_block

JUDGE_SYSTEM = (
    "You are the reviewer on a document desk. You do not add facts. "
    "Approve a claim only when the passage with the same file and location "
    "supports that claim. Reject anything the passage does not say. "
    "Reply with one JSON object and no other text: "
    '{"approved": [{"text": "", "filename": "", "location": ""}], '
    '"rejected": [{"text": "", "reason": ""}], '
    '"retry_query": "", "sufficient": true}'
)


def reviewer_node(state):
    """Judge claims and either ask for one more search or write the answer.

    Parameters
    ----------
    state : dict
        Uses ``claims``, ``passages``, ``question``, ``revision``, and ``run_id``.

    Returns
    -------
    dict
        When a claim was rejected and ``revision`` is still 0, the update sets
        ``revise`` true and a tighter ``search_query``, and does not set
        ``answer``. Otherwise it sets ``answer``, ``sources``, and ``revise``
        false. The answer is written only from approved claims. If none are
        approved, the answer is the fixed sentence that the files do not support
        an answer. That path does not call the chat model again.
    """
    emit(state, "reviewer", "running", "Checking claims against the passages.")
    claims = list(state.get("claims") or [])
    passages = list(state.get("passages") or [])
    if not claims:
        return _finish(
            state,
            approved=[],
            rejected=[],
            passages=passages,
            summary="No claims to check.",
        )
    user = (
        "Question: {0}\n\nPassages:\n{1}\n\nClaims:\n{2}"
    ).format(state["question"], passages_block(passages), _claims_block(claims))
    judged = generator.complete_json(JUDGE_SYSTEM, user)
    approved = clean_claims(judged.get("approved"), passages)
    rejected = _clean_rejected(judged.get("rejected"))
    can_retry = bool(rejected) and state.get("revision", 0) < 1
    if can_retry:
        query = _tighter_query(state, judged.get("retry_query"), rejected)
        summary = "Rejected {0}. Searching once more.".format(len(rejected))
        record = emit(state, "reviewer", "done", summary)
        return {
            "approved": approved,
            "rejected": rejected,
            "revise": True,
            "search_query": query,
            "trace": [record],
        }
    summary = "Approved {0}, rejected {1}.".format(len(approved), len(rejected))
    return _finish(state, approved, rejected, passages, summary)


def _finish(state, approved, rejected, passages, summary):
    """Write the final answer from ``approved`` and close the review.

    Parameters
    ----------
    state : dict
    approved : list of dict
    rejected : list of dict
    passages : list of dict
    summary : str
        Trace line. The function adds the answer outcome onto it when there
        is nothing to say.

    Returns
    -------
    dict
    """
    sources = _sources_for(approved, passages)
    if not approved:
        answer = "I do not know based on the uploaded documents."
        summary = summary or "No approved claims."
    else:
        answer = generator.generate_answer(state["question"], _prompt_sources(sources))
    record = emit(state, "reviewer", "done", summary)
    return {
        "approved": approved,
        "rejected": rejected,
        "revise": False,
        "answer": answer,
        "sources": _public_sources(sources),
        "trace": [record],
    }


def _claims_block(claims):
    """Number the claims for the judge prompt.

    Parameters
    ----------
    claims : list of dict

    Returns
    -------
    str
    """
    lines = []
    for index, claim in enumerate(claims, start=1):
        lines.append(
            "{0}. {1} (file: {2} | {3})".format(
                index,
                claim.get("text") or "",
                claim.get("filename") or "",
                claim.get("location") or "",
            )
        )
    return "\n".join(lines)


def _clean_rejected(raw):
    """Keep rejected items that have text.

    Parameters
    ----------
    raw : list

    Returns
    -------
    list of dict
        ``text`` and ``reason``.
    """
    rejected = []
    for item in raw or []:
        if not isinstance(item, dict):
            continue
        text = " ".join(str(item.get("text") or "").split())
        if not text:
            continue
        reason = " ".join(str(item.get("reason") or "").split()) or "Not in the passages."
        rejected.append({"text": text, "reason": reason})
    return rejected


def _tighter_query(state, retry_query, rejected):
    """Build the search string for the one allowed retry.

    Parameters
    ----------
    state : dict
        Provides the original question.
    retry_query : str
        Optional query suggested by the judge. Blank is ignored.
    rejected : list of dict
        Up to three rejected claim texts are appended.

    Returns
    -------
    str
        At most 500 characters.
    """
    parts = [state["question"]]
    extra = " ".join(str(retry_query or "").split())
    if extra:
        parts.append(extra)
    for item in rejected[:3]:
        parts.append(item["text"])
    return " ".join(parts)[:500]


def _sources_for(approved, passages):
    """Match approved claims to the passages they cite.

    Parameters
    ----------
    approved : list of dict
    passages : list of dict

    Returns
    -------
    list of dict
        Passage fields plus the claim text. Duplicate file and location pairs
        are returned once, first claim wins.
    """
    found = []
    seen = set()
    for claim in approved:
        key = (claim["filename"], claim["location"])
        if key in seen:
            continue
        seen.add(key)
        match = None
        for passage in passages:
            if passage.get("filename") == key[0] and passage.get("location") == key[1]:
                match = passage
                break
        if match is None:
            found.append(
                {
                    "filename": claim["filename"],
                    "location": claim["location"],
                    "chunk_index": None,
                    "score": None,
                    "excerpt": claim["text"],
                    "text": claim["text"],
                }
            )
            continue
        found.append(
            {
                "filename": match["filename"],
                "location": match["location"],
                "chunk_index": match.get("chunk_index"),
                "score": match.get("score"),
                "excerpt": match.get("excerpt") or claim["text"],
                "text": match.get("text") or claim["text"],
            }
        )
    return found


def _prompt_sources(sources):
    """Shape passages for ``generator.generate_answer``.

    Parameters
    ----------
    sources : list of dict

    Returns
    -------
    list of dict
        ``filename``, ``location``, and ``text`` only.
    """
    return [
        {
            "filename": item["filename"],
            "location": item["location"],
            "text": item["text"],
        }
        for item in sources
    ]


def _public_sources(sources):
    """Shape citations for the HTTP response. Full passage text is omitted.

    Parameters
    ----------
    sources : list of dict

    Returns
    -------
    list of dict
        ``filename``, ``location``, ``chunk_index``, ``score`` rounded to 4
        decimals or null, and ``excerpt``.
    """
    public = []
    for item in sources:
        score = item.get("score")
        if score is not None:
            score = round(float(score), 4)
        public.append(
            {
                "filename": item["filename"],
                "location": item["location"],
                "chunk_index": item.get("chunk_index"),
                "score": score,
                "excerpt": item.get("excerpt") or "",
            }
        )
    return public
