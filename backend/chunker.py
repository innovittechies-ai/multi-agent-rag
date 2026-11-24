"""Split long text into overlapping character windows.

A window is ``size`` characters. The next window starts ``size - overlap``
characters later, so neighboring chunks share some text and a fact that sits
on a boundary is not cut in half and lost.

A section shorter than ``size`` is left as one chunk. That is why a short
Excel row stays intact.
"""


def chunk_text(text, size, overlap):
    """Split ``text`` into overlapping pieces.

    Parameters
    ----------
    text : str
        Source text. Leading and trailing whitespace is removed.
    size : int
        Maximum characters in one chunk. Values below 1 are treated as 1.
    overlap : int
        Characters repeated from the end of one chunk at the start of the
        next. If ``overlap`` is greater than or equal to ``size``, it is
        reduced to one quarter of ``size`` so the window still moves forward.

    Returns
    -------
    list of str
        Chunks in reading order. Empty when ``text`` is blank.
    """
    text = (text or "").strip()
    if not text:
        return []
    size = max(int(size), 1)
    overlap = max(int(overlap), 0)
    if len(text) <= size:
        return [text]
    if overlap >= size:
        overlap = size // 4
    step = size - overlap
    chunks = []
    start = 0
    while start < len(text):
        piece = text[start : start + size].strip()
        if piece:
            chunks.append(piece)
        if start + size >= len(text):
            break
        start += step
    return chunks


def chunk_sections(sections, size, overlap):
    """Chunk every extracted section and keep its location label.

    Parameters
    ----------
    sections : list of dict
        Each dict needs ``text`` and ``location``, as returned by
        ``extractors.extract_file``.
    size : int
        Passed to ``chunk_text``.
    overlap : int
        Passed to ``chunk_text``.

    Returns
    -------
    list of dict
        Each dict has ``text``, ``location``, and ``chunk_index``.
        ``chunk_index`` starts at 0 across the whole file.
    """
    chunks = []
    for section in sections:
        pieces = chunk_text(section.get("text", ""), size, overlap)
        location = section.get("location") or ""
        for piece in pieces:
            chunks.append(
                {
                    "text": piece,
                    "location": location,
                    "chunk_index": len(chunks),
                }
            )
    return chunks
