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
