#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
PaperQAGenerator v9.5 - 智能比例控制版本

从学术论文生成问答对（QA）的系统，支持两阶段推理链生成，所有section都使用推理链生成。
新增：智能控制编号问题的比例，平衡简洁性与复杂性。

主要功能：
1. LLM调用模块 - 集成Anthropic Responses API
2. 文本预处理模块 - 从Markdown论文中提取章节
3. 两阶段推理链生成模块
4. 编号问题比例控制模块
5. 智能质量过滤模块
6. 文件处理模块 - 批量处理Excel中的ID列表
7. 质量控制模块 - 过滤不符合要求的问答

新增特性：
- 允许但限制编号问题的比例（默认20%）
- 对编号问题进行严格质量检查
- 实时统计编号问题比例
- 智能筛选高质量编号问题

修复内容：
- v9.4: 取消推理链使用次数限制，所有section都使用推理链生成
- v9.5: 新增编号问题比例控制，平衡简洁性与复杂性

作者：Claude Code
版本：9.5 (智能比例控制版本)
日期：2025-12-15
"""

import json
import os
import re
import time
import uuid
import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from pathlib import Path
from threading import Lock, local
import threading
from typing import Dict, List, Optional, Tuple, Union, Any

import pandas as pd
from dotenv import load_dotenv
from openai import OpenAI

# ==============================================================================
# 配置常量
# ==============================================================================

# 支持的模型列表
SUPPORTED_MODELS = {
    "gpt-5.1": "gpt-5.1",
    "gpt-4o": "gpt-4o",
    "gpt-4o-mini": "gpt-4o-mini",
    "default": "gpt-5.1",
}

# 需要使用Chat Completions API的模型列表
MODELS_REQUIRE_CHAT_COMPLETIONS = [
    "gpt-5.1",
    "gpt-4o",
    "gpt-4o-mini",
]

DEFAULT_MODEL = SUPPORTED_MODELS["gpt-5.1"]
SEARCH_BASE_PATHS = os.getenv("PAPER_SEARCH_PATHS", "examples").split(":")
OVER_GENERATE_FACTOR = 1.5
MAX_SECTION_LENGTH = 200
MIN_SECTION_LENGTH_FOR_PROCESSING = 200

# 新增：编号问题比例配置（已优化：进一步降低比例）
MAX_NUMBERED_RATIO = 0.1  # 默认最多10%的问题可以包含编号（从20%降低到10%）

# 加载环境变量，指定 .env 文件路径
env_path = os.getenv("PAPER_ENV_PATH", str(Path(__file__).parent / ".env"))
load_dotenv(dotenv_path=env_path)
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
DEFAULT_MODEL = os.getenv("DEFAULT_MODEL", SUPPORTED_MODELS["gpt-5.1"])

# ==============================================================================
# 初始化客户端
# ==============================================================================

# 使用 ChatGPT 5.1 的 OpenAI 标准 API 端点
# 如果环境变量中指定了 API_BASE_URL，则使用环境变量；否则使用 OpenAI 标准端点
DEFAULT_API_BASE_URL = os.getenv(
    "API_BASE_URL",
    os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1")
)

client = OpenAI(
    api_key=OPENAI_API_KEY,
    base_url=DEFAULT_API_BASE_URL,
)

# ==============================================================================
# LLM调用计数器（线程安全）
# ==============================================================================

_llm_call_counter = 0
_llm_call_lock = Lock()

# 文件写入锁（用于并发写入JSONL文件）
_file_write_lock = Lock()

# 线程本地存储（用于分区显示）
_thread_local = local()

# 实时统计相关全局变量
_stats_update_func = None
_stats_start_time = None
_stats_total_qas = 0
_stats_total_papers = 0
_stats_last_print_time = 0.0
_stats_lock = Lock()

# 新增：编号问题统计
_stats_numbered_qas = 0
_stats_lock_numbered = Lock()

def get_thread_id() -> int:
    """获取当前线程的编号（1-64）"""
    if not hasattr(_thread_local, 'thread_id'):
        thread_name = threading.current_thread().name
        try:
            if 'worker' in thread_name:
                worker_num = int(thread_name.split('worker-')[-1])
                _thread_local.thread_id = (worker_num % 64) + 1
            else:
                _thread_local.thread_id = 1
        except:
            _thread_local.thread_id = 1
    return _thread_local.thread_id

def set_thread_id(thread_id: int) -> None:
    """设置当前线程的编号"""
    _thread_local.thread_id = thread_id

def tprint(*args, **kwargs):
    """带线程标识的打印函数"""
    thread_id = get_thread_id()
    prefix = f"[线程{thread_id}]"
    print(prefix, *args, **kwargs)

def update_real_time_stats():
    """更新并显示实时统计信息（全局函数）"""
    global _stats_update_func
    if _stats_update_func:
        try:
            _stats_update_func()
        except:
            pass

def _increment_llm_call_counter() -> int:
    """增加LLM调用计数器并返回当前总数（线程安全）"""
    global _llm_call_counter
    with _llm_call_lock:
        _llm_call_counter += 1
        return _llm_call_counter

def get_llm_call_count() -> int:
    """获取当前LLM调用总次数"""
    with _llm_call_lock:
        return _llm_call_counter

def reset_llm_call_counter() -> None:
    """重置LLM调用计数器"""
    global _llm_call_counter
    with _llm_call_lock:
        _llm_call_counter = 0

def increment_numbered_qas_count() -> int:
    """增加编号问题计数器"""
    global _stats_numbered_qas
    with _stats_lock_numbered:
        _stats_numbered_qas += 1
        return _stats_numbered_qas

def get_numbered_qas_count() -> int:
    """获取编号问题总数"""
    with _stats_lock_numbered:
        return _stats_numbered_qas

def reset_numbered_qas_counter() -> None:
    """重置编号问题计数器"""
    global _stats_numbered_qas
    with _stats_lock_numbered:
        _stats_numbered_qas = 0

def _normalize_think_mode(mode: Optional[str]) -> Tuple[Optional[str], bool]:
    """
    归一化推理强度
    """
    if not mode:
        return None, False
    m = str(mode).strip().lower()
    if m in ["none", "off", "disable", "false"]:
        return None, False
    if m == "minimal" or m == "auto":
        m = "low"
    if m not in {"low", "medium", "high"}:
        return None, False
    return m, True

# ==============================================================================
# 1. LLM 调用相关函数
# ==============================================================================

def is_responses_api_supported(model: str) -> bool:
    """
    检查模型是否支持Responses API
    如果模型在Chat API列表中，则使用Chat API
    """
    # 优先检查是否在Chat API列表中（在thinking后缀检查之前）
    if model in MODELS_REQUIRE_CHAT_COMPLETIONS:
        return False
    # 其他模型默认支持Responses API
    return True

def call_chat_completions_api(
    question_prompt: str,
    model: str,
    max_output_tokens: int = 8000,
    think_mode: Optional[str] = None,
) -> Tuple[str, str]:
    """
    使用 Chat Completions API 调用模型
    支持 <think>... 标签提取COT
    """
    req_id = str(uuid.uuid4())[:8]

    start_time = time.time()
    try:
        _increment_llm_call_counter()
        update_real_time_stats()

        messages = [
            {
                "role": "user",
                "content": question_prompt
            }
        ]

        extra_args = {}
        if think_mode and think_mode.lower() not in ["none", "off", "disable", "false"]:
            # 为thinking模型添加thinking参数
            extra_args["extra_body"] = {"thinking": {"type": "enabled"}}

        try:
            response = client.chat.completions.create(
                model=model,
                messages=messages,
                max_tokens=max_output_tokens,
                temperature=0.7,
                **extra_args
            )
        except Exception as e:
            if "thinking" in str(e) or "Unknown parameter" in str(e):
                # API不支持thinking参数，回退到普通模式
                extra_args.pop("extra_body", None)
                response = client.chat.completions.create(
                    model=model,
                    messages=messages,
                    max_tokens=max_output_tokens,
                    temperature=0.7,
                    **extra_args
                )
            else:
                raise

        latency = time.time() - start_time

        raw_answer = response.choices[0].message.content

        if not raw_answer:
            raise RuntimeError("Chat Completions API 响应为空")

        clean_answer, think_content = split_think_content(raw_answer)

        # GLM 模型使用 reasoning_content 字段返回 thinking 内容
        glm_think_content = ""
        if model.startswith("glm-"):
            try:
                glm_think_content = response.choices[0].message.reasoning_content or ""
            except AttributeError:
                pass

        # 合并 thinking 内容
        if glm_think_content and think_content:
            think_content = glm_think_content + "\n\n" + think_content
        elif glm_think_content:
            think_content = glm_think_content

        return clean_answer, think_content or ""

    except Exception as e:
        print(f"[{req_id}] 调用 Chat Completions API 失败: {e}")
        raise

def split_think_content(raw_answer: str) -> Tuple[str, str]:
    """
    从模型回答中分离思维链（CoT）和最终答案。
    """
    if not raw_answer:
        return raw_answer, ""

    patterns = [
        re.compile(r"<think>(.*?)</think>", re.DOTALL),
        re.compile(r"<reasoning>(.*?)</reasoning>", re.DOTALL),
    ]

    for pattern in patterns:
        m = pattern.search(raw_answer)
        if m:
            think_content = m.group(1).strip()
            clean_answer = (raw_answer[:m.start()] + raw_answer[m.end():]).strip()
            return clean_answer, think_content

    return raw_answer.strip(), ""

def extract_cot_from_reasoning(response: Any) -> str:
    """
    从 Responses API 的 output 结构中抽取 COT。
    """
    try:
        if hasattr(response, "model_dump"):
            data = response.model_dump()
        else:
            data = json.loads(
                json.dumps(response, default=lambda o: getattr(o, "__dict__", str(o)))
            )
    except Exception:
        return ""

    def _collect_from_summaries(summaries: Any) -> List[str]:
        """从 summaries 中收集文本片段"""
        chunks: List[str] = []
        if summaries is None:
            return chunks

        if isinstance(summaries, (str, int, float)):
            txt = str(summaries).strip()
            if txt:
                chunks.append(txt)
            return chunks

        if isinstance(summaries, dict):
            summaries = [summaries]

        if not isinstance(summaries, list):
            return chunks

        for seg in summaries:
            if not isinstance(seg, dict):
                txt = str(seg).strip()
                if txt:
                    chunks.append(txt)
                continue

            seg_type = seg.get("type")
            if seg_type not in (None, "summary_text", "text", "reasoning_text"):
                continue

            txt = seg.get("text") or seg.get("content") or ""
            if txt and txt.strip():
                chunks.append(txt.strip())

        return chunks

    cot_chunks: List[str] = []

    try:
        outputs = data.get("output") or data.get("outputs") or []
        if not isinstance(outputs, list):
            return ""

        for out in outputs:
            if not isinstance(out, Dict):
                continue

            out_type = out.get("type")

            if out_type == "reasoning":
                summaries = out.get("summary")
                if summaries is None and isinstance(out.get("reasoning"), dict):
                    summaries = out["reasoning"].get("summary")

                cot_chunks.extend(_collect_from_summaries(summaries))
                continue

            contents = out.get("content") or out.get("contents") or []
            if not isinstance(contents, list):
                continue

            for content in contents:
                if not isinstance(content, Dict):
                    continue
                if content.get("type") != "reasoning":
                    continue

                summaries = None
                reasoning_obj = content.get("reasoning")
                if isinstance(reasoning_obj, dict) and "summary" in reasoning_obj:
                    summaries = reasoning_obj.get("summary")

                if summaries is None and "summary" in content:
                    summaries = content.get("summary")

                cot_chunks.extend(_collect_from_summaries(summaries))

    except Exception:
        return ""

    return "\n\n".join([c for c in cot_chunks if c.strip()]).strip()

def call_llm_with_cot(
    question_prompt: str,
    model: str = DEFAULT_MODEL,
    max_output_tokens: int = 8000,
    think_mode: Optional[str] = "high",
) -> Tuple[str, str]:
    """
    使用合适的 API 调用模型
    自动选择 Responses API 或 Chat Completions API
    """
    req_id = str(uuid.uuid4())[:8]

    # 检查是否需要使用 Chat Completions API
    if not is_responses_api_supported(model):
        # 对于明确需要 Chat API 的模型，直接使用 Chat API，失败则抛出异常
        return call_chat_completions_api(
            question_prompt=question_prompt,
            model=model,
            max_output_tokens=max_output_tokens,
            think_mode=think_mode,
        )

    # 使用 Responses API
    norm_effort, enable_reasoning = _normalize_think_mode(think_mode)

    resp_params: Dict[str, object] = {
        "model": model,
        "input": question_prompt,
        "max_output_tokens": max_output_tokens,
    }

    if enable_reasoning and norm_effort:
        try:
            resp_params["reasoning"] = {"effort": norm_effort}
        except Exception:
            pass

    start_time = time.time()
    try:
        _increment_llm_call_counter()
        update_real_time_stats()

        resp = client.responses.create(**resp_params)  # type: ignore[arg-type]
        latency = time.time() - start_time

        raw_answer: str = getattr(resp, "output_text", "") or ""
        if not raw_answer:
            raise RuntimeError("Responses API 响应为空")

        cot_from_reasoning = extract_cot_from_reasoning(resp)
        clean_answer, cot_from_tags = split_think_content(raw_answer)

        think_content = cot_from_reasoning or cot_from_tags
        return clean_answer, think_content or ""

    except Exception as e:
        print(f"[{req_id}] 调用 Responses API 失败: {e}")
        raise

def call_responses_for_json(
    prompt: str,
    model: str = DEFAULT_MODEL,
    think_mode: str = "minimal",
    max_output_tokens: int = 8000,
) -> Any:
    """
    使用 Responses API + 现有 call_llm_with_cot，期望模型输出 JSON 文本，并解析为 Python 对象。
    """
    norm_think_mode, _ = _normalize_think_mode(think_mode)

    answer_text, _ = call_llm_with_cot(
        question_prompt=prompt,
        model=model,
        max_output_tokens=max_output_tokens,
        think_mode=norm_think_mode or "none",
    )
    content = answer_text.strip()

    def _extract_balanced_json(txt: str) -> Optional[str]:
        """从文本中提取首个平衡的 JSON 块（{...} 或 [...]）"""
        start_idx = None
        start_ch = None
        for i, ch in enumerate(txt):
            if ch in ["{", "["]:
                start_idx = i
                start_ch = ch
                break
        if start_idx is None:
            return None

        stack = 0
        closing = "}" if start_ch == "{" else "]"
        for j in range(start_idx, len(txt)):
            c = txt[j]
            if c == start_ch:
                stack += 1
            elif c == closing:
                stack -= 1
                if stack == 0:
                    return txt[start_idx:j + 1]
        return None

    json_str = _extract_balanced_json(content) or content

    try:
        json_str_clean = re.sub(r'[\x00-\x1f\x7f-\x9f]', '', json_str)
        return json.loads(json_str_clean)
    except Exception as e:
        print(f"[JSON] 解析失败一次: {e}")
        try:
            json_str_clean2 = ''.join(
                ch for ch in json_str if ord(ch) >= 32 or ch in '\n\r\t'
            )
            return json.loads(json_str_clean2)
        except Exception as e2:
            print(f"[JSON] 二次解析仍失败: {e2}")
            raise

# ==============================================================================
# 2. 违禁短语和质量控制
# ==============================================================================

FORBIDDEN_PHRASES = [
    "文中指出", "文中提到", "文中认为", "文中表明",
    "本文指出", "本文认为", "本文表明", "本文中", "文本中", "实验中", "试验中",
    "文章指出", "文章认为", "文章表明", "文章中",
    "本研究指出", "本研究认为", "本研究表明", "本研究", "研究中",
    "该研究指出", "该研究认为", "该研究表明", "该研究", "该章节",
    "在该实验中", "在本实验中", "在本研究中", "在这项研究中",
    "在这篇文章中", "在该文章中", "在该论文中", "在上述研究中",
    "根据给定内容", "根据上述内容", "根据文中内容", "根据本文内容", "根据文本内容",
    "作者认为", "作者指出", "作者提到",
    "本综述认为", "该综述认为", "该综述指出", "Table", "Figure",
    "文本描述", "给定文本", "讨论中指出",
    "根据文中描述", "根据文中内容", "根据文中",
    "根据文本内容", "根据文本", "根据以上文本", "根据上述文本",
    "根据以下文本", "根据给定文本内容", "根据讨论部分",
    "在文中", "从文中可以看出", "由文中可知",
    "根据上述内容和文本", "结合文中内容", "依据文本",
    "根据给出的", "根据给出的文本", "根据给出的内容", "根据标题", "根据给出",
    "从标题可以看出", "从标题", "标题显示", "标题表明",
    "从文章某部分可以看出", "从文章部分可以看出", "从某部分可以看出",
    "从章节可以看出", "从段落可以看出", "从内容可以看出",
    "从上述内容可以看出", "从以上内容可以看出", "从以下内容可以看出",
    "从文本可以看出", "从给定文本可以看出", "从提供的文本可以看出",
    "从材料可以看出", "从资料可以看出", "从文献可以看出",
    "标题中", "文章中", "章节中", "段落中", "内容中",
    "这段文字", "这段文本", "这段内容", "这段研究", "这段描述",
]

# 新增：编号问题质量检查函数（已优化：更严格限制）
def is_acceptable_numbered_question(question: str) -> Tuple[bool, str]:
    """
    智能判断包含编号的问题是否可接受。
    返回：(是否可接受, 原因)

    允许条件（已优化，更严格）：
    1. 问题长度不超过250字符
    2. 编号点不超过2个（从3个减少到2个）
    3. 每个编号点内容不超过20字符（从30字符减少到20字符）
    4. 不使用冗余引导词
    """
    # 检查长度
    if len(question) > 250:
        return False, "问题过长(超过250字符)"

    # 检查编号数量
    numbered_patterns = [
        (r'[①-⑳]', "中文圈码"),
        (r'\d+[\.、]', "数字编号"),
        (r'[a-zA-Z][\.、]', "字母编号"),
    ]

    total_numbered = 0
    for pattern, name in numbered_patterns:
        matches = re.findall(pattern, question)
        total_numbered += len(matches)

    # 允许但限制：最多2个编号（从3个减少到2个）
    if total_numbered > 2:
        return False, f"编号过多({total_numbered}个，最多允许2个)"

    # 检查每个编号点的长度
    if total_numbered > 0:
        # 提取编号后的内容
        parts = re.split(r'[①-⑳]|\d+[\.、]|[a-zA-Z][\.、]', question)
        # 去掉空字符串和问题主体
        numbered_parts = parts[1:-1] if len(parts) > 2 else []

        for i, part in enumerate(numbered_parts):
            # 每个编号点不超过20字符（约10汉字，从30字符减少到20字符）
            part_stripped = part.strip()
            if len(part_stripped) > 20:
                return False, f"第{i+1}个编号点内容过长(超过20字符)"

    # 检查是否有冗余引导词
    redundant_guides = ['已知：', '已知:', '基于以下信息：', '基于以下信息:',
                        '根据以下事实：', '根据以下事实:', '如下信息：', '如下信息:',
                        '信息如下：', '信息如下:', '前提条件：', '前提条件:',
                        '基于这些信息：', '基于这些信息:', '根据这些信息：', '根据这些信息:',
                        '基于以下事实：', '基于以下事实:', '根据以下条件：', '根据以下条件:']
    for guide in redundant_guides:
        if guide in question:
            return False, f"使用冗余引导词'{guide}'"

    return True, "可接受"

def has_too_many_assumptions_or_conditions(question: str) -> Tuple[bool, str]:
    """
    检查问题中是否包含过多的假设、已知条件或列举式描述。
    返回：(是否包含过多假设/条件, 原因)

    检查项：
    1. 条件句/假设句数量（"如果"、"假设"、"当...时"等）
    2. 分号/冒号数量（用于列举事实）
    3. 问题是否以条件句开头
    4. 列举式描述的数量（即使没有编号）
    5. 引导词数量（"基于"、"根据"、"已知"等）
    """
    if not question:
        return False, ""

    # 1. 检查条件句/假设句数量
    condition_patterns = [
        r'如果[^，。；：]{0,50}[，。；：]',
        r'假设[^，。；：]{0,50}[，。；：]',
        r'当[^，。；：]{0,50}时[，。；：]',
        r'若[^，。；：]{0,50}[，。；：]',
        r'倘若[^，。；：]{0,50}[，。；：]',
        r'观测到[^，。；：]{0,50}[，。；：]',
        r'发现[^，。；：]{0,50}[，。；：]',
    ]
    condition_count = sum(len(re.findall(pattern, question)) for pattern in condition_patterns)

    # 允许最多1个条件句
    if condition_count > 1:
        return True, f"条件句/假设句过多({condition_count}个，最多允许1个)"

    # 2. 检查分号和冒号数量（用于列举事实）
    semicolon_count = question.count('；') + question.count(';')
    colon_count = question.count('：') + question.count(':')
    total_separators = semicolon_count + colon_count

    # 如果分号+冒号超过3个，可能包含过多列举
    if total_separators > 3:
        return True, f"列举分隔符过多(分号{semicolon_count}个，冒号{colon_count}个，总计{total_separators}个，最多允许3个)"

    # 3. 检查问题是否以条件句开头（不好的模式）
    starts_with_condition = re.match(r'^(如果|假设|当|若|倘若|已知|基于|根据)', question.strip())
    if starts_with_condition:
        # 如果以条件句开头，且后面还有多个条件，则拒绝
        if condition_count > 0 or total_separators > 2:
            return True, f"以条件句开头且包含过多条件/列举"

    # 4. 检查列举式描述的数量（通过分号、冒号、编号等判断）
    # 计算可能的列举项数量
    list_indicators = [
        len(re.findall(r'[①-⑳]', question)),  # 中文圈码
        len(re.findall(r'\d+[\.、]', question)),  # 数字编号
        semicolon_count,  # 分号
    ]
    total_list_items = sum(list_indicators)

    # 如果列举项超过3个，拒绝
    if total_list_items > 3:
        return True, f"列举项过多(总计{total_list_items}项，最多允许3项)"

    # 5. 检查引导词数量（"基于"、"根据"、"已知"等）
    guide_patterns = [
        r'基于[^，。；：]{0,20}(信息|事实|条件|数据|结果|发现)',
        r'根据[^，。；：]{0,20}(信息|事实|条件|数据|结果|发现)',
        r'已知[：:]',
        r'观测到[^，。；：]{0,20}[，。；：]',
    ]
    guide_count = sum(len(re.findall(pattern, question)) for pattern in guide_patterns)

    # 如果引导词超过2个，拒绝
    if guide_count > 2:
        return True, f"引导词过多({guide_count}个，最多允许2个)"

    # 6. 检查问题的信息密度（通过句子数量判断）
    # 计算句子数量（通过句号、问号、感叹号分隔）
    sentence_count = len(re.split(r'[。！？]', question))

    # 如果句子超过4个，且包含多个条件/列举，可能信息过密
    if sentence_count > 4 and (condition_count > 0 or total_list_items > 2):
        return True, f"信息密度过高(句子数{sentence_count}个，且包含条件/列举)"

    # 7. 检查是否包含"综合这些信息"、"基于上述信息"等表述
    summary_phrases = [
        '综合这些信息',
        '综合上述信息',
        '基于上述信息',
        '根据上述信息',
        '综合以上信息',
        '基于以上信息',
        '根据以上信息',
    ]
    for phrase in summary_phrases:
        if phrase in question:
            # 如果前面还有多个条件/列举，则拒绝
            if condition_count > 0 or total_list_items > 2:
                return True, f"包含'{phrase}'且前面条件/列举过多"

    return False, ""

def is_study_dependent(text: str) -> bool:
    """
    判断文本是否依赖本文或具体实验体系。
    """
    patterns = [
        r"根据(本|该|这项)?研究",
        r"在(本|该|这项)?研究中",
        r"(本|该)研究表明",
        r"(本文|该文)(中)?(认为|指出|表明|描述)",
        r"(结果|摘要|讨论|方法)(部分)?指出",
        r"在(本|该)?实验中",
        r"(本|该)实验(中)?",
        r"(本|该)试验(中)?",
        r"在(本|该)?体系中",
        r"(本文|该文)描述的.*体系中",
        r"这项研究(中|表明|发现)",
        r"这篇文章(中|指出|认为|表明)",
        r"该论文(中|指出|认为|表明)",
    ]

    for pattern in patterns:
        if re.search(pattern, text):
            return True
    return False

def is_author_related(text: str) -> bool:
    """
    判断问答内容是否是"作者信息/作者署名/通讯作者/单位信息"等。
    """
    if not text:
        return False

    t = text.lower()

    keywords = [
        "作者", "通讯作者", "第一作者", "共同作者", "作者信息",
        "作者单位", "作者顺序", "作者排序", "作者贡献", "作者简介",
        "联系作者", "联系方式", "电子邮箱", "邮箱地址",
        "通讯方式", "通信地址", "单位信息",
        "affiliation", "corresponding author", "co-author",
        "coauthor", "author list", "author order",
        "author contribution", "contributing authors",
    ]

    for kw in keywords:
        if kw in text or kw in t:
            return True

    patterns = [
        r"corresponding author",
        r"first author",
        r"co[- ]author",
        r"author\(s\)",
    ]
    for p in patterns:
        if re.search(p, t):
            return True

    return False

def has_unmentioned_specific_species_or_case(question: str, answer: str) -> bool:
    """
    检测答案中是否包含问题未提及的具体物种、品种、基因名称等具体案例。
    """
    if not question or not answer:
        return False

    q_lower = question.lower()
    a_lower = answer.lower()

    species_patterns = [
        r'[A-Z][a-z]+\s+[a-z]+(?:\s+cv\.\s+[A-Z][a-z]+)?',
        r'[A-Z][a-z]+\s+[a-z]+',
        r'[A-Z][a-z]+\s+[a-z]+\s+[a-z]+',
    ]

    cultivar_patterns = [
        r'cv\.\s+[A-Z][a-z]+',
        r'品种\s*[：:]\s*[A-Za-z0-9\u4e00-\u9fa5]+',
        r'品系\s*[：:]\s*[A-Za-z0-9\u4e00-\u9fa5]+',
    ]

    answer_species = []
    for pattern in species_patterns + cultivar_patterns:
        matches = re.findall(pattern, answer)
        if matches:
            answer_species.extend(matches)

    if not answer_species:
        return False

    for species in answer_species:
        species_key = re.sub(r'\s+cv\.\s+[A-Z][a-z]+', '', species).strip()
        species_key = re.sub(r'品种\s*[：:]\s*[A-Za-z0-9\u4e00-\u9fa5]+', '', species_key).strip()
        species_key = re.sub(r'品系\s*[：:]\s*[A-Za-z0-9\u4e00-\u9fa5]+', '', species_key).strip()

        if species_key and len(species_key) > 3:
            genus = species_key.split()[0] if ' ' in species_key else species_key

            if genus.lower() not in q_lower and species_key.lower() not in q_lower:
                question_has_species = any(
                    re.search(pattern, question) for pattern in species_patterns
                )
                if not question_has_species:
                    return True

    gene_patterns = [
        r'[A-Z][a-z0-9]+[-_]?[A-Z]?[a-z0-9]*\s+基因',
        r'基因\s+[A-Z][a-z0-9]+[-_]?[A-Z]?[a-z0-9]*',
    ]

    answer_genes = []
    for pattern in gene_patterns:
        matches = re.findall(pattern, answer)
        if matches:
            answer_genes.extend(matches)

    if answer_genes:
        for gene_match in answer_genes:
            gene_name = re.sub(r'基因', '', gene_match).strip()
            if gene_name and len(gene_name) > 2:
                if gene_name.lower() not in q_lower:
                    question_has_gene = any(
                        re.search(pattern, question) for pattern in gene_patterns
                    )
                    if not question_has_gene:
                        return True

    return False

def is_answer_just_restating_question(question: str, answer: str) -> bool:
    """
    检测答案是否只是简单复述问题中的信息。
    """
    if not question or not answer:
        return False

    q_lower = question.lower()
    a_lower = answer.lower()

    numbered_info_patterns = [
        r'[①-⑳]',
        r'[1-9][\.、]',
        r'已知[：:]',
        r'基于.*信息',
        r'根据.*信息',
    ]

    question_has_numbered_info = any(
        re.search(pattern, question) for pattern in numbered_info_patterns
    )

    if not question_has_numbered_info:
        return False

    q_cleaned = re.sub(r'[①-⑳]\s*', '', question)
    q_cleaned = re.sub(r'[1-9][\.、]\s*', '', q_cleaned)
    q_cleaned = re.sub(r'已知[：:]\s*', '', q_cleaned)
    q_cleaned = re.sub(r'基于.*信息[，,]?\s*', '', q_cleaned)
    q_cleaned = re.sub(r'根据.*信息[，,]?\s*', '', q_cleaned)

    def extract_key_entities(text: str) -> set:
        entities = set()

        gene_protein_pattern = r'\b[A-Z][a-z]*\d+\b'
        matches = re.findall(gene_protein_pattern, text)
        entities.update(m.lower() for m in matches)

        cell_types = ['酵母', '植物', '动物', '细胞', '胞质', 'yeast', 'plant', 'animal', 'cell']
        for ct in cell_types:
            if ct.lower() in text.lower():
                entities.add(ct.lower())

        mechanisms = ['耐热', '解聚', '蛋白', '机制', 'heat', 'thermal', 'protein', 'mechanism']
        for mech in mechanisms:
            if mech.lower() in text.lower():
                entities.add(mech.lower())

        return entities

    q_entities = extract_key_entities(q_cleaned)
    a_entities = extract_key_entities(answer)

    if len(q_entities) > 0:
        overlap_ratio = len(a_entities & q_entities) / len(q_entities) if q_entities else 0

        if overlap_ratio > 0.8:
            reasoning_keywords = [
                '推理', '因此', '所以', '结论', '依据', '逻辑', '因为', '由于',
                'reasoning', 'therefore', 'thus', 'conclusion', 'because', 'due to',
                '基于', '根据', '通过', '可以得出', '可以推断'
            ]

            has_reasoning = any(
                keyword in answer for keyword in reasoning_keywords
            )

            if len(answer) < len(question) * 1.5 and not has_reasoning:
                q_key_phrases = re.findall(r'[A-Z][a-z]+\s+\d+|[A-Z][a-z]+', q_cleaned)
                a_key_phrases = re.findall(r'[A-Z][a-z]+\s+\d+|[A-Z][a-z]+', answer)

                if q_key_phrases and a_key_phrases:
                    q_phrases_set = set(p.lower() for p in q_key_phrases)
                    a_phrases_set = set(p.lower() for p in a_key_phrases)
                    phrase_overlap = len(a_phrases_set & q_phrases_set) / len(q_phrases_set) if q_phrases_set else 0

                    if phrase_overlap > 0.7:
                        return True

    return False

# ==============================================================================
# 3. 文本预处理 & 分节
# ==============================================================================

def clean_md_basic(text: str) -> str:
    """
    对 md 做一个温和清洗。
    """
    # 删除 markdown 图片
    text = re.sub(r'!\[[^\]]*?\]\([^\)]*?\)', ' ', text)
    # 删除 html 图片
    text = re.sub(r'<img[^>]*?>', ' ', text, flags=re.IGNORECASE)
    # 删除 HTML 标签
    text = re.sub(r'<[^>]+>', ' ', text)
    # 删除 markdown 链接
    text = re.sub(r'\[([^\]]+)\]\([^\)]+\)', r'\1', text)
    # 删除 LaTeX 简单公式
    text = re.sub(r'\$\$[^$]+\$\$', ' ', text, flags=re.DOTALL)
    text = re.sub(r'\$[^$]+\$', ' ', text)
    # 删除 markdown 表格线
    text = re.sub(r'^\s*\|.*\|\s*$', ' ', text, flags=re.MULTILINE)
    text = re.sub(r'^[\s\-\:\|]+$', ' ', text, flags=re.MULTILINE)
    # 删除代码块
    text = re.sub(r'```.*?```', ' ', text, flags=re.DOTALL)
    # 合并多余空行和空格
    text = re.sub(r'\n{3,}', '\n\n', text)
    text = re.sub(r'[ \t]{2,}', ' ', text)
    return text.strip()

def should_skip_section(section_name: str, section_text: str) -> bool:
    """
    判断是否应该跳过这个章节。
    """
    skip_keywords = [
        'references', 'bibliography', 'acknowledg', 'appendix',
        'supplementary', 'author contribution', 'competing interest',
        'conflict of interest', 'funding', 'abbreviations',
        'Compliance with ethical standards'
    ]
    section_lower = section_name.lower()
    for keyword in skip_keywords:
        if keyword in section_lower:
            return True

    if len(section_text.strip()) < MIN_SECTION_LENGTH_FOR_PROCESSING:
        return True

    if re.fullmatch(r'[ATCGNatcgn\s]+', section_text.strip()):
        return True

    ref_patterns = [
        r'\d+\.\s+[A-Z][^.]+\.[A-Z][^.]+\.[\s\d]',
        r'\[?\d+\]?\s+[A-Z]',
        r'et al\.\s*\d{4}'
    ]
    ref_count = sum(1 for pattern in ref_patterns if re.search(pattern, section_text))
    if ref_count > 2:
        return True

    return False

def is_paper_main_title(title: str, level: int = None) -> bool:
    """
    判断是否是论文主标题（应该被跳过，不当作section）。
    """
    title_cleaned = re.sub(r'^[IVX]+\.\s*', '', title, flags=re.IGNORECASE)
    title_cleaned = re.sub(r'^\d+\.\s*', '', title_cleaned)
    title_cleaned = re.sub(r'^[A-Z]\.\s*', '', title_cleaned)
    title_cleaned = title_cleaned.strip()
    if not title_cleaned:
        title_cleaned = title.strip()

    t = title_cleaned.lower()

    standard_sections = [
        'introduction', 'abstract', 'background', 'summary', 'method', 'materials',
        'result', 'discussion', 'conclusion', 'reference', 'acknowledg'
    ]

    if any(s in t for s in standard_sections):
        return False

    if level == 1:
        if len(title) > 50:
            return True

    has_colon = ':' in title
    length_ok = 30 < len(title) < 300

    scientific_keywords = [
        'gene', 'family', 'expression', 'sequence', 'structure',
        'promoter', 'analysis', 'characterization', 'cloning',
        'identification', 'isolation', 'purification', 'function',
        'study', 'research', 'investigation', 'evaluation',
        'stress', 'response', 'regulation', 'wheat', 'maize', 'rice',
        'genetic', 'physiological', 'environmental', 'factors', 'concentration',
        'acrylamide', 'potato', 'products'
    ]

    keyword_count = sum(1 for kw in scientific_keywords if kw in title.lower())
    has_keywords = keyword_count >= 2

    not_section = not any(s in title.lower() for s in standard_sections)

    return (has_colon and length_ok and has_keywords and not_section) or (
        length_ok and keyword_count >= 3 and not_section
    )

def is_numbered_section(title: str) -> bool:
    """
    判断是否是编号章节。
    """
    numbered_patterns = [
        r'^[IVX]+\.',
        r'^[A-Z]\.',
        r'^\d+\.',
        r'^[a-z]\.',
    ]
    for pattern in numbered_patterns:
        if re.match(pattern, title.strip()):
            return True
    return False

def get_main_section_title(title: str, previous_main_section: str = None) -> Optional[str]:
    """
    根据标题内容，映射到主章节名。
    """
    original_title = title
    title_cleaned = re.sub(r'^[IVX]+\.\s*', '', title, flags=re.IGNORECASE)
    title_cleaned = re.sub(r'^\d+\.\s*', '', title_cleaned)
    title_cleaned = re.sub(r'^[A-Z]\.\s*', '', title_cleaned)
    title_cleaned = title_cleaned.strip()

    if not title_cleaned:
        title_cleaned = title.strip()

    t = title_cleaned.lower().strip()

    if "introduction" in t:
        return "Introduction"
    elif "abstract" in t:
        return "Abstract"
    elif "background" in t:
        return "Background"
    elif "summary" in t:
        return "Summary"
    elif "materials" in t and "method" in t:
        return "Materials & Methods"
    elif "results" in t and "discussion" in t:
        return "Results & Discussion"
    elif "results" in t:
        return "Results"
    elif "discussion" in t:
        return "Discussion"
    elif "conclusion" in t or "concluding remarks" in t:
        return "Conclusion"
    elif "method" in t:
        return "Methods"

    if is_paper_main_title(original_title):
        return None

    if re.search(r"[ATCG]{10,}", original_title) and len(original_title) < 100:
        return previous_main_section if previous_main_section else "Experimental Results"

    if is_numbered_section(original_title) and previous_main_section:
        return previous_main_section

    return original_title

def is_subsection_title(title: str, level: int) -> bool:
    """
    判断是否是小标题。
    """
    if level >= 3:
        return True

    if re.match(r'^\([a-z0-9]+\)', title.strip(), re.IGNORECASE):
        return True

    if len(title.strip()) < 50 and is_numbered_section(title):
        return True

    return False

def split_md_into_sections(md_text: str) -> Dict[str, str]:
    """
    按 markdown 标题切分 section，智能合并相关子章节。
    """
    lines = md_text.splitlines()
    sections = {}
    section_levels = {}

    current_main_section = None
    current_title = None
    current_level = None
    buf = []
    previous_main_section = None
    found_any_section = False
    first_title_skipped = False

    def commit_section(main_section: str, title: str, buf_lines: List[str], level: int):
        if not main_section:
            return
        text = "\n".join(buf_lines).strip()
        if not text:
            return

        if main_section in sections:
            sections[main_section].append(f"\n\n=== {title} ===\n{text}")
        else:
            sections[main_section] = [f"=== {title} ===\n{text}"]
            if main_section not in section_levels:
                section_levels[main_section] = level

    for line_idx, line in enumerate(lines):
        header_match = re.match(r'^(#{1,6})\s+(.*)', line.strip())

        if header_match:
            if buf and current_main_section and current_level is not None:
                commit_section(current_main_section, current_title or "Content", buf, current_level)

            buf = []
            level = len(header_match.group(1))
            raw_title = header_match.group(2).strip()

            if not first_title_skipped and is_paper_main_title(raw_title, level=level):
                first_title_skipped = True
                print(f"  ⏭️  跳过论文标题: {raw_title[:80]}...")
                continue

            is_subsection = is_subsection_title(raw_title, level)

            previous_main_section = current_main_section
            main_section = get_main_section_title(raw_title, previous_main_section)

            if main_section is None:
                if is_paper_main_title(raw_title, level=level):
                    print(f"  ⏭️  跳过论文标题: {raw_title[:80]}...")
                    continue
                else:
                    main_section = raw_title

            if is_subsection and previous_main_section:
                current_main_section = previous_main_section
                current_title = raw_title
                current_level = section_levels.get(previous_main_section, level)
                found_any_section = True
            else:
                current_main_section = main_section
                current_title = raw_title
                current_level = level
                found_any_section = True
        else:
            buf.append(line)

    if buf and current_main_section and current_level is not None:
        commit_section(current_main_section, current_title or "Content", buf, current_level)

    if not found_any_section or not sections:
        print("  ⚠️  未找到明确的section，将整篇文章作为一个section处理")
        cleaned_text = clean_md_basic(md_text)
        if len(cleaned_text) >= 100:
            text_lower = cleaned_text.lower()
            if "abstract" in text_lower[:500] or "summary" in text_lower[:500]:
                section_name = "Abstract"
            elif "background" in text_lower[:500]:
                section_name = "Background"
            elif "introduction" in text_lower[:500]:
                section_name = "Introduction"
            else:
                section_name = "Full Text"
            return {section_name: cleaned_text}
        else:
            print("  ⚠️  文章内容过短，跳过")
            return {}

    standard_sections_lower = [
        "introduction", "abstract", "background", "summary",
        "materials & methods", "methods",
        "results", "results & discussion",
        "discussion", "conclusion"
    ]

    standard_section_levels = set()
    for main_section, level in section_levels.items():
        main_section_lower = main_section.lower().strip()
        is_standard = any(
            std_sec in main_section_lower or main_section_lower in std_sec
            for std_sec in standard_sections_lower
        )
        if is_standard:
            standard_section_levels.add(level)

    if not standard_section_levels:
        standard_section_levels = {1, 2}

    merged = {}
    for main_section, texts in sections.items():
        joined = "\n".join(t.strip() for t in texts if t.strip())
        if not joined:
            continue

        cleaned_text = clean_md_basic(joined)

        main_section_lower = main_section.lower().strip()
        is_standard_section = any(
            std_sec in main_section_lower or main_section_lower in std_sec
            for std_sec in standard_sections_lower
        )

        section_level = section_levels.get(main_section, 999)
        is_same_level = section_level in standard_section_levels

        if (is_standard_section or is_same_level) and \
           not should_skip_section(main_section, cleaned_text) and \
           len(cleaned_text) >= 100:
            merged[main_section] = cleaned_text
        else:
            if not is_standard_section and not is_same_level:
                print(f"  ⏭️  跳过章节: {main_section} (不是标准section且级别不同)")
            else:
                print(f"  ⏭️  跳过章节: {main_section} (内容过短或类型不符)")

    return merged

# ==============================================================================
# 4. 文本清洗 & token 估计
# ==============================================================================

def sanitize_text_forbidden_phrases(text: str) -> str:
    """
    基础清理：主要是空白和标点的规范化。
    """
    if not text:
        return text

    text = re.sub(r'\n+', ' ', text)
    text = re.sub(r'\s{2,}', ' ', text)
    text = re.sub(r'[，。；：]{2,}', lambda m: m.group(0)[0], text)
    text = re.sub(r'^[，；：、\s]+', '', text)

    return text.strip()

def estimate_tokens(text: str) -> int:
    """
    粗略估算 token 数。
    """
    if not text:
        return 0
    words = len(text.split())
    return int(words * 1.3)

# ==============================================================================
# 5. Prompt 构建
# ==============================================================================

def build_prompt(section_name: str, section_text: str, max_q: int = 5) -> Tuple[str, str]:
    """
    构建系统与用户提示词，生成高质量SFT问答对。
    """
    knowledge_flexible = any(keyword in section_name.lower()
                             for keyword in ["conclusion", "结论", "全文", "full text", "总结"])

    forbidden_examples = "\n".join([f"   - '{phrase}'" for phrase in FORBIDDEN_PHRASES[:15]])
    if len(FORBIDDEN_PHRASES) > 15:
        forbidden_examples += f"\n   - ...等共 {len(FORBIDDEN_PHRASES)} 个违禁短语"

    prohibition_rules = (
        "【严格禁止】\n"
        "1. 问题和答案中严格禁止使用以下指代论文的表述：\n"
        f"{forbidden_examples}\n"
        "2. 问题中禁止围绕以下主题发问：\n"
        "   - '研究目标'、'技术路径'、'这项研究'\n"
        "   - 论文的写作结构或方法论评价\n"
        "   - 针对具体的图和表\n"
        "   - 具体的数值、参数、实验条件等细节\n"
        "   - 具体实验对象的列举（如'四个黄瓜基因型'、'13个群体'等）\n"
        "   - 具体实验处理（如'X与Y的差异'，其中X、Y是具体实验对象）\n"
        "3. 禁止引用外部数据库具体编号：\n"
        "   - 不得提及BioProject、GEO、SRA等数据库的具体登录号\n"
        "   - 不得引用具体的SNP编号（如rs7412）或基因库编号\n"
        "   - 不得要求验证外部数据库中的具体条目\n"
        "4. 答案中禁止提及具体的样本数量、群体数量、实验组数量等具体数值\n"
        "5. 禁止使用'在X个Y中'、'在特定群体中'、'在某个实验中'等限定性表述\n"
        "6. 问题和答案中禁止使用或涉'已有进化轨迹模型'、'已有研究'等模糊代称表述\n"
        "7. 答案中禁止引入问题中未提及的具体案例、基因名称、实验条件、数据等细节。例如：若问题未要求举例，答案不得自行添加如'CpiF-Box基因'等具体案例。\n"
        "   特别强调：如果问题中没有提到特定物种、品种或基因，答案中绝对禁止突然引入具体物种名称（如'油菜(Brassica napus, cv. Jet Neuf)'）、品种名称或基因名称。答案应保持通用性，使用一般性描述而非具体案例。\n"
        "8. 所有问题必须在脱离本文（例如换成同一领域的任意一篇类似研究）时仍然合理成立。\n"
        "9. 不得以'这篇文章/该研究/本实验'等类似主题作为前提来发问或在答案中引用。\n"
    )

    design_principles = (
        "【设计原则】\n"
        "1. 问题独立清晰：单个问答对可独立理解，无需上下文依赖\n"
        "2. 生物实体规范：标注物种来源\n"
        "3. 内容聚焦：关注通用概念、机制、原理、方法\n"
        "4. 宽泛适用：问题应具有普遍性\n"
        "5. 通用表述：使用一般现在时\n"
        "6. 术语准确\n"
        "7. 术语完整准确：在使用缩写时需给出含义\n"
    )

    question_guidance = (
        "【问题设计指导】\n"
        "1. 问题应关注通用科学原理而非具体案例\n"
        "2. 答案应描述一般规律而非具体数据\n"
        "3. 使用一般现在时\n"
        "4. 避免使用违禁短语\n"
        "5. 术语规范\n"
        "6. 答案必须与问题一致，不要额外扩展具体案例\n"
        "7. **减少编号信息使用**：\n"
        "   - 优先使用自然语言描述多个事实，避免使用①②③等编号\n"
        "   - 如果必须使用编号，最多2个编号点，每个编号点不超过20字符\n"
        "   - 避免使用'已知：'、'基于以下信息：'等冗余引导词\n"
        "   - 使用连接词（'同时'、'进一步'、'此外'等）自然串联多个事实\n"
        "8. **减少假设和已知条件**：\n"
        "   - 避免问题中包含过多的条件句（'如果'、'假设'、'当...时'等，最多1个）\n"
        "   - 避免使用过多的列举式描述（分号+冒号总计不超过3个）\n"
        "   - 避免问题以条件句开头（如'如果...'、'假设...'、'已知...'）\n"
        "   - 避免使用过多的引导词（'基于'、'根据'、'已知'等，最多2个）\n"
        "   - 避免使用'综合这些信息'、'基于上述信息'等总结性表述\n"
        "   - 问题应直接描述科学事实，而非列举多个假设条件后再提问\n"
    )

    base_rules = "\n".join([prohibition_rules, design_principles, question_guidance])

    knowledge_policy = (
        "结论和全文类章节可结合论文内容和领域知识生成全面答案，不局限于文本。"
        if knowledge_flexible else
        "所有内容必须严格基于给定文本，不得加入外部知识或推测。"
    )

    system_prompt = f"""你是一位农业与生命科学领域的专业问答生成系统，为科研人员和学术工作者提供准确、可验证的专业知识。行为准则：审慎、精确、负责。

{knowledge_policy}

{base_rules}

【质量要求】
- 问题通用性
- 答案一般化
- 语言规范性
- 术语准确性
- 输出规范性：严格输出JSON数组格式，无额外说明"""

    processed_text = (
        section_text[:10000] + "\n\n[以下内容因长度被截断]"
        if len(section_text) > 10000
        else section_text
    )

    flexible_note = (
        "结论和全文类章节可结合领域知识，包含应用价值、发展趋势等延伸内容。"
        if knowledge_flexible else ""
    )

    user_prompt = f"""任务：为以下论文章节生成 {max_q} 组高质量问答对。

【章节信息】
名称：{section_name}
内容：
{processed_text}

【核心要求】
1. 有效性检查
2. 零幻觉原则：{"结论和全文类章节可结合领域知识，其他章节严格基于给定文本" if flexible_note else "所有答案内容必须严格基于给定文本，不加入外部知识"}
3. 内容聚焦：核心科学概念、研究方法、机制原理、实验结果{"；" + flexible_note if flexible_note else ""}
4. 问题设计：关注通用概念
5. 元数据：难度分级 + 精确标签
6. **问题表述优化**：
   - 优先使用自然语言描述，避免使用①②③等编号列举
   - 如需描述多个事实，使用连接词自然串联（如"同时"、"进一步"、"此外"等）
   - 如果必须使用编号，严格限制在2个以内，每个编号点不超过20字符
   - 避免使用"已知："、"基于以下信息："等冗余引导词
   - **减少假设和已知条件**：
     * 避免包含过多的条件句（"如果"、"假设"、"当...时"等，最多1个）
     * 避免过多的列举式描述（分号+冒号总计不超过3个）
     * 避免问题以条件句开头
     * 避免使用"综合这些信息"、"基于上述信息"等总结性表述
     * 问题应直接描述科学事实，而非列举多个假设条件后再提问

【输出格式】
[
  {{
    "question": "问题内容（优先使用自然语言，避免过多编号）",
    "answer": "科学事实、机制或原理",
    "difficulty": "easy | medium | hard",
    "tags": ["tag1", "tag2"]
  }}
]"""

    return system_prompt, user_prompt

# ==============================================================================
# 6. 两阶段推理链生成方案（已优化：控制编号问题比例）
# ==============================================================================

def build_chain_extraction_prompt(
    section_name: str,
    section_text: str,
    max_chains: int = 3
) -> str:
    """
    构建"从章节文本抽取推理链"的大 prompt。
    """
    prompt = f"""你是一位农业育种与生命科学领域的专家阅读系统，擅长从论文片段中总结可复用的推理链。

【你的任务】
给定一个论文章节内容，请从中抽取 1~{max_chains} 条"可用于构造多步推理问答"的推理链。
每条推理链必须满足：
- 基于文本中明确出现的事实（试验设计、处理、结果、机制说明等）
- 通过 3~7 个逻辑步骤推理得出某个客观结论
- 结论是"客观可判断对错"的（如某种关系、趋势、比较、更优方案等）
- 推理过程不依赖'本文/该研究/本实验'等指代表述

【输出格式】
严格输出一个 JSON 对象：
{{
  "chains": [
    {{
      "id": "C1",
      "final_conclusion": "一句话客观结论（可直接作为答案）",
      "steps": [
        "Step 1: ...",
        "Step 2: ...",
        "Step 3: ..."
      ],
      "support_facts": [
        "从文本抽取或概括的关键事实1",
        "关键事实2"
      ],
      "potential_question_templates": [
        "围绕该结论可以提问的问题模板1",
        "问题模板2"
      ]
    }}
  ]
}}

【禁止内容】
- 不要使用"文中/本文/该研究/本实验"等指代原文的措辞
- 不要引用图表编号、表格编号、外部数据库编号
- 不要生成依赖于具体样本数量、具体群体数目、具体基因编号的结论

【论文章节】
名称：{section_name}
内容：
\"\"\"markdown
{section_text}
\"\"\""""
    return prompt

def build_chain_to_qa_prompt(chain_json_str: str) -> str:
    """
    构建"单条推理链 → 一道需要多步推理的问答对"的 prompt。
    已优化：减少编号信息，鼓励直接描述事实。
    """
    prompt = f"""你是一位农业育种与生命科学领域的教学专家，负责把结构化推理链转化为"需要多步推理才能回答的客观问答对"，用于大模型 SFT 训练。

下面是从论文中抽取的一条推理链（JSON）：
```json
{chain_json_str}
```

【你的任务】
基于这条推理链，构造 1 题"需要多步推理才能回答的问答对"，输出 JSON 对象：
{{
  "question": "面向研究生/科研人员、需要理解多个事实并综合推理的问题",
  "answer": "一段简明客观答案（不包含思维链）",
  "reasoning_steps": [
    "Step 1: ...",
    "Step 2: ...",
    "Step 3: ...",
    "Step 4: ..."
  ],
  "question_cot": "完整的推理过程描述（自然语言）",
  "final_conclusion": "最终结论（一句话）",
  "difficulty": "easy | medium | hard",
  "tags": ["concept", "mechanism", "method", "result", "application", "..."]
}}

【问题设计要求 - 重要优化】

**核心原则：尽量减少或避免使用编号信息（①②③等）**

1. **优先使用自然语言描述**：
   - ✅ 好的问题："在禾本科作物中，对多种器官及不同发育阶段的lemma和palea进行转录组分析发现，典型营养器官、典型生殖器官和胚乳分别形成三个明显的表达类群。lemma和palea在早期发育阶段与生殖器官类群聚在一起，而在晚期发育阶段则与营养器官类群聚在一起。GO分析进一步表明，早期lemma/palea中细胞增殖相关基因表达水平较高，晚期lemma/palea中光合作用相关基因表达水平较高。应如何判断lemma和palea在发育早、晚期分别在功能属性和器官归类上更接近哪一类器官？"
   - ❌ 差的问题："已知：① 典型营养器官...；② lemma和palea在早期...；③ GO分析表明...；④ 晚期lemma/palea中...。应如何判断..."

2. **如果必须使用编号，严格限制**：
   - 最多使用 2 个编号点（而不是3-4个）
   - 每个编号点内容不超过 20 字符（约10个汉字）
   - 避免使用"已知："、"基于以下信息："等冗余引导词

3. **问题应直接描述事实**：
   - 将多个事实自然地融入问题描述中
   - 使用连接词（"同时"、"进一步"、"此外"等）串联多个事实
   - 避免用编号列举，而是用自然语言叙述

4. **减少假设和已知条件**：
   - 避免包含过多的条件句（"如果"、"假设"、"当...时"等，最多1个）
   - 避免过多的列举式描述（分号+冒号总计不超过3个）
   - 避免问题以条件句开头（如"如果..."、"假设..."、"已知..."）
   - 避免使用"综合这些信息"、"基于上述信息"等总结性表述
   - 问题应直接描述科学事实，而非列举多个假设条件后再提问
   - ✅ 好的问题："在禾本科作物中，lemma和palea在早期发育阶段与生殖器官类群聚在一起，而在晚期发育阶段则与营养器官类群聚在一起。GO分析进一步表明，早期lemma/palea中细胞增殖相关基因表达水平较高，晚期lemma/palea中光合作用相关基因表达水平较高。应如何判断lemma和palea在发育早、晚期分别在功能属性和器官归类上更接近哪一类器官？"
   - ❌ 差的问题："假设观测到：①成熟叶片中存在大量与昼夜节律相关的周期性基因表达；②包括典型昼夜节律相关基因在内的一部分基因在叶片、叶鞘和根中都表现出稳定的昼夜节律表达；③田间条件下根部基本不直接接受光照；④在模式植物中已有证据表明...。基于上述信息，应如何推断..."

5. **必须需要综合多个 support_facts 和推理步骤才能得出答案**，不能是抄一句话即可回答。

5. **问题要脱离原论文也成立**，不能包含"该研究/本文/本实验/文中"等指代。

6. **问题聚焦通用的科学关系或机制**（如：哪类材料更适合作为育种亲本？哪种处理能更好提高抗性？）。

7. **答案必须提供问题中未直接给出的推理过程、逻辑依据或综合结论**，而不能只是简单复述问题中的信息。

【思维链（reasoning_steps）要求】

reasoning_steps 用 4~7 步自然语言中文推理，逐步从事实推导到结论。

**重要**：reasoning_steps应该基于推理链的抽象逻辑，而非论文中的具体数值或细节。描述的是通用的科学推理过程，适用于类似的其他研究。

例如：
- ✅ 好的reasoning："主成分分析将转录组分为三大类：营养器官、生殖器官以及胚乳。Lemma和palea在早期发育阶段的表达谱与生殖器官簇在同一类中聚类，说明其整体基因表达模式在早期更类似典型生殖器官。"
- ❌ 差的reasoning："在开花后5天的样本中，lemma和palea的转录组数据显示与生殖器官的相关系数为0.85。"

【禁止内容】

- 不要在 question 或 answer 中使用表格/图编号、具体数据库编号等。
- 不要在reasoning_steps中引用具体的数值、浓度、时间等论文特有细节。
- 避免使用"已知："、"基于以下信息："、"根据以下事实："等冗余引导词。
- 严格限制编号的使用，优先使用自然语言描述。
- **禁止包含过多的假设和已知条件**：
  * 禁止问题中包含超过1个条件句（"如果"、"假设"、"当...时"等）
  * 禁止使用超过3个分号/冒号进行列举
  * 禁止问题以条件句开头
  * 禁止使用"综合这些信息"、"基于上述信息"等总结性表述
  * 禁止列举多个假设条件后再提问的模式

【输出要求】

严格输出一个 JSON 对象（而不是数组）。

不要添加额外解释或自然语言说明。"""
    return prompt


# ==============================================================================
# 7. 缺失的函数（从 v9.2 复制并集成新检查逻辑）
# ==============================================================================

def is_reasoning_suitable_section(section_name: str) -> bool:
    """
    判断section是否适合使用推理链（Chain of Thought）。

    适合推理链的section需要多步推理才能得出结论，如实验结果分析、讨论等。
    不适合的section主要是事实性陈述和总结性内容。

    Args:
        section_name: 章节名称

    Returns:
        bool: True if 适合使用推理链，False otherwise
    """
    reasoning_sections = [
        "results",
        "results & discussion",
        "discussion",
        "materials & methods",
        "methods",
        "background",
        "introduction"
    ]

    non_reasoning_sections = [
        "abstract",
        "conclusion",
        "summary"
    ]

    section_lower = section_name.lower().strip()

    # 首先检查非推理链section
    for non_reasoning in non_reasoning_sections:
        if non_reasoning in section_lower:
            return False

    # 然后检查推理链section
    for reasoning in reasoning_sections:
        if reasoning in section_lower:
            return True

    # 默认返回True（对于未明确分类的section，默认使用推理链）
    return True



def generate_simple_qas_from_section(
    section_name: str,
    section_text: str,
    model: str = DEFAULT_MODEL,
    max_q: int = 5,
    think_mode: str = "minimal",
) -> Tuple[List[Dict[str, Any]], str]:
    """
    为不适合推理链的section生成简单的问答对。
    直接从文本生成问答，不使用两阶段推理链。

    Args:
        section_name: 章节名称
        section_text: 章节文本
        model: 模型名称
        max_q: 最大问题数
        think_mode: 推理模式

    Returns:
        Tuple[List[Dict[str, Any]], str]: (qas列表, think_mode)
    """
    system_prompt, user_prompt = build_prompt(section_name, section_text, max_q)

    try:
        # 直接调用 call_responses_for_json 获取JSON格式的问答对（避免冗余调用）
        qas_data = call_responses_for_json(
            prompt=f"{system_prompt}\n\n{user_prompt}",
            model=model,
            think_mode=think_mode,  # 使用传入的think_mode参数
            max_output_tokens=8000,
        )

        if not isinstance(qas_data, list):
            print(f"  ⚠️ 返回数据不是列表格式，section={section_name}")
            return [], think_mode

        qas = []
        for item in qas_data:
            if not isinstance(item, dict):
                continue

            q = str(item.get("question", "")).strip()
            a = str(item.get("answer", "")).strip()
            difficulty = str(item.get("difficulty", "")).strip().lower()
            tags = item.get("tags", [])

            if not q or not a or len(q) < 8 or len(a) < 20:
                continue

            # 清洗文本
            q = re.sub(r'\n+', ' ', q)
            a = re.sub(r'\n+', ' ', a)
            q = re.sub(r'\s{2,}', ' ', q).strip()
            a = re.sub(r'\s{2,}', ' ', a).strip()

            # 质量检查
            if is_study_dependent(q) or is_study_dependent(a):
                continue

            if any(phrase in q for phrase in FORBIDDEN_PHRASES) or \
               any(phrase in a for phrase in FORBIDDEN_PHRASES):
                continue

            # 检查答案中是否包含问题未提及的具体物种/品种/基因
            if has_unmentioned_specific_species_or_case(q, a):
                continue

            # 先清洗文本，然后进行检查
            q_clean = sanitize_text_forbidden_phrases(q)
            a_clean = sanitize_text_forbidden_phrases(a)

            if not q_clean or not a_clean:
                continue

            # 检查编号问题（新增）
            numbered_acceptable, numbered_reason = is_acceptable_numbered_question(q_clean)
            if not numbered_acceptable:
                continue  # 跳过不符合编号要求的问题

            # 检查假设/已知条件（新增）
            has_too_many_assumptions, assumption_reason = has_too_many_assumptions_or_conditions(q_clean)
            if has_too_many_assumptions:
                continue  # 跳过包含过多假设/已知条件的问题

            # 检查答案是否只是简单复述问题内容
            if is_answer_just_restating_question(q, a):
                continue

            bad_pattern = r'(文中|本文|文章中|根据文本|根据以上文本|根据上述文本|给定文本|这段文字|这段文本|这段内容|这段研究|这段描述)'
            if re.search(bad_pattern, q_clean) or re.search(bad_pattern, a_clean):
                continue

            if is_author_related(q_clean) or is_author_related(a_clean):
                continue

            if difficulty not in ["easy", "medium", "hard"]:
                if len(q_clean) < 40:
                    difficulty = "easy"
                elif len(q_clean) < 80:
                    difficulty = "medium"
                else:
                    difficulty = "hard"

            if not isinstance(tags, list):
                tags = [str(tags)]

            qas.append({
                "question": q_clean,
                "answer": a_clean,
                "reasoning_steps": [],  # 简单问答没有推理链steps
                "question_cot": "",     # 简单问答没有cot
                "final_conclusion": "", # 简单问答没有推理结论
                "difficulty": difficulty,
                "tags": tags,
            })

        return qas, think_mode

    except Exception as e:
        tprint(f"  ❌ 简单问答生成失败，section={section_name}, error={e}")
        return [], think_mode



def generate_reasoning_qas_from_section(
    section_name: str,
    section_text: str,
    model: str = DEFAULT_MODEL,
    max_q: int = 5,
    think_mode: str = "high",
) -> Tuple[List[Dict[str, Any]], str]:
    """
    两阶段流水线：
    1) 从 section 文本抽取多条 reasoning chains
    2) 每条 chain 生成一题需要多步推理的 QA（带 cot）
    3) 对生成的 QA 做清洗/过滤，返回统一结构

    Args:
        section_name: 章节名称
        section_text: 章节文本
        model: 模型名称
        max_q: 最大问题数
        think_mode: 推理模式

    Returns:
        Tuple[List[Dict[str, Any]], str]: (qas列表, think_mode)
    """
    # 1) 抽取推理链
    chain_prompt = build_chain_extraction_prompt(
        section_name=section_name,
        section_text=section_text,
        max_chains=max_q
    )
    try:
        chain_data = call_responses_for_json(
            prompt=chain_prompt,
            model=model,
            think_mode="minimal",
            max_output_tokens=8000,
        )
    except Exception:
        tprint(f"  ❌ 推理链抽取失败，section={section_name}")
        return [], think_mode

    chains = []
    if isinstance(chain_data, dict) and "chains" in chain_data:
        chains = chain_data.get("chains", [])
    elif isinstance(chain_data, list):
        chains = chain_data
    else:
        tprint(f"  ⚠️ 推理链返回结构异常，section={section_name}")
        return [], think_mode

    if not isinstance(chains, list) or not chains:
        tprint(f"  ⚠️ 未抽取到有效推理链，section={section_name}")
        return [], think_mode

    # 2) 每条 chain 生成一题 QA
    raw_qas = []
    # 控制最多生成 max_q 题
    for chain in chains:
        if len(raw_qas) >= max_q:
            break
        try:
            # 保存第一阶段推理链的steps（来自论文的推理逻辑）
            reasoning_steps = chain.get("steps", [])
            final_conclusion = chain.get("final_conclusion", "")

            chain_json_str = json.dumps(chain, ensure_ascii=False)
            qa_prompt = build_chain_to_qa_prompt(chain_json_str)
            qa_data = call_responses_for_json(
                prompt=qa_prompt,
                model=model,
                think_mode=think_mode,
                max_output_tokens=8000,
            )
            if isinstance(qa_data, list):
                qa_list = qa_data
            else:
                qa_list = [qa_data]

            for qa in qa_list:
                if len(raw_qas) >= max_q:
                    break
                q = str(qa.get("question", "")).strip()
                a = str(qa.get("answer", "")).strip()
                meta = qa.get("meta", {}) or {}
                difficulty = str(meta.get("difficulty", qa.get("difficulty", ""))).strip().lower()
                tags = meta.get("tags", qa.get("tags", [])) or []
                # 优先从question_cot获取，兼容旧的cot字段名
                cot_raw = qa.get("question_cot", "") or qa.get("cot", "")

                # 标准化第二阶段cot：可能是 list 或 str
                if isinstance(cot_raw, list):
                    question_cot = "\n".join(str(s).strip() for s in cot_raw if str(s).strip())
                else:
                    question_cot = str(cot_raw or "").strip()

                raw_qas.append({
                    "question": q,
                    "answer": a,
                    "reasoning_steps": reasoning_steps,  # 第一阶段：论文推理链steps
                    "question_cot": question_cot,        # 第二阶段：针对问题的推理链
                    "difficulty": difficulty,
                    "tags": tags,
                    "final_conclusion": final_conclusion,  # 推理链的结论
                })
        except Exception as e:
            tprint(f"  ⚠️ 从推理链生成 QA 失败: {e}")
            continue

    if not raw_qas:
        tprint(f"  ⚠️ 推理链生成 QA 为空，section={section_name}")
        return [], think_mode

    # 3) 清洗/过滤，与原逻辑保持一致风格
    qas: List[Dict[str, Any]] = []
    for item in raw_qas:
        q = str(item.get("question", "")).strip()
        a = str(item.get("answer", "")).strip()
        difficulty = str(item.get("difficulty", "")).strip().lower()
        tags = item.get("tags", [])
        reasoning_steps = item.get("reasoning_steps", [])
        question_cot = str(item.get("question_cot", "")).strip()
        final_conclusion = str(item.get("final_conclusion", "")).strip()

        if not isinstance(tags, list):
            tags = [str(tags)]

        if not q or not a or len(q) < 8 or len(a) < 20:
            continue

        q = re.sub(r'\n+', ' ', q)
        a = re.sub(r'\n+', ' ', a)
        q = re.sub(r'\s{2,}', ' ', q).strip()
        a = re.sub(r'\s{2,}', ' ', a).strip()

        if is_study_dependent(q) or is_study_dependent(a):
            continue

        if any(phrase in q for phrase in FORBIDDEN_PHRASES) or \
           any(phrase in a for phrase in FORBIDDEN_PHRASES):
            continue

        # 检查答案中是否包含问题未提及的具体物种/品种/基因
        if has_unmentioned_specific_species_or_case(q, a):
            continue

        # 先清洗文本，然后进行检查
        q_clean = sanitize_text_forbidden_phrases(q)
        a_clean = sanitize_text_forbidden_phrases(a)

        if not q_clean or not a_clean:
            continue

        # 检查编号问题（新增）
        numbered_acceptable, numbered_reason = is_acceptable_numbered_question(q_clean)
        if not numbered_acceptable:
            continue  # 跳过不符合编号要求的问题

        # 检查假设/已知条件（新增）
        has_too_many_assumptions, assumption_reason = has_too_many_assumptions_or_conditions(q_clean)
        if has_too_many_assumptions:
            continue  # 跳过包含过多假设/已知条件的问题

        # 检查答案是否只是简单复述问题内容
        if is_answer_just_restating_question(q, a):
            continue

        if not q_clean or not a_clean:
            continue

        bad_pattern = r'(文中|本文|文章中|根据文本|根据以上文本|根据上述文本|给定文本|这段文字|这段文本|这段内容|这段研究|这段描述)'
        if re.search(bad_pattern, q_clean) or re.search(bad_pattern, a_clean):
            continue

        if is_author_related(q_clean) or is_author_related(a_clean):
            continue

        if difficulty not in ["easy", "medium", "hard"]:
            if len(q_clean) < 40:
                difficulty = "easy"
            elif len(q_clean) < 80:
                difficulty = "medium"
            else:
                difficulty = "hard"

        # 清洗两个阶段的CoT
        question_cot_clean = sanitize_text_forbidden_phrases(question_cot) if question_cot else ""
        final_conclusion_clean = sanitize_text_forbidden_phrases(final_conclusion) if final_conclusion else ""

        qas.append({
            "question": q_clean,
            "answer": a_clean,
            "reasoning_steps": reasoning_steps,      # 第一阶段：论文推理链steps
            "question_cot": question_cot_clean,      # 第二阶段：针对问题的推理链
            "final_conclusion": final_conclusion_clean,  # 推理链的结论
            "difficulty": difficulty,
            "tags": tags,
        })

    return qas, think_mode



def sample_qas_with_strategy(
    qas: List[Dict[str, Any]],
    max_q: int,
    difficulty_target: Optional[Dict[str, int]] = None,
    tag_prefer_order: Optional[List[str]] = None,
) -> List[Dict[str, Any]]:
    """
    在模型生成的一批 qas 中，按"难度配比 + tag 多样性"采样 max_q 条。

    Args:
        qas: 问答对列表
        max_q: 最大采样数
        difficulty_target: 难度目标分布
        tag_prefer_order: 标签偏好顺序

    Returns:
        List[Dict[str, Any]]: 采样后的问答对列表
    """
    if not qas:
        return []

    if difficulty_target is None:
        difficulty_target = {"easy": 1, "medium": 3, "hard": 1}

    if tag_prefer_order is None:
        tag_prefer_order = ["concept", "mechanism", "method",
                            "result", "application", "limitation"]

    buckets = {"easy": [], "medium": [], "hard": []}
    for qa in qas:
        d = qa.get("difficulty", "medium")
        if d not in buckets:
            d = "medium"
        buckets[d].append(qa)

    total_target = sum(difficulty_target.values())
    if total_target == 0:
        total_target = 1
    scale = max_q / total_target

    scaled_target = {}
    for d, v in difficulty_target.items():
        scaled_target[d] = max(0, int(round(v * scale)))

    current_sum = sum(scaled_target.values())
    if current_sum > max_q:
        for d in ["hard", "medium", "easy"]:
            while current_sum > max_q and scaled_target[d] > 0:
                scaled_target[d] -= 1
                current_sum -= 1
    elif current_sum < max_q:
        for d in ["medium", "easy", "hard"]:
            while current_sum < max_q:
                scaled_target[d] += 1
                current_sum += 1
                if current_sum == max_q:
                    break

    selected = []

    def pop_some(bucket_list: List[Dict[str, Any]], need: int) -> List[Dict[str, Any]]:
        picked = []
        for qa in bucket_list:
            if len(picked) >= need:
                break
            picked.append(qa)
        return picked

    for d in ["easy", "medium", "hard"]:
        need = scaled_target.get(d, 0)
        cand = buckets[d]
        picked = pop_some(cand, need)
        selected.extend(picked)

    if len(selected) < max_q:
        remaining_qas = [qa for qa in qas if qa not in selected]

        used_tags = set()
        for qa in selected:
            for t in qa.get("tags", []):
                used_tags.add(t)

        def tag_score(qa: Dict[str, Any]) -> float:
            tags = qa.get("tags", [])
            if not tags:
                return 0
            new_tags = [t for t in tags if t not in used_tags]
            score = len(new_tags)
            for t in new_tags:
                if t in tag_prefer_order:
                    score += (len(tag_prefer_order) - tag_prefer_order.index(t)) * 0.1
            return score

        remaining_qas_sorted = sorted(
            remaining_qas,
            key=lambda qa: tag_score(qa),
            reverse=True
        )

        for qa in remaining_qas_sorted:
            if len(selected) >= max_q:
                break
            selected.append(qa)
            for t in qa.get("tags", []):
                used_tags.add(t)

    if len(selected) < max_q and len(selected) < len(qas):
        for qa in qas:
            if qa not in selected:
                selected.append(qa)
                if len(selected) >= max_q:
                    break

    return selected[:max_q]



def _parse_cell_to_id_and_rel_path(cell_value: Any) -> Tuple[Optional[str], Optional[str]]:
    """
    将单元格内容解析为 (id, rel_path)。

    Args:
        cell_value: Excel单元格值

    Returns:
        Tuple[Optional[str], Optional[str]]: (id, rel_path)
    """
    if pd.isna(cell_value):
        return None, None

    s = str(cell_value).strip()
    if not s:
        return None, None

    s = s.replace("\\", "/")

    if "/" in s:
        rel_path = s.lstrip("/")
        fname = os.path.basename(rel_path)
        if "." in fname:
            id_base = fname.rsplit(".", 1)[0]
        else:
            id_base = fname
        return id_base, rel_path

    fname = os.path.basename(s)
    if "." in fname:
        id_base = fname.rsplit(".", 1)[0]
    else:
        id_base = fname
    return id_base, None



def get_id_list_from_excel(excel_path: str) -> List[Dict[str, Any]]:
    """
    从Excel文件中读取ID及相对路径列表。

    Args:
        excel_path: Excel文件路径

    Returns:
        List[Dict[str, Any]]: ID列表
    """
    try:
        df = pd.read_excel(excel_path)

        if df.shape[1] < 39:
            print(f"❌ Excel文件列数不足，无法读取AL列和AM列（需要至少39列）")
            return []

        al_col_idx = 37
        am_col_idx = 38
        species_col_idx = 1  # B列

        items = []
        seen = set()

        for row_idx, row in df.iterrows():
            al_value = row.iloc[al_col_idx] if al_col_idx < df.shape[1] else None
            am_value = row.iloc[am_col_idx] if am_col_idx < df.shape[1] else None

            al_id, al_rel = _parse_cell_to_id_and_rel_path(al_value)
            am_id, am_rel = _parse_cell_to_id_and_rel_path(am_value)

            id_value = None
            alt_id_value = None
            rel_path = None
            alt_rel_path = None
            species_value = None

            if al_id and am_id:
                if al_id != am_id:
                    id_value, rel_path = al_id, al_rel
                    alt_id_value, alt_rel_path = am_id, am_rel
                    print(f"ℹ️  行 {row_idx + 2}: AL列ID='{al_id}' 与 AM列ID='{am_id}' 不同，将先尝试AL列")
                else:
                    id_value, rel_path = al_id, al_rel
            elif al_id:
                id_value, rel_path = al_id, al_rel
            elif am_id:
                id_value, rel_path = am_id, am_rel
            else:
                continue

            if species_col_idx < df.shape[1]:
                s_val = row.iloc[species_col_idx]
                if pd.notna(s_val):
                    species_value = str(s_val).strip()

            if id_value:
                clean_id = str(id_value).strip()
                dedup_key = (clean_id, alt_id_value) if alt_id_value else clean_id
                if clean_id and dedup_key not in seen:
                    seen.add(dedup_key)
                    item = {
                        "id": clean_id,
                        "rel_path": rel_path,
                        "species": species_value,
                    }
                    if alt_id_value:
                        item["alt_id"] = alt_id_value
                        item["alt_rel_path"] = alt_rel_path
                    items.append(item)

        print(f"✅ 从Excel文件读取到 {len(items)} 个唯一ID（含相对路径信息）")
        return items

    except Exception as e:
        print(f"❌ 读取Excel文件失败: {e}")
        import traceback
        traceback.print_exc()
        return []



def save_not_found_rows_to_excel(
    excel_path: str,
    not_found_ids: List[str],
    output_xlsx: str,
) -> None:
    """
    将未匹配上的 ID 对应的整行信息，从原始 Excel 中筛选出来，保存到新的 xlsx。

    Args:
        excel_path: 原始Excel路径
        not_found_ids: 未找到的ID列表
        output_xlsx: 输出Excel路径
    """
    if not not_found_ids:
        print("ℹ️ 未匹配 ID 列表为空，不生成未匹配 Excel。")
        return

    try:
        df = pd.read_excel(excel_path)
        if df.shape[1] < 39:
            print("❌ 原始 Excel 列数不足（<39），无法按 AL/AM 列重建 ID 进行匹配。")
            return

        al_col_idx = 37
        am_col_idx = 38

        extracted_ids = []
        for _, row in df.iterrows():
            id_value = None
            al_value = row.iloc[al_col_idx] if al_col_idx < df.shape[1] else None
            am_value = row.iloc[am_col_idx] if am_col_idx < df.shape[1] else None
            al_id, _ = _parse_cell_to_id_and_rel_path(al_value)
            am_id, _ = _parse_cell_to_id_and_rel_path(am_value)

            if al_id and am_id:
                id_value = al_id
            elif al_id:
                id_value = al_id
            elif am_id:
                id_value = am_id

            extracted_ids.append(id_value.strip() if isinstance(id_value, str) else None)

        df_ids = pd.Series(extracted_ids, name="__ID__")
        df_with_id = df.copy()
        df_with_id["__ID__"] = df_ids

        not_found_set = set(not_found_ids)
        mask = df_with_id["__ID__"].isin(not_found_set)
        df_not_found = df_with_id[mask].copy()

        if df_not_found.empty:
            print("⚠️ 未在原始 Excel 中找到与未匹配 ID 对应的行，未生成 xlsx。")
            return

        df_not_found = df_not_found.drop(columns=["__ID__"])

        os.makedirs(os.path.dirname(output_xlsx), exist_ok=True)
        df_not_found.to_excel(output_xlsx, index=False)
        print(f"✅ 未匹配 ID 及对应行信息已保存到: {output_xlsx} (共 {len(df_not_found)} 行)")

    except Exception as e:
        print(f"❌ 生成未匹配 ID xlsx 失败: {e}")
        import traceback
        traceback.print_exc()



def find_file_by_id(
    id_str: str,
    search_paths: Optional[List[str]] = None,
    rel_path: Optional[str] = None
) -> Optional[str]:
    """
    根据 ID 和可选的相对路径查找 md 文件。

    Args:
        id_str: ID字符串
        search_paths: 搜索路径列表
        rel_path: 相对路径

    Returns:
        Optional[str]: 找到的文件路径
    """
    id_clean = id_str.strip()
    if "." in id_clean:
        id_base = id_clean.rsplit(".", 1)[0]
    else:
        id_base = id_clean

    # 先使用 ID（例如 PMC8217532）在 SEARCH_BASE_PATHS 下直接匹配文件
    base_paths = search_paths if search_paths else SEARCH_BASE_PATHS
    for base in base_paths:
        md_path = os.path.join(base, f"{id_base}.md")
        if os.path.exists(md_path):
            return md_path

    # 如果按 ID 未找到，再回退到使用 rel_path + 旧 pubmed 目录结构
    if rel_path:
        rel_norm = rel_path.lstrip("/").replace("\\", "/")
        pubmed_base = SEARCH_BASE_PATHS[0] if SEARCH_BASE_PATHS else ""
        if not rel_norm.lower().endswith(".md"):
            rel_norm_md = rel_norm + ".md"
        else:
            rel_norm_md = rel_norm
        candidate = os.path.join(pubmed_base, rel_norm_md)
        if os.path.exists(candidate):
            return candidate

    return None



def ensure_output_dir(output_path: str) -> None:
    """确保输出目录存在"""
    output_dir = os.path.dirname(output_path)
    if output_dir:
        os.makedirs(output_dir, exist_ok=True)



def process_single_md(
    md_path: str,
    output_jsonl: Optional[str] = None,
    paper_id: Optional[str] = None,
    species: Optional[str] = None,
    by_section: bool = True,
    max_q_per_section: int = 5,
    model: str = DEFAULT_MODEL,
    min_section_length: int = MAX_SECTION_LENGTH,
) -> Tuple[List[Dict[str, Any]], int]:
    """
    处理单个 md 文件，生成问答记录列表。

    注意：所有section都使用推理链生成，所有问答对都包含推理过程。

    Args:
        md_path: Markdown文件路径
        output_jsonl: 输出JSONL文件路径（可选，如果为None则不写入文件）
        paper_id: 论文ID
        species: 物种信息
        by_section: 是否按章节处理
        max_q_per_section: 每章节最大问题数
        model: 模型名称
        min_section_length: 最小章节长度

    Returns:
        Tuple[List[Dict[str, Any]], int]: (问答对记录列表, 生成的问答对数量)
    """
    if paper_id is None:
        paper_id = Path(md_path).stem

    try:
        with open(md_path, "r", encoding="utf-8") as f:
            raw_md = f.read()
    except Exception as e:
        print(f"❌ 读取文件失败: {md_path}, error={e}")
        return [], 0

    sections = split_md_into_sections(raw_md)
    tprint(f"  找到 {len(sections)} 个章节: {list(sections.keys())}")

    units = []
    if not by_section or len(sections) <= 1:
        full_text = "\n\n".join(sections.values())
        if len(full_text) < 500:
            print(f"[WARN] {paper_id} 全文内容过短，跳过")
            return [], 0
        print("  ℹ️  仅有一个section/无法可靠切分，按全文 FullPaper 生成问答")
        units.append(("FullPaper", full_text))
    else:
        section_priority = {
            "Abstract": 1,
            "Summary": 1,
            "Background": 2,
            "Introduction": 3,
            "Materials & Methods": 4,
            "Methods": 4,
            "Results": 5,
            "Results & Discussion": 5,
            "Discussion": 6,
            "Conclusion": 7
        }

        sorted_sections = sorted(
            sections.items(),
            key=lambda x: section_priority.get(x[0], 999)
        )

        for sec_name, sec_text in sorted_sections:
            if len(sec_text) < min_section_length:
                tprint(f"  ⏭️  跳过章节: {sec_name} (内容过短: {len(sec_text)} 字符)")
                continue
            units.append((sec_name, sec_text))
            if len(units) >= 6:
                tprint("  ⏹️  达到章节数量上限，跳过剩余章节")
                break

    if not units:
        print(f"[WARN] {paper_id} 无可用章节，跳过")
        return [], 0

    if output_jsonl:
        ensure_output_dir(output_jsonl)

    all_records: List[Dict[str, Any]] = []
    total_qas = 0

    if len(units) == 1:
        actual_max_q = 3
        tprint(f"  ℹ️  文章只有1个section，将生成3个问题")
    else:
        actual_max_q = max_q_per_section

    model_max_q = actual_max_q * OVER_GENERATE_FACTOR

    # 所有section都使用推理链生成，取消限制
    # 使用锁保护文件写入（线程安全）
    for sec_name, sec_text in units:
            # 所有section都使用推理链生成
            tprint(f"▶ 生成推理型问答对: {sec_name} (使用推理链生成)")
            # 使用两阶段推理链方案
            raw_qas, think_mode = generate_reasoning_qas_from_section(
                section_name=sec_name,
                section_text=sec_text,
                model=model,
                max_q=model_max_q,
                think_mode="high",
            )
            generation_type = "推理型"

            if not raw_qas:
                tprint("  - 未生成有效问答对")
                continue

            sampled_qas = sample_qas_with_strategy(
                raw_qas,
                max_q=actual_max_q,
                difficulty_target={"easy": 1, "medium": 3, "hard": 1},
                tag_prefer_order=["concept", "mechanism", "method",
                                  "result", "application", "limitation"],
            )

            tprint(f"  📌 {generation_type}模型原始生成 {len(raw_qas)} 题，采样保留 {len(sampled_qas)} 题")

            if not sampled_qas:
                continue

            # 收集所有问答对记录
            for qa in sampled_qas:
                q = qa["question"]
                a = qa["answer"]
                difficulty = qa.get("difficulty", "medium")
                tags = qa.get("tags", [])
                reasoning_steps = qa.get("reasoning_steps", [])
                question_cot = qa.get("question_cot", "")
                final_conclusion = qa.get("final_conclusion", "")

                record = {
                    "species": species,
                    "paper_id": paper_id,
                    "question": q,
                    "answer": a,
                    "reasoning_steps": reasoning_steps,    # 第一阶段：论文推理链steps
                    "question_cot": question_cot,          # 第二阶段：针对问题的推理链
                    "final_conclusion": final_conclusion,  # 推理链的结论
                    "difficulty": difficulty,
                    "tags": tags,
                    "created_at": datetime.now().isoformat(timespec="seconds"),
                    "token_est_question": estimate_tokens(q),
                    "token_est_answer": estimate_tokens(a),
                    "section": sec_name,
                    "context": sec_text,
                    "Thinking模式": think_mode,
                    "generation_type": generation_type,    # 记录生成类型
                }
                all_records.append(record)

            total_qas += len(sampled_qas)
            tprint(f"  ✅ 生成 {len(sampled_qas)} 个{generation_type}问答对")

    tprint(f"📊 论文 {paper_id} 总计生成 {total_qas} 个问答对")
    return all_records, total_qas



def _process_single_id_item_with_thread(
    item: Union[str, Dict[str, Any]],
    item_index: int,
    total_count: int,
    search_paths: List[str],
    not_found_file: Optional[str],
    processed_ids: set,
    already_not_found_ids: set,
    by_section: bool,
    max_q_per_section: int,
    model: str,
    thread_id: int,
) -> Tuple[Optional[List[Dict[str, Any]]], Optional[int], Optional[str]]:
    """处理单个ID项（带线程标识的包装函数）"""
    set_thread_id(thread_id)
    return _process_single_id_item(
        item=item,
        item_index=item_index,
        total_count=total_count,
        search_paths=search_paths,
        not_found_file=not_found_file,
        processed_ids=processed_ids,
        already_not_found_ids=already_not_found_ids,
        by_section=by_section,
        max_q_per_section=max_q_per_section,
        model=model,
    )



def _process_single_id_item(
    item: Union[str, Dict[str, Any]],
    item_index: int,
    total_count: int,
    search_paths: List[str],
    not_found_file: Optional[str],
    processed_ids: set,
    already_not_found_ids: set,
    by_section: bool,
    max_q_per_section: int,
    model: str,
) -> Tuple[Optional[List[Dict[str, Any]]], Optional[int], Optional[str]]:
    """
    处理单个ID项（用于并发执行）。

    Args:
        item: ID项（字符串或字典）
        item_index: 项索引（从1开始）
        total_count: 总数量
        search_paths: 搜索路径列表
        not_found_file: 未找到ID文件路径
        processed_ids: 已处理ID集合
        already_not_found_ids: 已确认未找到ID集合
        by_section: 是否按章节处理
        max_q_per_section: 每章节最大问题数
        model: 模型名称

    Returns:
        Tuple[Optional[List[Dict[str, Any]]], Optional[int], Optional[str]]:
        (问答对记录列表, 生成的问答对数, 未找到的ID) 或 (None, None, None) 如果跳过
    """
    if isinstance(item, dict):
        id_str = str(item.get("id", "")).strip()
        rel_path = item.get("rel_path")
        species = item.get("species")
        alt_id = item.get("alt_id")
        alt_rel_path = item.get("alt_rel_path")
    else:
        id_str = str(item).strip()
        rel_path = None
        species = None
        alt_id = None
        alt_rel_path = None

    tprint(f"\n=== [{item_index}/{total_count}] 处理 ID: {id_str} ===")
    tprint(f"  ID: {id_str}")
    if alt_id:
        tprint(f"  备用ID (AM列): {alt_id}")

    if id_str in processed_ids:
        tprint(f"  ⏭️  已在输出文件中存在记录，跳过该 ID。")
        return None, None, None

    if id_str in already_not_found_ids:
        tprint(f"  ⏭️  之前已确认未找到文件，本次跳过该 ID。")
        return None, None, id_str

    file_path = find_file_by_id(id_str, search_paths, rel_path=rel_path)
    used_id = id_str

    if not file_path and alt_id:
        tprint(f"  ℹ️  AL列ID '{id_str}' 未找到文件，尝试AM列ID '{alt_id}'")
        file_path = find_file_by_id(alt_id, search_paths, rel_path=alt_rel_path)
        if file_path:
            used_id = alt_id
            tprint(f"  ✅ 使用AM列ID '{alt_id}' 找到文件")

    if not file_path:
        tprint(f"❌ 未找到文件: {id_str}" + (f" 和 {alt_id}" if alt_id else ""))
        if not_found_file:
            nf_dir = os.path.dirname(not_found_file)
            if nf_dir:
                os.makedirs(nf_dir, exist_ok=True)

            need_header = not os.path.exists(not_found_file)
            mode = "a" if os.path.exists(not_found_file) else "w"
            with open(not_found_file, mode, encoding="utf-8") as f:
                if need_header:
                    f.write("未找到的文件ID列表:\n")
                f.write(f"{id_str}\n")
        return None, None, id_str

    tprint(f"✅ 找到文件: {file_path}")
    md_name = os.path.basename(file_path) if file_path else ""
    tprint(f"  md_name: {md_name}")

    try:
        records, paper_qas_count = process_single_md(
            md_path=file_path,
            output_jsonl=None,  # 不直接写入，返回记录列表
            paper_id=used_id,
            species=species,
            by_section=by_section,
            max_q_per_section=max_q_per_section,
            model=model,
        )
        return records, paper_qas_count, None
    except Exception as e:
        tprint(f"  ❌ 处理文件失败: {e}")
        import traceback
        traceback.print_exc()
        return None, None, None



def batch_process_by_id_list(
    id_list: List[Union[str, Dict[str, Any]]],
    search_paths: List[str],
    output_jsonl: str,
    not_found_file: Optional[str] = None,
    excel_path: Optional[str] = None,
    not_found_excel: Optional[str] = None,
    by_section: bool = True,
    max_q_per_section: int = 5,
    model: str = DEFAULT_MODEL,
    max_workers: int = 64,
) -> Tuple[int, int, List[str]]:
    """
    根据ID列表批量处理文件（支持并发处理）。

    Args:
        id_list: ID列表
        search_paths: 搜索路径列表
        output_jsonl: 输出JSONL文件路径
        not_found_file: 未找到ID文件路径
        excel_path: Excel文件路径
        not_found_excel: 未找到ID的Excel输出路径
        by_section: 是否按章节处理
        max_q_per_section: 每章节最大问题数
        model: 模型名称
        max_workers: 最大并发工作线程数（默认4，避免API限流）

    Returns:
        Tuple[int, int, List[str]]: (处理论文数, 总问答对数, 未找到ID列表)
    """
    ensure_output_dir(output_jsonl)

    if not_found_file:
        ensure_output_dir(not_found_file)

    processed_ids = set()
    already_not_found_ids = set()

    if os.path.exists(output_jsonl):
        try:
            with open(output_jsonl, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        obj = json.loads(line)
                        pid = str(obj.get("paper_id", "")).strip()
                        if pid:
                            processed_ids.add(pid)
                    except Exception:
                        continue
            if processed_ids:
                print(f"🔁 检测到已有进度：JSONL 中已包含 {len(processed_ids)} 个 paper_id，将在本次运行中自动跳过。")
        except Exception as e:
            print(f"⚠️  读取已有 JSONL 进度失败（忽略继续）: {e}")

    if not_found_file and os.path.exists(not_found_file):
        try:
            with open(not_found_file, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line or line.startswith("未找到的文件ID列表"):
                        continue
                    already_not_found_ids.add(line)
            if already_not_found_ids:
                print(f"🔁 检测到已有未找到 ID 记录 {len(already_not_found_ids)} 条，本次将默认跳过这些 ID 的文件查找。")
        except Exception as e:
            print(f"⚠️  读取已有未找到 ID 列表失败（忽略继续）: {e}")

    print(f"开始处理 {len(id_list)} 个ID")
    print(f"搜索路径: {search_paths}")
    print(f"输出 JSONL: {output_jsonl}")
    print(f"按 section 生成: {by_section}, 每个 section 至多 {max_q_per_section} 题")
    print(f"并发处理: 最大 {max_workers} 个工作线程\n")

    # 重置LLM调用计数器
    reset_llm_call_counter()

    total_papers_processed = 0
    total_all_qas = 0
    not_found_ids = []

    # 记录开始时间（全局）
    global _stats_start_time, _stats_total_qas, _stats_total_papers, _stats_update_func, _stats_last_print_time
    _stats_start_time = time.time()
    _stats_total_qas = 0
    _stats_total_papers = 0
    _stats_last_print_time = _stats_start_time - 60  # 确保首次调用会打印

    def update_statistics(force: bool = False):
        """更新并显示实时统计信息（按分钟节流）"""
        if _stats_start_time is None:
            return
        now_ts = time.time()
        # 节流：每60秒更新一次，除非强制
        global _stats_last_print_time
        if not force and (now_ts - _stats_last_print_time) < 60:
            return

        _stats_last_print_time = now_ts
        elapsed_time = now_ts - _stats_start_time
        hours = int(elapsed_time // 3600)
        minutes = int((elapsed_time % 3600) // 60)
        seconds = int(elapsed_time % 60)
        time_str = f"{hours:02d}:{minutes:02d}:{seconds:02d}"

        llm_count = get_llm_call_count()

        # 使用全局变量获取统计信息
        with _stats_lock:
            current_total_qas = _stats_total_qas
            current_total_papers = _stats_total_papers

        # 使用 \r 实现同一行更新
        stats_line = f"\r📊 实时统计 | 运行时长: {time_str} | LLM调用: {llm_count} 次 | 已处理论文: {current_total_papers} 篇 | 问答对总数: {current_total_qas} 个"
        print(stats_line, end="", flush=True)

    # 设置全局统计更新函数
    _stats_update_func = update_statistics

    # 显示初始统计行
    print("\n📊 实时统计 | 运行时长: 00:00:00 | LLM调用: 0 次 | 已处理论文: 0 篇 | 问答对总数: 0 个", end="", flush=True)

    # 使用线程池并发处理
    # 使用字典存储结果，key为item_index，用于按顺序写入
    results_dict: Dict[int, Tuple[Optional[List[Dict[str, Any]]], Optional[int], Optional[str]]] = {}
    # 记录已写入的索引，用于最终检查
    written_indices = set()

    # 线程编号分配器
    thread_counter = 0
    thread_counter_lock = Lock()

    def get_next_thread_id():
        """获取下一个线程编号（1-64循环）"""
        nonlocal thread_counter
        with thread_counter_lock:
            thread_counter = (thread_counter % max_workers) + 1
            return thread_counter

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        # 提交所有任务
        futures = {}
        for i, item in enumerate(id_list, 1):
            thread_id = get_next_thread_id()
            future = executor.submit(
                _process_single_id_item_with_thread,
                item=item,
                item_index=i,
                total_count=len(id_list),
                search_paths=search_paths,
                not_found_file=not_found_file,
                processed_ids=processed_ids,
                already_not_found_ids=already_not_found_ids,
                by_section=by_section,
                max_q_per_section=max_q_per_section,
                model=model,
                thread_id=thread_id,
            )
            futures[future] = i

        # 收集结果并立即写入（每个论文处理完成后立即写入，避免数据丢失）
        for future in as_completed(futures):
            try:
                item_idx = futures[future]
                records, paper_qas_count, not_found_id = future.result()
                results_dict[item_idx] = (records, paper_qas_count, not_found_id)

                # 立即写入该论文的所有问答对（线程安全）
                if not_found_id:
                    not_found_ids.append(not_found_id)
                    # 标记为已处理（即使未找到文件，也避免重复检查）
                    written_indices.add(item_idx)
                elif records is not None and len(records) > 0:
                    with _file_write_lock:
                        with open(output_jsonl, "a", encoding="utf-8") as fout:
                            # 一次性写入该论文的所有问答对，确保连续
                            for record in records:
                                fout.write(json.dumps(record, ensure_ascii=False) + "\n")
                            fout.flush()  # 立即刷新到磁盘

                    total_all_qas += len(records)
                    if paper_qas_count and paper_qas_count > 0:
                        total_papers_processed += 1
                    written_indices.add(item_idx)

                    # 更新全局统计变量
                    with _stats_lock:
                        _stats_total_qas = total_all_qas
                        _stats_total_papers = total_papers_processed

                    # 更新实时统计
                    update_statistics()
                elif records is not None:
                    # records 是空列表，说明处理完成但没有生成QA对，标记为已处理
                    written_indices.add(item_idx)
                else:
                    # records 是 None，说明处理失败或跳过，标记为已处理以避免重复检查
                    written_indices.add(item_idx)
            except Exception as e:
                item_idx = futures[future]
                # 获取线程ID用于显示
                try:
                    thread_id = get_thread_id()
                    tprint(f"  ❌ 处理第 {item_idx} 项时发生异常: {e}")
                except:
                    print(f"  ❌ 处理第 {item_idx} 项时发生异常: {e}")
                import traceback
                traceback.print_exc()
                results_dict[item_idx] = (None, None, None)

    # 检查是否有未写入的结果（按顺序补写，确保同一paper_id的问答对连续）
    # 注意：由于并发处理，可能有些论文已经写入，这里只处理遗漏的
    remaining_to_write = []
    for i in range(1, len(id_list) + 1):
        if i not in results_dict or i in written_indices:
            continue

        records, paper_qas_count, not_found_id = results_dict[i]
        if records is not None and len(records) > 0:
            remaining_to_write.append((i, records, paper_qas_count))

    # 如果有遗漏的，按顺序写入
    if remaining_to_write:
        print(f"\n📝 补写遗漏的 {len(remaining_to_write)} 个论文的问答对...")
        remaining_to_write.sort(key=lambda x: x[0])  # 按索引排序
        with open(output_jsonl, "a", encoding="utf-8") as fout:
            for i, records, paper_qas_count in remaining_to_write:
                for record in records:
                    fout.write(json.dumps(record, ensure_ascii=False) + "\n")
                total_all_qas += len(records)
                if paper_qas_count and paper_qas_count > 0:
                    total_papers_processed += 1

        # 更新全局统计变量
        with _stats_lock:
            _stats_total_qas = total_all_qas
            _stats_total_papers = total_papers_processed
        update_statistics(force=True)

    # 最终更新统计并换行（强制刷新一次）
    update_statistics(force=True)
    print()  # 换行，让统计行完整显示

    # 显示最终LLM调用统计
    final_call_count = get_llm_call_count()
    print(f"📊 LLM调用统计: 本次运行共调用 {final_call_count} 次")

    if not_found_ids or already_not_found_ids:
        all_not_found = sorted(set(already_not_found_ids) | set(not_found_ids))
        print(f"\n⚠️  未找到 {len(all_not_found)} 个文件 (本次新增 {len(not_found_ids)} 个):")
        for id_str in all_not_found:
            print(f"  - {id_str}")

        if not_found_file:
            nf_dir = os.path.dirname(not_found_file)
            if nf_dir:
                os.makedirs(nf_dir, exist_ok=True)
            with open(not_found_file, "w", encoding="utf-8") as f:
                f.write("未找到的文件ID列表:\n")
                for id_str in all_not_found:
                    f.write(f"{id_str}\n")
            print(f"✅ 未找到的文件列表已汇总保存到: {not_found_file}")

        if excel_path and not_found_excel and all_not_found:
            print(f"\n📄 正在根据未匹配 ID 生成 Excel 汇总: {not_found_excel}")
            save_not_found_rows_to_excel(
                excel_path=excel_path,
                not_found_ids=all_not_found,
                output_xlsx=not_found_excel,
            )

    print("\n🎉 全部处理完成!")
    print(f"📊 统计: 成功处理 {total_papers_processed}/{len(id_list)} 篇论文")
    print(f"        生成 {total_all_qas} 个问答对")

    return total_papers_processed, total_all_qas, not_found_ids




# ==============================================================================
# 8. 主程序入口
# ==============================================================================

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="论文QA生成器")
    parser.add_argument("--excel", default=None, help="Excel文件路径（含论文ID列表）")
    parser.add_argument("--output", default="output/paper_qa.jsonl", help="输出JSONL文件路径")
    parser.add_argument("--search-paths", default=None, help="论文MD文件搜索路径，多个用冒号分隔")
    parser.add_argument("--max-q-per-section", type=int, default=1, help="每个section最大问题数")
    args = parser.parse_args()

    # ========== 配置参数 ==========
    excel_path = args.excel
    output_jsonl = args.output
    not_found_file = output_jsonl.replace(".jsonl", "_not_found.txt")
    not_found_excel = output_jsonl.replace(".jsonl", "_not_found.xlsx")
    max_q_per_section = args.max_q_per_section

    search_paths = args.search_paths.split(":") if args.search_paths else SEARCH_BASE_PATHS
    by_section = True

    print("📋 从Excel文件读取ID列表（AL列和AM列）...")
    if excel_path:
        id_list = get_id_list_from_excel(excel_path)
    else:
        # 没有Excel时，自动扫描搜索路径中的MD文件
        print("⚠️  未提供Excel文件，自动扫描搜索路径中的MD文件...")
        id_list = []
        seen = set()
        for sp in search_paths:
            sp_dir = Path(sp)
            if sp_dir.is_dir():
                for md_file in sorted(sp_dir.rglob("*.md")):
                    file_id = md_file.stem
                    if file_id not in seen:
                        seen.add(file_id)
                        id_list.append({
                            'id': file_id,
                            'rel_path': str(md_file.relative_to(sp_dir)),
                            'alt_id': None,
                            'alt_rel_path': None,
                            'species': 'unknown',
                        })
        print(f"📂 从搜索路径扫描到 {len(id_list)} 个MD文件")

    if not id_list:
        print("❌ 未读取到ID列表，程序退出")
        exit(1)

    batch_process_by_id_list(
        id_list=id_list,
        search_paths=search_paths,
        output_jsonl=output_jsonl,
        not_found_file=not_found_file,
        excel_path=excel_path,
        not_found_excel=not_found_excel,
        by_section=by_section,
        max_q_per_section=max_q_per_section,
        model=DEFAULT_MODEL,
    )
