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
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
if not OPENAI_API_KEY:
    raise ValueError("OPENAI_API_KEY 未在环境变量中设置")

# 注意：base_url 指到 /v1 根路径，Responses API 会自动走 /responses
client = OpenAI(
    api_key=OPENAI_API_KEY,
    base_url=os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1"),
)

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
        "is_rewrite": True,
        "data_source": ["pubmed"],
        "user_id": "1925460557258756097",
        "pubmed_topk": 10,
        "is_rerank": True,
        "language": "en",
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

                journal_info = doc.get("journal", {})
                journal_name = journal_info.get("title", "") or journal_info.get(
                    "abbreviation", ""
                )
                year = doc.get("pub_date", {}).get("year", "")
                doi = doc.get("doi", "")
                source = doc.get("source", "")
                source_id = doc.get("source_id", "")
                volume = journal_info.get("volume", "")
                issue = journal_info.get("issue", "")
                start_page = journal_info.get("startPage", "")
                end_page = journal_info.get("endPage", "")

                doc_info = {
                    "title": title,
                    "authors": authors,
                    "journal": journal_name,
                    "year": year,
                    "doi": doi,
                    "source": source,
                    "source_id": source_id,
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

请按以下格式输出：
【推理链】
请详细展示从问题到答案的推理过程，分步骤说明：
1. 首先分析问题的核心要点
2. 基于搜索结果和相关知识进行推理
3. 得出结论的过程
每一步推理都要有依据和逻辑。

【带引用版本】
[您的带引用回答]

【无引用版本】
[您的无引用回答]

请严格按照格式输出，推理链要详细、逻辑清晰。"""

    return base_prompt


def create_prompt_without_rag(question, main_category, sub_category, cur_date):
    """
    为非 RAG 模式创建带推理链要求的 prompt
    """
    base_prompt = f"""你是一位顶尖的农业育种技术顾问，为科研人员和一线从业者提供可靠、可验证、零幻觉的专业知识，覆盖水稻、玉米、小麦、油菜、大豆及主要畜禽领域。你的行为准则是：审慎、精确、负责。

必须遵守以下规则：

1. 问题有效性检查
- 在回答前，隐式检测问题是否包含科学错误、概念冲突或前提缺失。
- 若存在明显问题，则在回答开头用简短自然的一两句话指出问题，例如：
  "这个问法中存在概念混淆，需要先澄清……"
  或：
  "这里的分类方式在作物遗传学中并不常用，需要先说明……"
- 若问题科学上完全成立，则不添加任何前置说明，直接回答。

2. 真实性
- 回答基于教科书、行业标准、权威综述或长期验证的生产实践。
- 若问题确实依赖物种特异证据，并且该物种有公开研究，则在回答中自然使用该物种的已知结论，不加额外前置说明。
- 若目标物种证据缺乏，而其他作物证据充分，则在涉及该点的句子中自然说明：
  "该结论在[其他作物]证据充分，在[目标物种]属于合理推断，需试验验证。"
- 若问题本身不需要物种特异性（如统计方法、生物学通则、通用分子工具、实验设计原则），则不给出物种相关内容。
- 禁止虚构文献、编造数据或补全不存在的机制。

3. 边界
- 若问题涉及实时数据、未公开研究或需现场验证，必须声明："无法获取实时/专有数据，以下基于通用原理。"
- 不提供需要专业资质的具体操作，只说明科学原理、决策依据和潜在风险。

4. 自适应回答策略
- 简单问题：直接给出简洁、准确的结论。
- 中等问题：使用要点式结构，逻辑清晰。
- 复杂问题：从多维度给出系统化分析，不展开无意义背景。

5. 质量要求
- 结构化、逻辑严密、语言精炼。
- 不使用套话，不重复问题。
- 每句话都必须提供实质信息或决策价值。

问题信息：
类别：{main_category} - {sub_category}
问题：{question}

请按以下格式输出：
【推理链】
请详细展示从问题到答案的推理过程，分步骤说明：
1. 首先分析问题的核心要点
2. 基于已有知识和逻辑进行推理
3. 得出结论的过程
每一步推理都要有依据和逻辑。

【带引用版本】
[您的带引用回答]

【无引用版本】
[您的无引用回答]

请严格按照格式输出，推理链要详细、逻辑清晰。"""

    return base_prompt


def parse_dual_version_response(response_text):
    """
    解析响应文本，提取推理链、带引用版本和无引用版本
    返回: (推理链, 带引用版本, 无引用版本)
    """
    reasoning_chain = ""
    cited_version = ""
    no_citation_version = ""

    # 首先尝试标准格式提取推理链
    reasoning_match = re.search(
        r"【推理链】\s*(.*?)\s*【带引用版本】", response_text, re.DOTALL
    )
    if reasoning_match:
        reasoning_chain = reasoning_match.group(1).strip()
        logger.info(f"✅ 从标准格式提取到推理链: {len(reasoning_chain)} 字符")
    else:
        # 尝试多种宽松匹配模式
        logger.info("尝试宽松模式匹配推理链...")

        # 模式1: 查找所有以数字开头、包含推理关键词的段落
        lines = response_text.split('\n')
        reasoning_lines = []
        in_reasoning_section = False

        for line in lines:
            line_stripped = line.strip()

            # 检查是否是【推理链】标题的变体
            if "推理链" in line or "推理过程" in line or "思考过程" in line:
                in_reasoning_section = True
                continue

            # 检查是否进入下一节
            if "【带引用版本】" in line or "【无引用版本】" in line:
                in_reasoning_section = False
                continue

            # 收集推理内容
            if in_reasoning_section:
                if line_stripped:
                    reasoning_lines.append(line_stripped)

            # 单独检查数字开头的要点行
            elif re.match(r'^\d+\.', line_stripped) and any(
                keyword in line_stripped for keyword in ["要点", "分析", "推理", "结论", "推导", "核心"]
            ):
                reasoning_lines.append(line_stripped)

            # 检查"首先/其次/然后/最后"结构
            elif re.match(r'^(?:首先|其次|接着|然后|最后)', line_stripped) and any(
                keyword in line_stripped for keyword in ["要点", "分析", "推理", "结论", "推导"]
            ):
                reasoning_lines.append(line_stripped)

        # 如果找到推理内容，合并它们
        if reasoning_lines:
            reasoning_chain = "\n".join(reasoning_lines)
            logger.info(f"✅ 从宽松模式提取到推理链: {len(reasoning_chain)} 字符, 行数: {len(reasoning_lines)}")
        else:
            # 模式2: 检查是否整个开头的部分都是推理内容
            citation_pos = response_text.find("【带引用版本】")
            if citation_pos == -1:
                citation_pos = response_text.find("【无引用版本】")

            if citation_pos > 0:
                # 获取【带引用版本】之前的内容
                before_citation = response_text[:citation_pos].strip()

                # 如果包含推理关键词，且长度合理，认为是推理链
                if len(before_citation) > 30 and any(
                    keyword in before_citation for keyword in ["要点", "分析", "推理", "结论", "推导", "步骤"]
                ):
                    reasoning_chain = before_citation
                    logger.info(f"✅ 从前置内容提取到推理链: {len(reasoning_chain)} 字符")
                else:
                    logger.warning("未找到推理链内容（前置内容不含关键词或过短）")
            else:
                logger.warning("未找到【带引用版本】标记，无法定位推理链位置")

    # 提取带引用版本和无引用版本
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

    return reasoning_chain, cited_version, no_citation_version


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


# ==== Responses API 同步调用（主力函数）====
def call_llm_api_logged_single(
    question_prompt: str,
    model: str = "gpt-5.1",
    max_output_tokens: int = 8000,
    rag_used: bool = False,
    rag_documents_count: int = 0,
    think_mode: Optional[str] = None,
):
    """
    使用 Responses API 调用 GPT-5.1
    自动抽取 reasoning.summary 中的 COT；若无，再回退 <think>... 标签
    """
    req_id = str(uuid.uuid4())[:8]
    start_time = time.time()

    resp_params: Dict[str, Any] = {
        "model": model,
        "input": question_prompt,
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
        resp_params["reasoning"] = {"effort": effort, "summary": "detailed"}
        resp_params["text"] = {"verbosity": "medium"}
        logger.info(f"[{req_id}] 启用 thinking 模式: reasoning.effort='{effort}'")
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

        # 再从文本里尝试 <think>...</think>，并顺便去掉
        clean_answer, cot_from_tags = split_think_content(raw_answer)

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
                f"[{req_id}] thinking 模式已启用，COT长度: {len(think_content)} 字符"
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
        raise Exception(f"OpenAI Responses API 调用失败: {error_msg}")


# ==== “伪流式”调用：内部仍用 Responses API，一次性输出 ====
def call_llm_api_streaming_single(
    question_prompt: str,
    model: str = "gpt-5.1",
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

    # ---- 构造 Prompt ----
    try:
        # 统一使用 enhanced_prompt，无论是否使用 RAG
        cur_date = datetime.now().strftime("%Y-%m-%d")

        if rag_used and rag_context:
            # 有 RAG 结果时，使用增强的 prompt
            prompt_with_info = create_enhanced_prompt(
                question, rag_context, rag_references, cur_date
            )
        else:
            # 无 RAG 结果时，也使用带推理链要求的 prompt
            prompt_with_info = create_prompt_without_rag(
                question, main_category, sub_category, cur_date
            )
    except Exception as e:
        logger.error(f"Prompt构造失败: {e}")
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
                model,
                input_tokens,
                output_tokens,
                total_tokens,
                api_latency,
                think_content,
            ) = call_llm_api_streaming_single(
                prompt_with_info,
                model="gpt-5.1",
                max_output_tokens=8000,
                rag_used=rag_used,
                rag_documents_count=rag_documents_count,
                think_mode=think_mode_final,
            )
        else:
            (
                answer_raw,
                model,
                input_tokens,
                output_tokens,
                total_tokens,
                api_latency,
                think_content,
            ) = call_llm_api_logged_single(
                prompt_with_info,
                model="gpt-5.1",
                max_output_tokens=8000,
                rag_used=rag_used,
                rag_documents_count=rag_documents_count,
                think_mode=think_mode_final,
            )

        logger.info(
            f"答案生成成功 - 长度: {len(answer_raw)} 字符, 输入Tokens: {input_tokens}, 输出Tokens: {output_tokens}"
        )

        # 解析推理链、带引用 / 不带引用版本
        reasoning_chain, cited_answer, no_citation_answer = parse_dual_version_response(answer_raw)

        if rag_used and rag_references:
            cited_answer_with_refs = cited_answer + "\n\n" + rag_references
        else:
            cited_answer_with_refs = cited_answer

        global_stats["successful_questions"] += 1
        global_stats["total_input_tokens"] += input_tokens
        global_stats["total_output_tokens"] += output_tokens
        global_stats["total_tokens"] += total_tokens

        # ✅ 无论是否有 COT，都固定写入 api_cot 字段
        # ✅ 添加推理链字段
        output_data = {
            "question": question,
            "answer": no_citation_answer,
            "api_cot": think_content or "",
            "qa_cot_from_prompt": reasoning_chain or "",
            "reasoning_steps": [s.strip() for s in reasoning_chain.split('\n') if s.strip()] if reasoning_chain else [],
            "metadata": {
                "主分类": main_category,
                "亚类": sub_category,
                "物种": species,
                "生成时间": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "源数据": item_copy,
                "使用模型": model,
                "输入_tokens": input_tokens,
                "输出_tokens": output_tokens,
                "总_tokens": total_tokens,
                "api处理时间_秒": round(api_latency, 2),
                "使用RAG": rag_used,
                "RAG文献数量": rag_documents_count,
                "Thinking模式": think_mode_final or "none",
                "API_COT长度": len(think_content) if think_content else 0,
                "QA_COT长度": len(reasoning_chain) if reasoning_chain else 0,
                "推理步骤数": len([s.strip() for s in reasoning_chain.split('\n') if s.strip()]) if reasoning_chain else 0,
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

                # 展示推理链
                if "qa_cot_from_prompt" in item and item["qa_cot_from_prompt"]:
                    f.write("### 推理链:\n\n")
                    f.write("```text\n")
                    f.write(item["qa_cot_from_prompt"])
                    f.write("\n```\n\n")

                # 展示推理步骤
                if "reasoning_steps" in item and item["reasoning_steps"]:
                    f.write("### 推理步骤:\n\n")
                    for i, step in enumerate(item["reasoning_steps"], 1):
                        f.write(f"{i}. {step}\n")
                    f.write("\n")

                # 固定有 api_cot 字段，这里直接展示
                if "api_cot" in item and item["api_cot"]:
                    f.write("### 模型思考过程（COT）:\n\n")
                    f.write("```text\n")
                    f.write(item["api_cot"])
                    f.write("\n```\n\n")

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


# ==== 主函数 ====
def main():
    try:
        global_stats["start_time"] = datetime.now()

        # 生成带时间戳的输出目录
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        base_output_dir = "./output"
        output_dir = f"{base_output_dir}_{timestamp}"

        logger.info(f"创建输出目录: {output_dir}")
        os.makedirs(output_dir, exist_ok=True)

        master_jsonl_path = os.path.join(output_dir, "master.jsonl")
        answer_prompt_file = "./simple_text_prompt_v8.txt"

        input_dir = input("请输入包含多个问题文件的目录路径 (直接回车使用默认路径): ").strip()
        if not input_dir:
            input_dir = '../../03_data/reanswer_v5d/'

        print("\n=== 选择处理模式 ===")
        print("1. 同步顺序处理 (慢，但稳定)")
        print("2. 同步并发处理 (推荐，稳定且高效)")
        print("3. 使用ThreadPoolExecutor文件级并发 (多文件同时处理)")
        mode_input = input("请选择处理模式 (1-3, 默认2): ").strip()
        mode = mode_input if mode_input else "2"

        use_streaming_input = input("是否使用流式显示? (y/N): ").strip().lower()
        use_streaming = use_streaming_input in ["y", "yes"]

        use_rag_input = input("是否使用RAG检索文献? (y/N): ").strip().lower()
        use_rag = use_rag_input in ["y", "yes"]

        print("\n=== OpenAI Thinking模式设置 ===")
        print("说明：")
        print("  - auto: 自动根据问题难度动态选择 minimal/low/medium/high（推荐）")
        print("  - none/off: 不使用thinking模式")
        print("  - low/medium/high: 固定强度")
        think_input = input(
            "请选择think模式 (auto/none/low/medium/high, 直接回车默认为auto): "
        ).strip().lower()
        think_mode = think_input if think_input else "auto"

        max_workers = None
        if mode in ["2", "3"]:
            max_workers_input = input(
                f"最大工作线程数 (默认100, 系统最大): "
            ).strip()
            max_workers = int(max_workers_input) if max_workers_input else 100

        logger.info("开始批量处理")
        logger.info(f"输入目录: {input_dir}")
        logger.info(f"输出目录: {output_dir}")
        logger.info(f"Prompt文件: {answer_prompt_file}")
        logger.info(
            f"处理模式: {mode} ({'同步顺序' if mode == '1' else '同步并发' if mode == '2' else '文件级并发'})"
        )
        logger.info(f"使用流式: {use_streaming}")
        logger.info(f"使用RAG: {use_rag}")
        logger.info(f"Thinking模式(全局): {think_mode}")
        if max_workers:
            logger.info(f"最大工作线程数: {max_workers}")
        logger.info("连接池配置: 同步连接, 重试: 8次 (智能退避)")

        if mode == "2":
            logger.info("=" * 60)
            logger.info("同步并发模式优化配置:")
            logger.info(
                f"  ✓ 线程数: {max_workers if max_workers else 5} (用户设置)"
            )
            logger.info("  ✓ 分批处理: 避免一次性提交过多任务")
            logger.info("  ✓ 任务超时: 600秒")
            logger.info("  ✓ 批次延迟: 0.5秒 (防止过载)")
            logger.info("  ✓ 增强统计: 实时显示成功率、耗时等")
            logger.info("=" * 60)

        question_files = []
        for f in os.listdir(input_dir):
            if os.path.splitext(f)[-1].lower() in [".json", ".jsonl", ".xlsx", ".xls"]:
                question_files.append(os.path.join(input_dir, f))

        if not question_files:
            logger.warning(f"在目录 {input_dir} 中未找到问题文件")
            return

        logger.info(f"找到 {len(question_files)} 个问题文件")

        total_processed = 0
        if mode == "2":
            logger.info("使用同步并发模式 (问题级)")
            all_questions: List[Dict] = []
            for fpath in question_files:
                try:
                    with open(fpath, "r", encoding="utf-8") as f:
                        if fpath.endswith(".jsonl"):
                            questions_data = [json.loads(line) for line in f]
                        else:
                            questions_data = json.load(f)
                        all_questions.extend(questions_data)
                except Exception as e:
                    logger.error(f"读取文件失败 {fpath}: {e}")

            global_stats["total_files"] = len(question_files)
            global_stats["total_questions"] = len(all_questions)

            if all_questions:
                results = process_questions_concurrent(
                    all_questions,
                    output_dir,
                    answer_prompt_file,
                    use_streaming,
                    use_rag,
                    max_workers=max_workers,
                    think_mode=think_mode,
                )
                logger.info(f"并发处理完成，共生成 {len(results)} 个结果")
            total_processed = len(question_files)

        elif mode == "3":
            logger.info("使用文件级并发模式")

            total_questions_count = 0
            for fpath in question_files:
                try:
                    with open(fpath, "r", encoding="utf-8") as f:
                        if fpath.endswith(".jsonl"):
                            questions_data = [json.loads(line) for line in f]
                        else:
                            questions_data = json.load(f)
                        total_questions_count += len(questions_data)
                except Exception as e:
                    logger.error(f"读取文件失败 {fpath}: {e}")

            global_stats["total_files"] = len(question_files)
            global_stats["total_questions"] = total_questions_count

            process_files_concurrent(
                question_files,
                output_dir,
                answer_prompt_file,
                use_streaming,
                use_rag,
                max_workers=max_workers,
                think_mode=think_mode,
            )
            total_processed = len(question_files)

        else:
            logger.info("使用同步顺序模式")
            for i, fpath in enumerate(question_files):
                logger.info("=" * 60)
                logger.info(
                    f"处理文件 ({i+1}/{len(question_files)}): {os.path.basename(fpath)}"
                )
                logger.info("=" * 60)

                process_question_file(
                    fpath,
                    output_dir,
                    master_jsonl_path,
                    answer_prompt_file,
                    use_streaming,
                    use_rag,
                    think_mode=think_mode,
                )
                total_processed += 1

        global_stats["end_time"] = datetime.now()
        processing_stats = generate_overall_report(output_dir)

        logger.info(f"所有文件处理完成! 共处理 {total_processed} 个文件")
        logger.info(f"主数据文件: {master_jsonl_path}")

        logger.info("最终统计:")
        logger.info(f"- 总问题数: {global_stats['total_questions']}")
        logger.info(f"- 成功问题数: {global_stats['successful_questions']}")
        logger.info(f"- 失败问题数: {global_stats['failed_questions']}")
        logger.info(f"- 成功率: {processing_stats['success_rate']:.2f}%")
        logger.info(f"- 总Tokens: {global_stats['total_tokens']:,}")
        logger.info(f"- 总处理时间: {processing_stats['processing_time']}")
        if use_rag:
            logger.info(f"- 使用RAG的问题数: {global_stats['rag_used_count']}")
            logger.info(
                f"- RAG找到的总文献数: {global_stats['rag_documents_found']}"
            )

    except KeyboardInterrupt:
        logger.info("用户中断处理")
    except Exception as e:
        logger.error(f"程序异常退出: {e}", exc_info=True)
        raise


if __name__ == "__main__":
    main()


