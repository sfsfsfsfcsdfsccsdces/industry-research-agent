from __future__ import annotations

from app.services.llm import OpenAICompatibleClient

DEFAULT_DIMENSIONS = [
    "市场背景、目标用户与核心需求是什么？",
    "主要参与者及各自的产品定位、核心能力是什么？",
    "各方案在功能、技术架构、部署和成本方面有何差异？",
    "当前市场机会、风险与发展趋势是什么？",
    "结合证据，应当如何选择并制定落地路线？",
]


class ResearchPlanner:
    def __init__(self, llm: OpenAICompatibleClient) -> None:
        self.llm = llm

    async def plan(self, query: str, max_questions: int) -> list[str]:
        if self.llm.enabled:
            result = await self.llm.complete_json(
                "你是企业市场研究规划师。将调研目标拆成互不重复、可检索、可验证的问题，只返回 JSON。",
                f'调研目标：{query}\n请返回 {max_questions} 个问题，格式：{{"questions":["..."]}}',
            )
            questions = [str(item).strip() for item in result.get("questions", []) if str(item).strip()]
        else:
            questions = [f"围绕“{query}”，{dimension}" for dimension in DEFAULT_DIMENSIONS]

        # Stable de-duplication prevents repeated searches and runaway graph loops.
        deduplicated: list[str] = []
        seen: set[str] = set()
        for question in questions:
            key = "".join(question.lower().split())
            if key not in seen:
                seen.add(key)
                deduplicated.append(question)
        return deduplicated[:max_questions]
