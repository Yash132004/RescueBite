"""Retrieval-grounded, stateless RescueBite help assistant."""

import logging
import os
import re
import traceback
from pathlib import Path

from django.conf import settings

from .help_rag.index import DEFAULT_INDEX_PATH, SOURCE_PATH, check_index
from .help_rag.prompts import SYSTEM_INSTRUCTIONS, build_generation_input
from .help_rag.retrieval import RELEVANCE_THRESHOLD, make_bm25, retrieve


logger = logging.getLogger(__name__)
FALLBACK_MESSAGE = (
    "I'm currently unable to connect to the help service. You can still "
    "explore the application using the options on this page."
)
MAX_MESSAGE_LENGTH = 1200
OUT_OF_SCOPE_MESSAGE = (
    "The current RescueBite project doesn't specify that. I can help with "
    "what RescueBite is, its roles, registration and login, donating food, "
    "claiming donations, and volunteer delivery."
)

_INDEX_CACHE_LOADED = False
_INDEX_CACHE = None
_BM25_CACHE = None


def configured_index_path():
    """Allow a Django deployment setting to override the default artifact path."""
    return Path(getattr(settings, "HELP_RAG_INDEX_PATH", DEFAULT_INDEX_PATH))


def _load_index_once(index_path=None, source_path=SOURCE_PATH):
    global _INDEX_CACHE_LOADED, _INDEX_CACHE, _BM25_CACHE
    if _INDEX_CACHE_LOADED:
        return _INDEX_CACHE, _BM25_CACHE

    _INDEX_CACHE_LOADED = True
    path = Path(index_path or configured_index_path())
    try:
        expected_model = os.environ.get(
            "GEMINI_EMBEDDING_MODEL", "gemini-embedding-001"
        )
        artifact = check_index(path, source_path, expected_model)
        _INDEX_CACHE = artifact
        _BM25_CACHE = make_bm25(artifact["chunks"])
    except (OSError, ValueError, TypeError, KeyError) as error:
        logger.warning("RescueBite help index is unavailable (%s).", type(error).__name__)
        _INDEX_CACHE = None
        _BM25_CACHE = None
    return _INDEX_CACHE, _BM25_CACHE


def reset_index_cache():
    """Clear the process cache; exposed for deterministic tests and maintenance."""
    global _INDEX_CACHE_LOADED, _INDEX_CACHE, _BM25_CACHE
    _INDEX_CACHE_LOADED = False
    _INDEX_CACHE = None
    _BM25_CACHE = None


def ask_help(question):
    """Retrieve trusted product context and generate a short grounded answer."""
    if not isinstance(question, str) or not question.strip() or len(question.strip()) > MAX_MESSAGE_LENGTH:
        return FALLBACK_MESSAGE
    api_key = os.environ.get("GEMINI_API_KEY", "").strip()
    if not api_key:
        return FALLBACK_MESSAGE
    generation_model = os.environ.get("GEMINI_MODEL", "").strip()
    if not generation_model:
        logger.warning("RescueBite help request failed (GEMINI_MODEL is not configured).")
        return FALLBACK_MESSAGE

    try:
        stage = "index loading"
        index, bm25 = _load_index_once()
        if index is None:
            return FALLBACK_MESSAGE

        from openai import OpenAI

        client = OpenAI(
            api_key=api_key,
            base_url=os.environ.get(
                "GEMINI_BASE_URL", "https://generativelanguage.googleapis.com/v1beta/openai/"
            ),
            # Gemini 3 Flash may take longer than the previous 12-second limit.
            timeout=45,
            max_retries=0,
        )
        embedding_model = os.environ.get(
            "GEMINI_EMBEDDING_MODEL", "gemini-embedding-001"
        )
        stage = "question embedding"
        query_response = client.embeddings.create(
            model=embedding_model,
            input=question.strip(),
        )
        query_vector = query_response.data[0].embedding
        stage = "retrieval"
        retrieved, best_similarity = retrieve(index, question, query_vector, bm25=bm25)
        if best_similarity < RELEVANCE_THRESHOLD:
            return OUT_OF_SCOPE_MESSAGE

        prompt = build_generation_input(question.strip(), retrieved, index["limitations"])
        stage = "answer generation"
        generation_options = {
            "model": generation_model,
            "messages": [
                {"role": "system", "content": SYSTEM_INSTRUCTIONS},
                {"role": "user", "content": prompt},
            ],
            "max_tokens": 1200,
            # Gemini 3 does not support disabling thinking; low is supported and
            # avoids the default medium thinking latency for help-chat answers.
            "reasoning_effort": ("low" if "gemini-3" in generation_model else "none"),
        }
        # Gemini 3 is optimized for its default temperature; retain the prior
        # value only for Gemini 2.5 models.
        if "gemini-3" not in generation_model:
            generation_options["temperature"] = 0.1
        response = client.chat.completions.create(**generation_options)
        answer = response.choices[0].message.content
        if isinstance(answer, str) and answer.strip():
            return answer.strip()[:2000]
    except Exception as error:
        # Classify failures and retain a sanitized server-side diagnostic. Never
        # include the API key or the user's exact question in logs.
        status = getattr(error, "status_code", None)
        name = type(error).__name__.lower()
        if status == 429 or "ratelimit" in name:
            category = "rate limited"
        elif status == 401 or "authentication" in name:
            category = "auth failed"
        elif "timeout" in name:
            category = "timed out"
        elif "connection" in name:
            category = "network error"
        elif status == 403:
            category = "quota or permission error"
        elif status == 400:
            category = "request rejected"
        elif status == 404:
            category = "model or endpoint not found"
        elif status == 503:
            category = "service unavailable"
        elif status and status >= 500:
            category = "provider server error"
        else:
            category = "provider error"
        message = str(error) or "<no message>"
        for sensitive in (api_key, question.strip()):
            if sensitive:
                message = message.replace(sensitive, "[REDACTED]")
        message = re.sub(
            r"(?i)(bearer\s+)[^\s,;]+", r"\1[REDACTED]", message
        )
        message = re.sub(r"AIza[0-9A-Za-z_-]{20,}", "[REDACTED]", message)
        message = re.sub(
            r"(?i)(api[_ -]?key\s*[=:]\s*)[^\s,;]+", r"\1[REDACTED]", message
        )
        message = " ".join(message.split())[:500]
        frames = traceback.extract_tb(error.__traceback__)
        failure_location = (
            f"{Path(frames[-1].filename).name}:{frames[-1].lineno}"
            if frames else "unknown location"
        )
        app_frames = [frame for frame in frames if Path(frame.filename).name == "chatbot.py"]
        if app_frames:
            app_frame = app_frames[-1]
            location = f"{failure_location}; chatbot call {Path(app_frame.filename).name}:{app_frame.lineno}"
        else:
            location = failure_location
        diagnostic = f"{type(error).__name__}"
        if status:
            diagnostic += f" HTTP {status}"
        logger.warning(
            "RescueBite help request failed (%s during %s; %s; %s; at %s).",
            category,
            stage,
            diagnostic,
            message,
            location,
        )
    return FALLBACK_MESSAGE
