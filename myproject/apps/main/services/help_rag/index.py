"""Build and read the single-file RescueBite help retrieval index."""

import hashlib
import json
import os
import tempfile
from pathlib import Path

from django.conf import settings

from .chunker import chunk_markdown, extract_pinned_limitations


SOURCE_PATH = Path(settings.BASE_DIR) / "RESCUEBITE_PRODUCT_CONTEXT.md"
DEFAULT_INDEX_PATH = Path(settings.BASE_DIR) / ".help_index" / "rescuebite_help_index.json"
INDEX_VERSION = 1


def source_sha256(source_path=SOURCE_PATH):
    return hashlib.sha256(Path(source_path).read_bytes()).hexdigest()


def build_index(source_path, index_path, embed_texts, embedding_model, batch_size=64):
    """Chunk and embed the source via injected ``embed_texts``; atomically save JSON."""
    source_path = Path(source_path)
    index_path = Path(index_path)
    markdown = source_path.read_text(encoding="utf-8")
    chunks = chunk_markdown(markdown)
    if not chunks:
        raise ValueError("The product context contains no indexable chunks.")

    vectors = []
    for start in range(0, len(chunks), batch_size):
        batch = chunks[start:start + batch_size]
        batch_vectors = embed_texts([chunk["text"] for chunk in batch])
        if len(batch_vectors) != len(batch):
            raise ValueError("Embedding response count did not match chunk count.")
        vectors.extend([[float(value) for value in vector] for vector in batch_vectors])

    artifact = {
        "version": INDEX_VERSION,
        "source_sha256": hashlib.sha256(source_path.read_bytes()).hexdigest(),
        "embedding_model": embedding_model,
        "limitations": extract_pinned_limitations(markdown),
        "chunks": chunks,
        "embeddings": vectors,
    }
    index_path.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w", encoding="utf-8", dir=index_path.parent,
            prefix=index_path.name + ".", suffix=".tmp", delete=False,
        ) as handle:
            temporary = Path(handle.name)
            json.dump(artifact, handle, ensure_ascii=False, separators=(",", ":"))
        os.replace(temporary, index_path)
    finally:
        if temporary is not None and temporary.exists():
            temporary.unlink()
    return artifact


def read_index(index_path):
    """Read and minimally validate an index artifact."""
    with Path(index_path).open(encoding="utf-8") as handle:
        artifact = json.load(handle)
    if artifact.get("version") != INDEX_VERSION:
        raise ValueError("Unsupported help index version.")
    chunks = artifact.get("chunks")
    embeddings = artifact.get("embeddings")
    if not isinstance(chunks, list) or not chunks or not isinstance(embeddings, list):
        raise ValueError("Help index is missing chunks or embeddings.")
    if len(chunks) != len(embeddings):
        raise ValueError("Help index chunks and embeddings have different lengths.")
    if not isinstance(artifact.get("limitations"), str):
        raise ValueError("Help index is missing pinned limitations.")
    return artifact


def check_index(index_path, source_path=SOURCE_PATH, embedding_model=None):
    """Raise if the index is absent, malformed, stale, or built with another model."""
    artifact = read_index(index_path)
    current_hash = source_sha256(source_path)
    if artifact.get("source_sha256") != current_hash:
        raise ValueError("Help index is stale: the product context hash has changed.")
    if embedding_model and artifact.get("embedding_model") != embedding_model:
        raise ValueError("Help index is stale: the embedding model has changed.")
    return artifact
