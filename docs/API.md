# HTTP API

Base URL is wherever the Flask app is hosted, with no trailing slash. Example: `https://yourname.pythonanywhere.com`.

The browser page sends these calls. You can also call them with curl while you rehearse.

All error bodies use this shape:

```json
{"error": "What went wrong."}
```

Upload failures that name more than one file also include `documents` and `errors`.

## GET /api/health

No body.

```json
{
  "status": "ok",
  "llm_provider": "gemini",
  "google_key_set": true,
  "groq_key_set": false,
  "embed_model": "gemini-embedding-2",
  "chat_model": "gemini-3.8-flash",
  "embed_dim": 768,
  "chunk_size": 800,
  "chunk_overlap": 120,
  "top_k": 4
}
```

`google_key_set` is false when `GOOGLE_API_KEY` is empty. The key itself is not in the response.

## POST /api/upload

Multipart form. The field name is `file`. Repeat the field to send more than one file.

```bash
curl -X POST "%BASE%/api/upload" -F "file=@notes.pdf" -F "file=@sales.xlsx"
```

HTTP 201 when at least one file is indexed:

```json
{
  "documents": [
    {
      "id": "a1b2c3d4e5f64789a0b1c2d3e4f56789",
      "filename": "notes.pdf",
      "filetype": ".pdf",
      "uploaded_at": "2026-11-24T06:30:00+00:00",
      "chunk_count": 6
    }
  ],
  "errors": []
}
```

A file that fails while another succeeds is listed in `errors`, and the status is still 201. `documents` holds only the files that were indexed.

HTTP 400 when nothing was saved:

```json
{
  "error": "No readable text was found in scan.pdf. Scanned PDFs and empty files cannot be indexed.",
  "documents": [],
  "errors": [
    {
      "filename": "scan.pdf",
      "error": "No readable text was found in scan.pdf. Scanned PDFs and empty files cannot be indexed."
    }
  ]
}
```

When several files fail, `error` is `No files were saved.` and `errors` lists each one.

HTTP 400 also covers a missing file field and an unsupported extension (`.doc`, `.xls`, images).

HTTP 413 when the whole request is larger than `MAX_UPLOAD_MB` (default 10):

```json
{"error": "File is larger than 10 MB."}
```

Indexing calls Gemini once per chunk, so a long PDF can take a while and can hit a free-tier rate limit. The embedding client retries a 429 once, after two seconds.

## GET /api/documents

```json
{
  "documents": [
    {
      "id": "a1b2c3d4e5f64789a0b1c2d3e4f56789",
      "filename": "notes.pdf",
      "filetype": ".pdf",
      "uploaded_at": "2026-11-24T06:30:00+00:00",
      "chunk_count": 6
    }
  ]
}
```

Newest upload first. An empty library returns `"documents": []`.

## DELETE /api/documents/{id}

```bash
curl -X DELETE "%BASE%/api/documents/a1b2c3d4e5f64789a0b1c2d3e4f56789"
```

Success:

```json
{"deleted": "a1b2c3d4e5f64789a0b1c2d3e4f56789"}
```

Unknown id, HTTP 404:

```json
{"error": "Document not found."}
```

Chunks for that document are deleted with it.

## POST /api/ask

The response is a server-sent event stream, not one JSON document. `Content-Type` is `text/event-stream`.

```bash
curl -N -X POST "%BASE%/api/ask" \
  -H "Content-Type: application/json" \
  -d "{\"question\": \"What does the policy require, and do the numbers meet it?\", \"top_k\": 4}"
```

- `question` (string, required). Blank is HTTP 400, `Question is empty.`, as a normal JSON error. The stream has not started.
- `top_k` (integer, optional). Default is the server `TOP_K`, usually 4. Allowed range is 1 to 20. Each specialist reads at most this many passages of its own kind. The librarian first retrieves up to twice that, capped at 12.

Agent event:

```
data: {"type": "agent", "name": "librarian", "status": "done", "summary": "Retrieved 8 passages, 4 written and 4 from sheets."}
```

`name` is `lead`, `librarian`, `reader`, `analyst`, or `reviewer`. `status` is `running`, `done`, or `skipped`.

Final event:

```
data: {"type": "result", "answer": "The policy requires ... The sheet shows ...", "sources": [{"filename": "policy.pdf", "location": "page 2", "chunk_index": 1, "score": 0.8123, "excerpt": "..."}], "trace": [{"agent": "lead", "status": "done", "summary": "Needs the policy and the figures."}]}
```

`score` is cosine similarity rounded to 4 decimals, or `null` when a claim could not be matched back to a stored passage. `excerpt` is at most 400 characters. `trace` is the terminal record for each visit, including a second librarian and a second reviewer when the desk searches again. Running events are not repeated in `trace`.

No uploads yet. The stream is a single result and the graph does not start:

```
data: {"type": "result", "answer": "No documents have been uploaded yet.", "sources": [], "trace": []}
```

A provider failure after the stream has started:

```
data: {"type": "error", "error": "GOOGLE_API_KEY is not set. Add it to backend/.env on the server."}
```

The HTTP status stays 200 in that case. Hosts that buffer the stream still deliver the same lines together at the end. The page renders `trace` from the result event when that happens.

## GET /

```json
{"service": "document-desk", "health": "/api/health"}
```

Not used by the demo page.
