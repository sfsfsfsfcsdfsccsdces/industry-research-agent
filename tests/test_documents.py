from app.models import SourceDocument
from app.services.documents import chunk_document


def test_chunk_document_preserves_metadata_and_bounds():
    document = SourceDocument(title="长文档", content=("第一段是产品能力说明。" * 40) + "\n\n" + ("第二段是风险说明。" * 40), metadata={"owner": "demo"})
    chunks = chunk_document(document, chunk_size=180, overlap=20)
    assert len(chunks) > 2
    assert all(len(item.content) <= 180 for item in chunks)
    assert all(item.metadata["owner"] == "demo" for item in chunks)
