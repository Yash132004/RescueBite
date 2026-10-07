"""Cosine and BM25 hybrid retrieval with reciprocal-rank fusion."""

import re

import numpy as np
from rank_bm25 import BM25Okapi


# Keep complete identifiers/statuses and their useful component words searchable.
IDENTIFIER_RE = re.compile(r"/?[A-Za-z0-9_]+(?:[-/][A-Za-z0-9_]+)*")
RRF_K = 60
TOP_K = 5
# Provisional and uncalibrated operating point for Gemini embeddings. Keep this
# value until eval_help_bot has real Gemini answerable/out-of-scope measurements.
RELEVANCE_THRESHOLD = 0.22


def tokenize(text):
    tokens = []
    for match in IDENTIFIER_RE.findall(text):
        value = match.lower().strip("/")
        if not value:
            continue
        tokens.append(value)
        components = re.split(r"[/]", value)
        for component in components:
            tokens.append(component)
            tokens.extend(part for part in component.split("-") if part)
    return tokens


def make_bm25(chunks):
    return BM25Okapi([tokenize(chunk["text"]) for chunk in chunks])


def retrieve(index, query, query_embedding, bm25=None, top_k=TOP_K):
    """Return top chunks by RRF and the strongest semantic similarity."""
    chunks = index["chunks"]
    vectors = np.asarray(index["embeddings"], dtype=float)
    query_vector = np.asarray(query_embedding, dtype=float)
    if vectors.ndim != 2 or query_vector.ndim != 1 or vectors.shape[1] != query_vector.shape[0]:
        raise ValueError("Query and stored embedding dimensions do not match.")
    if vectors.shape[0] != len(chunks):
        raise ValueError("Stored chunk and embedding counts do not match.")

    query_norm = float(np.linalg.norm(query_vector))
    if query_norm == 0:
        raise ValueError("Query embedding has zero length.")
    norms = np.linalg.norm(vectors, axis=1)
    similarities = np.divide(
        vectors @ query_vector,
        norms * query_norm,
        out=np.zeros(len(chunks), dtype=float),
        where=(norms * query_norm) != 0,
    )
    semantic_order = np.argsort(-similarities, kind="stable")

    bm25 = bm25 or make_bm25(chunks)
    lexical_scores = np.asarray(bm25.get_scores(tokenize(query)), dtype=float)
    lexical_order = np.argsort(-lexical_scores, kind="stable")

    fused = {}
    for rank, chunk_id in enumerate(semantic_order, start=1):
        fused[int(chunk_id)] = fused.get(int(chunk_id), 0.0) + 1.0 / (RRF_K + rank)
    for rank, chunk_id in enumerate(lexical_order, start=1):
        fused[int(chunk_id)] = fused.get(int(chunk_id), 0.0) + 1.0 / (RRF_K + rank)

    ranked_ids = sorted(fused, key=lambda chunk_id: (-fused[chunk_id], chunk_id))[:top_k]
    results = []
    for chunk_id in ranked_ids:
        results.append({
            **chunks[chunk_id],
            "cosine_similarity": float(similarities[chunk_id]),
            "rrf_score": fused[chunk_id],
        })
    return results, float(np.max(similarities))
