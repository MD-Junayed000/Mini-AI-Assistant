"""Chunker + ingester regression (Docling/RapidOCR/HF are integration-tested separately)."""
from backend.ingestion.chunker import chunk_text


def test_short_text_single_chunk():
    out = chunk_text("Hello world.")
    assert len(out) == 1
    assert out[0].text == "Hello world."


def test_long_text_splits_with_overlap():
    para = ("Sentence one. " * 50).strip()
    out = chunk_text(para, chunk_size=200, overlap=40)
    assert len(out) >= 2
    for c in out:
        assert len(c.text) <= 220


def test_paragraph_breaks_split():
    text = "Para one content.\n\nPara two content."
    out = chunk_text(text, chunk_size=100)
    texts = [c.text for c in out]
    assert any("Para one" in t for t in texts)
    assert any("Para two" in t for t in texts)


def test_section_attr_passes_through():
    out = chunk_text("Some text.", section="manual")
    assert out[0].section == "manual"


def test_unicode_handled():
    out = chunk_text("日本語と English mix. " * 20, chunk_size=80)
    assert all(c.text for c in out)
