const API_KEY = "rag-api-base";

const NAMES = {
  lead: "Lead",
  librarian: "Librarian",
  reader: "Reader",
  analyst: "Analyst",
  reviewer: "Reviewer",
};

const apiBaseInput = document.querySelector("#api-base");
const healthNode = document.querySelector("#health");
const uploadStatus = document.querySelector("#upload-status");
const askStatus = document.querySelector("#ask-status");
const documentsNode = document.querySelector("#documents");
const answerNode = document.querySelector("#answer");
const emptyAnswer = document.querySelector("#empty-answer");
const answerText = document.querySelector("#answer-text");
const sourcesNode = document.querySelector("#sources");
const traceNode = document.querySelector("#trace");

let traceRows = [];

apiBaseInput.value = localStorage.getItem(API_KEY) || "";

document.querySelector("#settings-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  const base = normalizeBase(apiBaseInput.value);
  apiBaseInput.value = base;
  localStorage.setItem(API_KEY, base);
  await checkHealth();
  await loadDocuments();
});

document.querySelector("#upload-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  const input = document.querySelector("#file");
  if (!input.files.length) {
    setNote(uploadStatus, "Choose a file first.", true);
    return;
  }
  const body = new FormData();
  for (const file of input.files) {
    body.append("file", file, file.name);
  }
  setNote(uploadStatus, "Indexing…");
  setBusy(event.target, true);
  try {
    const payload = await requestJson("/api/upload", { method: "POST", body });
    const saved = (payload.documents || []).length;
    const failed = payload.errors || [];
    if (!saved && payload.error) {
      setNote(uploadStatus, payload.error, true);
    } else if (failed.length) {
      setNote(uploadStatus, "Saved " + saved + ". " + failed.map(formatUploadError).join(" "), true);
    } else {
      setNote(uploadStatus, "Saved " + saved + " file" + (saved === 1 ? "" : "s") + ".");
    }
    input.value = "";
    await loadDocuments();
  } catch (error) {
    setNote(uploadStatus, error.message, true);
  } finally {
    setBusy(event.target, false);
  }
});

document.querySelector("#ask-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  const question = document.querySelector("#question").value.trim();
  traceRows = [];
  renderTrace();
  answerNode.hidden = true;
  emptyAnswer.hidden = true;
  sourcesNode.replaceChildren();
  setNote(askStatus, "The desk is working.");
  setBusy(event.target, true);
  try {
    await ask(question);
    setNote(askStatus, "");
  } catch (error) {
    setNote(askStatus, error.message, true);
    if (answerNode.hidden) emptyAnswer.hidden = false;
  } finally {
    setBusy(event.target, false);
  }
});

if (apiBaseInput.value) {
  checkHealth().then(loadDocuments);
} else {
  renderDocuments([]);
  renderTrace();
}

function normalizeBase(value) {
  return value.trim().replace(/\/+$/, "");
}

function baseUrl() {
  const base = normalizeBase(apiBaseInput.value);
  if (!base) throw new Error("Connect an API URL first.");
  return base;
}

async function checkHealth() {
  healthNode.className = "health";
  healthNode.textContent = "Connecting…";
  try {
    const payload = await requestJson("/api/health");
    const key = payload.google_key_set ? "Google key is set" : "Google key is missing";
    healthNode.textContent = "Connected. " + key + ". " + payload.llm_provider + " / " + payload.chat_model + ".";
    healthNode.classList.add("ok");
  } catch (error) {
    healthNode.textContent = error.message;
    healthNode.classList.add("bad");
  }
}

async function loadDocuments() {
  try {
    const payload = await requestJson("/api/documents");
    renderDocuments(payload.documents || []);
  } catch (error) {
    documentsNode.replaceChildren();
    const item = document.createElement("li");
    item.textContent = error.message;
    documentsNode.append(item);
  }
}

function renderDocuments(documents) {
  documentsNode.replaceChildren();
  if (!documents.length) {
    const item = document.createElement("li");
    item.textContent = "No files in the library.";
    documentsNode.append(item);
    return;
  }
  for (const doc of documents) {
    const item = document.createElement("li");
    const row = document.createElement("div");
    row.className = "file-row";
    const copy = document.createElement("p");
    const name = document.createElement("strong");
    name.textContent = doc.filename;
    const meta = document.createElement("small");
    meta.textContent = fileKind(doc.filetype) + " · " + doc.chunk_count + " chunks";
    copy.append(name, meta);
    const button = document.createElement("button");
    button.type = "button";
    button.className = "text";
    button.textContent = "Remove";
    button.addEventListener("click", () => removeDocument(doc.id, button));
    row.append(copy, button);
    item.append(row);
    documentsNode.append(item);
  }
}

async function removeDocument(id, button) {
  button.disabled = true;
  try {
    await requestJson("/api/documents/" + encodeURIComponent(id), { method: "DELETE" });
    await loadDocuments();
  } catch (error) {
    setNote(uploadStatus, error.message, true);
    button.disabled = false;
  }
}

async function ask(question) {
  const response = await fetch(baseUrl() + "/api/ask", {
    method: "POST",
    headers: { "Content-Type": "application/json", Accept: "text/event-stream" },
    body: JSON.stringify({ question }),
  });
  const type = response.headers.get("content-type") || "";
  if (!response.ok) {
    let payload = {};
    try { payload = await response.json(); } catch (_error) { payload = {}; }
    throw new Error(payload.error || ("Request failed (" + response.status + ")."));
  }
  if (!response.body || type.indexOf("text/event-stream") === -1) {
    const payload = await response.json();
    applyResult(payload);
    return;
  }
  await readStream(response);
}

async function readStream(response) {
  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  let sawResult = false;
  while (true) {
    const step = await reader.read();
    if (step.done) break;
    buffer += decoder.decode(step.value, { stream: true });
    buffer = buffer.replace(/\r\n/g, "\n").replace(/\r/g, "\n");
    const parts = buffer.split("\n\n");
    buffer = parts.pop();
    for (const part of parts) {
      const event = parseEvent(part);
      if (!event) continue;
      if (applyEvent(event)) sawResult = true;
    }
  }
  if (buffer.trim()) {
    const event = parseEvent(buffer) || parseBareJson(buffer);
    if (event && applyEvent(event)) sawResult = true;
  }
  if (!sawResult) throw new Error("The desk ended without an answer.");
}

function parseEvent(block) {
  const lines = block.split("\n").filter((line) => line.startsWith("data:"));
  if (!lines.length) return parseBareJson(block);
  const raw = lines.map((line) => line.slice(5).trim()).join("\n");
  return parseBareJson(raw);
}

function parseBareJson(raw) {
  const text = (raw || "").trim();
  if (!text || text.charAt(0) !== "{") return null;
  try { return JSON.parse(text); } catch (_error) { return null; }
}

function applyEvent(event) {
  if (event.type === "agent") {
    onAgent(event);
    return false;
  }
  if (event.type === "error") throw new Error(event.error || "The desk failed.");
  if (event.type === "result" || event.answer) {
    applyResult(event);
    return true;
  }
  return false;
}

function onAgent(event) {
  const last = traceRows[traceRows.length - 1];
  if (last && last.agent === event.name && last.status === "running" && event.status !== "running") {
    last.status = event.status;
    last.summary = event.summary || "";
  } else {
    traceRows.push({
      agent: event.name,
      status: event.status,
      summary: event.summary || "",
    });
  }
  renderTrace();
}

function applyResult(event) {
  if (Array.isArray(event.trace) && event.trace.length) {
    traceRows = event.trace.map((item) => ({
      agent: item.agent || item.name,
      status: item.status,
      summary: item.summary || "",
    }));
    renderTrace();
  }
  answerText.textContent = event.answer || "";
  sourcesNode.replaceChildren();
  const sources = event.sources || [];
  if (!sources.length) {
    const item = document.createElement("li");
    item.className = "sources-empty";
    item.textContent = "No citations.";
    sourcesNode.append(item);
  } else {
    for (const source of sources) {
      const item = document.createElement("li");
      const title = document.createElement("strong");
      const score = source.score == null ? "" : " · " + source.score;
      title.textContent = source.filename + " · " + (source.location || "passage") + score;
      const excerpt = document.createElement("p");
      excerpt.textContent = source.excerpt || "";
      item.append(title, excerpt);
      sourcesNode.append(item);
    }
  }
  emptyAnswer.hidden = true;
  answerNode.hidden = false;
}

function renderTrace() {
  traceNode.replaceChildren();
  if (!traceRows.length) {
    const item = document.createElement("li");
    item.textContent = "The team appears here after you ask.";
    traceNode.append(item);
    return;
  }
  for (const row of traceRows) {
    const item = document.createElement("li");
    item.className = row.status || "";
    const top = document.createElement("div");
    top.className = "trace-top";
    const name = document.createElement("strong");
    name.textContent = NAMES[row.agent] || row.agent;
    const status = document.createElement("span");
    status.className = "status " + (row.status || "");
    status.textContent = statusLabel(row.status);
    top.append(name, status);
    item.append(top);
    if (row.summary) {
      const summary = document.createElement("p");
      summary.textContent = row.summary;
      item.append(summary);
    }
    traceNode.append(item);
  }
}

async function requestJson(path, options) {
  let response;
  try {
    response = await fetch(baseUrl() + path, options);
  } catch (_error) {
    throw new Error("Could not reach the server. Check the API URL, and that the server allows this page's origin.");
  }
  let payload = {};
  try { payload = await response.json(); } catch (_error) { payload = {}; }
  if (!response.ok) throw new Error(payload.error || ("Request failed (" + response.status + ")."));
  return payload;
}

function formatUploadError(item) {
  return item.filename + ": " + item.error;
}

function fileKind(filetype) {
  if (filetype === ".pdf") return "PDF";
  if (filetype === ".docx") return "Word";
  if (filetype === ".xlsx") return "Excel";
  if (filetype === ".txt") return "Text";
  return filetype || "File";
}

function statusLabel(status) {
  if (status === "running") return "Running";
  if (status === "skipped") return "Skipped";
  if (status === "done") return "Done";
  return status || "";
}

function setNote(node, message, isError) {
  node.textContent = message;
  node.classList.toggle("bad", Boolean(isError));
}

function setBusy(form, busy) {
  const button = form.querySelector("button[type='submit']");
  if (button) button.disabled = busy;
}
