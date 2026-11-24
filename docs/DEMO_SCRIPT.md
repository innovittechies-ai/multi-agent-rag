# Demo script

About seven minutes. Have the page open, the API URL already connected, and two short files you have already tested: a written policy (PDF or Word) and a spreadsheet. The question that crosses both is the one you rehearse: "What does the policy require, and do the numbers meet it?"

Keep a second question the files cannot answer.

The right-hand column is the talk. The answer is the proof.

## 1. Name the team (45 seconds)

Point at `backend/desk/graph.py`.

"Upload is still extract, chunk, embed, store. A question is a graph. LangGraph only connects the nodes. There is no agent framework on top of it. Five functions. The lead plans. The librarian searches. The reader reads prose. The analyst reads rows. The reviewer is the only one allowed to let a sentence through."

## 2. Show the library (40 seconds)

The left column is the library. If the files are already there, say so. If you upload live, wait for the chunk counts.

"Those chunks are in SQLite. The vector database is `vector_store.py`: save, cosine similarity, delete. The original file is not kept."

## 3. Ask the crossing question (2 minutes)

Read the question, then submit. The agent column fills in order.

When the lead finishes: "That was one JSON call. It did not answer. It decided we need both the written file and the sheet, and it wrote the search query."

When the librarian finishes: "This node does not call a chat model. It embeds that query and runs cosine similarity. The summary counts written passages and sheet rows. Open `librarian.py` if someone asks where the retrieval is."

When reader and analyst finish: "These two start together. LangGraph `Send` does that, in `fan_out`. The reader never sees spreadsheet rows. The analyst never sees the PDF. If one of them says skipped, the question did not need that kind of file, or the search did not return one."

When the reviewer finishes: "It checks each claim against the passage. If it rejects something important, it may send the librarian back once. It will not loop a second time. The answer is written only from the claims it kept. The citations under the answer are those passages, with the cosine score."

## 4. Ask a question the files cannot answer (45 seconds)

"The same graph runs. If nothing survives the reviewer, the answer is the sentence 'I do not know based on the uploaded documents.' That path does not ask the model to improvise."

## 5. Where the key sits (20 seconds)

"The browser stores the server URL, not the Google key. The key is in `backend/.env`. Embeddings are `gemini-embedding-2`. Chat is `gemini-3.8-flash`, unless `LLM_PROVIDER` is `groq`, and then chat is `openai/gpt-oss-20b` while embeddings stay on Gemini."

## If something fails on stage

- Connect says the Google key is missing: the server `.env` was not loaded, or the web app was not reloaded after you edited it.
- A file fails with "No readable text": the PDF is a scan. Use the text-based file you rehearsed.
- The agent column stops on an error that mentions 429: the free-tier limit. Wait, then ask again with the shorter files.
- The page says it could not reach the server: the API URL, HTTPS, or `CORS_ORIGINS`. Connect does not call Google. Upload of a one-line text file does. Details are in [DEPLOY.md](DEPLOY.md).

## One sentence to end on

"The librarian finds passages. The specialists are not allowed to leave their file type. The reviewer is the only writer, and it can only write what those passages support."
