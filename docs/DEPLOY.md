# Deploy

Install packages on the server, not on the presentation computer. The page on Vercel is only HTML, CSS, and JavaScript.

You need a host that can open outbound HTTPS to:

- `generativelanguage.googleapis.com` (embeddings, and answers if you stay on Gemini)
- `api.groq.com` (only if `LLM_PROVIDER=groq`)

PythonAnywhere’s free plan often blocks those hosts. If upload or ask fails with a network error there, use any small host that allows outbound HTTPS. A small AWS instance is enough. The same Flask app runs in either place.

## 1. Keys

Gemini, required: [Google AI Studio API keys](https://aistudio.google.com/apikey). Put it in `GOOGLE_API_KEY`.

Groq, optional: [Groq console keys](https://console.groq.com/keys). Leave `LLM_PROVIDER` as `gemini` until you want the Groq answer path. Then set `LLM_PROVIDER=groq` and `GROQ_API_KEY`. Embeddings still use the Google key.

## 2. Files on the server

Copy this repository to the server. From the `backend` directory:

```bash
python -m pip install -r requirements.txt
cp .env.example .env
```

Edit `.env` and set `GOOGLE_API_KEY`. The other settings and their defaults are listed in [BACKEND_GUIDE.md](BACKEND_GUIDE.md).

`pip install -r requirements.txt` also installs `langgraph`. That package brings `langchain-core`. The desk uses `StateGraph` only. It does not use LangChain agents, tools, or a vector-store integration.

A question that needs both a written file and a spreadsheet is several model calls, plus one embedding call. Use a short PDF and a short sheet in the live demo so the free tier and the room can wait.

After you know the Vercel URL, set:

```
CORS_ORIGINS=https://your-demo.vercel.app
```

`*` works for a rehearsal. A specific origin is better once the page is public, so random sites cannot call your server from a browser.

## 3. PythonAnywhere

Create a new web app, manual configuration, Python 3.10 or newer. The virtualenv should have the packages from `requirements.txt` installed.

The source lives at something like `/home/YOUR_USERNAME/rag-arch/backend`.

Open the WSGI file PythonAnywhere generated and replace its contents with:

```python
import sys
sys.path.insert(0, "/home/YOUR_USERNAME/rag-arch/backend")
from wsgi import application
```

`backend/wsgi.py` exposes `application`, which is the Flask app. Reload the web app on the PythonAnywhere Web tab.

Visit `https://YOUR_USERNAME.pythonanywhere.com/api/health`. You want `"status": "ok"` and `"google_key_set": true`.

Free PythonAnywhere accounts have a small daily CPU allowance. Embedding a long file spends that allowance, because each chunk is one outbound call plus the SQLite write. For the talk, use a short PDF or a small spreadsheet.

## 4. Any other Python host, including a small AWS instance

From `backend`, with `.env` filled in:

```bash
python -m pip install -r requirements.txt
flask --app app run --host 0.0.0.0 --port 8000
```

Open the port on the instance security group. Put the process behind a process manager if you want it to survive logout. HTTPS can be a reverse proxy, or the platform’s load balancer. The browser page should call the HTTPS URL, because a Vercel page is HTTPS and browsers block requests from it to a plain HTTP API.

Health check: `https://your-host/api/health`.

SQLite is a file on that machine (`backend/data/rag.sqlite`). It survives a process restart. It does not survive a new disk. Upload the demo files again if you rebuild the machine. Do not run two copies of the app against one SQLite file.

## 5. Vercel

In the Vercel project, set the root directory to `frontend`. [frontend/vercel.json](../frontend/vercel.json) sets no framework and no build command, and serves that folder as-is.

Deploy. You get a URL like `https://your-demo.vercel.app`.

Open it. Paste the backend base URL, without a trailing slash, into the API field. Click **Connect**. The status line should say the Google key is set and name the chat model. That URL is stored in the browser only.

If the status says the server could not be reached, the usual causes are:

- the API URL is wrong or still uses `http://` from an HTTPS page
- the host cannot be contacted from the public internet
- `CORS_ORIGINS` is set to a different Vercel URL than the one in the address bar
- PythonAnywhere blocked the outbound call, and even `/api/health` is fine while upload is not. Health does not call Google. Try an upload of a one-line `.txt` file. If that returns a network error from inside the JSON `error` field, the host cannot reach Gemini.

## 6. Rehearse the data

Upload the policy file and the spreadsheet once before the talk. Ask the question you plan to show, and one the files cannot answer. The second should produce `I do not know based on the uploaded documents.` Leave those files in SQLite if you want the library already filled when you walk on.

## Switching the answer model during a rehearsal

Change `LLM_PROVIDER` and reload the process (or reload the PythonAnywhere web app). You do not re-upload. Stored vectors stay valid because embeddings did not change. You do re-upload if you change `GEMINI_EMBED_MODEL`, `EMBED_DIM`, `CHUNK_SIZE`, or `CHUNK_OVERLAP`.
