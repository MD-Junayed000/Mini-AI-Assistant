"""Recursive chunker — sentence-aware, character-bounded.

Splits text into chunks of roughly 800 characters with a 120-character
overlap, while trying to respect sentence and paragraph boundaries.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

_SENT_END = re.compile(r"(?<=[.!?])\s+|\n{2,}")
_SENT_BOUND = re.compile(r"(?<=[.!?])\s+")


@dataclass
class Chunk:
    text: str
    char_start: int
    char_end: int
    section: str | None


def _split_paragraphs(text: str) -> list[str]:
    parts = [p.strip() for p in text.split("\n\n") if p.strip()]
    return parts


def _split_sentences(para: str) -> list[str]:
    return [s.strip() for s in _SENT_BOUND.split(para) if s.strip()]


def chunk_text(
    text: str,
    chunk_size: int = 800,
    overlap: int = 120,
    section: str | None = None,
) -> list[Chunk]:
    """Recursive chunker.

    1. Split on blank lines into paragraphs.
    2. Pack sentences into chunks bounded by `chunk_size`.
    3. Overlap by `overlap` characters at the boundary.
    """
    chunks: list[Chunk] = []
    pos = 0
    for para in _split_paragraphs(text):
        para_start = text.find(para, pos)
        if para_start < 0:
            para_start = pos
        pos = para_start + len(para)

        buf: list[str] = []
        buf_len = 0
        for sent in _split_sentences(para):
            sent = sent.strip()
            if not sent:
                continue
            # If a single sentence exceeds chunk_size, hard-split it.
            if len(sent) > chunk_size:
                if buf:
                    chunks.append(_flush(buf, section))
                    buf, buf_len = [], 0
                for i in range(0, len(sent), chunk_size):
                    piece = sent[i : i + chunk_size]
                    chunks.append(
                        Chunk(
                            text=piece,
                            char_start=para_start + i,
                            char_end=para_start + i + len(piece),
                            section=section,
                        )
                    )
                continue
            if buf_len + len(sent) + 1 > chunk_size:
                chunks.append(_flush(buf, section))
                tail = chunks[-1].text[-overlap:] if overlap > 0 else ""
                buf, buf_len = [tail] if tail else [], len(tail)
                if tail:
                    buf.append(sent)
                    buf_len += len(sent) + 1
                else:
                    buf.append(sent)
                    buf_len += len(sent)
            else:
                buf.append(sent)
                buf_len += len(sent) + 1

        if buf:
            chunks.append(_flush(buf, section))

    return chunks


def _flush(buf: list[str], section: str | None) -> Chunk:
    text = " ".join(b for b in buf if b).strip()
    return Chunk(text=text, char_start=0, char_end=len(text), section=section)