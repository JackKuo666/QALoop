"""LLM 服务模块 - 封装 LLM API 调用逻辑"""

from typing import Any

import httpx
from sqlalchemy.orm import Session

from qa_annotate.database.crud import SystemConfigCRUD

LLM_CONFIG_KEYS = {
    "api_key": "llm_api_key",
    "base_url": "llm_base_url",
    "model_name": "llm_model_name",
}


def get_llm_config(db: Session) -> dict[str, str | None]:
    """从 SystemConfig 读取 LLM 配置

    Returns:
        dict: 包含 api_key, base_url, model_name 的字典
    """
    config = {}
    for field, key in LLM_CONFIG_KEYS.items():
        record = SystemConfigCRUD.get_by_key(db, key=key)
        config[field] = record.value if record else None
    return config


async def call_llm_chat(
    api_key: str,
    base_url: str,
    model_name: str,
    system_prompt: str,
    user_message: str,
) -> str:
    """调用 OpenAI 兼容的 Chat Completions API

    Args:
        api_key: API Key
        base_url: API Base URL（如 https://api.openai.com/v1）
        model_name: 模型名称
        system_prompt: 系统提示词
        user_message: 用户消息

    Returns:
        str: LLM 返回的文本内容

    Raises:
        httpx.HTTPStatusError: API 返回非 2xx 状态码
        httpx.TimeoutException: 请求超时
    """
    url = f"{base_url.rstrip('/')}/chat/completions"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    payload: dict[str, Any] = {
        "model": model_name,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_message},
        ],
        "temperature": 0.7,
        "max_tokens": 4096,
    }

    async with httpx.AsyncClient(timeout=180.0) as client:
        try:
            response = await client.post(url, json=payload, headers=headers)
            response.raise_for_status()
        except httpx.TimeoutException as e:
            raise RuntimeError(f"请求超时（180秒）：{e}") from e
        except httpx.HTTPStatusError as e:
            detail = ""
            try:
                detail = e.response.text
            except Exception:
                pass
            raise RuntimeError(
                f"HTTP {e.response.status_code}: {detail}"
            ) from e
        except httpx.RequestError as e:
            raise RuntimeError(f"网络请求失败：{e}") from e

        data = response.json()
        return data["choices"][0]["message"]["content"]


def _format_stats_section(stats: dict) -> str:
    """将项目统计信息格式化为文本"""
    lines = ["## 项目标注统计概览", ""]

    # 总体统计
    lines.append("### 总体数据")
    lines.append(f"- 数据集数量：{stats.get('total_datasets', 0)}")
    lines.append(f"- QA 对总数：{stats.get('total_items', 0)}")
    lines.append(f"- 已标注 QA 对（至少1个配置）：{stats.get('annotated_items_count', 0)}")
    lines.append(f"- 已完整标注 QA 对（所有配置）：{stats.get('fully_annotated_count', 0)}")
    lines.append(f"- 完整标注率：{stats.get('completion_rate', 0) * 100:.1f}%")
    lines.append("")

    # 按配置统计
    configs_stats = stats.get("configs_stats", [])
    if configs_stats:
        lines.append("### 各标注配置统计")
        for cfg in configs_stats:
            cfg_name = cfg.get("config_name", "未知")
            cfg_type = cfg.get("annotation_type", "未知")
            total_ann = cfg.get("total_annotations", 0)
            coverage = cfg.get("coverage", 0) * 100
            lines.append(f"#### {cfg_name}（类型：{cfg_type}）")
            lines.append(f"- 标注数：{total_ann}")
            lines.append(f"- 覆盖率：{coverage:.1f}%")

            # 按类型输出详细统计
            detail = cfg.get("stats", {})
            if cfg_type == "score" and "average" in detail:
                lines.append(f"- 平均分：{detail['average']:.2f}（范围 {detail.get('min', '?')}-{detail.get('max', '?')}）")
                if "distribution" in detail:
                    dist_items = sorted(detail["distribution"].items(), key=lambda x: int(x[0]))
                    dist_str = ", ".join(f"{k}分: {v}条" for k, v in dist_items)
                    lines.append(f"- 分数分布：{dist_str}")
            elif cfg_type in ("single_choice", "multi_choice") and "option_distribution" in detail:
                labels = detail.get("option_labels", {})
                for k, v in detail["option_distribution"].items():
                    label = labels.get(k, k)
                    lines.append(f"  - {label}: {v}")
            elif cfg_type == "binary" and "true_count" in detail:
                lines.append(f"- 是/否：{detail['true_count']} / {detail['false_count']}")
                lines.append(f"- '是'占比：{detail.get('true_ratio', 0) * 100:.1f}%")
            elif cfg_type == "category" and "category_distribution" in detail:
                for cat, cnt in detail["category_distribution"].items():
                    lines.append(f"  - {cat}: {cnt}")
            elif cfg_type == "text" and "avg_length" in detail:
                lines.append(f"- 平均长度：{detail['avg_length']:.0f} 字符")
                lines.append(f"- 长度范围：{detail.get('min_length', '?')} - {detail.get('max_length', '?')} 字符")
            lines.append("")

    return "\n".join(lines)


def build_notes_analysis_prompt(
    notes_data: list[dict],
    stats: dict | None = None,
    language: str = "zh",
) -> tuple[str, str]:
    """构造标注备注分析的提示词

    Args:
        notes_data: 标注备注数据列表，每项包含 config_name, count, notes
        stats: 项目统计信息 dict（可选）

    Returns:
        tuple: (system_prompt, user_message)
    """
    if language == "zh":
        system_prompt = """你是一位专业的 QA 数据质量分析专家。你的任务是分析标注人员对 QA 对的标注结果和备注，生成结构化的分析报告，重点关注如何改进 QA 数据的生成管线。

请按以下结构输出分析报告（使用 Markdown 格式）：

## 总体概述
基于统计概览和标注备注，简要概括项目标注的整体情况和主要发现。

## 标注结果分析
分析各标注配置的统计数据，识别标注模式和异常。例如评分分布是否合理、分类是否均衡、是否有明显的标注倾向等。

## 标注备注分析
分析标注人员留下的备注内容，提炼关键信息，识别反复出现的问题和关注点。

## QA 生成管线改进建议
**这是最重要的部分。** 基于标注统计和备注，提出具体的 QA 数据生成管线改进方向：
- 数据质量问题：标注备注中反映了哪些 QA 对的常见问题（如回答不准确、问题不清晰、事实错误等）
- 生成策略调整：如何优化 prompt、模型选择、参数设置来减少低质量 QA 的产生
- 质量把控：建议在管线中增加哪些筛选或验证步骤
- 数据分布优化：如何改善 QA 数据的多样性和覆盖面

## 总结
简要总结关键发现和最优先的改进方向。

注意：
- 报告使用中文撰写
- 分析要客观、具体、有数据支撑
- 改进建议要可落地，不要空泛
- 如果数据量较少，适当简化分析内容"""
    else:
        system_prompt = """You are a professional QA data quality analyst. Your task is to analyze annotators' results and notes on QA pairs, generate a structured analysis report, with a focus on how to improve the QA data generation pipeline.

Please output the analysis report in the following structure (using Markdown format):

## Overview
Based on the statistical overview and annotation notes, briefly summarize the overall status and key findings of the project annotation.

## Annotation Results Analysis
Analyze the statistics for each annotation config, identify patterns and anomalies. For example, whether score distributions are reasonable, whether categories are balanced, whether there are noticeable annotation biases, etc.

## Annotation Notes Analysis
Analyze the notes left by annotators, extract key information, identify recurring issues and concerns.

## QA Generation Pipeline Improvement Suggestions
**This is the most important section.** Based on annotation statistics and notes, propose specific improvement directions for the QA data generation pipeline:
- Data quality issues: What common QA pair problems are reflected in the annotation notes (e.g., inaccurate answers, unclear questions, factual errors, etc.)
- Generation strategy adjustments: How to optimize prompts, model selection, and parameter settings to reduce low-quality QA generation
- Quality control: What screening or validation steps should be added to the pipeline
- Data distribution optimization: How to improve the diversity and coverage of QA data

## Summary
Briefly summarize key findings and the highest-priority improvement directions.

Notes:
- Write the report in English
- Analysis should be objective, specific, and data-driven
- Improvement suggestions should be actionable, not vague
- If the data volume is small, simplify the analysis accordingly"""

    # 格式化 user message
    parts = []

    # 统计信息部分
    if stats:
        parts.append(_format_stats_section(stats))
        parts.append("---")
        parts.append("")

    # 备注部分
    total_notes = 0
    notes_parts = []
    for item in notes_data:
        config_name = item.get("config_name", "未知配置")
        notes = item.get("notes", [])
        display_notes = notes[:50]
        total_notes += len(notes)

        notes_parts.append(f"### 标注配置：{config_name}")
        notes_parts.append(f"备注数量：{len(notes)} 条")
        notes_parts.append("")
        for i, note in enumerate(display_notes, 1):
            notes_parts.append(f"{i}. {note}")
        if len(notes) > 50:
            notes_parts.append(f"\n... 还有 {len(notes) - 50} 条备注未显示")
        notes_parts.append("")

    parts.append("## 标注备注数据")
    parts.append(f"以下是各标注配置下的标注备注（共 {total_notes} 条）：")
    parts.append("")
    parts.extend(notes_parts)

    if language == "zh":
        parts.append("请基于以上统计数据和标注备注，生成结构化的分析报告，重点给出 QA 生成管线的改进建议。")
    else:
        parts.append("Based on the above statistics and annotation notes, generate a structured analysis report with a focus on QA generation pipeline improvement suggestions.")

    user_message = "\n".join(parts)

    return system_prompt, user_message
