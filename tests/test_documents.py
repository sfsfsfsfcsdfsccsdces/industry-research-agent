from app.models import SourceDocument
from app.services.documents import chunk_document, load_and_chunk_documents


def test_chunk_document_preserves_metadata_and_bounds():
    document = SourceDocument(title="长文档", content=("第一段是产品能力说明。" * 40) + "\n\n" + ("第二段是风险说明。" * 40), metadata={"owner": "demo"})
    chunks = chunk_document(document, chunk_size=180, overlap=20)
    assert len(chunks) > 2
    assert all(len(item.content) <= 180 for item in chunks)
    assert all(item.metadata["owner"] == "demo" for item in chunks)


def test_load_and_chunk_documents_chunks_files_before_retrieval(tmp_path):
    path = tmp_path / "long.md"
    path.write_text(("# 产品能力\n\n" + "知识库检索能力。" * 30) + ("\n\n# 风险\n\n" + "数据治理风险。" * 30), encoding="utf-8")

    chunks = load_and_chunk_documents([path], chunk_size=160, overlap=20)

    assert len(chunks) > 2
    assert all(len(item.content) <= 160 for item in chunks)
    assert all(item.metadata["path"] == str(path) for item in chunks)
    assert all(item.metadata["parent_title"] == "long" for item in chunks)
    assert [item.metadata["chunk_index"] for item in chunks] == list(range(len(chunks)))
