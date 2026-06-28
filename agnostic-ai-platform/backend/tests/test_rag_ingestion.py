from __future__ import annotations

from fastapi.testclient import TestClient

from app.auth import create_access_token
from app.main import create_app
from app.rag_ingestion import clean_text, chunk_loaded_pages, load_document


def auth_headers() -> dict[str, str]:
    token = create_access_token(user_id="user-1", role="admin", tenant_id="tenant-1")
    return {"Authorization": f"Bearer {token}"}


def test_clean_text_normalizes_whitespace() -> None:
    assert clean_text("hello\t world\r\n\r\n\r\nnext") == "hello world\n\nnext"


def test_text_loader_and_chunker_extract_metadata() -> None:
    pages = load_document(content=b"alpha beta gamma delta", filename="notes.md")
    chunks = chunk_loaded_pages(pages, chunk_size=10, chunk_overlap=2)

    assert chunks
    assert chunks[0].text == "alpha beta"
    assert chunks[0].metadata["filename"] == "notes.md"
    assert chunks[0].metadata["page"] == 1
    assert chunks[0].metadata["source"] == "notes.md"
    assert chunks[1].text.startswith("ta")


def test_ingest_endpoint_accepts_batch_txt_and_markdown() -> None:
    client = TestClient(create_app())

    response = client.post(
        "/v1/documents/ingest",
        headers=auth_headers(),
        data={"chunk_size": "100", "chunk_overlap": "10"},
        files=[
            ("files", ("first.txt", b"first document text", "text/plain")),
            ("files", ("second.md", b"# Title\n\nsecond document text", "text/markdown")),
        ],
    )

    assert response.status_code == 200
    body = response.json()
    assert body["total_documents"] == 2
    assert body["total_chunks"] == 2
    assert body["chunk_size"] == 100
    assert body["chunk_overlap"] == 10
    assert body["documents"][0]["filename"] == "first.txt"
    assert body["documents"][0]["chunks"][0]["metadata"]["source"] == "first.txt"


def test_ingest_endpoint_rejects_unsupported_type() -> None:
    client = TestClient(create_app())

    response = client.post(
        "/v1/documents/ingest",
        headers=auth_headers(),
        files=[("files", ("data.csv", b"a,b\n1,2", "text/csv"))],
    )

    assert response.status_code == 415
    assert "unsupported document type" in response.json()["detail"]


def test_ingest_endpoint_validates_overlap() -> None:
    client = TestClient(create_app())

    response = client.post(
        "/v1/documents/ingest",
        headers=auth_headers(),
        data={"chunk_size": "100", "chunk_overlap": "100"},
        files=[("files", ("first.txt", b"first document text", "text/plain"))],
    )

    assert response.status_code == 422
    assert response.json()["detail"] == "chunk_overlap must be smaller than chunk_size"
