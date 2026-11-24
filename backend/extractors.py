"""Turn an uploaded file into a list of text sections.

Each section is a dict with two keys:

* ``text`` — the words that will be chunked and embedded
* ``location`` — a short label such as ``page 3`` or ``sheet Sales, row 12``

Scanned PDFs (a photo of a page) have no text layer, so they come back empty.
Old ``.doc`` and ``.xls`` files are not supported.
"""

from pathlib import Path


class ExtractError(ValueError):
    """The file type is unsupported or the file could not be read."""


def _suffix(filename):
    """Return the lowercase extension, including the dot. Example: ``.pdf``."""
    return Path(filename).suffix.lower()


def extract_file(path, filename):
    """Dispatch to the extractor that matches ``filename``.

    Parameters
    ----------
    path : path-like
        Where the uploaded bytes were saved.
    filename : str
        Original file name, used only to choose the extractor.

    Returns
    -------
    list of dict
        Sections with ``text`` and ``location``. Empty when the file has no
        readable text.
    """
    kind = _suffix(filename)
    if kind == ".pdf":
        return extract_pdf(path)
    if kind == ".docx":
        return extract_docx(path)
    if kind == ".xlsx":
        return extract_xlsx(path)
    if kind == ".txt":
        return extract_txt(path)
    raise ExtractError(
        "Unsupported file type. Upload a .pdf, .docx, .xlsx, or .txt file."
    )


def extract_pdf(path):
    """Read each page of a PDF with ``pypdf``.

    Parameters
    ----------
    path : path-like
        Path to a ``.pdf`` file.

    Returns
    -------
    list of dict
        One section per page that contains text. ``location`` is ``page N``.
    """
    from pypdf import PdfReader

    reader = PdfReader(str(path))
    sections = []
    for index, page in enumerate(reader.pages, start=1):
        text = (page.extract_text() or "").strip()
        if text:
            sections.append({"text": text, "location": "page {0}".format(index)})
    return sections


def extract_docx(path):
    """Read paragraphs and table rows from a Word ``.docx`` file.

    Parameters
    ----------
    path : path-like
        Path to a ``.docx`` file.

    Returns
    -------
    list of dict
        One section for the whole document when any text was found.
        ``location`` is ``document``.
    """
    from docx import Document

    document = Document(str(path))
    parts = []
    for paragraph in document.paragraphs:
        text = paragraph.text.strip()
        if text:
            parts.append(text)
    for table_index, table in enumerate(document.tables, start=1):
        for row_index, row in enumerate(table.rows, start=1):
            cells = []
            seen = set()
            for cell in row.cells:
                text = cell.text.strip()
                if text and text not in seen:
                    seen.add(text)
                    cells.append(text)
            if cells:
                parts.append(
                    "table {0}, row {1}: {2}".format(
                        table_index, row_index, " | ".join(cells)
                    )
                )
    if not parts:
        return []
    return [{"text": "\n".join(parts), "location": "document"}]


def extract_xlsx(path):
    """Read an Excel workbook. Each non-empty row becomes one section.

    The first row is treated as column headers when every filled cell is
    text. Each later row is written as ``Header: value | Header: value``
    so numbers stay attached to their column name.

    Parameters
    ----------
    path : path-like
        Path to a ``.xlsx`` file.

    Returns
    -------
    list of dict
        One section per data row. ``location`` is ``sheet NAME, row N``.
    """
    from openpyxl import load_workbook

    workbook = load_workbook(str(path), read_only=True, data_only=True)
    sections = []
    try:
        for sheet in workbook.worksheets:
            rows = []
            for row in sheet.iter_rows(values_only=True):
                if any(cell is not None and str(cell).strip() != "" for cell in row):
                    rows.append(row)
            if not rows:
                continue
            headers, start = _excel_headers(rows)
            for offset, row in enumerate(rows[start:], start=start + 1):
                pairs = []
                for index, cell in enumerate(row):
                    if cell is None or str(cell).strip() == "":
                        continue
                    name = headers[index] if index < len(headers) else "Column {0}".format(index + 1)
                    pairs.append("{0}: {1}".format(name, cell))
                if pairs:
                    sections.append(
                        {
                            "text": " | ".join(pairs),
                            "location": "sheet {0}, row {1}".format(sheet.title, offset),
                        }
                    )
    finally:
        workbook.close()
    return sections


def _excel_headers(rows):
    """Return ``(headers, first_data_index)`` for a sheet's non-empty rows.

    If the first row is all text, it is the header and data starts at index
    1. Otherwise headers are ``Column 1``, ``Column 2``, and data starts at 0.
    """
    width = max(len(row) for row in rows)
    first = rows[0]
    textual = True
    for cell in first:
        if cell is None or str(cell).strip() == "":
            continue
        if not isinstance(cell, str):
            textual = False
            break
    if textual:
        headers = []
        for index in range(width):
            cell = first[index] if index < len(first) else None
            label = str(cell).strip() if cell else ""
            headers.append(label or "Column {0}".format(index + 1))
        return headers, 1
    headers = ["Column {0}".format(index + 1) for index in range(width)]
    return headers, 0


def extract_txt(path):
    """Read a plain text file as UTF-8, replacing bad bytes.

    Parameters
    ----------
    path : path-like
        Path to a ``.txt`` file.

    Returns
    -------
    list of dict
        One section, or an empty list when the file is blank.
        ``location`` is ``file``.
    """
    text = Path(path).read_text(encoding="utf-8", errors="replace").strip()
    if not text:
        return []
    return [{"text": text, "location": "file"}]
