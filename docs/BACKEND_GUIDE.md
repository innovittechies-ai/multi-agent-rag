# Backend guide

Every Python function, in the order a file moves through the system. Paths are relative to the repository root. Line numbers will drift if you edit the files; the function name is the stable pointer.

Private helpers start with `_`. They are listed because a question from the room will land on them.

## `backend/config.py`

Loaded first by every other module. On import it reads `backend/.env` if that file exists, then copies the settings below into module variables. A variable already set by the server wins over the file.

### `_load_dotenv()`

Reads `backend/.env`. Ignores blank lines and lines that start with `#`. Splits on the first `=`. Strips matching quotes around the value. Calls `os.environ.setdefault`, so it will not overwrite a real environment variable.

No parameters. No return value.

### `_int(name, default)`

- `name` (str): environment variable name.
- `default` (int): used when the variable is missing or not an integer.

Returns an int.

### `_str(name, default)`

- `name` (str): environment variable name.
- `default` (str): used when the variable is missing or blank.

Returns a str. Leading and trailing whitespace is removed.

### Settings

| Name | Default | Meaning |
| --- | --- | --- |
| `GOOGLE_API_KEY` | empty | Google AI Studio key. Required for embeddings and for Gemini answers. |
| `GROQ_API_KEY` | empty | Required only when `LLM_PROVIDER` is `groq`. |
| `LLM_PROVIDER` | `gemini` | `gemini` or `groq`. Stored in lowercase. |
| `GEMINI_CHAT_MODEL` | `gemini-3.8-flash` | Answer model for the Gemini provider. |
| `GEMINI_EMBED_MODEL` | `gemini-embedding-2` | Embedding model. |
| `GEMINI_THINKING_LEVEL` | `low` | `low`, `medium`, `high`, or `off`. |
| `GROQ_CHAT_MODEL` | `openai/gpt-oss-20b` | Answer model for the Groq provider. |
| `EMBED_DIM` | `768` | Length of each stored vector. Recommended values are 768, 1536, and 3072. Changing it after upload makes old vectors the wrong length. Delete and re-upload. |
| `CHUNK_SIZE` | `800` | Maximum characters per chunk. |
| `CHUNK_OVERLAP` | `120` | Characters shared by neighboring chunks. |
| `TOP_K` | `4` | Passages sent to the answer model when the request does not pass `top_k`. |
| `MAX_UPLOAD_MB` | `10` | Reject larger request bodies with HTTP 413. |
| `CORS_ORIGINS` | `*` | Comma-separated browser origins allowed to call the API. |
| `DATA_DIR` | `backend/data` | Folder that holds `rag.sqlite`. |
| `SQLITE_PATH` | `DATA_DIR/rag.sqlite` | Derived. Not an environment variable. |
| `ALLOWED_EXTENSIONS` | `.pdf` `.docx` `.xlsx` `.txt` | Fixed in code. |
| `EXCERPT_CHARS` | `400` | Length of the excerpt returned to the browser. |
| `REQUEST_TIMEOUT_SECONDS` | `90` | HTTP timeout for Gemini and Groq. |

`BASE_DIR` is the `backend/` directory.

## `backend/extractors.py`

Turns a file into sections. A section is a dict with `text` and `location`.

### `ExtractError`

Raised for an unsupported type or a file with no readable text. It is a `ValueError`.

### `_suffix(filename)`

- `filename` (str)

Returns the lowercase extension, including the dot. `Report.PDF` becomes `.pdf`.

### `extract_file(path, filename)`

- `path`: where the bytes were saved.
- `filename` (str): original name. Only the extension is used, to pick the extractor.

Returns a list of section dicts. Raises `ExtractError` for any other extension.

### `extract_pdf(path)`

Uses `pypdf.PdfReader`. One section per page that has text. `location` is `page N`, starting at 1. Empty pages are skipped. A scanned page usually extracts as empty text.

### `extract_docx(path)`

Uses `python-docx`. Collects non-empty paragraphs, then each table row. Cells that repeat because of a merged cell are kept once per row. Rows are written as `table 1, row 2: cell | cell`. If anything was found, the function returns one section whose `location` is `document`.

### `extract_xlsx(path)`

Uses `openpyxl` in read-only mode with `data_only=True`. Each non-empty data row is one section, so a short row is not glued to the next row before chunking. The text looks like `Quarter: Q1 | Revenue: 1200`. `location` is `sheet NAME, row N`. The workbook is closed when reading finishes.

### `_excel_headers(rows)`

- `rows`: non-empty tuples from one sheet.

Returns `(headers, first_data_index)`.

If every filled cell in the first row is text, that row is the header and data starts at index 1. Blank header cells become `Column 1`, `Column 2`, and so on. If any filled cell is a number or a date, the first row is data and the headers are `Column 1` onward. `first_data_index` is then 0.

### `extract_txt(path)`

Reads UTF-8 and replaces invalid bytes instead of failing. Returns one section with `location` `file`, or an empty list when the file is blank.

## `backend/chunker.py`

### `chunk_text(text, size, overlap)`

- `text` (str): stripped before splitting.
- `size` (int): maximum characters. Values below 1 are treated as 1.
- `overlap` (int): characters repeated on the next window. Negative values are treated as 0. If `overlap` is greater than or equal to `size`, it is reduced to `size // 4` so the window still moves forward.

Returns a list of strings. A blank string returns `[]`. Text shorter than or equal to `size` returns one chunk, unchanged except for stripped ends. That is why a short Excel row stays intact.

The step forward is `size - overlap`. The loop stops once a window reaches the end of the text.

### `chunk_sections(sections, size, overlap)`

- `sections`: list of `{text, location}` from the extractors.
- `size`, `overlap`: passed through to `chunk_text`.

Returns a list of `{text, location, chunk_index}`. `chunk_index` starts at 0 and counts across the whole file, not per page. The location label is copied onto every piece cut from that section, so a long page 3 still says `page 3` on each of its chunks.

## `backend/embeddings.py`

### `EmbeddingError`

Raised when the key is missing, Google returns a non-200 status, the vector is empty, or the length is not `EMBED_DIM`.

### `prepare_document(content, title)`

- `content` (str): chunk text.
- `title` (str): file name. Blank becomes `none`.

Returns `title: {title} | text: {content}`.

### `prepare_query(question)`

- `question` (str): stripped.

Returns `task: question answering | query: {question}`.

### `embed_text(text)`

- `text` (str): already prefixed.

Returns a list of floats. Calls `_post_embed`. If that raises `EmbeddingError` and the message contains `429`, waits 2 seconds and tries once more. Any other error is raised immediately. A second 429 is also raised.

### `embed_documents(chunks, title)`

- `chunks`: list of dicts. Each must have `text`.
- `title` (str): file name passed to `prepare_document`.

Returns a list of vectors, one per chunk, same order. One HTTP request per chunk. Embedding 2 merges several inputs in a single request into one vector, which would make search meaningless, so this function does not batch.

### `embed_question(question)`

- `question` (str)

Returns one vector, via `prepare_query` and `embed_text`.

### `_post_embed(text)`

POSTs to

`https://generativelanguage.googleapis.com/v1beta/models/{GEMINI_EMBED_MODEL}:embedContent`

Headers: `Content-Type: application/json`, `x-goog-api-key`.

JSON body:

- `content.parts[0].text` — the prefixed string
- `output_dimensionality` — `config.EMBED_DIM`

Timeout is `REQUEST_TIMEOUT_SECONDS`. A non-200 body is clipped to 300 characters and wrapped in `EmbeddingError`. The vector must be exactly `EMBED_DIM` long.

### `_read_values(payload)`

- `payload` (dict): parsed JSON.

Returns the float list from `embedding.values`, or from `embeddings[0].values` if the first shape is absent. Returns `[]` when neither is present.

## `backend/vector_store.py`

This is the vector database.

### `init_db()`

Creates `DATA_DIR` and the `documents` and `chunks` tables if they are missing. Safe to call more than once.

### `connect()`

Returns a new `sqlite3.Connection` with `row_factory` set so columns can be read by name, and with `PRAGMA foreign_keys = ON`. Callers use it as a context manager so the connection closes and the transaction commits.

### `cosine_similarity(left, right)`

- `left`, `right`: sequences of floats. Extra tail values are ignored if the lengths differ, because the loop uses `zip`.

Computes `dot / (sqrt(sum of squares of left) * sqrt(sum of squares of right))`. Returns `0.0` when either vector has length 0, so a bad vector cannot divide by zero.

The result is between -1 and 1. For these embeddings it is usually between 0 and 1.

### `add_document(filename, filetype, chunks)`

- `filename` (str)
- `filetype` (str): lowercase extension, including the dot.
- `chunks`: list of dicts with `text`, `location`, `chunk_index`, and `embedding` (list of floats).

Creates a hex `uuid`. Writes one `documents` row and one `chunks` row per chunk. The embedding is stored with `json.dumps`. `uploaded_at` is UTC, seconds precision, ISO 8601.

Returns `{id, filename, filetype, uploaded_at, chunk_count}`.

### `search(query_embedding, top_k)`

- `query_embedding`: list of floats.
- `top_k` (int): values below 1 become 1.

Loads every chunk joined to its file name, scores each with `cosine_similarity`, sorts descending, and returns the first `top_k`.

Each result dict has `document_id`, `filename`, `chunk_index`, `location`, `text`, `score`, and `excerpt`. The raw vector is not included.

### `list_documents()`

Returns a list of `{id, filename, filetype, uploaded_at, chunk_count}`, newest `uploaded_at` first.

### `delete_document(document_id)`

- `document_id` (str)

Deletes matching rows from `chunks`, then from `documents`. Returns `True` when a document row was removed, `False` when the id is unknown.

### `_excerpt(text, limit=None)`

- `text` (str)
- `limit` (int or None): defaults to `EXCERPT_CHARS` (400).

Collapses whitespace into single spaces. If the result is longer than `limit`, it is cut and ends with `...`.

## `backend/generator.py`

### `GeneratorError`

Raised for a missing key, a bad `LLM_PROVIDER`, a non-200 chat response, or an empty answer.

### `SYSTEM_PROMPT`

A fixed string. The model may use only the passages in the user message, must name the source file when it states a fact, and must say it does not know when the passages do not contain the answer.

### `build_prompt(question, sources)`

- `question` (str)
- `sources`: list of dicts with `filename`, `location`, and `text`.

Returns one string. Passages are numbered starting at 1, each as:

```
[1] file: report.pdf | page 2
<chunk text>
```

The question is appended, then the line `Answer using only these passages.`

### `generate_answer(question, sources)`

Builds the prompt and calls `_complete` with `SYSTEM_PROMPT` and `json_mode` false.

Returns the answer string. The reviewer calls this only after claims have been approved.

### `complete_json(system, user)`

- `system` (str): role instruction.
- `user` (str): the question, passages, or claims.

Calls `_complete` with `json_mode` true, then `parse_json_object`. Returns a dict. Raises `GeneratorError` when the provider fails or the text is not a JSON object. The lead, reader, analyst, and reviewer use this. The librarian does not.

### `parse_json_object(text)`

- `text` (str)

Strips a markdown fence if the text starts with one. Parses the slice from the first `{` to the last `}`. Returns a dict. Raises `GeneratorError` when there is no object, the JSON is invalid, or the value is a list.

### `_complete(system, user, json_mode)`

- `system` (str)
- `user` (str)
- `json_mode` (bool)

Calls `_gemini` or `_groq`. Any other `LLM_PROVIDER` raises `GeneratorError`.

### `_gemini(prompt, system=None, json_mode=False)`

- `prompt` (str): user message.
- `system` (str or None): defaults to `SYSTEM_PROMPT`.
- `json_mode` (bool): first attempt sets `responseMimeType` to `application/json`.

Requires `GOOGLE_API_KEY`. Tries thinking plus the requested JSON mode, then thinking without JSON mode if JSON mode was on, then neither. Stops early on any status other than 400. A final non-200 raises `GeneratorError`.

Returns the string from `_gemini_text`.

### `_gemini_body(prompt, include_thinking, system=None, json_mode=False)`

- `prompt` (str)
- `include_thinking` (bool)
- `system` (str or None): defaults to `SYSTEM_PROMPT`.
- `json_mode` (bool)

Returns the JSON body:

- `systemInstruction.parts[0].text` = `system`
- `contents[0].role` = `user`
- `contents[0].parts[0].text` = `prompt`
- `generationConfig.temperature` = `0.2`
- `generationConfig.thinkingConfig.thinkingLevel` = `GEMINI_THINKING_LEVEL`, only when `include_thinking` is true and the level is not blank or `off`
- `generationConfig.responseMimeType` = `application/json` when `json_mode` is true

### `_gemini_text(payload)`

- `payload` (dict)

Reads `candidates[0].content.parts`. Skips any part with `thought` set, so a hidden reasoning trace is not shown as the answer. Joins the remaining `text` fields with newlines. Raises `GeneratorError` when there is no candidate or no visible text.

### `_groq(prompt, system=None, json_mode=False)`

- `prompt` (str)
- `system` (str or None): defaults to `SYSTEM_PROMPT`.
- `json_mode` (bool)

Requires `GROQ_API_KEY`. Calls `_groq_post`. If the status is 400 and `json_mode` was true, calls `_groq_post` again without JSON mode. Returns `choices[0].message.content`, stripped. Raises `GeneratorError` when the status is not 200, when `choices` is empty, or when the content is blank.

### `_groq_post(prompt, system, json_mode)`

- `prompt` (str)
- `system` (str)
- `json_mode` (bool)

POSTs to `https://api.groq.com/openai/v1/chat/completions` with `Authorization: Bearer <key>`.

JSON body:

- `model` = `GROQ_CHAT_MODEL`
- `temperature` = `0.2`
- `messages` = a system message and a user message
- `response_format` = `{"type": "json_object"}` when `json_mode` is true

Returns the `requests` response. It does not raise on HTTP errors.

### `_post_json(url, extra_headers, body)`

- `url` (str)
- `extra_headers` (dict): merged onto `Content-Type: application/json`
- `body` (dict): sent as JSON

Returns the `requests` response. It does not raise on HTTP errors. Timeout is `REQUEST_TIMEOUT_SECONDS`.

### `_http_error(name, response)`

- `name` (str): `Gemini` or `Groq`, used in the sentence.
- `response`: a `requests` response.

Returns a string with the status code and at most 300 characters of the body, newlines replaced by spaces.

## `backend/rag.py`

The only module the routes need for the pipeline.

### `ingest_file(path, filename)`

- `path`: temporary file path.
- `filename` (str): original name.

Calls, in order:

1. `extractors.extract_file`
2. `chunker.chunk_sections` with `CHUNK_SIZE` and `CHUNK_OVERLAP`
3. `embeddings.embed_documents`
4. `vector_store.add_document`

Attaches each vector onto its chunk as `embedding` before the store call. The filetype stored on the document is the lowercase suffix of `filename`.

Raises `ExtractError` when extraction or chunking yields nothing. The message says scanned PDFs and empty files cannot be indexed. Propagates `EmbeddingError`.

Returns the dict from `add_document`. Ingest does not run the graph.

### `ask_stream(question, top_k=None)`

- `question` (str)
- `top_k` (int or None): `None` uses `config.TOP_K`. Passed to `desk.graph.stream_question`.

Yields the same events as `stream_question`. This is what `POST /api/ask` iterates.

### `ask(question, top_k=None)`

Collects `ask_stream`. Returns `{answer, sources, trace}`.

Raises `ValueError` when the question is blank. Raises `RuntimeError` when the stream emits `type: error` or ends without a result. The HTTP route does not call `ask`. It calls `ask_stream` and forwards the error event.

## `backend/desk/state.py`

Shared state and the live-event queue. `RUNS` is a dict from `run_id` to a `queue.Queue`. `PROSE_SUFFIXES` is `.pdf`, `.docx`, `.txt`. `SHEET_SUFFIX` is `.xlsx`.

### `DeskState`

TypedDict. `claims` uses `merge_claims`. `trace` uses `merge_trace`. Other fields are replaced when a node returns them.

### `merge_trace(left, right)`

- `left`, `right`: lists or None.

Returns `left` plus `right`.

### `merge_claims(left, right)`

- `left`: list or None.
- `right`: list, dict, or None.

If `right` is a dict with `__reset__` true, returns `[]`. That is how the librarian clears claims before a retry. Any other dict leaves `left` as it is. A list is appended.

### `emit(state, name, status, summary)`

- `state` (dict): read for `run_id`.
- `name` (str): `lead`, `librarian`, `reader`, `analyst`, or `reviewer`.
- `status` (str): `running`, `done`, or `skipped`.
- `summary` (str): collapsed to one line and clipped to 180 characters.

If `RUNS` has this `run_id`, puts `{type: agent, name, status, summary}` on that queue. Returns `{agent, status, summary}` for the trace reducer. Nodes put only the terminal record on the trace. Running events go to the queue only.

### `open_run()`

Creates a hex `run_id` and a queue, stores them in `RUNS`, and returns `(run_id, queue)`.

### `close_run(run_id)`

Removes that queue. Safe to call more than once.

### `passage_kind(filename)`

- `filename` (str)

Returns `sheet` when the suffix is `.xlsx`. Otherwise returns `prose`.

### `passages_block(passages)`

- `passages`: list of dicts with `filename`, `location`, and `text`.

Returns a numbered string, `[1] file: name | location`, then the text.

### `clean_claims(raw, passages)`

- `raw` (list): model output.
- `passages` (list): the only files this agent was allowed to cite.

Drops items that are not objects, have no text, or name a file that is not in `passages`. If the location is not one of that file's passages, it is replaced with the first passage location for that file. Returns a list of `{text, filename, location}`.

## `backend/desk/lead.py`

### `LEAD_SYSTEM`

Tells the model it does not answer, and to return `need_reader`, `need_analyst`, `search_query`, and `intent`.

### `lead_node(state)`

- `state`: `question`, `run_id`.

Emits `running`, calls `complete_json`, then emits `done`. If both flags are false, both are set true. A blank `search_query` becomes the question. A blank `intent` becomes `Needs written files`, `Needs spreadsheet rows`, or both.

Returns `need_reader`, `need_analyst`, `search_query`, and one trace event.

## `backend/desk/librarian.py`

### `RESET_CLAIMS`

The dict `{"__reset__": True}` passed as the `claims` update.

### `librarian_node(state)`

- `state`: `search_query`, `question`, `top_k`, `revise`, `revision`, `run_id`.

Does not call a chat model. Embeds `search_query` with `embeddings.embed_question`. Searches with pool size `min(max(top_k * 2, 8), 12)`. Tags each hit with `passage_kind`.

Emits `running` (`Searching again...` when `revise` is true and `revision` is still 0, otherwise `Searching the library.`). The done summary counts written passages and sheet passages.

When this visit is the retry, `revision` becomes `revision + 1`. `revise` is set false. `claims` is `RESET_CLAIMS`.

Returns `passages`, `claims`, `revision`, `revise`, and one trace event.

## `backend/desk/reader.py`

### `READER_SYSTEM`

Tells the model to extract claims from written passages only and to return `claims` with `text`, `filename`, and `location`.

### `reader_node(state)`

- `state`: `need_reader`, `passages`, `question`, `top_k`, `run_id`.

Emits `running`. Returns a `skipped` trace and no claims when `need_reader` is false, or when no passage has kind `prose`. Otherwise keeps at most `top_k` prose passages, calls `complete_json`, and runs `clean_claims`. The done summary is `Extracted N claims from written passages.`

Returns `claims` and one trace event. A skip returns only the trace event.

## `backend/desk/analyst.py`

### `ANALYST_SYSTEM`

Same shape as the reader, restricted to spreadsheet rows. The instruction forbids inventing a total, average, or difference that is not written in a row.

### `analyst_node(state)`

- `state`: `need_analyst`, `passages`, `question`, `top_k`, `run_id`.

Same control flow as `reader_node`, using passages whose kind is `sheet`. Skip summaries are `Not needed for this question.` and `No spreadsheet rows were retrieved.`

## `backend/desk/reviewer.py`

### `JUDGE_SYSTEM`

Tells the model to approve a claim only when the passage with the same file and location supports it. The object is `approved`, `rejected` (`text`, `reason`), `retry_query`, and `sufficient`.

### `reviewer_node(state)`

- `state`: `claims`, `passages`, `question`, `revision`, `run_id`.

Emits `running`. If `claims` is empty, calls `_finish` with summary `No claims to check.` Otherwise calls `complete_json`, then `clean_claims` on `approved` and `_clean_rejected` on `rejected`.

If `rejected` is non-empty and `revision` is still 0, emits `Rejected N. Searching once more.`, sets `revise` true, and sets `search_query` from `_tighter_query`. It does not set `answer`. The graph edge `after_reviewer` sends that state back to the librarian.

Otherwise calls `_finish`.

### `_finish(state, approved, rejected, passages, summary)`

- `state` (dict)
- `approved`, `rejected`, `passages`: lists
- `summary` (str)

Builds citations with `_sources_for`. If `approved` is empty, `answer` is `I do not know based on the uploaded documents.` and the chat model is not called. Otherwise `generator.generate_answer` is called with `_prompt_sources`. Emits `done` with `summary`.

Returns `approved`, `rejected`, `revise` false, `answer`, `sources` from `_public_sources`, and one trace event.

### `_claims_block(claims)`

- `claims` (list)

Returns numbered lines: `1. text (file: name | location)`.

### `_clean_rejected(raw)`

- `raw` (list)

Keeps objects that have text. Missing reasons become `Not in the passages.` Returns `{text, reason}`.

### `_tighter_query(state, retry_query, rejected)`

- `state`: provides `question`.
- `retry_query` (str): appended when non-blank.
- `rejected`: up to three claim texts are appended.

Returns one string, at most 500 characters.

### `_sources_for(approved, passages)`

Matches each approved claim to a passage with the same filename and location. Duplicate pairs are kept once. When no passage matches, the claim text is used as both `text` and `excerpt`, and `score` and `chunk_index` are None.

### `_prompt_sources(sources)`

Returns `filename`, `location`, and `text` only, which is what `generate_answer` reads.

### `_public_sources(sources)`

Returns `filename`, `location`, `chunk_index`, `score` rounded to 4 decimals or None, and `excerpt`. Full passage text is not included.

## `backend/desk/graph.py`

`graph` is the compiled graph, built at import.

### `fan_out(state)`

- `state`: the state after the librarian.

Returns two `Send` values, one for `reader` and one for `analyst`. The payload is a plain dict: question, top_k, search query, both need-flags, passages, revision, `revise` false, and `run_id`. Both agents always start.

`Send` is imported from `langgraph.types`, or from `langgraph.constants` if that import fails.

### `after_reviewer(state)`

- `state`: `revise`, `revision`.

Returns `librarian` when `revise` is true and `revision` is still 0. Otherwise returns `END`.

### `build_graph()`

Adds the five nodes. The reviewer is added with `defer=True` so it waits for the reader and the analyst. If the installed LangGraph rejects that argument, the node is added without it.

Edges: start to lead, lead to librarian, librarian through `fan_out` to reader and analyst, both of those to reviewer, reviewer through `after_reviewer` to librarian or end.

Returns the compiled graph.

### `stream_question(question, top_k)`

- `question` (str): stripped. Blank raises `ValueError` with `Question is empty.`
- `top_k` (int)

If `list_documents()` is empty, yields one result and does not start the graph:

`answer` is `No documents have been uploaded yet.`, `sources` and `trace` are empty.

Otherwise opens a run, starts `graph.invoke` on a daemon thread with `recursion_limit` 20, and yields each queue event until the thread puts `None`. Then closes the run.

If the thread stored an exception, yields `{type: error, error: message}` and stops. Otherwise yields `{type: result, answer, sources, trace}` from the final state. A missing answer becomes `I do not know based on the uploaded documents.`

### `_initial_state(question, top_k, run_id)`

Returns the dict passed to `invoke`: the question, top_k, search query equal to the question, both need-flags true, empty passages, claims, approved, rejected, sources, and trace, `revision` 0, `revise` false, `answer` `""`, and `run_id`.

## `backend/app.py`

Flask application object: `app`. JSON errors always look like `{"error": "..."}`.

CORS applies to `/api/*`. `CORS_ORIGINS=*` allows any origin. Any other value is split on commas.

`MAX_CONTENT_LENGTH` is `MAX_UPLOAD_MB` times 1024 times 1024.

### `_error(message, status)`

- `message` (str)
- `status` (int)

Returns a Flask response pair: JSON `{"error": message}` and the status code.

### `file_too_large(_error)`

Error handler for Werkzeug `RequestEntityTooLarge`. Returns HTTP 413 and `File is larger than N MB.`

### `root()`

`GET /`. Returns `{"service": "document-desk", "health": "/api/health"}`. This is only so a browser visit to the host is not an empty 404. The demo page does not call it.

### `health()`

`GET /api/health`. Calls `init_db()` so the data folder exists before the first upload. Returns status, provider, whether each key is non-empty, model ids, embedding dimension, chunk size, overlap, and top-k. Key values are never included. `chat_model` is the Groq model when the provider is `groq`, otherwise the Gemini chat model.

### `upload()`

`POST /api/upload`. Reads the multipart list named `file`. A missing list, or files with no name, returns HTTP 400.

For each file, the stored name is the base name only, so a path in the client filename cannot write outside the temp directory. The extension must be in `ALLOWED_EXTENSIONS`. The bytes go to a `NamedTemporaryFile` with that suffix, then `rag.ingest_file`. The temp file is removed in `finally`, including when ingest fails.

Any exception from one file is recorded in `errors` and the loop continues, so one bad file does not discard the others.

If nothing was saved, HTTP 400 with `error`, an empty `documents` list, and `errors`. If at least one file was saved, HTTP 201 with `documents` and `errors`. `errors` is an empty list when every file succeeded.

### `documents()`

`GET /api/documents`. Returns `{"documents": [...]}` from `list_documents`.

### `delete_document(document_id)`

`DELETE /api/documents/<document_id>`.

- `document_id` (str): path parameter.

HTTP 404 and `Document not found.` when `vector_store.delete_document` returns false. Otherwise `{"deleted": "<id>"}`.

### `ask()`

`POST /api/ask`. JSON body, parsed with `silent=True` so a bad body becomes `{}`.

- `question` (str): blank is HTTP 400, `Question is empty.`, before any stream starts.
- `top_k` (optional int): must be from 1 to 20. A non-integer is HTTP 400.

Otherwise the response is `text/event-stream`. Each yield is `data: ` plus one JSON object and a blank line. Headers include `Cache-Control: no-cache` and `X-Accel-Buffering: no`.

The generator iterates `rag.ask_stream`. An exception there becomes a final `data:` line with `type` `error`, because the HTTP status was already 200.

## `backend/wsgi.py`

Binds `application` to the Flask `app` object. PythonAnywhere’s WSGI file imports that name. There is no function in this module.
