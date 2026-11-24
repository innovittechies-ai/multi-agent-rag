# Install on a local computer

Use this on a machine that can install software. The presentation laptop does not need these packages. Nothing in this file installs software by itself. You run the commands.

You need two things running at once:

1. The Python API, from the `backend` folder, on port 8000.
2. The browser page, from the `frontend` folder, on port 5500.

The page is plain HTML. It does not use Node, npm, or a build step.

## What the computer must already have

- Windows 10 or 11, macOS, or Linux.
- Python 3.10 or newer. Python 3.11 or 3.12 is the comfortable choice. LangGraph and this project both expect 3.10 or above.
- `pip`, which comes with that Python.
- A browser.
- Outbound HTTPS to `generativelanguage.googleapis.com`. That is Google AI Studio. If you later set `LLM_PROVIDER=groq`, the computer also needs HTTPS to `api.groq.com`.
- About 500 MB free disk for the virtual environment. `langgraph` also installs `langchain-core`. That is expected. The desk does not use LangChain agents or a separate vector database.

Check the Python version before you create the environment.

Windows PowerShell:

```powershell
py -3 --version
```

If `py` is not recognized, try:

```powershell
python --version
```

macOS or Linux:

```bash
python3 --version
```

You want a line like `Python 3.11.9`. If the number starts with 3.9 or lower, install a newer Python from [python.org](https://www.python.org/downloads/) and open a new terminal. On Windows, the installer should include "Add python.exe to PATH" and pip.

## 1. Copy the project

Put the whole project folder on that computer. The folder must contain `backend` and `frontend` side by side. These steps call that folder the project root. On Windows an example path is `C:\rag-arch`. On macOS or Linux an example is `~/rag-arch`.

Open a terminal in the project root.

## 2. Create a virtual environment

Stay in the project root. A virtual environment keeps these packages off the rest of the computer.

Windows PowerShell:

```powershell
py -3 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
```

If PowerShell refuses to run the activate script, run this once, then try activate again:

```powershell
Set-ExecutionPolicy -Scope CurrentUser RemoteSigned
```

You can also skip activate and call the environment Python by its full path in the later steps: `.\.venv\Scripts\python.exe`.

macOS or Linux:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
```

The terminal prompt usually starts with `(.venv)` after activate. Every later `python` and `pip` command in this guide assumes that environment is active.

## 3. Install the Python packages

From the project root, with the environment active:

Windows PowerShell:

```powershell
python -m pip install -r backend\requirements.txt
```

macOS or Linux:

```bash
python -m pip install -r backend/requirements.txt
```

That file installs Flask, Flask-CORS, pypdf, python-docx, openpyxl, requests, and langgraph. Wait until pip exits with no error. Then confirm the imports:

```bash
python -c "import flask, langgraph, pypdf, docx, openpyxl, requests; print('packages ok')"
```

`packages ok` means the install worked. This check does not call Google and does not need an API key.

## 4. Add the API key

Create the env file.

Windows PowerShell, from the project root:

```powershell
Copy-Item backend\.env.example backend\.env
notepad backend\.env
```

macOS or Linux:

```bash
cp backend/.env.example backend/.env
```

Open `backend/.env` in any editor. Set this line to the key from [Google AI Studio](https://aistudio.google.com/apikey):

```
GOOGLE_API_KEY=paste-the-key-here
```

Leave the rest of the file as copied, unless you want the optional changes below. Do not put quotes around the key. Do not commit `backend/.env`. It is listed in `.gitignore`.

For a local browser page, this line can stay as it is:

```
CORS_ORIGINS=*
```

That allows `http://127.0.0.1:5500` to call `http://127.0.0.1:8000`.

Optional. Answers stay on Gemini until you change both of these. Embeddings still use the Google key.

```
LLM_PROVIDER=groq
GROQ_API_KEY=paste-the-groq-key-here
```

The Groq key comes from [the Groq console](https://console.groq.com/keys).

The other settings and what they do:

| Setting | Default | What it changes |
| --- | --- | --- |
| `LLM_PROVIDER` | `gemini` | `gemini` or `groq`. Groq is only the chat step. |
| `GEMINI_CHAT_MODEL` | `gemini-3.8-flash` | Chat model when the provider is Gemini. |
| `GEMINI_EMBED_MODEL` | `gemini-embedding-2` | Embedding model. Do not use `text-embedding-004`. It was shut down. |
| `GEMINI_THINKING_LEVEL` | `low` | `low`, `medium`, `high`, or `off`. `low` returns faster in a demo. |
| `GROQ_CHAT_MODEL` | `openai/gpt-oss-20b` | Chat model when the provider is Groq. |
| `EMBED_DIM` | `768` | Length of each stored vector. If you change it, delete the uploaded files and upload them again. |
| `CHUNK_SIZE` | `800` | Maximum characters in one chunk. |
| `CHUNK_OVERLAP` | `120` | Characters repeated between neighboring chunks. |
| `TOP_K` | `4` | How many passages of each kind a specialist may read. |
| `MAX_UPLOAD_MB` | `10` | Largest upload, in megabytes. |
| `DATA_DIR` | unset | Folder for `rag.sqlite`. When unset, the file is `backend/data/rag.sqlite`. |

## 5. Start the API

Open a terminal in the project root, activate the virtual environment the same way as in step 2, then change into `backend`. The app imports `config`, `rag`, and `desk` as top-level modules, so the working directory must be `backend`.

Windows PowerShell:

```powershell
cd backend
python -m flask --app app run --host 127.0.0.1 --port 8000
```

macOS or Linux:

```bash
cd backend
python -m flask --app app run --host 127.0.0.1 --port 8000
```

Leave this terminal open. A ready server prints a line like:

```
Running on http://127.0.0.1:8000
```

In a second terminal, still with nothing else required:

```bash
curl http://127.0.0.1:8000/api/health
```

Windows PowerShell can use the same `curl` if it is installed, or:

```powershell
Invoke-RestMethod http://127.0.0.1:8000/api/health
```

A good response has `"status": "ok"` and `"google_key_set": true`. The key itself is not in the response. `"google_key_set": false` means `backend/.env` is missing, the key line is empty, or you started Flask from a directory other than `backend`.

The first health check also creates `backend/data/rag.sqlite`.

## 6. Start the page

Open a third terminal, or reuse the second one. You do not need the virtual environment for this. Python's standard library can serve the folder.

Windows PowerShell, from the project root:

```powershell
cd frontend
python -m http.server 5500
```

If that `python` is not the one inside `.venv`, use the full path, or any Python 3:

```powershell
py -3 -m http.server 5500
```

macOS or Linux, from the project root:

```bash
cd frontend
python3 -m http.server 5500
```

Leave this terminal open. In the browser, open:

```
http://127.0.0.1:5500
```

Do not open `frontend/index.html` as a file. A `file://` page is blocked from calling `http://127.0.0.1:8000`.

On the page:

1. In the API field, enter `http://127.0.0.1:8000` with no slash at the end.
2. Click **Connect**. The status line should say the Google key is set, then `gemini / gemini-3.8-flash` unless you switched the provider.
3. Under **Library**, add a short PDF or Word file and a short `.xlsx` file. Text files (`.txt`) also work. Old `.doc` and `.xls` files do not. A scanned PDF, which is a photo of a page, has no text and will be rejected.
4. Ask: `What does the policy require, and do the numbers meet it?` Use a question your own files can answer.

The right-hand column fills as each agent finishes: Lead, Librarian, Reader, Analyst, Reviewer. The center shows the answer and the citations. One question is several calls to Google, so the first ask can take a while. Keep the sample files short.

## 7. Stop it

In the API terminal and the page terminal, press Ctrl+C. The uploaded text stays in `backend/data/rag.sqlite` and is still there the next time you start the API. Deleting that file clears the library.

## If something fails

**`py` or `python` is not recognized.** Install Python 3.10 or newer and open a new terminal. On Windows, re-run the installer and choose "Add python.exe to PATH".

**`No module named flask` or `No module named langgraph`.** The virtual environment is not active in that terminal, or pip was run from a different folder. Activate `.venv` again and run the pip command from the project root.

**Flask says the address is already in use.** Another program has port 8000. Stop that program, or start Flask on 8001 and type `http://127.0.0.1:8001` in the page's API field. Do the same for port 5500 if the page server cannot start.

**Connect says it could not reach the server.** The API terminal must still be running, and the API field must be `http://127.0.0.1:8000` with no path and no trailing slash. The page must be opened as `http://127.0.0.1:5500`, not as a file.

**Health shows the Google key is missing.** `backend/.env` must sit next to `app.py`. The line must be `GOOGLE_API_KEY=` followed by the key, with no spaces and no quotes. Restart Flask after you save the file. Flask reads the file when the process starts.

**Upload returns a message about no readable text.** The PDF is a scan, or the file is empty. Use a PDF that you can copy text out of, a `.docx`, a `.xlsx`, or a `.txt`.

**Upload or Ask returns HTTP 429, or the agent column stops with a rate-limit error.** The free Gemini quota is exhausted for the moment. Wait and try a shorter file. Each chunk is one embedding call during upload. Each question is several chat calls.

**Ask returns a network error that names `generativelanguage.googleapis.com`.** This computer cannot reach Google. Check the firewall, the proxy, and that the key is a Google AI Studio key.

**You changed `EMBED_DIM`, `CHUNK_SIZE`, or `CHUNK_OVERLAP` after uploading.** Delete those files in the library and upload them again. Old vectors were built with the previous settings.
