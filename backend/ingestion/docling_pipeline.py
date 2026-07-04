"""PDF/text extraction pipeline with a docling-first, pure-Python-fallback strategy.

Docling gives the highest-quality structured output (native text + figure-node
enumeration + layout awareness), but it pulls in `torch` as a dependency. On
Windows the torch runtime DLLs (`c10.dll`) frequently fail to initialize with
`OSError: [WinError 1114]`, taking the whole ingest endpoint down with a 500.

This module guards the docling import and falls back to pdfplumber whenever
docling (or any of its transitive deps) fails to load. pdfplumber is pure
Python (no torch), produces acceptable text for most search-style retrieval,
and is already in requirements.txt for the figure-render step.

Stages:
  1. Native text — docling when available, otherwise pdfplumber.
  2. OCR fallback — RapidOCR for low-text-density PDFs.
  3. Figure descriptions — best-effort; skipped if docling isn't available.
"""
from __future__ import annotations

import asyncio
import logging
import os
import re
from dataclasses import dataclass
from pathlib import Path

from backend.observability.logging_config import get_logger

# Docling imports torch, which on Windows frequently prints noisy DLL init
# errors to stderr even when the import ultimately succeeds. Quiet those down
# so the CLI surface stays readable on every `python -m backend.ingestion.pipeline`
# run; the probe below will still tell us whether the backend is usable.
os.environ.setdefault("TRANSFORMERS_VERBOSITY", "error")
os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")
logging.getLogger("torch").setLevel(logging.ERROR)
logging.getLogger("transformers").setLevel(logging.ERROR)

log = get_logger("ingest")


@dataclass
class ExtractedDocument:
    source: str
    text: str
    figure_descriptions: list[str]
    ocr_pages: int


_TEXT_DENSITY_FLOOR = 80  # chars per page; below this → OCR fallback


def _is_pdf(p: Path) -> bool:
    return p.suffix.lower() == ".pdf"


# ---------------------------------------------------------------------------
# Docling availability probe — cached at module import.
# ---------------------------------------------------------------------------
_DOCLING_AVAILABLE: bool | None = None
_DOCLING_ERROR: str | None = None


def _probe_docling() -> tuple[bool, str | None]:
    """Try importing docling. Returns (available, error_message)."""
    global _DOCLING_AVAILABLE, _DOCLING_ERROR
    if _DOCLING_AVAILABLE is not None:
        return _DOCLING_AVAILABLE, _DOCLING_ERROR
    try:
        import docling.document_converter  # noqa: F401
        _DOCLING_AVAILABLE = True
        log.info("docling_backend", status="available")
        return True, None
    except Exception as exc:  # noqa: BLE001 — any import failure
        _DOCLING_AVAILABLE = False
        _DOCLING_ERROR = f"{type(exc).__name__}: {exc}"
        log.info("docling_backend_unavailable", error=_DOCLING_ERROR)
        return False, _DOCLING_ERROR


# ---------------------------------------------------------------------------
# Stage 1: native text + figure-node enumeration.
# ---------------------------------------------------------------------------
async def _docling_native(pdf_path: Path) -> tuple[str, list[str]]:
    """Stage 1 (docling branch). Returns (joined_text, list_of_figure_node_ids)."""
    from docling.document_converter import DocumentConverter  # type: ignore

    def _run() -> tuple[str, list[str]]:
        converter = DocumentConverter()
        result = converter.convert(str(pdf_path))
        doc = result.document
        text_parts: list[str] = []
        figure_nodes: list[str] = []
        md = doc.export_to_markdown() if hasattr(doc, "export_to_markdown") else ""
        if md:
            text_parts.append(md)
        if hasattr(doc, "iterate_items"):
            for item, _level in doc.iterate_items():
                label = getattr(item, "label", None) or ""
                if str(label).lower().startswith("figure") or str(label).lower().startswith("picture"):
                    figure_nodes.append(str(getattr(item, "self_ref", getattr(item, "name", "?"))))
        return "\n\n".join(text_parts), figure_nodes

    return await asyncio.to_thread(_run)


async def _pdfplumber_native(pdf_path: Path) -> tuple[str, list[str]]:
    """Stage 1 (pure-Python fallback). Returns (joined_text, empty_figure_list)."""

    def _run() -> tuple[str, list[str]]:
        import pdfplumber  # type: ignore

        parts: list[str] = []
        with pdfplumber.open(str(pdf_path)) as pdf:
            for i, page in enumerate(pdf.pages, start=1):
                page_text = page.extract_text() or ""
                if page_text.strip():
                    parts.append(f"## Page {i}\n\n{page_text.strip()}")
        return "\n\n".join(parts), []

    return await asyncio.to_thread(_run)


async def _extract_native(pdf_path: Path) -> tuple[str, list[str]]:
    """Pick the best native extractor available."""
    available, err = _probe_docling()
    if available:
        try:
            return await _docling_native(pdf_path)
        except Exception as exc:  # noqa: BLE001
            log.warning("docling_extract_failed_falling_back", error=str(exc))
    else:
        log.info("using_pdfplumber_backend", reason=err)
    return await _pdfplumber_native(pdf_path)


# ---------------------------------------------------------------------------
# Stage 2: OCR for low-text-density PDFs.
# ---------------------------------------------------------------------------
async def _ocr_low_density_pages(pdf_path: Path, native_text: str) -> tuple[str, int]:
    """Stage 2: OCR pages that native missed."""
    try:
        pages = native_text.split("\f") if "\f" in native_text else native_text.split("\n\n")
    except Exception:  # noqa: BLE001
        pages = [native_text]

    if pages and (sum(len(p) for p in pages) / max(len(pages), 1)) > _TEXT_DENSITY_FLOOR:
        return native_text, 0

    def _ocr() -> str:
        try:
            from rapidocr_onnxruntime import RapidOCR  # type: ignore

            engine = RapidOCR()
            result, _elapsed = engine(str(pdf_path))
            if not result:
                return native_text
            lines = [r[1] for r in result if len(r) >= 2]
            return (native_text + "\n\n" + "\n".join(lines)).strip()
        except Exception as e:  # noqa: BLE001
            log.warning("ocr_failed", error=str(e))
            return native_text

    return await asyncio.to_thread(_ocr), len(pages)


# ---------------------------------------------------------------------------
# Stage 3: VLM descriptions for figure nodes (best-effort).
# ---------------------------------------------------------------------------
async def _describe_figures(pdf_path: Path, figure_node_ids: list[str]) -> list[str]:
    """Stage 3: VLM descriptions for figure nodes only.

    Skipped entirely if docling isn't available (we can't enumerate figures
    without it). Otherwise renders page crops to PNG and calls the HF VLM.
    """
    if not figure_node_ids:
        return []
    if not _probe_docling()[0]:
        return []

    def _render() -> list[bytes]:
        try:
            import pdfplumber  # type: ignore
            from io import BytesIO

            out: list[bytes] = []
            with pdfplumber.open(str(pdf_path)) as pdf:
                for page in pdf.pages[: max(1, len(figure_node_ids))]:
                    img = page.to_image(resolution=144)
                    buf = BytesIO()
                    img.original.save(buf, format="PNG")
                    out.append(buf.getvalue())
            return out
        except Exception as e:  # noqa: BLE001
            log.warning("figure_render_failed", error=str(e))
            return []

    images = await asyncio.to_thread(_render)
    if not images:
        return []

    import base64
    import httpx

    from backend.config import get_settings

    s = get_settings()
    headers = {
        "Authorization": f"Bearer {s.hf_inference_api_key}",
        "Content-Type": "application/json",
    }
    descriptions: list[str] = []
    timeout = 60
    async with httpx.AsyncClient(timeout=timeout) as cx:
        for img_bytes in images[:3]:  # cap at 3 to stay within free tier
            payload = {
                "model": s.hf_vision_model,
                "messages": [
                    {
                        "role": "user",
                        "content": [
                            {"type": "text", "text": "Describe this figure in one short sentence."},
                            {
                                "type": "image_url",
                                "image_url": {"url": f"data:image/png;base64,{base64.b64encode(img_bytes).decode()}"},
                            },
                        ],
                    }
                ],
                "max_tokens": 120,
            }
            try:
                r = await cx.post(
                    f"{s.hf_inference_base_url.rstrip('/')}/chat/completions",
                    headers=headers,
                    json=payload,
                )
                r.raise_for_status()
                desc = r.json()["choices"][0]["message"]["content"]
                descriptions.append(desc.strip())
            except Exception as e:  # noqa: BLE001
                log.warning("vlm_failed", error=str(e))
    return descriptions


# ---------------------------------------------------------------------------
# Public entrypoint.
# ---------------------------------------------------------------------------
async def extract(pdf_path: Path) -> ExtractedDocument:
    """Three-stage extraction pipeline.

    Always succeeds for non-PDF inputs. For PDFs, returns whatever text the
    best available backend can produce — never raises on backend failure
    (the goal is to keep /ingest working even when docling is broken).
    """
    doc, _backend, _reason = await extract_with_backend(pdf_path)
    return doc


async def extract_with_backend(
    pdf_path: Path,
) -> tuple[ExtractedDocument, str, str | None]:
    """Like `extract` but also reports which backend was used.

    Returns (ExtractedDocument, backend_name, fallback_reason_or_None).
    `backend_name` is one of: "docling", "pdfplumber", "plaintext".
    `fallback_reason` is None when docling succeeded; otherwise it's a
    short machine-readable code describing why docling was skipped
    (e.g. "docling_dll_unavailable").
    """
    if not _is_pdf(pdf_path):
        # Plain text / markdown — fast path.
        text = pdf_path.read_text(encoding="utf-8", errors="ignore")
        return (
            ExtractedDocument(
                source=str(pdf_path),
                text=text,
                figure_descriptions=[],
                ocr_pages=0,
            ),
            "plaintext",
            None,
        )

    available, probe_err = _probe_docling()
    fallback_reason: str | None = None
    if not available:
        # Translate the most common probe error into a stable code so the
        # UI can show "indexed with pdfplumber (docling unavailable)".
        if probe_err and ("WinError 1114" in probe_err or "DLL" in probe_err):
            fallback_reason = "docling_dll_unavailable"
        else:
            fallback_reason = "docling_unavailable"

    try:
        if available:
            try:
                native_text, figure_nodes = await _docling_native(pdf_path)
                backend_used = "docling"
            except Exception as inner:  # noqa: BLE001
                # Docling loaded but failed on this specific file (e.g. a
                # corrupt page). Fall back to pdfplumber rather than 500.
                log.warning(
                    "docling_runtime_failed_falling_back", error=str(inner)[:200]
                )
                fallback_reason = "docling_runtime_failed"
                native_text, figure_nodes = await _pdfplumber_native(pdf_path)
                backend_used = "pdfplumber"
        else:
            native_text, figure_nodes = await _pdfplumber_native(pdf_path)
            backend_used = "pdfplumber"
    except Exception as exc:  # noqa: BLE001
        log.error("all_pdf_extractors_failed", error=str(exc))
        return (
            ExtractedDocument(
                source=str(pdf_path),
                text="",
                figure_descriptions=[],
                ocr_pages=0,
            ),
            "none",
            "all_extractors_failed",
        )

    text, ocr_pages = await _ocr_low_density_pages(pdf_path, native_text)
    descriptions = await _describe_figures(pdf_path, figure_nodes)

    return (
        ExtractedDocument(
            source=str(pdf_path),
            text=re.sub(r"\n{3,}", "\n\n", text).strip(),
            figure_descriptions=descriptions,
            ocr_pages=ocr_pages,
        ),
        backend_used,
        fallback_reason,
    )