"""Markdown chunking that preserves RescueBite section and heading context."""

import re


MAX_CHUNK_TOKENS = 500
TOKEN_RE = re.compile(r"[A-Za-z0-9_]+(?:[-/][A-Za-z0-9_]+)*|[^\w\s]", re.UNICODE)


def token_count(text):
    """Return a consistent rough token count without a tokenizer dependency."""
    return len(TOKEN_RE.findall(text))


def _excluded_section(heading):
    return bool(re.match(r"^\s*(?:15|16)(?:[.)\s])", heading))


def _atomic_units(lines):
    """Group paragraphs, complete tables, and fenced blocks as indivisible units."""
    units = []
    index = 0
    while index < len(lines):
        if not lines[index].strip():
            index += 1
            continue

        if lines[index].lstrip().startswith("```"):
            block = [lines[index]]
            index += 1
            while index < len(lines):
                block.append(lines[index])
                index += 1
                if block[-1].lstrip().startswith("```"):
                    break
            units.append("\n".join(block).strip())
            continue

        if lines[index].lstrip().startswith("|"):
            table = []
            while index < len(lines) and lines[index].lstrip().startswith("|"):
                table.append(lines[index])
                index += 1
            units.append("\n".join(table).strip())
            continue

        paragraph = []
        while (index < len(lines) and lines[index].strip()
               and not lines[index].lstrip().startswith(("```", "|"))):
            paragraph.append(lines[index])
            index += 1
        if paragraph:
            units.append("\n".join(paragraph).strip())
    return units


def _split_oversized(unit, available):
    """Split oversized prose/list units, preserving sentence and line boundaries."""
    if token_count(unit) <= available:
        return [unit]
    parts = re.split(r"(?<=[.!?])\s+|\n", unit)
    result = []
    current = []
    for part in parts:
        words = part.split()
        # A single long sentence/line is split by words as a final fallback.
        segments = []
        pending = []
        for word in words:
            if pending and token_count(" ".join(pending + [word])) > available:
                segments.append(" ".join(pending))
                pending = []
            pending.append(word)
        if pending:
            segments.append(" ".join(pending))
        for segment in segments:
            candidate = " ".join(current + [segment]).strip()
            if current and token_count(candidate) > available:
                result.append(" ".join(current).strip())
                current = [segment]
            else:
                current.append(segment)
    if current:
        result.append(" ".join(current).strip())
    return [item for item in result if item]


def chunk_markdown(markdown, max_tokens=MAX_CHUNK_TOKENS):
    """Return chunks with heading paths; FAQ headings each form their own chunk."""
    chunks = []
    root_heading = None
    subsection_heading = None
    excluded = False
    block_lines = []

    def flush_block():
        nonlocal block_lines
        if not root_heading or excluded:
            block_lines = []
            return
        path = " > ".join(
            heading for heading in (root_heading, subsection_heading) if heading
        )
        prefix = f"{path}\n\n"
        limit = max_tokens - token_count(prefix)
        current = []
        current_count = token_count(prefix)

        def flush_chunk():
            nonlocal current, current_count
            body = "\n\n".join(current).strip()
            text = f"{prefix}{body}".strip()
            if body and token_count(text) <= max_tokens:
                chunks.append({"section": path, "text": text})
            current = []
            current_count = token_count(prefix)

        for unit in _atomic_units(block_lines):
            if token_count(prefix + unit) > max_tokens and not unit.lstrip().startswith(("|", "```")):
                pieces = _split_oversized(unit, limit)
            else:
                pieces = [unit]
            for piece in pieces:
                piece_count = token_count(piece)
                if current and current_count + piece_count > max_tokens:
                    flush_chunk()
                current.append(piece)
                current_count += piece_count
        if current:
            flush_chunk()
        block_lines = []

    for line in markdown.splitlines():
        if line.startswith("## "):
            flush_block()
            root_heading = line[3:].strip()
            subsection_heading = None
            excluded = _excluded_section(root_heading)
            continue
        if line.startswith("### ") and root_heading:
            flush_block()
            subsection_heading = line[4:].strip()
            continue
        # Ignore introductory document prose before the first level-two heading.
        if root_heading:
            block_lines.append(line)

    flush_block()
    return chunks


def extract_pinned_limitations(markdown):
    """Extract section 15 prohibitions and section 16's explicit unknown list."""
    sections = {}
    current = None
    collected = []
    for line in markdown.splitlines():
        if line.startswith("## "):
            if current is not None:
                sections[current] = "\n".join(collected).strip()
            current = line[3:].strip()
            collected = []
        elif current is not None:
            collected.append(line)
    if current is not None:
        sections[current] = "\n".join(collected).strip()

    section15 = next((body for heading, body in sections.items()
                      if re.match(r"^15(?:[.)\s])", heading)), "")
    section16 = next((body for heading, body in sections.items()
                      if re.match(r"^16(?:[.)\s])", heading)), "")
    prohibited = re.search(
        r"(?m)^### The chatbot must not claim or assume\s*$([\s\S]*?)(?=^### |\Z)",
        section15,
    )
    unknown_lines = [
        line.strip() for line in section16.splitlines()
        if "Unknown / Not specified" in line
    ]
    parts = []
    if prohibited:
        parts.append("### The chatbot must not claim or assume\n" + prohibited.group(1).strip())
    if unknown_lines:
        parts.append("### Unknown / Not specified\n" + "\n".join(unknown_lines))
    return "\n\n".join(parts)
