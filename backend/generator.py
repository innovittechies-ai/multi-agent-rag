"""Chat calls for the document desk.

``generate_answer`` writes the final prose answer from approved passages.
``complete_json`` is what the lead, reader, analyst, and reviewer use when
they need a JSON object instead of a paragraph.

``LLM_PROVIDER=gemini`` calls ``gemini-3.8-flash``.
``LLM_PROVIDER=groq`` calls Groq's OpenAI-compatible chat endpoint.
Embeddings always stay on Gemini. Groq is only a chat provider.
"""

import json

import requests

import config


class GeneratorError(RuntimeError):
    """The chat API refused the request or returned no text."""


SYSTEM_PROMPT = (
    "You answer questions for a document demo. Use only the passages in the "
    "user message. When you state a fact, name the source file. If the "
    "passages do not contain the answer, say you do not know based on the "
    "uploaded documents. Do not invent numbers, dates, or names."
)


def build_prompt(question, sources):
    """Assemble the user message: numbered passages, then the question.

    Parameters
    ----------
    question : str
    sources : list of dict
        Each dict needs ``filename``, ``location``, and ``text``. These are
        the chunks returned by ``vector_store.search``.

    Returns
    -------
    str
    """
    blocks = []
    for index, source in enumerate(sources, start=1):
        location = source.get("location") or "unknown location"
        blocks.append(
            "[{0}] file: {1} | {2}\n{3}".format(
                index, source["filename"], location, source["text"]
            )
        )
    passages = "\n\n".join(blocks)
    return (
        "Passages:\n{0}\n\nQuestion: {1}\n\n"
        "Answer using only these passages."
    ).format(passages, question.strip())


def generate_answer(question, sources):
    """Call the configured chat provider and return the answer text.

    Parameters
    ----------
    question : str
    sources : list of dict
        Passed to ``build_prompt``. Each dict needs ``filename``,
        ``location``, and ``text``.

    Returns
    -------
    str
    """
    prompt = build_prompt(question, sources)
    return _complete(SYSTEM_PROMPT, prompt, json_mode=False)


def complete_json(system, user):
    """Ask the chat model for one JSON object and parse it.

    Parameters
    ----------
    system : str
        Role instruction. The model is told to return JSON only.
    user : str
        The question, passages, or claims for this call.

    Returns
    -------
    dict

    Raises
    ------
    GeneratorError
        The provider failed, or the text was not a JSON object.
    """
    text = _complete(system, user, json_mode=True)
    return parse_json_object(text)


def parse_json_object(text):
    """Pull the first JSON object out of a model reply.

    Parameters
    ----------
    text : str
        Raw model text. Markdown fences are stripped. If the model adds a
        sentence around the object, the slice from the first ``{`` to the
        last ``}`` is parsed.

    Returns
    -------
    dict

    Raises
    ------
    GeneratorError
        No object was found, the JSON is invalid, or the value is not an object.
    """
    raw = (text or "").strip()
    if raw.startswith("```"):
        lines = raw.splitlines()
        lines = lines[1:]
        if lines and lines[-1].strip().startswith("```"):
            lines = lines[:-1]
        raw = "\n".join(lines).strip()
    start = raw.find("{")
    end = raw.rfind("}")
    if start < 0 or end <= start:
        raise GeneratorError("The model did not return JSON.")
    try:
        value = json.loads(raw[start : end + 1])
    except json.JSONDecodeError as exc:
        raise GeneratorError("The model returned invalid JSON.") from exc
    if not isinstance(value, dict):
        raise GeneratorError("The model did not return a JSON object.")
    return value


def _complete(system, user, json_mode):
    """Dispatch one chat call to Gemini or Groq.

    Parameters
    ----------
    system : str
    user : str
    json_mode : bool
        When True, ask the provider for a JSON response. A 400 caused by that
        flag is retried once without it. ``parse_json_object`` still runs.

    Returns
    -------
    str
    """
    provider = config.LLM_PROVIDER
    if provider == "gemini":
        return _gemini(user, system=system, json_mode=json_mode)
    if provider == "groq":
        return _groq(user, system=system, json_mode=json_mode)
    raise GeneratorError(
        "LLM_PROVIDER must be 'gemini' or 'groq'. It is '{0}'.".format(provider)
    )


def _gemini(prompt, system=None, json_mode=False):
    """POST ``generateContent`` to the Gemini chat model.

    ``GEMINI_THINKING_LEVEL`` is sent as ``thinkingConfig.thinkingLevel`` so
    a live demo does not wait on a long hidden reasoning pass. Set that
    variable to ``off`` to omit the field.

    The call is retried without JSON mode, and then without thinking, when
    Google responds with HTTP 400.

    Parameters
    ----------
    prompt : str
        User message.
    system : str or None
        Defaults to ``SYSTEM_PROMPT``.
    json_mode : bool
        Adds ``generationConfig.responseMimeType = application/json``.
    """
    if not config.GOOGLE_API_KEY:
        raise GeneratorError(
            "GOOGLE_API_KEY is not set. Add it to backend/.env on the server."
        )
    if system is None:
        system = SYSTEM_PROMPT
    url = (
        "https://generativelanguage.googleapis.com/v1beta/models/{0}:generateContent"
    ).format(config.GEMINI_CHAT_MODEL)
    attempts = [(True, json_mode)]
    if json_mode:
        attempts.append((True, False))
    attempts.append((False, False))
    response = None
    seen = set()
    for include_thinking, as_json in attempts:
        key = (include_thinking, as_json)
        if key in seen:
            continue
        seen.add(key)
        response = _post_json(
            url,
            {"x-goog-api-key": config.GOOGLE_API_KEY},
            _gemini_body(prompt, include_thinking, system, as_json),
        )
        if response.status_code == 200:
            return _gemini_text(response.json())
        if response.status_code != 400:
            break
    raise GeneratorError(_http_error("Gemini", response))


def _gemini_body(prompt, include_thinking, system=None, json_mode=False):
    """Build the ``generateContent`` JSON body.

    Parameters
    ----------
    prompt : str
        The user message.
    include_thinking : bool
        When True and ``GEMINI_THINKING_LEVEL`` is not ``off``, add
        ``thinkingConfig.thinkingLevel``.
    system : str or None
        System instruction. Defaults to ``SYSTEM_PROMPT``.
    json_mode : bool
        When True, set ``responseMimeType`` to ``application/json``.

    Returns
    -------
    dict
    """
    if system is None:
        system = SYSTEM_PROMPT
    generation = {"temperature": 0.2}
    level = config.GEMINI_THINKING_LEVEL.lower()
    if include_thinking and level and level != "off":
        generation["thinkingConfig"] = {"thinkingLevel": level}
    if json_mode:
        generation["responseMimeType"] = "application/json"
    return {
        "systemInstruction": {"parts": [{"text": system}]},
        "contents": [{"role": "user", "parts": [{"text": prompt}]}],
        "generationConfig": generation,
    }


def _gemini_text(payload):
    """Join the visible answer parts and skip hidden thought parts."""
    candidates = payload.get("candidates") or []
    if not candidates:
        raise GeneratorError("Gemini returned no candidates.")
    parts = ((candidates[0].get("content") or {}).get("parts")) or []
    texts = []
    for part in parts:
        if part.get("thought"):
            continue
        text = part.get("text")
        if text:
            texts.append(text)
    answer = "\n".join(texts).strip()
    if not answer:
        raise GeneratorError("Gemini returned an empty answer.")
    return answer


def _groq(prompt, system=None, json_mode=False):
    """POST a chat completion to Groq.

    Groq uses the same JSON shape as OpenAI's chat completions API.
    The model id defaults to ``openai/gpt-oss-20b``.

    Parameters
    ----------
    prompt : str
    system : str or None
        Defaults to ``SYSTEM_PROMPT``.
    json_mode : bool
        When True, send ``response_format: json_object``. A 400 is retried
        once without that field.
    """
    if not config.GROQ_API_KEY:
        raise GeneratorError(
            "GROQ_API_KEY is not set, and LLM_PROVIDER is groq."
        )
    if system is None:
        system = SYSTEM_PROMPT
    response = _groq_post(prompt, system, json_mode)
    if response.status_code == 400 and json_mode:
        response = _groq_post(prompt, system, False)
    if response.status_code != 200:
        raise GeneratorError(_http_error("Groq", response))
    payload = response.json()
    choices = payload.get("choices") or []
    if not choices:
        raise GeneratorError("Groq returned no choices.")
    answer = ((choices[0].get("message") or {}).get("content") or "").strip()
    if not answer:
        raise GeneratorError("Groq returned an empty answer.")
    return answer


def _groq_post(prompt, system, json_mode):
    """POST one Groq chat completion and return the response object.

    Parameters
    ----------
    prompt : str
    system : str
    json_mode : bool

    Returns
    -------
    requests.Response
    """
    body = {
        "model": config.GROQ_CHAT_MODEL,
        "temperature": 0.2,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": prompt},
        ],
    }
    if json_mode:
        body["response_format"] = {"type": "json_object"}
    return requests.post(
        "https://api.groq.com/openai/v1/chat/completions",
        headers={
            "Content-Type": "application/json",
            "Authorization": "Bearer {0}".format(config.GROQ_API_KEY),
        },
        json=body,
        timeout=config.REQUEST_TIMEOUT_SECONDS,
    )


def _post_json(url, extra_headers, body):
    """POST JSON and return the ``requests`` response without raising.

    Parameters
    ----------
    url : str
    extra_headers : dict
        Added on top of ``Content-Type: application/json``.
    body : dict
        Sent as JSON.

    Returns
    -------
    requests.Response
    """
    headers = {"Content-Type": "application/json"}
    headers.update(extra_headers)
    return requests.post(
        url,
        headers=headers,
        json=body,
        timeout=config.REQUEST_TIMEOUT_SECONDS,
    )


def _http_error(name, response):
    """Short error string with the HTTP status and a clipped body."""
    detail = response.text.strip().replace("\n", " ")
    if len(detail) > 300:
        detail = detail[:300] + "..."
    return "{0} returned HTTP {1}: {2}".format(name, response.status_code, detail)
