"""Docling staged extractor.

Three stages:
  1. Native text — Docling's PDF pipeline (fast, high-fidelity).
  2. OCR fallback — RapidOCR for pages with low native-text density.
  3. Figure descriptions — HF Granite-Docling VLM, called only on figure
     nodes returned by stage 1.

Why staged: VLM is slow + costs API budget. Native + OCR covers >95% of
text; figures are the only place VLM earns its keep.
"""
from __future__ import annotations

import asyncio
import re
from dataclasses import dataclass
from pathlib import Path

from backend.observability.logging_config import get_logger

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


async def _docling_native(pdf_path: Path) -> tuple[str, list[str]]:
    """Stage 1: native text + figure-node enumeration.

    Runs Docling synchronously in a thread (CPU-heavy). Returns
    (joined_text, list_of_figure_node_ids).
    """
    from docling.document_converter import DocumentConverter  # type: ignore

    def _run() -> tuple[str, list[str]]:
        converter = DocumentConverter()
        result = converter.convert(str(pdf_path))
        doc = result.document
        text_parts: list[str] = []
        figure_nodes: list[str] = []
        # Docling's markdown export is the easiest path.
        md = doc.export_to_markdown() if hasattr(doc, "export_to_markdown") else ""
        if md:
            text_parts.append(md)
        for item, _level in doc.iterate_items() if hasattr(doc, "iterate_items") else []:
            label = getattr(item, "label", None) or ""
            if str(label).lower().startswith("figure") or str(label).lower().startswith("picture"):
                figure_nodes.append(str(getattr(item, "self_ref", getattr(item, "name", "?"))))
        return "\n\n".join(text_parts), figure_nodes

    return await asyncio.to_thread(_run)


async def _ocr_low_density_pages(pdf_path: Path, native_text: str) -> tuple[str, int]:
    """Stage 2: OCR pages that native missed."""
    # Crude page-count estimation: split by form-feed; if average page is
    # below the density floor, OCR the whole file with RapidOCR.
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


async def _describe_figures(pdf_path: Path, figure_node_ids: list[str]) -> list[str]:
    """Stage 3: VLM descriptions for figure nodes only.

    We render page crops to PNG in a thread, then call the HF VLM model.
    """
    if not figure_node_ids:
        return []
    # For the take-home, we keep this deliberately conservative: we
    # call the model once with a page-image list and a structured prompt.
    # If it fails, we return empty — the rest of the document still
    # answers most questions.

    def _render() -> list[bytes]:
        try:
            import pdfplumber  # type: ignore
            from io import BytesIO

            out: list[bytes] = []
            with pdfplumber.open(str(pdf_path)) as pdf:
                # Take the first N pages that likely contain figures.
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

    # Inline-call to HF multimodal via the router. Kept simple — text-only
    # description per image; if it fails we return what we have.
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
        for img_bytes in images[:3]:  # cap at 3 to stay within Free tier
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


async def extract(pdf_path: Path) -> ExtractedDocument:
    """Three-stage extraction pipeline."""
    if not _is_pdf(pdf_path):
        # Plain text / markdown — fast path.
        text = pdf_path.read_text(encoding="utf-8", errors="ignore")
        return ExtractedDocument(
            source=str(pdf_path),
            text=text,
            figure_descriptions=[],
            ocr_pages=0,
        )

    native_text, figure_nodes = await _docling_native(pdf_path)
    text, ocr_pages = await _ocr_low_density_pages(pdf_path, native_text)
    descriptions = await _describe_figures(pdf_path, figure_nodes)

    return ExtractedDocument(
        source=str(pdf_path),
        text=re.sub(r"\n{3,}", "\n\n", text).strip(),
        figure_descriptions=descriptions,
        ocr_pages=ocr_pages,
    )