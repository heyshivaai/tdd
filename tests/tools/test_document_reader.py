import pytest
from pathlib import Path
from tools.document_reader import extract_text_from_pdf, chunk_text


def test_extract_text_returns_list_of_chunks(sample_pdf_path):
    result = extract_text_from_pdf(sample_pdf_path)
    assert isinstance(result, list)
    assert len(result) >= 1


def test_extract_text_chunk_has_required_fields(sample_pdf_path):
    result = extract_text_from_pdf(sample_pdf_path)
    chunk = result[0]
    assert "text" in chunk
    assert "source_doc" in chunk
    assert "chunk_index" in chunk
    assert "total_chunks" in chunk


def test_extract_text_source_doc_is_filename(sample_pdf_path):
    result = extract_text_from_pdf(sample_pdf_path)
    assert result[0]["source_doc"] == Path(sample_pdf_path).name


def test_chunk_text_respects_max_chars():
    long_text = "word " * 10000  # ~50,000 chars
    chunks = chunk_text(long_text, source_doc="test.pdf", max_chars=32000)
    for chunk in chunks:
        assert len(chunk["text"]) <= 32000


def test_chunk_text_preserves_all_content():
    text = "Hello world this is a test document."
    chunks = chunk_text(text, source_doc="test.pdf", max_chars=32000)
    combined = " ".join(c["text"] for c in chunks)
    for word in text.split():
        assert word in combined


def test_chunk_text_chunk_index_is_sequential():
    long_text = "x " * 20000
    chunks = chunk_text(long_text, source_doc="test.pdf", max_chars=5000)
    for i, chunk in enumerate(chunks):
        assert chunk["chunk_index"] == i
        assert chunk["total_chunks"] == len(chunks)


def test_extract_nonexistent_file_returns_empty_list():
    result = extract_text_from_pdf("/nonexistent/path/file.pdf")
    assert result == []
