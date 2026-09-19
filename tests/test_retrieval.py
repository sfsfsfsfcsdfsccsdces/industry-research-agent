from app.models import SourceDocument
from app.services.retrieval import ChromaVectorIndex, HybridReranker


def test_hybrid_reranker_prefers_query_match(tmp_path):
    docs = [
        SourceDocument(source_id="S1", title="RAG 检索", content="企业知识库采用向量检索和重排提升准确率", credibility_score=0.8),
        SourceDocument(source_id="S2", title="天气", content="今天阳光很好适合户外活动", credibility_score=0.8),
    ]
    ranker = HybridReranker(ChromaVectorIndex(tmp_path / "chroma", "test_rank"))
    result = ranker.rank("企业知识库 RAG 向量检索", docs)
    assert result[0].source_id == "S1"
    assert result[0].relevance_score > result[1].relevance_score


def test_hybrid_reranker_uses_chroma_query_results(tmp_path):
    class FakeCollection:
        def __init__(self):
            self.ids = []
            self.query_called = False

        def upsert(self, *, ids, documents, embeddings, metadatas):
            self.ids = ids

        def query(self, *, query_embeddings, n_results, where, include):
            self.query_called = True
            assert n_results == 2
            assert where == {"document_id": {"$in": self.ids}}
            assert include == ["distances"]
            return {"ids": [self.ids], "distances": [[0.9, 0.1]]}

    docs = [
        SourceDocument(source_id="S1", title="甲", content="完全无关的第一份资料", credibility_score=0.8),
        SourceDocument(source_id="S2", title="乙", content="完全无关的第二份资料", credibility_score=0.8),
    ]
    index = ChromaVectorIndex(tmp_path / "chroma", "test_chroma_query")
    fake_collection = FakeCollection()
    index._collection = fake_collection
    index.add(docs)

    result = HybridReranker(index).rank("不存在的查询词", docs)

    assert fake_collection.query_called is True
    assert index.last_query_backend == "chroma"
    assert result[0].source_id == "S2"
