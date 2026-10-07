import os
import re
import time
import traceback
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from apps.main.services.help_rag.index import (
    DEFAULT_INDEX_PATH,
    SOURCE_PATH,
    build_index,
    check_index,
)


class Command(BaseCommand):
    help = "Build or verify the local retrieval index for the RescueBite help assistant."

    def add_arguments(self, parser):
        parser.add_argument(
            "--check", action="store_true",
            help="Fail if the index is missing or stale compared with the source document.",
        )
        parser.add_argument(
            "--path", type=Path,
            help="Index artifact path (default: HELP_RAG_INDEX_PATH or the local .help_index directory).",
        )

    def handle(self, *args, **options):
        index_path = options["path"] or Path(
            getattr(settings, "HELP_RAG_INDEX_PATH", DEFAULT_INDEX_PATH)
        )
        if options["check"]:
            try:
                model = os.environ.get(
                    "GEMINI_EMBEDDING_MODEL", "gemini-embedding-001"
                )
                artifact = check_index(index_path, SOURCE_PATH, model)
            except (OSError, ValueError, TypeError, KeyError) as error:
                raise CommandError(str(error)) from error
            self.stdout.write(self.style.SUCCESS(
                f"Help index is current ({len(artifact['chunks'])} chunks): {index_path}"
            ))
            return

        api_key = os.environ.get("GEMINI_API_KEY", "").strip()
        if not api_key:
            raise CommandError("Set GEMINI_API_KEY before building the help index.")
        model = os.environ.get("GEMINI_EMBEDDING_MODEL", "gemini-embedding-001")
        base_url = os.environ.get(
            "GEMINI_BASE_URL", "https://generativelanguage.googleapis.com/v1beta/openai/"
        )

        try:
            from openai import OpenAI

            client = OpenAI(api_key=api_key, base_url=base_url, timeout=30, max_retries=0)

            def embed_texts(texts):
                for attempt in range(4):
                    try:
                        response = client.embeddings.create(model=model, input=texts)
                        break
                    except Exception as error:
                        is_rate_limit = (
                            getattr(error, "status_code", None) == 429
                            or "ratelimit" in type(error).__name__.lower()
                        )
                        if not is_rate_limit or attempt == 3:
                            raise
                        time.sleep(2 ** attempt)
                # Gemini's compatibility endpoint can omit OpenAI's optional
                # per-item index. In that case response order matches input order.
                items = list(response.data)
                indices = [getattr(item, "index", None) for item in items]
                if all(isinstance(index, int) for index in indices):
                    items.sort(key=lambda item: item.index)
                return [item.embedding for item in items]

            artifact = build_index(SOURCE_PATH, index_path, embed_texts, model, batch_size=8)
        except Exception as error:
            category = "rate limited" if getattr(error, "status_code", None) == 429 else type(error).__name__
            message = str(error) or "<no message>"
            if api_key:
                message = message.replace(api_key, "[REDACTED]")
            message = re.sub(
                r"(?i)(bearer\s+)[^\s,;]+", r"\1[REDACTED]", message
            )
            message = re.sub(r"AIza[0-9A-Za-z_-]{20,}", "[REDACTED]", message)
            message = re.sub(
                r"(?i)(api[_ -]?key\s*[=:]\s*)[^\s,;]+", r"\1[REDACTED]", message
            )
            message = " ".join(message.split())[:300]
            frames = traceback.extract_tb(error.__traceback__)
            location = (
                f"{Path(frames[-1].filename).name}:{frames[-1].lineno}"
                if frames else "unknown location"
            )
            raise CommandError(
                f"Could not build the help index ({category}: {message}; at {location}); "
                "check Gemini access, quota, and source configuration."
            ) from error

        self.stdout.write(self.style.SUCCESS(
            f"Built help index with {len(artifact['chunks'])} chunks at {index_path}"
        ))
