from openai import OpenAI
import pandas as pd
import json
import os
import time
import hashlib
from collections import defaultdict
from typing import List, Dict, Any, Optional, Tuple
import re
import csv
import uuid
from datetime import datetime
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from concurrent.futures import ThreadPoolExecutor, as_completed
from functools import partial
from dotenv import load_dotenv
import logging
import textwrap
import shutil
import random
import argparse

# ==== 配置日志 ====
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[
        logging.FileHandler("api_processing.log", encoding="utf-8"),
        logging.StreamHandler(),
    ],
)
logger = logging.getLogger(__name__)

# ==== 重试配置常量 ====
RETRY_CONFIG = {
    "sync_total_retries": 8,
    "sync_connect_retries": 5,
    "sync_read_retries": 5,
    "sync_status_retries": 5,
    "async_retries": 8,
    "backoff_factor": 1.5,
    "max_retry_delay": 60,
    "retryable_status_codes": [408, 409, 429, 500, 502, 503, 504],
    "rate_limit_min_wait": 5.0,
}

# ==== API 配置 ====
load_dotenv()

# ==== API 端点配置 ====
# 支持多种 API 端点选择
# 可以通过环境变量 API_BASE_URL 或 OPENAI_BASE_URL 覆盖默认端点
DEFAULT_API_BASE_URL = os.getenv(
    "OPENAI_BASE_URL",
    os.getenv("API_BASE_URL", "https://api.openai.com/v1")
)
# Fallback 到特殊端点（如果默认端点不可用）
FALLBACK_API_BASE_URL = "https://api.deepseek.com/v3.2_speciale_expires_on_20251215"

# ==== API Key 选择逻辑 ====
def get_api_key_for_endpoint(base_url: str) -> str:
    """
    根据端点 URL 选择合适的 API Key
    - DeepSeek 相关端点: 使用 DEEPSEEK_API_KEY
    - 其他端点: 使用 OPENAI_API_KEY
    """
    # 检查是否为 DeepSeek 端点
    if "deepseek.com" in base_url.lower():
        deepseek_api_key = os.getenv("DEEPSEEK_API_KEY")
        if deepseek_api_key:
            logger.info(f"使用 DeepSeek API Key (端点: {base_url})")
            return deepseek_api_key
        else:
            raise ValueError(
                f"DEEPSEEK_API_KEY 未在环境变量中设置，但使用了 DeepSeek 端点: {base_url}"
            )
    else:
        openai_api_key = os.getenv("OPENAI_API_KEY")
        if openai_api_key:
            logger.info(f"使用 OpenAI API Key (端点: {base_url})")
            return openai_api_key
        else:
            raise ValueError(
                f"OPENAI_API_KEY 未在环境变量中设置，但使用了非 DeepSeek 端点: {base_url}"
            )

# ==== OpenAI 客户端初始化 ====
# 获取适合当前端点的 API Key
try:
    api_key = get_api_key_for_endpoint(DEFAULT_API_BASE_URL)

    client = OpenAI(
        api_key=api_key,
        base_url=DEFAULT_API_BASE_URL,
    )
    logger.info(f"OpenAI 客户端初始化完成 - 端点: {DEFAULT_API_BASE_URL}")
except Exception as e:
    logger.warning(f"默认端点初始化失败: {e}")
    # 尝试使用 fallback 端点
    try:
        fallback_api_key = get_api_key_for_endpoint(FALLBACK_API_BASE_URL)
        client = OpenAI(
            api_key=fallback_api_key,
            base_url=FALLBACK_API_BASE_URL,
        )
        logger.info(f"使用 Fallback 端点: {FALLBACK_API_BASE_URL}")
    except Exception as fallback_error:
        logger.error(f"Fallback 端点也初始化失败: {fallback_error}")
        raise

# 配置同步会话（给 RAG 用）
sync_session = requests.Session()
retry_strategy = Retry(
    total=RETRY_CONFIG["sync_total_retries"],
    connect=RETRY_CONFIG["sync_connect_retries"],
    read=RETRY_CONFIG["sync_read_retries"],
    status=RETRY_CONFIG["sync_status_retries"],
    status_forcelist=RETRY_CONFIG["retryable_status_codes"],
    allowed_methods=[
        "HEAD",
        "GET",
        "PUT",
        "DELETE",
        "OPTIONS",
        "POST",
        "TRACE",
    ],
    backoff_factor=RETRY_CONFIG["backoff_factor"],
    respect_retry_after_header=True,
    raise_on_status=False,
)
adapter = HTTPAdapter(
    pool_connections=1000,
    pool_maxsize=1000,
    max_retries=retry_strategy,
    pool_block=False,
)
sync_session.mount("http://", adapter)
sync_session.mount("https://", adapter)
logger.info("同步API客户端初始化完成 (连接池: 1000, 重试: 8次, 指数退避: 1.5倍)")

# ==== 支持的模型列表 ====
SUPPORTED_MODELS = {
    # OpenAI GPT 系列
    "gpt-5.1": "GPT-5.1",
    "gpt5.1": "GPT-5.1",
    "gpt-5.2": "GPT-5.2",
    "gpt-4o": "GPT-4o",
    # Claude 系列
    "claude-sonnet-4-5-20250929": "Claude Sonnet 4.5 (2025-09-29)",
    "claude-sonnet-4-5-20250929-thinking": "Claude Sonnet 4.5 Thinking (2025-09-29)",
    "claude-sonnet-4-20250514": "Claude Sonnet 4 (Deprecated, 2025-05-14)",
    "claude-opus-4-20250514": "Claude Opus 4 (Deprecated, 2025-05-14)",
    "claude-3-5-haiku-20241022": "Claude 3.5 Haiku (2024-10-22)",
    # Gemini 系列
    "gemini-2-5-pro": "Gemini 2.5 Pro",
    "gemini-2-5-flash": "Gemini 2.5 Flash",
    # DeepSeek 系列
    "deepseek-v3.2": "DeepSeek V3.2",
    "deepseek-v3.2-thinking": "DeepSeek V3.2 Thinking",
    "deepseek-v3": "DeepSeek V3",
    "deepseek-v2.5": "DeepSeek V2.5",
    # Grok 系列
    "grok-4-1-fast-reasoning": "Grok 4.1 Fast (Reasoning)",
    # GLM 系列
    "glm-4.6": "GLM-4.6",
    # Qwen 系列
    "qwen3-30b-a3b": "Qwen3 30B A3B",
    "qwen3-30b-a3b-think": "Qwen3 30B A3B Think",
    "qwen-max": "Qwen Max",
    "qwen-plus": "Qwen Plus",
    "qwen-turbo": "Qwen Turbo",
    "gpt-oss-120b": "GPT-OSS-120B",
    # 默认模型
    "default": "gpt-5.1",
}

# 思考模式模型后缀映射
THINKING_MODEL_SUFFIXES = ["-thinking", "-think", "-cot", "-reasoning"]

# 需要使用Chat Completions API的模型列表
# 需要使用Chat Completions API的模型列表
MODELS_REQUIRE_CHAT_COMPLETIONS = [
    "qwen-max",
    "qwen-plus",
    "qwen-turbo",
    "claude-sonnet-4-5-20250929",
    "claude-sonnet-4-5-20250929-thinking",
    "deepseek-v3.2",
    "deepseek-v3.2-thinking",
    "grok-4-1-fast-reasoning",
    "glm-4.6",
    "qwen3-30b-a3b-think",
    "gpt-5.1",      # GPT-5.1 使用 Chat API (避免 503 错误)
    "gpt-oss-120b"
]

# ==== API辅助函数 ====
def is_responses_api_supported(model: str) -> bool:
    """
    检查模型是否支持Responses API
    thinking模型强制使用Responses API以提取COT
    但如果模型在Chat API列表中，则优先使用Chat API
    """
    # 优先检查是否在Chat API列表中（在thinking后缀检查之前）
    if model in MODELS_REQUIRE_CHAT_COMPLETIONS:
        return False

    # 如果模型名称包含thinking相关后缀，使用Responses API
    if any(model.lower().endswith(suffix.lower()) for suffix in THINKING_MODEL_SUFFIXES):
        return True

    # 其他模型根据是否在Chat API列表中判断
    return model not in MODELS_REQUIRE_CHAT_COMPLETIONS

# ==== RAG API配置 ====
RAG_URL = "http://localhost:9487/retrieve"
RAG_HEADERS = {"Content-Type": "application/json"}
RAG_RETRY_CONFIG = {
    "timeout": 300,
    "max_retries": 5,
    "retry_delay": 2.0,
    "exponential_backoff": True,
    "backoff_factor": 2.0,
}

# ==== 全局统计 ====
global_stats = {
    "total_files": 0,
    "total_questions": 0,
    "successful_questions": 0,
    "failed_questions": 0,
    "total_processing_time": 0,
    "total_input_tokens": 0,
    "total_output_tokens": 0,
    "total_tokens": 0,
    "start_time": None,
    "end_time": None,
    "rag_used_count": 0,
    "rag_documents_found": 0,
    "rag_api_call_time": 0,
    "rag_api_timeout_count": 0,
    "rag_api_retry_count": 0,
}

LOG_FILE = "llm_api_log.csv"

# ==== 日志 ====
def _log_api_event(
    req_id,
    model,
    status,
    error_type=None,
    message=None,
    attempt=1,
    used_search=False,
    latency=None,
    input_tokens=None,
    output_tokens=None,
    total_tokens=None,
    rag_used=False,
    rag_documents_count=0,
):
    """记录API调用日志"""
    header = [
        "timestamp",
        "req_id",
        "model_used",
        "status",
        "error_type",
        "message",
        "attempt",
        "used_search",
        "latency_s",
        "input_tokens",
        "output_tokens",
        "total_tokens",
        "rag_used",
        "rag_documents_count",
    ]
    row = [
        datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        req_id,
        model,
        status,
        error_type or "",
        message or "",
        attempt,
        used_search,
        f"{latency:.2f}" if latency else "",
        input_tokens or 0,
        output_tokens or 0,
        total_tokens or 0,
        rag_used,
        rag_documents_count,
    ]
    new_file = not os.path.exists(LOG_FILE)
    try:
        with open(LOG_FILE, "a", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            if new_file:
                w.writerow(header)
            w.writerow(row)
    except Exception as e:
        logger.error(f"写入日志文件失败: {e}")

# ==== 工具：解析 <think> 与自动 Think 模式 ====
def split_think_content(raw_answer: str) -> Tuple[str, str]:
    """
    从字符串中提取 <think>...</think> 内容
    返回：(clean_answer, think_content)
    """
    if not raw_answer:
        return raw_answer, ""

    pattern = re.compile(r"<think>(.*?)</think>", re.DOTALL)
    m = pattern.search(raw_answer)
    if not m:
        return raw_answer.strip(), ""

    think_content = m.group(1).strip()
    clean_answer = (raw_answer[:m.start()] + raw_answer[m.end():]).strip()
    return clean_answer, think_content

def extract_cot_from_reasoning(response) -> str:
    """
    从 Responses API 的 output 结构中抽取 COT：
    兼容两种结构：
    A) 你现在的真实结构（推荐的新版）：
        output: [
          { "type": "reasoning", "summary": [...] },
          { "type": "message", ... }
        ]
    B) 旧结构（reasoning 嵌在 message.content 里面）：
        output: [
          {
            "type": "message",
            "content": [
              { "type": "reasoning", "summary": [...] },
              { "type": "output_text", "text": "..." }
            ]
          }
        ]
    """
    # 先把 response 转成普通 dict
    try:
        if hasattr(response, "model_dump"):
            data = response.model_dump()
        else:
            data = json.loads(
                json.dumps(response, default=lambda o: getattr(o, "__dict__", str(o)))
            )
    except Exception as e:
        logger.warning(f"解析 Responses 对象为 dict 失败，跳过 reasoning 解析: {e}")
        return ""

    def _collect_from_summaries(summaries) -> List[str]:
        """内部小工具：从各种 summary 形态里收集文本"""
        chunks: List[str] = []
        if summaries is None:
            return chunks

        # 单个 dict / 单个字符串
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
            # 可能是纯字符串
            if not isinstance(seg, dict):
                txt = str(seg).strip()
                if txt:
                    chunks.append(txt)
                continue

            seg_type = seg.get("type")
            if seg_type not in (None, "summary_text", "text", "reasoning_text"):
                # 避免把奇怪类型也当成 COT
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
            if not isinstance(out, dict):
                continue

            out_type = out.get("type")

            # ====== A. 顶层 reasoning 对象（你现在的真实结构）======
            if out_type == "reasoning":
                # 1) 直接挂在 out["summary"]
                summaries = out.get("summary")

                # 2) 有些实现可能嵌在 out["reasoning"]["summary"]
                if summaries is None and isinstance(out.get("reasoning"), dict):
                    summaries = out["reasoning"].get("summary")

                cot_chunks.extend(_collect_from_summaries(summaries))
                # 继续循环是安全的，避免将来有多个 reasoning 块时丢掉信息
                continue

            # ====== B. 旧结构：reasoning 藏在 message.content 里 ======
            contents = out.get("content") or out.get("contents") or []
            if not isinstance(contents, list):
                continue

            for content in contents:
                if not isinstance(content, dict):
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

    except Exception as e:
        # 这里的异常只影响 COT，不影响主回答
        logger.warning(f"从 reasoning.summary 中抽取 COT 时出错(已忽略): {e}")
        return ""

    return "\n\n".join([c for c in cot_chunks if c.strip()]).strip()

def auto_select_think_mode(
    question: str, main_category: str, sub_category: str
) -> str:
    """
    根据问题“难度”自动选择 reasoning.effort
    返回值：minimal / low / medium / high / none
    """
    q = (question or "").strip()
    length = len(q)

    # 关键词加权：涉及“设计/评估/监管/多因素”的问题更复杂
    complex_keywords = [
        "方案",
        "设计",
        "评估",
        "监管",
        "标准",
        "策略",
        "框架",
        "比较",
        "优劣",
        "原理",
        "机制",
        "模型",
        "联合",
        "多因素",
    ]

    score = 0
    for kw in complex_keywords:
        if kw in q:
            score += 1

    # 根据长度粗分
    if length < 25:
        base = "minimal"
    elif length < 60:
        base = "low"
    elif length < 120:
        base = "medium"
    else:
        base = "high"

    # 如果包含较多复杂关键词，提高一档
    if score >= 3 and base == "low":
        base = "medium"
    if score >= 3 and base == "medium" and length > 80:
        base = "high"

    # 某些主分类默认加权（例如“育种方案设计与评估”）
    if "设计" in sub_category or "评估" in sub_category:
        if base == "minimal":
            base = "low"
        elif base == "low":
            base = "medium"

    logger.info(
        f"[AUTO-THINK] 问题长度={length}, 关键词命中={score}, 分类={main_category}-{sub_category}, 自动选择 effort={base}"
    )
    return base

# ==== RAG相关函数 ====
def get_rag_data(query):
    return {
        "query": query,
        "top_k": 5,
        "search_type": "keyword",
        "data_source": ["pubmed"],
        "pubmed_topk": 10,
    }

def parse_json_response(json_response):
    documents = []
    try:
        if isinstance(json_response, str):
            response_data = json.loads(json_response)
        else:
            response_data = json_response

        if (
            response_data.get("success")
            and "data" in response_data
            and isinstance(response_data["data"], list)
        ):
            for doc in response_data["data"]:
                title = doc.get("title", "Unknown Title")
                authors = doc.get("authors", "")
                if isinstance(authors, list):
                    authors = ", ".join(authors)
                elif not authors:
                    authors = "Unknown Authors"

                abstract = doc.get("abstract", "")
                text = doc.get("text", "")
                content = doc.get("content", "")

                final_abstract = abstract
                if not final_abstract or final_abstract.strip() == "":
                    final_abstract = text
                if not final_abstract or final_abstract.strip() == "":
                    final_abstract = content
                if not final_abstract or final_abstract.strip() == "":
                    final_abstract = "摘要信息不可用"

                # Handle both string and dict formats for journal
                journal_info = doc.get("journal", {})
                if isinstance(journal_info, str):
                    journal_name = journal_info
                else:
                    journal_name = journal_info.get("title", "") or journal_info.get(
                        "abbreviation", ""
                    )

                # Handle both string and dict formats for pub_date
                pub_date = doc.get("pub_date", "")
                if isinstance(pub_date, dict):
                    year = pub_date.get("year", "")
                elif isinstance(pub_date, str) and pub_date:
                    # Extract year from format like "2015-Mar-12"
                    year_match = re.match(r"(\d{4})", pub_date)
                    year = year_match.group(1) if year_match else ""
                else:
                    year = ""

                doi = doc.get("doi", "")
                source = doc.get("source", "")
                source_id = doc.get("source_id", "")
                url = doc.get("url", "")

                # Handle journal dict fields if available
                volume = journal_info.get("volume", "") if isinstance(journal_info, dict) else ""
                issue = journal_info.get("issue", "") if isinstance(journal_info, dict) else ""
                start_page = journal_info.get("startPage", "") if isinstance(journal_info, dict) else ""
                end_page = journal_info.get("endPage", "") if isinstance(journal_info, dict) else ""

                doc_info = {
                    "title": title,
                    "authors": authors,
                    "journal": journal_name,
                    "year": year,
                    "doi": doi,
                    "source": source,
                    "source_id": source_id,
                    "url": url,
                    "volume": volume,
                    "issue": issue,
                    "start_page": start_page,
                    "end_page": end_page,
                    "abstract": final_abstract,
                    "content": final_abstract,
                    "full_data": doc,
                }
                documents.append(doc_info)
    except (json.JSONDecodeError, AttributeError) as e:
        logger.error(f"Error parsing JSON response: {e}")
    return documents

def parse_stream_response(response_text):
    documents = []
    try:
        response_data = json.loads(response_text)
        documents = parse_json_response(response_data)
    except json.JSONDecodeError:
        lines = response_text.strip().split("\n")
        for line in lines:
            line = line.strip()
            if not line:
                continue
            if line.startswith("{") and line.endswith("}"):
                try:
                    response_data = json.loads(line)
                    parsed_docs = parse_json_response(response_data)
                    documents.extend(parsed_docs)
                except json.JSONDecodeError:
                    continue

    context = generate_context_from_documents(documents)
    references = generate_reference_citations(documents)
    return context, references, documents

def generate_context_from_documents(documents, max_documents=5):
    if not documents:
        return "未找到相关文献。"

    context = "相关文献信息：\n\n"
    for i, doc in enumerate(documents[:max_documents], 1):
        context += f"文献 {i}:\n"
        context += f"标题: {doc.get('title', 'Unknown')}\n"
        abstract = doc.get("abstract", "")
        if not abstract or abstract == "摘要信息不可用":
            abstract = doc.get("content", "")
        if len(abstract) > 800:
            abstract = abstract[:800] + "..."
        context += f"摘要: {abstract}\n\n"

    return context

def get_terminal_width():
    try:
        terminal_size = shutil.get_terminal_size()
        return terminal_size.columns
    except (AttributeError, ValueError, OSError):
        return 120

def format_abstract_with_wrap(abstract, indent=4):
    if not abstract or abstract == "摘要信息不可用":
        return "   摘要信息不可用"

    terminal_width = get_terminal_width()
    available_width = terminal_width - indent - 4
    min_width = 60
    max_width = 160

    text_width = max(min_width, min(available_width, max_width))

    wrapped_abstract = textwrap.fill(
        abstract,
        width=text_width,
        initial_indent=" " * indent,
        subsequent_indent=" " * indent,
        break_long_words=False,
        break_on_hyphens=False,
    )
    return wrapped_abstract

def generate_reference_citations(documents, max_references=5):
    if not documents:
        return ""

    references = "参考文献：\n\n"
    for i, doc in enumerate(documents[:max_references], 1):
        authors = doc.get("authors", "")
        year = doc.get("year", "")
        title = doc.get("title", "")
        journal = doc.get("journal", "")
        volume = doc.get("volume", "")
        issue = doc.get("issue", "")
        start_page = doc.get("start_page", "")
        end_page = doc.get("end_page", "")
        doi = doc.get("doi", "")
        url = doc.get("url", "")
        abstract = doc.get("abstract", "")
        if not abstract or abstract.strip() == "":
            abstract = doc.get("content", "")

        author_list = authors.split(", ") if ", " in authors else [authors]
        if len(author_list) > 3:
            formatted_authors = f"{author_list[0]} et al."
        else:
            formatted_authors = authors

        journal_info = journal
        if volume:
            journal_info += f" {volume}"
        if issue:
            journal_info += f"({issue})"
        if start_page:
            if end_page and end_page != start_page:
                journal_info += f":{start_page}-{end_page}"
            else:
                journal_info += f":{start_page}"

        citation = f"[{i}] {formatted_authors} ({year}). {title}. {journal_info}"
        if doi:
            citation += f". https://doi.org/{doi}"
        elif url:
            citation += f". {url}"

        formatted_abstract = format_abstract_with_wrap(abstract)
        citation += f"\n   摘要:\n{formatted_abstract}"

        references += citation + "\n\n"

    return references

def fetch_documents(query, max_retries=None, timeout=None):
    max_retries = max_retries if max_retries is not None else RAG_RETRY_CONFIG["max_retries"]
    timeout = timeout if timeout is not None else RAG_RETRY_CONFIG["timeout"]
    retry_delay = RAG_RETRY_CONFIG["retry_delay"]
    exponential_backoff = RAG_RETRY_CONFIG["exponential_backoff"]
    backoff_factor = RAG_RETRY_CONFIG["backoff_factor"]

    last_exception = None

    for attempt in range(max_retries):
        try:
            if attempt > 0:
                if exponential_backoff:
                    delay = retry_delay * (backoff_factor ** (attempt - 1))
                else:
                    delay = retry_delay
                logger.info(f"  → {delay:.1f}秒后进行第{attempt + 1}次重试...")
                time.sleep(delay)
                logger.info(f"[RAG重试 {attempt + 1}/{max_retries}] 重新发送请求...")

            logger.info(f"发送请求到RAG API (尝试 {attempt + 1}/{max_retries})...")
            logger.info(f"查询: {query}")
            data = get_rag_data(query)

            response = requests.post(
                RAG_URL, headers=RAG_HEADERS, json=data, timeout=timeout
            )

            logger.info(f"响应状态码: {response.status_code}")
            response.raise_for_status()

            logger.info("原始响应接收成功，解析流格式...")
            logger.info(f"响应长度: {len(response.text)} 字符")

            if response.text.strip() == "":
                logger.warning("警告: 从RAG API接收到空响应")
                return None, None, []

            context, references, documents = parse_stream_response(response.text)

            if documents:
                logger.info(f"✅ RAG检索成功: 成功提取 {len(documents)} 篇文献")
                for i, doc in enumerate(documents, 1):
                    abstract = doc.get("abstract", "")
                    logger.info(
                        f"  文献 {i} 摘要长度: {len(abstract)} 字符, 标题: {doc.get('title', 'Unknown')}"
                    )
            else:
                logger.warning("未找到文献")

            return context, references, documents

        except requests.exceptions.Timeout:
            last_exception = f"请求超时 ({timeout}秒)"
            logger.error(f"[RAG重试 {attempt + 1}/{max_retries}] 错误: 请求超时")

        except requests.exceptions.ConnectionError:
            last_exception = "连接错误"
            logger.error(f"[RAG重试 {attempt + 1}/{max_retries}] 错误: 连接错误")

        except requests.exceptions.RequestException as e:
            last_exception = str(e)
            logger.error(f"[RAG重试 {attempt + 1}/{max_retries}] 错误: {e}")

        except Exception as e:
            last_exception = f"{type(e).__name__}: {e}"
            logger.error(f"[RAG重试 {attempt + 1}/{max_retries}] 意外错误: {e}")

    logger.error(f"❌ RAG API调用失败，已重试{max_retries}次")
    logger.error(f"最终错误: {last_exception}")
    return None, None, []

def create_enhanced_prompt(question, context, references, cur_date):
    base_prompt = f"""请基于以下搜索结果为用户问题提供专业回答。今天是 {cur_date}。
{context}

请按照以下准则回答：
1. 首先评估搜索结果的相关性，优先使用最相关的信息
2. 如果搜索结果不相关或不足，请基于专业知识简洁回答
3. 对于列表类问题，关键点限制在10个以内，优先提供最完整、最相关的项目
4. 回答应全面考虑，不局限于搜索结果中的少数观点
5. 确保回答专业、准确且有依据

用户问题：{question}

请生成两个版本的回答：
版本1：在回答中适当引用相关文献，使用指定的引用格式
版本2：内容与版本1保持一致，但不显示任何引用标记

请按以下格式输出：
【带引用版本】
[您的带引用回答]

【无引用版本】
[您的无引用回答]"""
    return base_prompt

def parse_dual_version_response(response_text):
    cited_version = ""
    no_citation_version = ""

    cited_match = re.search(
        r"【带引用版本】\s*(.*?)\s*【无引用版本】", response_text, re.DOTALL
    )
    no_citation_match = re.search(r"【无引用版本】\s*(.*?)$", response_text, re.DOTALL)

    if cited_match and no_citation_match:
        cited_version = cited_match.group(1).strip()
        no_citation_version = no_citation_match.group(1).strip()
    else:
        lines = response_text.split("\n")
        cited_section = False
        no_citation_section = False
        for line in lines:
            if "带引用版本" in line:
                cited_section = True
                no_citation_section = False
                continue
            elif "无引用版本" in line:
                cited_section = False
                no_citation_section = True
                continue
            elif cited_section:
                cited_version += line + "\n"
            elif no_citation_section:
                no_citation_version += line + "\n"

        cited_version = cited_version.strip()
        no_citation_version = no_citation_version.strip()

    if not cited_version and not no_citation_version:
        cited_version = response_text
        no_citation_version = response_text
    elif not cited_version and no_citation_version:
        cited_version = no_citation_version
    elif cited_version and not no_citation_version:
        no_citation_version = re.sub(
            r"\[bdd-rag-citation:\d+\]", "", cited_version
        ).strip()

    return cited_version, no_citation_version

# ==== 哈希与去重 ====
def calculate_question_similarity_hash(question):
    question_clean = re.sub(r"[^\w\s]", "", question.lower())
    words = sorted(set(question_clean.split()))
    normalized_text = " ".join(words)
    return hashlib.md5(normalized_text.encode("utf-8")).hexdigest()

def deduplicate_qa_pairs(qa_pairs, existing_hashes=None):
    if existing_hashes is None:
        existing_hashes = set()

    unique_pairs = []
    duplicate_count = 0

    for qa in qa_pairs:
        question = qa.get("question", "") or qa.get("问题", "")
        if not question:
            continue

        question_hash = calculate_question_similarity_hash(question)
        if question_hash in existing_hashes:
            duplicate_count += 1
            logger.debug(f"发现重复问题: {question[:50]}...")
            continue

        unique_pairs.append(qa)
        existing_hashes.add(question_hash)

    logger.info(
        f"去重完成: 原始 {len(qa_pairs)} 条, 去重后 {len(unique_pairs)} 条, 重复 {duplicate_count} 条"
    )
    return unique_pairs, duplicate_count, existing_hashes

# ==== Chat Completions API 调用 ====
def call_chat_completions_api(
    formatted_prompt: str,
    model: str,
    max_output_tokens: int = 8000,
    think_mode: Optional[str] = None,
):
    """
    使用 Chat Completions API 调用模型
    支持 <think>... 标签提取COT
    """
    req_id = str(uuid.uuid4())[:8]
    start_time = time.time()

    messages = [
        {
            "role": "user",
            "content": formatted_prompt
        }
    ]

    extra_args = {}
    if think_mode and think_mode.lower() not in ["none", "off", "disable", "false"]:
        logger.info(f"[{req_id}] 启用 thinking 模式（Chat API）: {think_mode}")
        # 为thinking模型添加thinking参数
        if any(model.lower().endswith(suffix.lower()) for suffix in THINKING_MODEL_SUFFIXES):
            extra_args["extra_body"] = {"thinking": {"type": "enabled"}}
            logger.info(f"[{req_id}] 为thinking模型添加thinking参数")
    else:
        logger.info(f"[{req_id}] thinking 模式关闭 ({think_mode})")

    logger.info(f"[{req_id}] 开始 Chat Completions API 调用 - 模型: {model}")

    try:
        response = client.chat.completions.create(
            model=model,
            messages=messages,
            max_tokens=max_output_tokens,
            temperature=0.7,
            **extra_args
        )
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
                if glm_think_content:
                    logger.info(f"[{req_id}] GLM模型检测到reasoning_content，COT长度: {len(glm_think_content)} 字符")
            except AttributeError:
                # 如果响应中没有 reasoning_content 字段，忽略
                pass

        # 合并 thinking 内容（GLM 的 reasoning_content + 标准 thinking 标记）
        if glm_think_content and think_content:
            think_content = glm_think_content + "\n\n" + think_content
        elif glm_think_content:
            think_content = glm_think_content

        input_tokens = response.usage.prompt_tokens if response.usage else 0
        output_tokens = response.usage.completion_tokens if response.usage else 0
        total_tokens = response.usage.total_tokens if response.usage else input_tokens + output_tokens

        logger.info(
            f"[{req_id}] Chat Completions API 调用成功 - 输入Tokens: {input_tokens}, 输出Tokens: {output_tokens}, 耗时: {latency:.2f}s"
        )

        if think_content:
            logger.info(f"[{req_id}] thinking 模式已启用，COT长度: {len(think_content)} 字符")
        else:
            logger.info(f"[{req_id}] 未检测到thinking标记，COT长度为0")

        return (
            clean_answer,
            model,
            input_tokens,
            output_tokens,
            total_tokens,
            latency,
            think_content,
        )

    except Exception as e:
        latency = time.time() - start_time
        error_msg = str(e)
        logger.error(f"[{req_id}] Chat Completions API 调用失败: {error_msg}")
        raise Exception(f"OpenAI Chat Completions API 调用失败: {error_msg}")

# ==== Responses API 同步调用（主力函数）====
def call_llm_api_logged_single(
    question_prompt: str,
    formatted_prompt: Optional[str] = None,
    model: str = SUPPORTED_MODELS["default"],
    max_output_tokens: int = 8000,
    rag_used: bool = False,
    rag_documents_count: int = 0,
    think_mode: Optional[str] = None,
    main_category: str = "核心知识问答",
    sub_category: str = "",
):
    """
    使用合适的 API 调用模型
    自动选择 Responses API 或 Chat Completions API
    自动抽取 reasoning.summary 中的 COT；若无，再回退 <think>... 标签
    """
    req_id = str(uuid.uuid4())[:8]
    start_time = time.time()

    # 如果没有提供 formatted_prompt，则使用默认格式化
    if formatted_prompt is None:
        # 简单的默认提示词（用于 Responses API）
        formatted_prompt = (
            f"你是一名农业育种与生物学领域的专业助手。\n\n"
            f"问题信息：\n类别：{main_category} - {sub_category}\n问题：{question_prompt}\n\n请直接回答问题。"
        )

    # 检查是否需要使用 Chat Completions API
    if not is_responses_api_supported(model):
        logger.info(f"[{req_id}] 模型 {model} 需要使用 Chat Completions API")
        try:
            return call_chat_completions_api(
                formatted_prompt=formatted_prompt,
                model=model,
                max_output_tokens=max_output_tokens,
                think_mode=think_mode,
            )
        except Exception as e:
            logger.error(f"[{req_id}] Chat Completions API 调用失败，尝试 Responses API: {e}")
            # 如果 Chat Completions API 也失败，继续尝试 Responses API

    # 使用 Responses API（改为走完整 prompt 模板）
    resp_params: Dict[str, Any] = {
        "model": model,
        "input": formatted_prompt,              # ★ 使用完整 prompt 模板
        "max_output_tokens": max_output_tokens,
    }

    # Thinking 配置（none/off/disable/false → 不启用）
    if think_mode and think_mode.lower() not in ["none", "off", "disable", "false"]:
        effort = think_mode.lower()
        if effort == "auto":
            effort = "low"

        valid_efforts = {"minimal", "low", "medium", "high"}
        if effort not in valid_efforts:
            logger.warning(
                f"[{req_id}] 无效的 think 模式值: {think_mode}，回退为 'low'"
            )
            effort = "low"

        # ★ 使用字符串 "detailed" 作为 summary
        resp_params["reasoning"] = {"effort": effort, "summary": "detailed"}
        # resp_params["text"] = {"verbosity": "medium"}
        logger.info(f"[{req_id}] 启用 thinking 模式: reasoning.effort='{effort}', summary='detailed'")
    else:
        logger.info(f"[{req_id}] thinking 模式关闭 ({think_mode})")

    logger.info(f"[{req_id}] 开始 Responses API 调用 - 模型: {model}")

    try:
        response = client.responses.create(**resp_params)
        latency = time.time() - start_time

        # 完整文本
        raw_answer: str = response.output_text
        if not raw_answer:
            raise RuntimeError("Responses API 响应为空")

        # 先从 reasoning.summary 提取 COT
        cot_from_reasoning = extract_cot_from_reasoning(response)

        # 再从文本里尝试 <think>...
        clean_answer, cot_from_tags = split_think_content(raw_answer)

        # 额外处理：移除【思考过程】格式的内容
        if '【思考过程】' in clean_answer:
            # 查找【思考过程】的位置并移除
            parts = clean_answer.split('【思考过程】')
            if len(parts) > 1:
                # 保留第一部分（问题回答），移除思考过程
                clean_answer = parts[0].strip()
                # 将思考过程也保存到cot_from_tags
                think_text = '【思考过程】'.join(parts[1:]).strip()
                if think_text:
                    cot_from_tags = think_text if not cot_from_tags else cot_from_tags

        # COT 优先使用 reasoning.summary，没有就用 <think> 标签
        think_content = cot_from_reasoning or cot_from_tags
        answer = clean_answer

        usage = response.usage
        input_tokens = getattr(usage, "input_tokens", 0) or 0
        output_tokens = getattr(usage, "output_tokens", 0) or 0
        total_tokens = getattr(usage, "total_tokens", 0) or (
            input_tokens + output_tokens
        )

        _log_api_event(
            req_id=req_id,
            model=model,
            status="success",
            attempt=1,
            used_search=False,
            latency=latency,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            total_tokens=total_tokens,
            rag_used=rag_used,
            rag_documents_count=rag_documents_count,
        )

        logger.info(
            f"[{req_id}] Responses API 调用成功 - 输入Tokens: {input_tokens}, 输出Tokens: {output_tokens}, 耗时: {latency:.2f}s"
        )

        if think_mode and think_mode.lower() not in ["none", "off", "disable", "false"]:
            logger.info(
                f"[{req_id}] thinking 模式已启用，COT长度: {len(think_content) if think_content else 0} 字符"
            )

        return (
            answer,
            model,
            input_tokens,
            output_tokens,
            total_tokens,
            latency,
            think_content,
        )

    except Exception as e:
        latency = time.time() - start_time
        error_msg = str(e)

        _log_api_event(
            req_id=req_id,
            model=model,
            status="error",
            error_type=type(e).__name__,
            message=error_msg,
            attempt=1,
            used_search=False,
            latency=latency,
            input_tokens=0,
            output_tokens=0,
            total_tokens=0,
            rag_used=rag_used,
            rag_documents_count=rag_documents_count,
        )

        logger.error(f"[{req_id}] Responses API 调用失败: {error_msg}")

        # 对于thinking模型，如果Responses API失败，回退到Chat API
        if any(model.lower().endswith(suffix.lower()) for suffix in THINKING_MODEL_SUFFIXES):
            logger.info(f"[{req_id}] thinking模型Responses API失败，回退到Chat API")
            try:
                return call_chat_completions_api(
                    formatted_prompt=formatted_prompt,
                    model=model,
                    max_output_tokens=max_output_tokens,
                    think_mode=think_mode,
                )
            except Exception as chat_e:
                logger.error(f"[{req_id}] Chat API 回退也失败: {chat_e}")

        raise Exception(f"OpenAI Responses API 调用失败: {error_msg}")

# ==== "伪流式"调用：内部仍用 Responses API，一次性输出 ====
def call_llm_api_streaming_single(
    question_prompt: str,
    model: str = SUPPORTED_MODELS["default"],
    max_output_tokens: int = 8000,
    rag_used: bool = False,
    rag_documents_count: int = 0,
    think_mode: Optional[str] = None,
):
    """
    流式显示版本：
    实际仍然调用 Responses API 一次性拿完整回答，然后 print 出来。
    """
    (
        answer,
        model_used,
        input_tokens,
        output_tokens,
        total_tokens,
        latency,
        think_content,
    ) = call_llm_api_logged_single(
        question_prompt=question_prompt,
        formatted_prompt=None,
        model=model,
        max_output_tokens=max_output_tokens,
        rag_used=rag_used,
        rag_documents_count=rag_documents_count,
        think_mode=think_mode,
    )

    print("\n🤖 模型回答（一次性输出，伪流式）:\n")
    print(answer)
    print()
    return (
        answer,
        model_used,
        input_tokens,
        output_tokens,
        total_tokens,
        latency,
        think_content,
    )

# ==== 分类字段处理 ====
def get_category_value(item, field_names, default_value="未知"):
    for field in field_names:
        value = item.get(field)
        if value is not None and value != "":
            if isinstance(value, float) and pd.isna(value):
                continue
            if isinstance(value, str) and value.lower() in ["nan", "null", "none", ""]:
                continue
            return value
    return default_value

# ==== 生成答案（整合 RAG + 自动 Thinking）====
def generate_answer_for_item(
    item,
    answer_prompt_file,
    use_streaming=False,
    use_rag=False,
    think_mode: Optional[str] = None,
    model: str = SUPPORTED_MODELS["default"],
):
    question = item.get("question", "") or item.get("问题", "")
    main_category = get_category_value(
        item, ["主分类", "category", "main_category"], "核心知识问答"
    )
    sub_category = get_category_value(
        item, ["亚类", "sub_category"], "物种特异性知识问答"
    )
    species = get_category_value(item, ["物种", "species"], "大豆")

    if not question:
        logger.warning("问题为空，跳过")
        return None

    from copy import deepcopy
    item_copy = deepcopy(item)

    # ---- 自动 Thinking 模式展开 ----
    if not think_mode:
        think_mode_base = "auto"
    else:
        think_mode_base = think_mode.lower()

    if think_mode_base == "auto":
        auto_effort = auto_select_think_mode(question, main_category, sub_category)
        think_mode_final = auto_effort
    else:
        think_mode_final = think_mode_base

    logger.info(
        f"问题使用 Thinking 模式: base='{think_mode_base}', final effort='{think_mode_final}'"
    )

    # ---- RAG 检索 ----
    rag_context = ""
    rag_references = ""
    rag_documents_count = 0
    rag_used = False

    if use_rag:
        rag_start_time = time.time()
        logger.info(f"使用RAG检索问题: {question[:80]}...")
        logger.info(
            f"RAG配置: 超时{RAG_RETRY_CONFIG['timeout']}秒, 最大重试{RAG_RETRY_CONFIG['max_retries']}次"
        )

        context, references, documents = fetch_documents(question)
        rag_api_time = time.time() - rag_start_time
        global_stats["rag_api_call_time"] += rag_api_time

        if documents:
            rag_context = context
            rag_references = references
            rag_documents_count = len(documents)
            rag_used = True

            global_stats["rag_used_count"] += 1
            global_stats["rag_documents_found"] += rag_documents_count

            logger.info(
                f"✅ RAG检索成功: 找到 {rag_documents_count} 篇文献 (耗时: {rag_api_time:.1f}秒)"
            )
        else:
            logger.warning(f"⚠️ RAG检索失败或未找到文献 (耗时: {rag_api_time:.1f}秒)")

    # ---- 读取 prompt 模板 ----
    try:
        with open(answer_prompt_file, "r", encoding="utf-8") as f:
            prompt_template = f.read()

        if rag_used:
            cur_date = datetime.now().strftime("%Y-%m-%d")
            prompt_with_info = create_enhanced_prompt(
                question, rag_context, rag_references, cur_date
            )
        else:
            prompt_with_info = prompt_template.format(
                main_category=main_category,
                sub_category=sub_category,
                question=question,
            )
    except Exception as e:
        logger.error(f"Prompt读取或格式化失败: {e}")
        return None

    logger.info(f"开始处理问题: {question[:80]}...")
    logger.info(f"分类: {main_category} - {sub_category}, 物种: {species}")
    if rag_used:
        logger.info(f"RAG: 使用 {rag_documents_count} 篇文献")

    try:
        # 选择 API 调用方式
        if use_streaming:
            (
                answer_raw,
                model_used,
                input_tokens,
                output_tokens,
                total_tokens,
                api_latency,
                think_content,
            ) = call_llm_api_streaming_single(
                question_prompt=question,
                model=model,
                max_output_tokens=8000,
                rag_used=rag_used,
                rag_documents_count=rag_documents_count,
                think_mode=think_mode_final,
            )
        else:
            (
                answer_raw,
                model_used,
                input_tokens,
                output_tokens,
                total_tokens,
                api_latency,
                think_content,
            ) = call_llm_api_logged_single(
                question_prompt=question,
                formatted_prompt=prompt_with_info,
                model=model,
                max_output_tokens=8000,
                rag_used=rag_used,
                rag_documents_count=rag_documents_count,
                think_mode=think_mode_final,
                main_category=main_category,
                sub_category=sub_category,
            )

        logger.info(
            f"答案生成成功 - 长度: {len(answer_raw)} 字符, 输入Tokens: {input_tokens}, 输出Tokens: {output_tokens}"
        )

        # 解析带引用 / 不带引用版本
        cited_answer, no_citation_answer = parse_dual_version_response(answer_raw)
        if rag_used and rag_references:
            cited_answer_with_refs = cited_answer + "\n\n" + rag_references
        else:
            cited_answer_with_refs = cited_answer

        global_stats["successful_questions"] += 1
        global_stats["total_input_tokens"] += input_tokens
        global_stats["total_output_tokens"] += output_tokens
        global_stats["total_tokens"] += total_tokens

        # ✅ 输出数据（不保存 cot 字段）
        output_data = {
            "question": question,
            "answer": no_citation_answer,
            "metadata": {
                "主分类": main_category,
                "亚类": sub_category,
                "物种": species,
                "生成时间": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "源数据": item_copy,
                "使用模型": model_used,
                "输入_tokens": input_tokens,
                "输出_tokens": output_tokens,
                "总_tokens": total_tokens,
                "api处理时间_秒": round(api_latency, 2),
                "使用RAG": rag_used,
                "RAG文献数量": rag_documents_count,
                "Thinking模式": think_mode_final or "none",
            },
        }

        if rag_used:
            output_data["answer_with_citation"] = cited_answer_with_refs
            output_data["metadata"]["RAG参考文献"] = rag_references

        return output_data

    except Exception as e:
        logger.error(f"生成答案失败: {e}")
        global_stats["failed_questions"] += 1
        return None

# ==== 保存函数 ====
def save_batch_results(
    results: List[Dict],
    output_dir: str,
    master_jsonl_path: str,
    batch_num: Optional[int] = None,
):
    if not results:
        return

    os.makedirs(output_dir, exist_ok=True)

    try:
        with open(master_jsonl_path, "a", encoding="utf-8") as f:
            for item in results:
                f.write(json.dumps(item, ensure_ascii=False) + "\n")
    except Exception as e:
        logger.error(f"保存到主文件失败: {e}")

    if batch_num is not None:
        batch_file = os.path.join(output_dir, f"batch_{batch_num}.jsonl")
        try:
            with open(batch_file, "w", encoding="utf-8") as f:
                for item in results:
                    f.write(json.dumps(item, ensure_ascii=False) + "\n")
        except Exception as e:
            logger.error(f"保存批次文件失败: {e}")

def save_to_jsonl(data_list, file_path):
    try:
        os.makedirs(os.path.dirname(file_path), exist_ok=True)
        with open(file_path, "a", encoding="utf-8") as f:
            for item in data_list:
                f.write(json.dumps(item, ensure_ascii=False) + "\n")
        logger.info(f"已保存 {len(data_list)} 条数据到: {file_path}")
    except Exception as e:
        logger.error(f"保存文件失败 {file_path}: {e}")

def save_to_markdown(data_list, file_path, processing_stats=None):
    try:
        os.makedirs(os.path.dirname(file_path), exist_ok=True)
        with open(file_path, "w", encoding="utf-8") as f:
            if processing_stats:
                f.write("# 处理统计报告\n\n")
                f.write("## 总体统计\n")
                f.write(f"- **处理时间**: {processing_stats['processing_time']}\n")
                f.write(f"- **处理文件数**: {processing_stats['total_files']}\n")
                f.write(f"- **总问题数**: {processing_stats['total_questions']}\n")
                f.write(
                    f"- **成功问题数**: {processing_stats['successful_questions']}\n"
                )
                f.write(f"- **失败问题数**: {processing_stats['failed_questions']}\n")
                f.write(f"- **成功率**: {processing_stats['success_rate']:.2f}%\n")
                f.write(
                    f"- **总输入Tokens**: {processing_stats['total_input_tokens']:,}\n"
                )
                f.write(
                    f"- **总输出Tokens**: {processing_stats['total_output_tokens']:,}\n"
                )
                f.write(f"- **总Tokens**: {processing_stats['total_tokens']:,}\n")
                f.write(
                    f"- **平均每个问题Tokens**: {processing_stats['avg_tokens_per_question']:,}\n"
                )
                f.write(
                    f"- **平均处理时间/问题**: {processing_stats['avg_time_per_question']:.2f}秒\n"
                )
                if processing_stats.get("rag_used_count", 0) > 0:
                    f.write(
                        f"- **使用RAG的问题数**: {processing_stats['rag_used_count']}\n"
                    )
                    f.write(
                        f"- **RAG找到的总文献数**: {processing_stats['rag_documents_found']}\n"
                    )
                f.write("\n")

            f.write("# 问题与答案列表\n\n")
            for i, item in enumerate(data_list, 1):
                f.write(f"## 问题 {i}\n\n")
                f.write(f"**问题**: {item['question']}\n\n")
                f.write(
                    f"**分类**: {item['metadata']['主分类']} - {item['metadata']['亚类']}\n\n"
                )
                f.write(f"**物种**: {item['metadata']['物种']}\n\n")
                f.write(f"**生成时间**: {item['metadata']['生成时间']}\n\n")
                f.write(f"**使用模型**: {item['metadata']['使用模型']}\n\n")
                f.write(
                    f"**Tokens使用**: 输入 {item['metadata']['输入_tokens']}, 输出 {item['metadata']['输出_tokens']}, 总计 {item['metadata']['总_tokens']}\n\n"
                )
                f.write(
                    f"**API处理时间**: {item['metadata']['api处理时间_秒']}秒\n\n"
                )
                if item["metadata"].get("使用RAG"):
                    f.write(
                        f"**使用RAG**: 是 (找到 {item['metadata']['RAG文献数量']} 篇文献)\n\n"
                    )
                else:
                    f.write(f"**使用RAG**: 否\n\n")

                f.write("### 答案（不带引用）:\n\n")
                f.write(f"{item['answer']}\n\n")

                if item["metadata"].get("使用RAG"):
                    f.write("### 答案（带引用）:\n\n")
                    f.write(f"{item['answer_with_citation']}\n\n")

                f.write("---\n\n")

        logger.info(f"已保存 {len(data_list)} 条数据到Markdown文件: {file_path}")
    except Exception as e:
        logger.error(f"保存Markdown文件失败 {file_path}: {e}")

# ==== 处理单个文件 ====
def process_question_file(
    file_path,
    output_dir,
    master_jsonl_path,
    answer_prompt_file,
    use_streaming=False,
    use_rag=False,
    think_mode: Optional[str] = None,
    model: str = SUPPORTED_MODELS["default"],
):
    logger.info(f"处理文件: {os.path.basename(file_path)}")
    file_start_time = time.time()

    if think_mode:
        logger.info(f"文件使用think模式: {think_mode}")

    try:
        with open(file_path, "r", encoding="utf-8") as f:
            if file_path.endswith(".jsonl"):
                questions_data = [json.loads(line) for line in f]
            else:
                questions_data = json.load(f)
    except Exception as e:
        logger.error(f"读取文件失败 {file_path}: {e}")
        return

    output_data_list = []
    success_count = 0
    fail_count = 0

    for i, item in enumerate(questions_data):
        logger.info(f"处理第 {i+1}/{len(questions_data)} 个问题")
        output_data = generate_answer_for_item(
            item,
            answer_prompt_file,
            use_streaming=use_streaming,
            use_rag=use_rag,
            think_mode=think_mode,
            model=model,
        )
        if output_data:
            output_data_list.append(output_data)
            success_count += 1
        else:
            fail_count += 1

    file_processing_time = time.time() - file_start_time

    global_stats["total_files"] += 1
    global_stats["total_questions"] += len(questions_data)

    if output_data_list:
        output_filename = (
            os.path.basename(file_path).split(".")[0] + "_answers.jsonl"
        )
        output_filepath = os.path.join(output_dir, output_filename)

        save_to_jsonl(output_data_list, output_filepath)
        save_to_jsonl(output_data_list, master_jsonl_path)

        md_filename = os.path.basename(file_path).split(".")[0] + "_answers.md"
        md_filepath = os.path.join(output_dir, md_filename)

        file_stats = {
            "processing_time": f"{file_processing_time:.2f}秒",
            "total_files": 1,
            "total_questions": len(questions_data),
            "successful_questions": success_count,
            "failed_questions": fail_count,
            "success_rate": (success_count / len(questions_data)) * 100
            if questions_data
            else 0,
            "total_input_tokens": sum(
                item["metadata"]["输入_tokens"] for item in output_data_list
            ),
            "total_output_tokens": sum(
                item["metadata"]["输出_tokens"] for item in output_data_list
            ),
            "total_tokens": sum(
                item["metadata"]["总_tokens"] for item in output_data_list
            ),
            "avg_tokens_per_question": sum(
                item["metadata"]["总_tokens"] for item in output_data_list
            )
            / len(output_data_list)
            if output_data_list
            else 0,
            "avg_time_per_question": file_processing_time / len(questions_data)
            if questions_data
            else 0,
            "rag_used_count": sum(
                1 for item in output_data_list if item["metadata"].get("使用RAG")
            ),
            "rag_documents_found": sum(
                item["metadata"].get("RAG文献数量", 0) for item in output_data_list
            ),
        }

        save_to_markdown(output_data_list, md_filepath, file_stats)

    logger.info(
        f"文件处理完成: 成功 {success_count}, 失败 {fail_count}, 耗时: {file_processing_time:.2f}秒"
    )

# ==== 并发处理：问题级 ====
def process_questions_concurrent(
    questions_data: List[Dict],
    output_dir: str,
    answer_prompt_file: str,
    use_streaming: bool = False,
    use_rag: bool = False,
    max_workers: int = 100,
    think_mode: Optional[str] = None,
    model: str = SUPPORTED_MODELS["default"],
) -> List[Dict]:
    think_info = f", think模式: {think_mode}" if think_mode else ""
    logger.info(
        f"开始同步并发处理 {len(questions_data)} 个问题 "
        f"(线程数: {max_workers}, 使用RAG: {use_rag}{think_info})"
    )

    results: List[Dict] = []
    failed_count = 0
    start_time = time.time()
    batch_size = max(10, max_workers * 2)

    with ThreadPoolExecutor(
        max_workers=max_workers, thread_name_prefix="QA-Worker"
    ) as executor:
        for i in range(0, len(questions_data), batch_size):
            batch = questions_data[i : i + batch_size]
            batch_num = i // batch_size + 1
            total_batches = (len(questions_data) + batch_size - 1) // batch_size

            logger.info(
                f"提交批次 {batch_num}/{total_batches}: {len(batch)} 个任务"
            )

            batch_futures = {
                executor.submit(
                    generate_answer_for_item,
                    item,
                    answer_prompt_file,
                    use_streaming,
                    use_rag,
                    think_mode,
                    model,
                ): item
                for item in batch
            }

            for future in as_completed(batch_futures):
                item = batch_futures[future]
                try:
                    result = future.result(timeout=600)
                    if result:
                        results.append(result)
                    else:
                        failed_count += 1
                        logger.warning(
                            f"处理失败: {item.get('question', '')[:50]}..."
                        )
                except Exception as e:
                    failed_count += 1
                    error_msg = str(e)[:100]
                    logger.error(
                        f"处理异常: {item.get('question', '')[:50]}... - {error_msg}"
                    )

            if i + batch_size < len(questions_data):
                time.sleep(0.5)

    elapsed_time = time.time() - start_time
    success_rate = (
        len(results) / len(questions_data) * 100 if questions_data else 0
    )

    logger.info("同步并发处理完成:")
    logger.info(f"  总问题数: {len(questions_data)}")
    logger.info(f"  成功: {len(results)}")
    logger.info(f"  失败: {failed_count}")
    logger.info(f"  成功率: {success_rate:.1f}%")
    logger.info(f"  总耗时: {elapsed_time:.2f}秒")
    if questions_data:
        logger.info(
            f"  平均耗时/问题: {elapsed_time/len(questions_data):.2f}秒"
        )

    if results:
        output_filename = (
            f"concurrent_results_{datetime.now().strftime('%Y%m%d_%H%M%S')}.jsonl"
        )
        output_filepath = os.path.join(output_dir, output_filename)
        save_to_jsonl(results, output_filepath)
        logger.info(f"结果已保存到: {output_filepath}")

    return results

# ==== 并发处理：文件级 ====
def process_files_concurrent(
    file_paths: List[str],
    output_dir: str,
    answer_prompt_file: str,
    use_streaming: bool = False,
    use_rag: bool = False,
    max_workers: int = 100,
    think_mode: Optional[str] = None,
    model: str = SUPPORTED_MODELS["default"],
) -> List[Dict]:
    think_info = f", think模式: {think_mode}" if think_mode else ""
    logger.info(
        f"开始并发处理 {len(file_paths)} 个文件 "
        f"(文件并发数: {max_workers}, 使用RAG: {use_rag}{think_info})"
    )

    results: List[Dict] = []
    start_time = time.time()

    with ThreadPoolExecutor(
        max_workers=max_workers, thread_name_prefix="File-Worker"
    ) as executor:
        batch_size = max(2, max_workers)

        for i in range(0, len(file_paths), batch_size):
            batch = file_paths[i : i + batch_size]
            batch_num = i // batch_size + 1
            total_batches = (len(file_paths) + batch_size - 1) // batch_size

            logger.info(
                f"提交文件批次 {batch_num}/{total_batches}: {len(batch)} 个文件"
            )

            batch_futures = {
                executor.submit(
                    process_question_file,
                    file_path,
                    output_dir,
                    os.path.join(output_dir, "master_concurrent.jsonl"),
                    answer_prompt_file,
                    use_streaming,
                    use_rag,
                    think_mode,
                    model,
                ): file_path
                for file_path in batch
            }

            for future in as_completed(batch_futures):
                file_path = batch_futures[future]
                try:
                    future.result(timeout=900)
                    logger.info(f"文件处理完成: {os.path.basename(file_path)}")
                except Exception as e:
                    logger.error(
                        f"文件处理失败: {os.path.basename(file_path)} - {str(e)[:100]}"
                    )

            if i + batch_size < len(file_paths):
                time.sleep(1.0)

    elapsed_time = time.time() - start_time
    logger.info("所有文件并发处理完成")
    logger.info(f"  总文件数: {len(file_paths)}")
    logger.info(f"  总耗时: {elapsed_time:.2f}秒")
    if file_paths:
        logger.info(
            f"  平均耗时/文件: {elapsed_time/len(file_paths):.2f}秒"
        )

    return results

# ==== 总体报告 ====
def generate_overall_report(output_dir):
    if global_stats["end_time"] and global_stats["start_time"]:
        total_processing_time = (
            global_stats["end_time"] - global_stats["start_time"]
        )
        total_seconds = total_processing_time.total_seconds()
        processing_time_str = f"{total_seconds:.2f}秒"
    else:
        total_seconds = 0
        processing_time_str = "0.00秒"

    processing_stats = {
        "processing_time": processing_time_str,
        "total_files": global_stats["total_files"],
        "total_questions": global_stats["total_questions"],
        "successful_questions": global_stats["successful_questions"],
        "failed_questions": global_stats["failed_questions"],
        "success_rate": (
            global_stats["successful_questions"]
            / global_stats["total_questions"]
            * 100
            if global_stats["total_questions"] > 0
            else 0
        ),
        "total_input_tokens": global_stats["total_input_tokens"],
        "total_output_tokens": global_stats["total_output_tokens"],
        "total_tokens": global_stats["total_tokens"],
        "avg_tokens_per_question": global_stats["total_tokens"]
        / global_stats["successful_questions"]
        if global_stats["successful_questions"] > 0
        else 0,
        "avg_time_per_question": total_seconds
        / global_stats["total_questions"]
        if global_stats["total_questions"] > 0
        else 0,
        "rag_used_count": global_stats["rag_used_count"],
        "rag_documents_found": global_stats["rag_documents_found"],
    }

    report_file = os.path.join(output_dir, "processing_report.md")
    with open(report_file, "w", encoding="utf-8") as f:
        f.write("# 总体处理报告\n\n")
        f.write("## 处理统计\n\n")
        for key, value in processing_stats.items():
            if isinstance(value, float):
                if "rate" in key:
                    f.write(f"- **{key}**: {value:.2f}%\n")
                elif "tokens" in key or "time" in key:
                    if "time" in key and key != "processing_time":
                        f.write(f"- **{key}**: {value:.2f}\n")
                    else:
                        f.write(f"- **{key}**: {value:,.2f}\n")
                else:
                    f.write(f"- **{key}**: {value}\n")
            else:
                f.write(f"- **{key}**: {value}\n")

        f.write(f"\n## 处理时间范围\n")
        f.write(
            f"- **开始时间**: {global_stats['start_time'].strftime('%Y-%m-%d %H:%M:%S') if global_stats['start_time'] else 'N/A'}\n"
        )
        f.write(
            f"- **结束时间**: {global_stats['end_time'].strftime('%Y-%m-%d %H:%M:%S') if global_stats['end_time'] else 'N/A'}\n"
        )
        f.write(f"- **总处理时间**: {processing_time_str}\n")

    logger.info(f"已生成总体报告: {report_file}")
    return processing_stats

# ==== 多模型批量处理函数（顺序版本）====
def process_species_questions_with_multiple_models(
    input_dir=None,
    output_dir=None,
    models_to_test=None
):
    """
    处理物种问题，依次调用多个模型（顺序版本）

    Args:
        input_dir: 输入目录路径（包含JSON问题文件）
        output_dir: 输出目录路径（保存结果）
        models_to_test: 要测试的模型列表，None则使用默认列表
    """
    # 配置要测试的模型列表
    if models_to_test is None:
        models_to_test = [
            "gpt-5.2",
            "gpt-oss-120b",
        ]

    # 输入和输出路径
    if input_dir is None:
        input_dir = os.getenv("EXPERTQ_INPUT_DIR", "examples")
    if output_dir is None:
        output_dir = os.getenv("EXPERTQ_OUTPUT_DIR", "output_multi_model")

    os.makedirs(output_dir, exist_ok=True)
    print(f"输入目录: {input_dir}")
    print(f"输出目录: {output_dir}")

    # 加载并缓存提示词模板
    prompt_file_path = os.getenv("EXPERTQ_PROMPT_FILE", "")
    try:
        with open(prompt_file_path, 'r', encoding='utf-8') as f:
            prompt_template = f.read()
        print(f"✅ 已加载提示词模板: {prompt_file_path}")
    except Exception as e:
        logger.warning(f"无法加载提示词文件: {e}")
        prompt_template = None

    # 获取所有 JSON 文件
    json_files = [f for f in os.listdir(input_dir) if f.endswith('.json')]

    print(f"发现 {len(json_files)} 个输入文件")
    print(f"将依次调用 {len(models_to_test)} 个模型")
    print()

    # 统计信息
    total_questions = 0
    successful_questions = 0
    failed_questions = 0

    # 处理每个文件
    for json_file in json_files:
        species_name = json_file.replace('_sampled_100.json', '')
        print(f"\n{'=' * 80}")
        print(f"处理物种: {species_name}")
        print(f"文件: {json_file}")
        print('=' * 80)

        # 读取问题
        with open(os.path.join(input_dir, json_file), 'r', encoding='utf-8') as f:
            questions = json.load(f)

        # 输出文件路径
        output_file = os.path.join(output_dir, f"{species_name}_multi_model_answers.jsonl")

        # 处理每个问题
        with open(output_file, 'w', encoding='utf-8') as out_f:
            for i, q_item in enumerate(questions, 1):
                question = q_item['question']
                category = q_item.get('category', '')
                sub_category = q_item.get('sub_category', '')

                print(f"\n问题 {i}/{len(questions)}: {question[:50]}...")

                # 格式化提示词
                if prompt_template:
                    formatted_prompt = prompt_template.format(
                        main_category=category if category else "核心知识问答",
                        sub_category=sub_category,
                        question=question
                    )
                else:
                    # 如果无法加载模板，使用默认提示词
                    formatted_prompt = (
                        f"你是一名农业育种与生物学领域的专业助手。\n\n"
                        f"问题信息：\n类别：{category} - {sub_category}\n问题：{question}\n\n请直接回答问题。"
                    )

                # 为每个模型生成答案
                model_answers = {}
                failed_models = []
                successful_models = []

                for model in models_to_test:
                    try:
                        print(f"  🔹 调用模型: {model} ...", end=" ", flush=True)

                        # 调用模型
                        result = call_llm_api_logged_single(
                            question_prompt=question,
                            formatted_prompt=formatted_prompt,
                            model=model,
                            max_output_tokens=4000,
                            think_mode="high",
                            main_category=category if category else "核心知识问答",
                            sub_category=sub_category
                        )

                        answer, used_model, input_tokens, output_tokens, total_tokens, latency, cot = result

                        # 保存答案
                        model_answers[model] = {
                            "answer": answer,
                            "input_tokens": input_tokens,
                            "output_tokens": output_tokens,
                            "total_tokens": total_tokens,
                            "latency": latency,
                            "model": used_model
                        }

                        successful_models.append(model)
                        print(f"✓ ({latency:.2f}s)")

                    except Exception as e:
                        error_msg = str(e)
                        print(f"✗ ({error_msg[:50]})")

                        # 记录失败的模型
                        failed_models.append({
                            "model": model,
                            "error": error_msg
                        })

                        # 跳过失败的模型，不保存到 model_answers 中
                        logger.warning(f"模型 {model} 调用失败，跳过: {error_msg}")

                # 打印本轮处理统计
                if successful_models:
                    print(f"  🔹 ✓ 成功: {len(successful_models)}/{len(models_to_test)} 模型")

                if failed_models:
                    print(f"  🔹 ✗ 失败: {len(failed_models)}/{len(models_to_test)} 模型")
                    for failed in failed_models[:3]:  # 只显示前3个失败的模型
                        print(f"     - {failed['model']}: {failed['error'][:60]}")
                    if len(failed_models) > 3:
                        print(f"     ... 还有 {len(failed_models) - 3} 个模型失败")

                # 构建合并的答案文本 - 仅包含成功的模型
                combined_answer = ""

                # 遍历成功的模型，按成功顺序分配标签
                for i, (model, result) in enumerate(model_answers.items()):
                    # 动态生成模型标签：🔹🔹🔹🔹 + 模型名（去除前缀）
                    model_display_name = model.replace("gpt-", "").replace("-", "_")
                    label = f"🔹🔹🔹🔹 {model_display_name}"
                    combined_answer += f"{label}：\n"
                    combined_answer += result["answer"] + "\n\n"
                    combined_answer += "---\n\n"

                # 添加处理信息
                if failed_models:
                    combined_answer += f"\n【处理信息】\n"
                    combined_answer += f"本轮处理共调用 {len(models_to_test)} 个模型，"
                    combined_answer += f"成功 {len(successful_models)} 个，"
                    combined_answer += f"失败 {len(failed_models)} 个\n"
                    combined_answer += f"失败的模型: {', '.join([m['model'] for m in failed_models])}\n"

                # 构建输出记录 - 合并后的单答案格式
                output_record = {
                    "question": question,
                    "category": category,
                    "sub_category": sub_category,
                    "species": species_name,
                    "answer": combined_answer.strip(),
                    "timestamp": datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                }

                # 写入文件
                out_f.write(json.dumps(output_record, ensure_ascii=False) + '\n')

                # 更新统计
                total_questions += 1
                # 只有当所有模型都失败时才记为失败问题
                if len(successful_models) == 0:
                    failed_questions += 1
                    print(f"  ⚠️ 警告: 所有模型都失败，问题标记为失败")
                else:
                    successful_questions += 1

        print(f"\n✓ 物种 {species_name} 处理完成")
        print(f"  输出文件: {output_file}")

    # 生成总体报告
    print(f"\n{'=' * 80}")
    print("总体处理报告")
    print('=' * 80)
    print(f"总问题数: {total_questions}")
    print(f"成功问题数: {successful_questions}")
    print(f"失败问题数: {failed_questions}")
    print(f"成功率: {(successful_questions/total_questions*100):.2f}%" if total_questions > 0 else "N/A")
    print(f"\n所有输出文件已保存到: {output_dir}")
    print('=' * 80)

# ==== 多模型批量处理函数（并发版本）====
def process_species_questions_with_multiple_models_concurrent(
    input_dir: str,
    output_dir: str,
    max_workers: int = 4,
    models_to_test: Optional[List[str]] = None
):
    """
    处理物种问题，并发调用多个模型（文件级并发）

    Args:
        input_dir: 输入目录路径
        output_dir: 输出目录路径
        max_workers: 最大并发文件数
        models_to_test: 要测试的模型列表，None则使用默认列表
    """
    # 配置要测试的模型列表
    if models_to_test is None:
        models_to_test = [
            "gpt-5.2",
            "gpt-oss-120b",
        ]

    os.makedirs(output_dir, exist_ok=True)

    # 加载并缓存提示词模板
    prompt_file_path = './simple_text_prompt_v8.txt'
    try:
        with open(prompt_file_path, 'r', encoding='utf-8') as f:
            prompt_template = f.read()
        print(f"✅ 已加载提示词模板: {prompt_file_path}")
    except Exception as e:
        logger.warning(f"无法加载提示词文件: {e}")
        prompt_template = None

    # 获取所有 JSON 文件
    json_files = sorted([f for f in os.listdir(input_dir) if f.endswith('.json')])

    print(f"\n{'=' * 80}")
    print("多模型批量处理模式（文件级并发）")
    print('=' * 80)
    print(f"发现 {len(json_files)} 个输入文件")
    print(f"将使用 {max_workers} 个并发线程处理")
    print(f"每个文件将依次调用 {len(models_to_test)} 个模型")
    print()

    # 统计信息
    stats = {
        "total_files": len(json_files),
        "processed_files": 0,
        "successful_files": 0,
        "failed_files": 0,
        "total_questions": 0,
        "successful_questions": 0,
        "failed_questions": 0,
    }

    # 定义单个文件的处理函数
    def process_single_file(json_file):
        """处理单个物种文件"""
        file_stats = {
            "total_questions": 0,
            "successful_questions": 0,
            "failed_questions": 0,
        }

        species_name = json_file.replace('_sampled_100.json', '')
        logger.info(f"[并发] 开始处理文件: {json_file}")

        try:
            # 读取问题
            with open(os.path.join(input_dir, json_file), 'r', encoding='utf-8') as f:
                questions = json.load(f)

            # 输出文件路径
            output_file = os.path.join(output_dir, f"{species_name}_multi_model_answers.jsonl")

            # 处理每个问题
            with open(output_file, 'w', encoding='utf-8') as out_f:
                for i, q_item in enumerate(questions, 1):
                    question = q_item['question']
                    category = q_item.get('category', '')
                    sub_category = q_item.get('sub_category', '')

                    # 格式化提示词
                    if prompt_template:
                        formatted_prompt = prompt_template.format(
                            main_category=category if category else "核心知识问答",
                            sub_category=sub_category,
                            question=question
                        )
                    else:
                        # 如果无法加载模板，使用默认提示词
                        formatted_prompt = (
                            f"你是一名农业育种与生物学领域的专业助手。\n\n"
                            f"问题信息：\n类别：{category} - {sub_category}\n问题：{question}\n\n请直接回答问题。"
                        )

                    # 为每个模型生成答案
                    model_answers = {}
                    failed_models = []
                    successful_models = []

                    for model in models_to_test:
                        try:
                            # 调用模型
                            result = call_llm_api_logged_single(
                                question_prompt=question,
                                formatted_prompt=formatted_prompt,
                                model=model,
                                max_output_tokens=4000,
                                think_mode="high",
                                main_category=category if category else "核心知识问答",
                                sub_category=sub_category
                            )

                            answer, used_model, input_tokens, output_tokens, total_tokens, latency, cot = result

                            # 保存答案
                            model_answers[model] = {
                                "answer": answer,
                                "input_tokens": input_tokens,
                                "output_tokens": output_tokens,
                                "total_tokens": total_tokens,
                                "latency": latency,
                                "model": used_model
                            }

                            successful_models.append(model)

                        except Exception as e:
                            error_msg = str(e)
                            logger.warning(f"模型 {model} 调用失败，跳过: {error_msg}")

                            # 记录失败的模型
                            failed_models.append({
                                "model": model,
                                "error": error_msg
                            })

                    # 构建合并的答案文本 - 仅包含成功的模型
                    combined_answer = ""

                    # 遍历成功的模型，按成功顺序分配标签
                    for i, (model, result) in enumerate(model_answers.items()):
                        # 动态生成模型标签：🔹🔹🔹🔹 + 模型名（去除前缀）
                        model_display_name = model.replace("gpt-", "").replace("-", "_")
                        label = f"🔹🔹🔹🔹 {model_display_name}"
                        combined_answer += f"{label}：\n"
                        combined_answer += result["answer"] + "\n\n"
                        combined_answer += "---\n\n"

                    # 添加处理信息
                    if failed_models:
                        combined_answer += f"\n【处理信息】\n"
                        combined_answer += f"本轮处理共调用 {len(models_to_test)} 个模型，"
                        combined_answer += f"成功 {len(successful_models)} 个，"
                        combined_answer += f"失败 {len(failed_models)} 个\n"
                        combined_answer += f"失败的模型: {', '.join([m['model'] for m in failed_models])}\n"

                    # 构建输出记录 - 合并后的单答案格式
                    output_record = {
                        "question": question,
                        "category": category,
                        "sub_category": sub_category,
                        "species": species_name,
                        "answer": combined_answer.strip(),
                        "timestamp": datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                    }

                    # 写入文件
                    out_f.write(json.dumps(output_record, ensure_ascii=False) + '\n')

                    # 更新统计
                    file_stats["total_questions"] += 1
                    # 只有当所有模型都失败时才记为失败问题
                    if len(successful_models) == 0:
                        file_stats["failed_questions"] += 1
                        logger.warning(f"[并发] 物种 {species_name} 问题 {i}: 所有模型都失败")
                    else:
                        file_stats["successful_questions"] += 1

            logger.info(f"[并发] ✅ 物种 {species_name} 处理完成: {file_stats['successful_questions']}/{file_stats['total_questions']} 成功")
            return True, file_stats, json_file

        except Exception as e:
            logger.error(f"[并发] ❌ 物种 {species_name} 处理失败: {str(e)[:100]}")
            return False, file_stats, json_file

    # 使用线程池并发处理文件
    start_time = time.time()
    results = []

    with ThreadPoolExecutor(max_workers=max_workers, thread_name_prefix="Species-Worker") as executor:
        # 提交所有任务
        future_to_file = {
            executor.submit(process_single_file, json_file): json_file
            for json_file in json_files
        }

        # 收集结果
        for future in as_completed(future_to_file):
            json_file = future_to_file[future]
            try:
                success, file_stats, _ = future.result(timeout=1800)  # 30分钟超时
                results.append((success, file_stats))

                # 更新全局统计
                stats["processed_files"] += 1
                if success:
                    stats["successful_files"] += 1
                else:
                    stats["failed_files"] += 1

                stats["total_questions"] += file_stats["total_questions"]
                stats["successful_questions"] += file_stats["successful_questions"]
                stats["failed_questions"] += file_stats["failed_questions"]

                # 打印进度
                elapsed = time.time() - start_time
                avg_time_per_file = elapsed / stats["processed_files"]
                eta = avg_time_per_file * (stats["total_files"] - stats["processed_files"])

                print(f"🔹 [并发进度] {stats['processed_files']}/{stats['total_files']} 文件完成, "
                      f"成功: {stats['successful_files']}, 失败: {stats['failed_files']}, "
                      f"预计剩余时间: {eta/60:.1f}分钟")

            except Exception as e:
                logger.error(f"[并发] 获取结果失败: {str(e)[:100]}")
                stats["processed_files"] += 1
                stats["failed_files"] += 1

    # 生成总体报告
    elapsed_time = time.time() - start_time
    success_rate = (stats["successful_files"] / stats["total_files"] * 100) if stats["total_files"] > 0 else 0
    question_success_rate = (stats["successful_questions"] / stats["total_questions"] * 100) if stats["total_questions"] > 0 else 0

    print(f"\n{'=' * 80}")
    print("总体处理报告（文件级并发）")
    print('=' * 80)
    print(f"总文件数: {stats['total_files']}")
    print(f"成功文件数: {stats['successful_files']}")
    print(f"失败文件数: {stats['failed_files']}")
    print(f"文件成功率: {success_rate:.2f}%")
    print()
    print(f"总问题数: {stats['total_questions']}")
    print(f"成功问题数: {stats['successful_questions']}")
    print(f"失败问题数: {stats['failed_questions']}")
    print(f"问题成功率: {question_success_rate:.2f}%")
    print()
    print(f"总耗时: {elapsed_time/60:.2f} 分钟")
    print(f"平均每文件耗时: {elapsed_time/stats['total_files']:.2f} 秒")
    print(f"\n所有输出文件已保存到: {output_dir}")
    print('=' * 80)

    return stats

# ==== 单模型处理模式 ====
def _run_single_model_mode():
    print("\n注意：单模型处理模式未完整实现，请使用多模型批量处理模式")
    print("或使用原来的运行方式（通过参数或其他方式）")
    return

# ==== 获取输入输出目录 ====
def get_input_output_dirs(args, mode_num):
    """
    获取输入输出目录

    Args:
        args: 命令行参数
        mode_num: 运行模式编号（2或3）

    Returns:
        tuple: (input_dir, output_dir)
    """
    # 确定输入输出目录
    if args.input:
        input_dir = args.input
        print(f"\n使用命令行参数指定输入目录: {input_dir}")
    else:
        print("\n" + "-" * 80)
        input_dir = input("输入目录 (回车使用默认): ").strip()
        if not input_dir:
            input_dir = "../../03_data/reanswer_v5d/"
            print(f"使用默认输入目录: {input_dir}")

    if args.output:
        output_dir = args.output
        print(f"使用命令行参数指定输出目录: {output_dir}")
    else:
        output_dir = input("输出目录 (回车使用默认): ").strip()
        if not output_dir:
            output_dir = "./output_multi_model/"
            print(f"使用默认输出目录: {output_dir}")

    # 检查输入目录
    if not os.path.exists(input_dir):
        print(f"❌ 错误: 输入目录不存在: {input_dir}")
        return None, None

    # 创建输出目录
    os.makedirs(output_dir, exist_ok=True)

    print("-" * 80)
    print(f"输入目录: {input_dir}")
    print(f"输出目录: {output_dir}")

    return input_dir, output_dir

# ==== 主函数 ====
def main():
    # ==== 解析命令行参数 ====
    parser = argparse.ArgumentParser(
        description='生物RAG问答系统 - 多模型批量处理',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
使用示例:
  # 使用默认参数（交互式选择模式）
  python script.py

  # 直接指定模式和目录
  python script.py --mode 3 --input /path/to/input --output /path/to/output --workers 4

  # 仅指定输入输出目录，使用默认并发数
  python script.py --input /path/to/input --output /path/to/output

  # 指定要使用的模型列表
  python script.py --mode 3 --input /path/to/input --output /path/to/output --models gpt-5.2 gpt-oss-120b

  # 使用自动模式，指定模型和并发数
  python script.py --auto --input /path/to/input --output /path/to/output --models gpt-5.2 gpt-oss-120b --workers 8
        """
    )

    parser.add_argument(
        '--input',
        type=str,
        help='输入目录路径（包含JSON问题文件）',
        default=None
    )

    parser.add_argument(
        '--output',
        type=str,
        help='输出目录路径（保存结果）',
        default=None
    )

    parser.add_argument(
        '--mode',
        type=int,
        choices=[1, 2, 3],
        help='运行模式: 1=单模型, 2=多模型顺序, 3=多模型并发（推荐）',
        default=None
    )

    parser.add_argument(
        '--workers',
        type=int,
        help='并发处理的最大线程数（仅模式3有效）',
        default=7
    )

    parser.add_argument(
        '--auto',
        action='store_true',
        help='自动模式：使用默认配置，无需交互',
        default=False
    )

    parser.add_argument(
        '--models',
        type=str,
        nargs='+',
        help='要使用的模型列表，例如: --models gpt-5.2 gpt-oss-120b',
        default=None
    )

    args = parser.parse_args()

    try:
        global_stats["start_time"] = datetime.now()

        # ==== 模式选择 ====
        print("\n" + "=" * 80)
        print(" 欢迎使用生物RAG问答系统")
        print("=" * 80)

        # 确定运行模式
        if args.mode is not None:
            mode_choice = str(args.mode)
            print(f"\n已通过命令行参数指定模式: {args.mode}")
        elif args.auto:
            mode_choice = "3"  # 默认使用并发模式
            print("\n自动模式: 使用默认配置（多模型并发模式）")
        else:
            print("\n请选择运行模式:")
            print("1. 单模型处理模式")
            print("2. 多模型批量处理模式（顺序）")
            print("3. 多模型批量处理模式（文件级并发，推荐）")
            mode_choice = input("\n请选择 (1-3, 默认3): ").strip() or "3"

        if mode_choice == "1":
            # 单模型处理模式
            _run_single_model_mode()
        elif mode_choice == "2":
            # 多模型批量处理模式（顺序）
            print("\n" + "=" * 80)
            print(" 多模型批量处理模式（顺序）")
            print("=" * 80)

            # 确定要使用的模型列表
            models_to_test = args.models if args.models else [
                "gpt-5.2",
                "gpt-oss-120b",
            ]

            print(f"\n🔹 将依次调用以下{len(models_to_test)}个模型:")
            for i, model in enumerate(models_to_test):
                print(f"  {i}. {model}")

            # 获取输入输出目录
            input_dir, output_dir = get_input_output_dirs(args, 2)
            if input_dir is None:
                return  # 目录检查失败，已输出错误信息

            if not args.auto:
                confirm = input("\n是否继续? (y/N, 默认y): ").strip()
                if confirm.lower() == 'n':
                    print("已取消操作")
                    return
            else:
                print("\n自动模式：跳过确认，直接开始处理")

            # 执行顺序处理
            process_species_questions_with_multiple_models(
                input_dir=input_dir,
                output_dir=output_dir,
                models_to_test=models_to_test
            )
        else:
            # 多模型批量处理模式（文件级并发）
            print("\n" + "=" * 80)
            print(" 多模型批量处理模式（文件级并发）")
            print("=" * 80)

            # 确定要使用的模型列表
            models_to_test = args.models if args.models else [
                "gpt-5.2",
                "gpt-oss-120b",
            ]

            print(f"\n🔹 将依次调用以下{len(models_to_test)}个模型:")
            for i, model in enumerate(models_to_test):
                print(f"  {i}. {model}")

            # 获取输入输出目录
            input_dir, output_dir = get_input_output_dirs(args, 3)
            if input_dir is None:
                return  # 目录检查失败，已输出错误信息

            # 获取并发数
            if args.workers:
                max_workers = args.workers
                print(f"使用命令行参数指定并发数: {max_workers}")
            else:
                max_workers_input = input("最大并发数 (回车默认4): ").strip()
                if not max_workers_input:
                    max_workers = 4
                else:
                    max_workers = int(max_workers_input)

            print(f"最大并发数: {max_workers}")

            if not args.auto:
                confirm = input("\n是否继续? (y/N, 默认y): ").strip()
                if confirm.lower() == 'n':
                    print("已取消操作")
                    return
            else:
                print("\n自动模式：跳过确认，直接开始处理")

            # 执行并发处理
            process_species_questions_with_multiple_models_concurrent(
                input_dir=input_dir,
                output_dir=output_dir,
                max_workers=max_workers,
                models_to_test=models_to_test
            )

    except KeyboardInterrupt:
        logger.info("用户中断操作")
        print("\n用户中断操作")
    except Exception as e:
        logger.error(f"主函数执行出错: {e}")
        print(f"\n错误: {e}")
        import traceback
        traceback.print_exc()
    finally:
        global_stats["end_time"] = datetime.now()
        logger.info("程序执行完毕")

# ==== 使用示例 ====
"""
多模型批量处理系统使用示例

1. 命令行方式 - 指定模型列表：

   # 使用默认模型（gpt-5.2 和 gpt-oss-120b）
   python bdd_pubmed_chat_v2_1_final_multiple_model.py --mode 3 \
       --input /path/to/input --output /path/to/output

   # 自定义模型列表
   python bdd_pubmed_chat_v2_1_final_multiple_model.py --mode 3 \
       --input /path/to/input --output /path/to/output \
       --models gpt-5.2 gpt-oss-120b deepseek-v3.2

   # 自动模式（无需交互）
   python bdd_pubmed_chat_v2_1_final_multiple_model.py --auto \
       --input /path/to/input --output /path/to/output \
       --models gpt-5.2 gpt-oss-120b --workers 8

2. 编程方式 - 调用函数：

   from bdd_pubmed_chat_v2_1_final_multiple_model import (
       process_species_questions_with_multiple_models,
       process_species_questions_with_multiple_models_concurrent
   )

   # 方式1：顺序处理（自定义模型）
   models = ["gpt-5.2", "gpt-oss-120b", "deepseek-v3.2"]
   process_species_questions_with_multiple_models(
       input_dir="/path/to/input",
       output_dir="/path/to/output",
       models_to_test=models
   )

   # 方式2：并发处理（推荐）
   process_species_questions_with_multiple_models_concurrent(
       input_dir="/path/to/input",
       output_dir="/path/to/output",
       max_workers=8,
       models_to_test=models
   )

3. 可用模型列表：
   - gpt-5.1, gpt-5.2, gpt-4o, gpt-4o-mini
   - gpt-oss-120b
   - deepseek-v3.2, deepseek-v3.2-thinking
   - qwen-max, qwen-plus, qwen-turbo
   - gemini-2-5-pro, gemini-2-5-flash
   - claude-sonnet-4-5-20250929, claude-sonnet-4-20250514, claude-opus-4-20250514
   - grok-4-1-fast-reasoning
   - glm-4.6

   注意：模型名称必须完全匹配，不区分大小写。
"""

if __name__ == "__main__":
    main()
