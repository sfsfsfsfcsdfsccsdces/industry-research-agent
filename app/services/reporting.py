from __future__ import annotations

import re

from app.models import SourceDocument
from app.services.llm import OpenAICompatibleClient


def compress_context(sources: list[SourceDocument], char_limit: int) -> str:
    """Evidence-aware extractive compression that preserves citation anchors."""
    sections: list[str] = []
    budget = char_limit
    for item in sources:
        header = f"[{item.source_id}] {item.title}（可信度 {item.credibility_score:.2f}）\n"
        sentences = [s.strip() for s in re.split(r"(?<=[。！？.!?])\s*", item.content) if len(s.strip()) >= 12]
        chosen = " ".join(sentences[:5]) or item.content[:900]
        block = header + chosen[:1200]
        if len(block) > budget:
            block = block[:budget]
        if block:
            sections.append(block)
            budget -= len(block)
        if budget <= 0:
            break
    return "\n\n".join(sections)


def _extract_claims(source: SourceDocument, limit: int = 2) -> list[str]:
    sentences = [
        re.sub(r"\s+", " ", item).strip(" -#")
        for item in re.split(r"(?<=[。！？.!?])\s*|\n+", source.content)
    ]
    return [item for item in sentences if 28 <= len(item) <= 260][:limit]


class ReportWriter:
    def __init__(self, llm: OpenAICompatibleClient) -> None:
        self.llm = llm

    async def write(self, query: str, questions: list[str], context: str, sources: list[SourceDocument]) -> str:
        if self.llm.enabled:
            prompt = f"""调研目标：{query}
研究问题：{questions}
证据上下文：
{context}

请用中文生成专业、审慎的市场/竞品调研报告。必须包含执行摘要、研究范围与方法、市场与需求、竞品对比、机会与风险、落地建议、局限性。所有事实结论都必须使用 [S1] 格式引用，不要虚构证据。"""
            return await self.llm.complete("你是企业级调研报告撰写 Agent，只能基于提供的证据回答。", prompt)
        return self._write_demo(query, questions, sources)

    def _write_demo(self, query: str, questions: list[str], sources: list[SourceDocument]) -> str:
        source_refs = " ".join(f"[{item.source_id}]" for item in sources[:4]) or "[无来源]"
        claims: list[tuple[str, SourceDocument]] = []
        for source in sources[:8]:
            claims.extend((claim, source) for claim in _extract_claims(source, 2))

        def bullets(items: list[tuple[str, SourceDocument]], start: int, count: int) -> str:
            selected = items[start:start + count]
            if not selected:
                return "- 当前证据不足，建议补充官方材料和用户访谈。"
            return "\n".join(f"- {claim} [{source.source_id}]" for claim, source in selected)

        rows = []
        for source in sources[:5]:
            strength = _extract_claims(source, 1)
            rows.append(f"| {source.title[:24]} | {strength[0][:48] if strength else '需进一步核验'} | {source.credibility_score:.2f} | [{source.source_id}] |")
        table = "\n".join(rows) or "| 暂无 | 暂无 | 0.00 | - |"
        question_list = "\n".join(f"{index}. {question}" for index, question in enumerate(questions, 1))
        return f"""# {query}：智能调研报告

## 执行摘要

本报告围绕“{query}”完成了问题拆解、多源检索、来源去重、可信度评估和证据压缩。当前结论基于 {len(sources)} 个去重来源，主要证据覆盖产品定位、技术能力、部署方式与应用风险。综合证据表明，选型不应只比较功能数量，还应同时验证数据治理、集成成本、可运维性和实际业务闭环。{source_refs}

## 1. 研究范围与方法

本次调研由 Planner Agent 拆分为以下子问题：

{question_list}

系统对网页与本地资料执行混合检索，使用向量相关度、关键词匹配、来源可信度和跨来源支持度进行重排。演示模式使用内置样例资料，结论用于展示工作流，不能替代采购尽调。

## 2. 市场背景与核心需求

{bullets(claims, 0, 4)}

## 3. 竞品与方案对比

| 对象/来源 | 证据摘要 | 来源评分 | 引用 |
|---|---|---:|---|
{table}

从选型视角看，应优先建立统一评价口径：目标用户、核心流程覆盖率、模型与数据可控性、二次开发成本、部署方式、安全合规及持续运维成本。不同产品的公开定位不能直接等同于真实交付能力，需要通过 PoC 和用户访谈复核。{source_refs}

## 4. 机会与风险

### 机会

{bullets(claims, 4, 3)}

### 风险

- 公开资料可能存在营销偏差、版本滞后或统计口径不一致，应对关键结论进行至少两个独立来源的交叉验证。{source_refs}
- 大模型生成内容存在幻觉风险；平台通过强制引用、来源追踪和报告后置校验降低风险，但不能完全消除。
- 外部搜索、模型服务与向量库均可能发生超时或限流，生产部署需要配置重试、熔断、降级和成本告警。

## 5. 落地建议

1. **先定义决策问题**：明确本次研究最终支持技术选型、竞品策略还是市场进入判断，避免无限扩展检索范围。
2. **建立证据门槛**：关键数字只采用官方、监管、论文或两个独立来源共同支持的内容。
3. **执行小范围 PoC**：选择 2—3 个真实业务任务，对准确率、时延、集成工作量和总拥有成本进行量化验证。
4. **保留人工审核**：涉及采购、合规或战略决策时，由领域人员确认引用上下文和推论边界。

## 6. 局限性

本报告在演示模式下由本地样例资料生成，未进行实时互联网检索；来源评分是启发式信号，不代表权威评级。接入 Tavily 与真实模型后，可获得最新网页证据和更自然的综合分析，但仍需人工复核高风险决策。

## 参考来源

""" + "\n".join(
            f"- [{item.source_id}] [{item.title}]({item.url}) — 可信度 {item.credibility_score:.2f}，交叉支持 {item.cross_validation_count}"
            for item in sources
        )


def validate_citations(markdown: str, sources: list[SourceDocument]) -> tuple[str, list[str]]:
    valid = {item.source_id for item in sources}
    found = re.findall(r"\[(S\d+)\]", markdown)
    invalid = sorted(set(found) - valid)
    warnings: list[str] = []
    if invalid:
        warnings.append(f"发现无效引用：{', '.join(invalid)}")
        for citation in invalid:
            markdown = markdown.replace(f"[{citation}]", "[引用待核验]")
    if not found:
        warnings.append("报告未包含来源引用")
    return markdown, warnings
