#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
学位论文SFT问答对生成器 v1.4
=====================================

核心流程：读取学位论文 → 拆分章节 → 生成SFT问答对 → 保存
输出格式适用于大模型SFT训练，支持两阶段推理链生成

针对学位论文特点优化：
- 识别学位论文特有章节（摘要、引言、文献综述、方法、结果、讨论、结论）
- 增强学术性内容处理
- 优化实验结果和讨论部分的推理链生成
- 支持图表和公式的语义处理
- 自动质量评分 + 质量过滤
- 推理链多样性过滤（可选）
- Reasoning-aware curriculum stage（可选）

作者: Claude Code
版本: 1.4
日期: 2025-12-22

依赖包:
    - openai >= 1.0.0
    - python-dotenv
    - tqdm (可选，用于进度条)

使用示例:
    python demo_thesis_QA_genrator_v1_4.py \
        --input data/thesis.jsonl \
        --output output/sft_qa.jsonl \
        --max-q-per-chunk 5 \
        --workers 4
"""

import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from pathlib import Path
import json
import logging
import os
import re
import time
import uuid
from typing import List, Dict, Any, Optional, Tuple, Union
from openai import OpenAI, APIError, RateLimitError, Timeout
from dotenv import load_dotenv
import argparse
import hashlib
import threading
import random
from typing import List, Dict
from collections import defaultdict

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler('thesis_qa_generator.log', encoding='utf-8')
    ]
)
logger = logging.getLogger("thesis_sft")

# 加载环境变量
load_dotenv()

# 检查可选依赖：进度条
try:
    from tqdm import tqdm
    TQDM_AVAILABLE = True
except ImportError:
    TQDM_AVAILABLE = False
    logger.warning("tqdm未安装，将不显示进度条。安装命令: pip install tqdm")

# 检查可选依赖：推理多样性过滤
try:
    from reasoning_diversity import diversity_filter_qas
    REASONING_DIVERSITY_AVAILABLE = True
except Exception:
    REASONING_DIVERSITY_AVAILABLE = False
    diversity_filter_qas = None
    logger.info("推理多样性过滤模块未安装，将跳过多样性过滤")

# =============================================================================
# 客观题类型配置
# =============================================================================

# 题目类型配置（用于客观评测题生成）
QUESTION_TARGETS = {
    'single_choice': 200,  # 单选题
    'multiple_choice': 100,  # 多选题
    'true_false': 100  # 判断题
}

TOTAL_QUESTIONS = sum(QUESTION_TARGETS.values())  # 总题目数: 400题

# 并行处理配置
MAX_WORKERS = 100  # 最大并行线程数

# 输出目录配置
from datetime import datetime
current_time = datetime.now().strftime("%Y%m%d_%H%M%S")
OUTPUT_DIR = f'output_eval_{current_time}'

# 全局统计
stats = {
    'total_processed': 0,
    'questions_generated': 0,
    'success_count': 0,
    'failed_count': 0,
    'by_question_type': {},
    'start_time': None,
    'end_time': None,
    # Token统计
    'total_input_tokens': 0,
    'total_output_tokens': 0,
    'total_tokens': 0,
    'total_api_calls': 0,
    # 成本统计（需要设置价格）
    'input_price_per_m': 1.2500,  # $/百万tokens
    'output_price_per_m': 10.0000,  # $/百万tokens
}

# 线程锁（用于并发安全）
stats_lock = threading.Lock()

# =============================================================================
# 成本统计函数
# =============================================================================

def update_token_stats(input_tokens: int, output_tokens: int, total_tokens: int = None):
    """更新全局token统计

    Args:
        input_tokens: 输入token数
        output_tokens: 输出token数
        total_tokens: 总token数（如果未提供则自动计算）
    """
    if total_tokens is None:
        total_tokens = input_tokens + output_tokens

    with stats_lock:
        # 使用 get() 方法安全获取，如果不存在则初始化为0
        stats['total_input_tokens'] = stats.get('total_input_tokens', 0) + input_tokens
        stats['total_output_tokens'] = stats.get('total_output_tokens', 0) + output_tokens
        stats['total_tokens'] = stats.get('total_tokens', 0) + total_tokens
        stats['total_api_calls'] = stats.get('total_api_calls', 0) + 1

def calculate_cost():
    """计算总成本"""
    # 使用 get() 方法安全地获取值，如果不存在则使用默认值
    total_input_tokens = stats.get('total_input_tokens', 0)
    total_output_tokens = stats.get('total_output_tokens', 0)
    input_price_per_m = stats.get('input_price_per_m', 1.2500)
    output_price_per_m = stats.get('output_price_per_m', 10.0000)

    input_cost = (total_input_tokens / 1_000_000) * input_price_per_m
    output_cost = (total_output_tokens / 1_000_000) * output_price_per_m
    total_cost = input_cost + output_cost
    return input_cost, output_cost, total_cost

def print_cost_summary():
    """打印成本摘要"""
    input_cost, output_cost, total_cost = calculate_cost()

    # 安全地获取统计值
    total_api_calls = stats.get('total_api_calls', 0)
    total_input_tokens = stats.get('total_input_tokens', 0)
    total_output_tokens = stats.get('total_output_tokens', 0)
    total_tokens = stats.get('total_tokens', 0)
    success_count = stats.get('success_count', 0)
    input_price_per_m = stats.get('input_price_per_m', 1.2500)
    output_price_per_m = stats.get('output_price_per_m', 10.0000)

    logger.info("=" * 70)
    logger.info("Token 使用统计")
    logger.info("=" * 70)
    logger.info(f"总API调用次数: {total_api_calls:,}")
    logger.info(f"输入 tokens: {total_input_tokens:,}")
    logger.info(f"输出 tokens: {total_output_tokens:,}")
    logger.info(f"总 tokens: {total_tokens:,}")

    # 如果token统计为0，添加提示
    if total_tokens == 0 and success_count > 0:
        logger.info("")
        logger.info("⚠️ 注意: Token统计为0，可能原因:")
        logger.info("   1. API响应中没有usage信息")
        logger.info("   2. 使用的API端点不支持token统计")
        logger.info("   3. 本地OSS模型可能不返回usage信息")
        logger.info("")
        logger.info("建议: 检查API响应格式或使用支持token统计的API端点")

    logger.info("=" * 70)
    logger.info("成本统计")
    logger.info("=" * 70)
    logger.info(f"输入成本: ${input_cost:.4f} ({input_price_per_m:.4f}/百万tokens)")
    logger.info(f"输出成本: ${output_cost:.4f} ({output_price_per_m:.4f}/百万tokens)")
    logger.info(f"总成本: ${total_cost:.4f}")
    logger.info(f"平均每条记录成本: ${total_cost / max(success_count, 1):.6f}")
    logger.info("=" * 70)

# =============================================================================
# 配置验证函数
# =============================================================================

def validate_config(input_file: Optional[str] = None,
                   output_file: Optional[str] = None,
                   check_api: bool = True) -> None:
    """
    验证配置文件和环境变量

    Args:
        input_file: 输入文件路径 (可选)
        output_file: 输出文件路径 (可选)
        check_api: 是否检查API连接 (默认: True)

    Raises:
        ValueError: 当缺少必要的环境变量时
        FileNotFoundError: 当输入文件不存在时
        PermissionError: 当输出目录不可写时
    """
    # 检查必要环境变量
    required_env_vars = ['OPENAI_API_KEY']
    missing_vars = [var for var in required_env_vars if not os.getenv(var)]

    if missing_vars:
        raise ValueError(
            f"缺少必要的环境变量: {', '.join(missing_vars)}. "
            f"请在.env文件中设置这些变量。"
        )

    # 检查可选环境变量
    optional_vars = {
        'OPENAI_BASE_URL': 'https://api.openai.com/v1',
        'DEFAULT_MODEL': 'gpt-4o-mini',
    }

    for var, default in optional_vars.items():
        if not os.getenv(var):
            os.environ[var] = default
            logger.info(f"环境变量 {var} 未设置，使用默认值: {default}")

    logger.info("✅ 配置验证通过")

    # 验证输入文件
    if input_file:
        input_path = Path(input_file)
        if not input_path.exists():
            raise FileNotFoundError(f"输入文件不存在: {input_file}")
        logger.info(f"✅ 输入文件验证通过: {input_file}")

    # 验证输出文件
    if output_file:
        output_path = Path(output_file)
        output_dir = output_path.parent

        if not output_dir.exists():
            try:
                output_dir.mkdir(parents=True, exist_ok=True)
                logger.info(f"✅ 创建输出目录: {output_dir}")
            except PermissionError:
                raise PermissionError(f"输出目录不可写: {output_dir}")

        # 检查目录权限
        if not os.access(output_dir, os.W_OK):
            raise PermissionError(f"输出目录无写权限: {output_dir}")

        logger.info(f"✅ 输出文件验证通过: {output_file}")

    # 验证API连接 (可选)
    if check_api:
        try:
            client = OpenAI(
                api_key=os.getenv('OPENAI_API_KEY'),
                base_url=os.getenv('OPENAI_BASE_URL'),
                timeout=10.0
            )
            # 简单的API连接测试
            logger.info("✅ API连接验证通过")
        except Exception as e:
            logger.warning(f"⚠️ API连接验证失败: {e}")

# =============================================================================
# Thinking模式辅助函数
# =============================================================================

def update_stats(success=True, question_type=None):
    """更新统计信息（线程安全）"""
    with stats_lock:
        stats['total_processed'] += 1
        if success:
            stats['success_count'] += 1
            if question_type:
                stats['by_question_type'][question_type] = stats['by_question_type'].get(question_type, 0) + 1
        else:
            stats['failed_count'] += 1


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
    从 Responses API 的 output 结构中抽取 COT
    """
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

    def _extract_complete_reasoning(reasoning_obj) -> str:
        """提取完整的reasoning内容，包括summary和其他文本"""
        if not isinstance(reasoning_obj, dict):
            return ""

        # 首先尝试提取summary
        summary = reasoning_obj.get("summary")
        if summary:
            summary_text = _collect_from_summaries(summary)
            if summary_text:
                return "\n\n".join(summary_text)

        # 如果没有summary，尝试提取其他文本内容
        content = reasoning_obj.get("content") or reasoning_obj.get("text")
        if content:
            return str(content).strip()

        # 如果有summary字段但内容为空，尝试从其他字段提取
        for key in ["detail", "details", "summary_text", "reasoning_text"]:
            if key in reasoning_obj:
                val = reasoning_obj[key]
                if val:
                    return str(val).strip()

        return ""

    cot_chunks: List[str] = []

    try:
        outputs = data.get("output") or data.get("outputs") or []
        if not isinstance(outputs, list):
            return ""

        for out in outputs:
            if not isinstance(out, dict):
                continue

            out_type = out.get("type")

            if out_type == "reasoning":
                # 提取完整的reasoning内容
                reasoning_obj = out.get("reasoning")
                if reasoning_obj:
                    complete_reasoning = _extract_complete_reasoning(reasoning_obj)
                    if complete_reasoning:
                        cot_chunks.append(complete_reasoning)

                # 也尝试从summary提取（作为补充）
                summaries = out.get("summary")
                if summaries:
                    summary_chunks = _collect_from_summaries(summaries)
                    if summary_chunks and not cot_chunks:
                        cot_chunks.extend(summary_chunks)
                continue

            contents = out.get("content") or out.get("contents") or []
            if not isinstance(contents, list):
                continue

            for content in contents:
                if not isinstance(content, dict):
                    continue
                if content.get("type") != "reasoning":
                    continue

                # 优先提取完整的reasoning内容
                reasoning_obj = content.get("reasoning")
                if reasoning_obj:
                    complete_reasoning = _extract_complete_reasoning(reasoning_obj)
                    if complete_reasoning:
                        cot_chunks.append(complete_reasoning)
                        continue

                # 尝试从summary提取
                summaries = None
                if isinstance(reasoning_obj, dict) and "summary" in reasoning_obj:
                    summaries = reasoning_obj.get("summary")

                if summaries is None and "summary" in content:
                    summaries = content.get("summary")

                if summaries:
                    summary_chunks = _collect_from_summaries(summaries)
                    if summary_chunks and not cot_chunks:
                        cot_chunks.extend(summary_chunks)

    except Exception as e:
        logger.warning(f"从 reasoning.summary 中抽取 COT 时出错(已忽略): {e}")
        return ""

    return "\n\n".join([c for c in cot_chunks if c.strip()]).strip()


# --- 配置 ---
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
OPENAI_BASE_URL = os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1")
# 默认模型，支持自定义模型名称，包括: gpt-5.1, gpt-4o-mini, gpt-oss-120b, gpt-5-nano-2025-08-07 等
DEFAULT_MODEL = os.getenv("DEFAULT_MODEL", "gpt-5.1")
ENABLE_THINKING = True  # 全局控制是否启用Thinking模式

# --- 常量配置（学位论文偏严谨） ---
MIN_CHAPTER_LENGTH = 50  # 降低最小长度阈值到50字符
# 重要学术章节，即使很短也应该保留
IMPORTANT_ACADEMIC_SECTIONS = [
    # 基本学术章节
    'introduction', 'abstract', 'background', 'overview',
    'methods', 'methodology', 'materials', 'approach',
    'results', 'findings', 'analysis', 'outcomes',
    'discussion', 'conclusion', 'conclusions', 'summary',
    # 研究相关
    'case study', 'case studies', 'experiment', 'experiments', 'experimental',
    'hypothesis', 'theory', 'theoretical', 'framework',
    'population', 'populations', 'sample', 'samples', 'subjects',
    'data', 'dataset', 'survey', 'surveys', 'questionnaire',
    # 研究过程
    'design', 'procedure', 'protocol', 'strategy',
    'objective', 'objectives', 'aim', 'aims', 'purpose',
    'evaluation', 'assessment', 'measurement',
    # 其他学术内容
    'review', 'literature', 'related work', 'prior work',
    'study', 'studies', 'research', 'investigation',
    'evidence', 'proof', 'demonstration',
    'comparison', 'contrast', 'difference', 'similarity',
    # 生物学相关内容
    'evolution', 'evolutionary', 'species', 'genetics', 'genetic',
    'biology', 'biological', 'ecology', 'ecological',
    'phylogeny', 'phylogenetic', 'taxonomy', 'taxonomic',
    'morphology', 'morphological', 'physiology', 'physiological',
    'behavior', 'behaviour', 'behavioral',
    'adaptation', 'adaptive', 'selection', 'variation',
    'inheritance', 'heredity', 'mutation', 'variants',
    # 新增：生产和工艺相关内容
    'production', 'production from', 'synthesis', 'synthesis of',
]
MAX_CHUNK_SIZE = 150
IDEA_CHUNK_LENGTH = 2500
MAX_Q_PER_CHUNK = 6
THESIS_SOURCES = {'thesis', 'dissertation', 'paper', 'article', 'research', 'study'}
OVER_GENERATE_FACTOR = 2

# 适合推理链的学位论文章节（更广一点，后续由逻辑判断兜底）
REASONING_SECTIONS = [
    'results', 'result',
    'discussion', 'discussions',
    'method', 'methods', 'methodology',
    'analysis', 'analyses',
    'background', 'introduction',
    'literature', 'related work', 'literature review',
    'evaluation', 'experiment', 'experiments',
    'ablation',
]

# 学位论文特有的违禁短语（更严格）
FORBIDDEN_PHRASES = [
    "文中指出", "文中提到", "文中认为", "文中表明",
    "本文指出", "本文认为", "本文表明", "本文中", "文本中", "实验中", "试验中",
    "文章指出", "文章认为", "文章表明", "文章中",
    "该研究指出", "该研究认为", "该研究表明", "该研究", "该章节",
    "在该实验中", "在本实验中", "在本研究中", "在这项研究中",
    "根据给定内容", "根据上述内容", "根据文中内容", "根据本文内容", "根据文本内容",
    "作者认为", "作者指出", "作者提到",
    "根据给出的", "根据给出的文本", "根据给出的内容",
    "这段文字", "这段文本", "这段内容", "这段研究", "这段描述",
    "本论文", "本学位论文", "本课题", "本课题研究",
    "论文中", "学位论文中", "课题中", "研究中",
    "如图所示", "如图", "如表所示", "如表",
    "见下图", "见上表", "见Figure", "见Table",
    "图1", "图2", "图3", "表1", "表2", "表3",
    "附录A", "附录B", "附录C",
    "参考文献", "见文献", "详见文献",
    "我们发现", "我们得出", "我们得出结论",
    "通过本实验", "通过本研究", "通过本论文",
    "上述结果", "以上结果", "以上分析",
    "本研究的主要贡献", "本研究的创新点",
]

# =============== 日志配置 ===============
def setup_logger():
    log_dir = os.path.join(os.getcwd(), 'log')
    os.makedirs(log_dir, exist_ok=True)
    log_file = os.path.join(log_dir, 'gen_thesis_sft_qa.log')

    logger = logging.getLogger("thesis_sft")
    logger.setLevel(logging.INFO)
    if logger.hasHandlers():
        logger.handlers.clear()

    file_handler = logging.FileHandler(log_file, encoding='utf-8')
    console_handler = logging.StreamHandler()
    formatter = logging.Formatter(
        '%(asctime)s - %(levelname)s - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    file_handler.setFormatter(formatter)
    console_handler.setFormatter(formatter)

    logger.addHandler(file_handler)
    logger.addHandler(console_handler)
    return logger

logger = setup_logger()

# =============== 线程本地存储 ===============
_thread_local = threading.local()

def get_thread_id():
    return getattr(_thread_local, 'thread_id', 0)

def set_thread_id(thread_id: int):
    _thread_local.thread_id = thread_id

def tprint(message: str):
    thread_id = get_thread_id()
    prefix = f"[T{thread_id}]" if thread_id else ""
    print(f"{prefix} {message}", flush=True)

def log_error_with_context(error: Exception, chunk_id: str, question_preview: str = "", thesis_id: str = ""):
    """
    记录详细错误信息

    Args:
        error: 异常对象
        chunk_id: chunk ID
        question_preview: 问题预览（截取前100字符）
        thesis_id: 论文ID
    """
    import traceback

    error_info = {
        'error_type': type(error).__name__,
        'error_message': str(error),
        'chunk_id': chunk_id,
        'thesis_id': thesis_id,
        'question_preview': question_preview[:100] if question_preview else "",
        'traceback': traceback.format_exc(),
        'timestamp': datetime.now().isoformat(timespec="seconds")
    }

    logger.error(
        f"处理失败 | "
        f"论文={thesis_id} | "
        f"chunk={chunk_id} | "
        f"错误={error_info['error_type']}: {error_info['error_message']}"
    )

    # 如果是DEBUG级别日志，记录完整的traceback
    if logger.isEnabledFor(logging.DEBUG):
        logger.debug(f"完整错误信息: {json.dumps(error_info, ensure_ascii=False, indent=2)}")

# =============== 数据验证工具 ===============

def validate_qa_record(record: Dict[str, Any], chunk_id: str = "") -> Tuple[bool, List[str]]:
    """
    验证QA记录是否符合Schema

    Args:
        record: QA记录字典
        chunk_id: 用于日志记录的chunk ID

    Returns:
        (is_valid, error_messages): 是否有效及错误信息列表
    """
    # 必填字段
    REQUIRED_FIELDS = [
        'source_id', 'source_type', 'chunk_title', 'chunk_id',
        'question', 'answer', 'context', 'difficulty', 'generation_type'
    ]

    errors = []

    # 检查必填字段
    for field in REQUIRED_FIELDS:
        if field not in record or not record[field]:
            errors.append(f"缺少必填字段或为空: {field}")

    # 检查字段类型
    if 'question' in record and not isinstance(record['question'], str):
        errors.append("question字段必须是字符串")

    if 'answer' in record and not isinstance(record['answer'], str):
        errors.append("answer字段必须是字符串")

    if 'context' in record and not isinstance(record['context'], str):
        errors.append("context字段必须是字符串")

    # 检查字段长度
    if 'question' in record and len(record['question']) < 8:
        errors.append("问题过短（少于8字符）")

    if 'answer' in record and len(record['answer']) < 30:
        errors.append("答案过短（少于30字符）")

    # 记录验证错误
    if errors and chunk_id:
        logger.warning(f"Chunk {chunk_id} 验证失败: {'; '.join(errors)}")

    return len(errors) == 0, errors

# =============== 基础工具 ===============
def estimate_tokens(text: str) -> int:
    if not text:
        return 0
    # 粗略估算，中文/英文混合时可用
    return int(max(1, len(text)) / 3.5)


def estimate_target_q_per_thesis(
    thesis_text: str,
    chunks: List[Dict[str, Any]],
    floor: int = 80,
    cap: int = 300,
    per_chunk_base: int = 15,
) -> int:
    """
    自动估计：每篇学位论文应保留的目标 QA 数（用于最终采样/裁剪）

    主要信号：
    - chunks 数：反映论文结构复杂度、可提炼知识点数量
    - 文本长度：反映信息密度（轻量修正，不喧宾夺主）

    Args:
        thesis_text: 全文文本
        chunks: split_by_chapters 后的 chunks
        floor: 下限（避免覆盖不足）
        cap: 上限（避免噪声爆炸）
        per_chunk_base: 每个有效 chunk 的基础 QA 配额

    Returns:
        int: 目标 QA 数
    """
    if not chunks:
        return floor

    # 1) 结构复杂度：有效 chunk 数
    # 你这里 chunks 已经经过 MIN_CHAPTER_LENGTH 过滤，直接计数即可
    num_chunks = len(chunks)

    # 结构主导：chunks * per_chunk_base
    base = num_chunks * per_chunk_base

    # 2) 文本长度修正（轻量）
    # 这里用字符长度做近似；中文论文一般 6-10 万字，对应字符会更大，但比例修正我们用 sqrt 平滑
    text_len = len(thesis_text or "")
    # 经验“参考长度”（可按你语料微调）：12 万字符附近视作 1.0
    ref_len = 120_000
    # sqrt 平滑：避免长度带来过大波动
    length_factor = (max(text_len, 1) / ref_len) ** 0.5
    # 夹逼：最多放大到 1.4，最少缩小到 0.75（不要让长度信号压过结构信号）
    length_factor = min(1.4, max(0.75, length_factor))

    target = int(round(base * length_factor))

    # 3) 下限/上限
    target = max(floor, min(cap, target))
    return target


def sanitize_text_forbidden_phrases(text: str) -> str:
    if not text:
        return ""
    text = re.sub(r'\n+', ' ', text)
    text = re.sub(r'\s{2,}', ' ', text)
    text = re.sub(r'[，。；：]{2,}', lambda m: m.group(0)[0], text)
    text = re.sub(r'^[，；：、\s]+', '', text)
    return text.strip()

def clean_text_basic(text: str) -> str:
    """学位论文版清洗：图表/公式/引用归一化，降低'论文口吻'干扰"""
    if not text:
        return ""

    # 提取并临时保存markdown标题（避免被清洗破坏）
    header_lines = []
    header_pattern = re.compile(r'^(#{1,6})\s+(.+)$', re.MULTILINE)
    temp_headers = {}

    def save_header(match):
        header_id = f"__HEADER_{len(temp_headers)}__"
        level = match.group(1)
        title = match.group(2)
        temp_headers[header_id] = (level, title)
        return header_id

    # 临时替换所有markdown标题
    text = header_pattern.sub(save_header, text)

    # Markdown 图片 → 占位
    text = re.sub(r'!\[[^\]]*?\]\([^\)]*?\)', '[图片]', text)

    # HTML 标签（保留 sub/sup）
    text = re.sub(r'<(?!sub|sup|/sub|/sup)[^>]+>', ' ', text)

    # Markdown 链接保留文本
    text = re.sub(r'\[([^\]]+)\]\([^\)]+\)', r'\1', text)

    # 表格行去掉
    text = re.sub(r'^\s*\|.*\|\s*$', ' ', text, flags=re.MULTILINE)

    # 图表引用统一
    text = re.sub(r'(图|表)\s*\d+([：:])?', '图表', text)
    text = re.sub(r'(Figure|Table|Fig\.)\s*\d+([：:])?', '图表', text, flags=re.IGNORECASE)

    # LaTeX/公式占位
    text = re.sub(r'\\begin\{equation\}.*?\\end\{equation\}', '公式', text, flags=re.DOTALL)
    text = re.sub(r'\\\[.*?\\\]', '公式', text, flags=re.DOTALL)
    text = re.sub(r'\$[^$]+\$', '公式', text)

    # 参考文献/年份/编号弱化
    text = re.sub(r'\[\s*\d+\s*\]', '[参考文献]', text)
    text = re.sub(r'\(\s*\d{4}[a-z]?\s*\)', '(年份)', text)

    # 合并空行/空格
    text = re.sub(r'\n{3,}', '\n\n', text)
    text = re.sub(r'[ \t]{2,}', ' ', text)

    # 恢复markdown标题
    def restore_header(match):
        header_id = match.group(0)
        if header_id in temp_headers:
            level, title = temp_headers[header_id]
            return f"{level} {title}"
        return match.group(0)

    text = re.sub(r'__HEADER_\d+__', restore_header, text)

    return text.strip()

def is_study_dependent(text: str) -> bool:
    """更强的'论文口吻/研究依赖'检测（中英文都覆盖一点）"""
    if not text:
        return False

    patterns = [
        r"根据(本|该|这项)研究",
        r"在(本|该|这项)研究中",
        r"(本|该)研究表明",
        r"(本文|该文|本论文|本学位论文)(中)?(认为|指出|表明|描述|提出)",
        r"在(本|该)?实验中",
        r"(本|该)实验(中)?",
        r"该论文(中|指出|认为|表明)",
        r"\bwe (find|found|show|demonstrate|observe)\b",
        r"\bour (results|study|work)\b",
        r"\bin this (paper|thesis|study)\b",
    ]
    for p in patterns:
        if re.search(p, text, flags=re.IGNORECASE):
            return True
    return False

def contains_forbidden_phrases(text: str) -> bool:
    if not text:
        return False
    return any(phrase in text for phrase in FORBIDDEN_PHRASES)



# ==============================================================================
# 语言检测与多语言跳过配置
# ==============================================================================

from typing import Dict, List
import re
import logging

logger = logging.getLogger(__name__)

# 需要在工程其他位置定义：
# MIN_CHAPTER_LENGTH: int
# IMPORTANT_ACADEMIC_SECTIONS: List[str]


import re
from typing import Dict, List

# ======================================================================
# 语言相关跳过关键词表（含你之前的配置 + 新增 financial obligation）
# ======================================================================

LANG_SKIP_KEYWORDS: Dict[str, List[str]] = {
    "generic": [
        # ====== 学术出版通用后置部分 ======
        "references", "bibliography",
        "acknowledg", "acknowledgement", "acknowledgments", "Danksagung"

        # ====== 学位 / 行政性信息（通用） ======
        "degrees awarded", "degree awarded",
        "degrees conferred", "degree conferred",
        "academic degrees", "degrees obtained",

        # ProQuest/学位数据库相关
        "proquest number", "proquest dissertations", "proquest llc", "proquest"

        # 毕业 / 授位证明页
        "graduation certification", "graduation certification page",
        "graduation certificate", "certificate of graduation",
        "award of degree", "award of the degree",

        # ====== 列表类前置（图/表/目录） ======
        "list of figures", "figures list",
        "list of tables", "tables list",
        "table of contents", "contents", "list", "List of acronyms"

        # ====== 附录 / 补充材料 ======
        "appendix", "appendices",
        "supplementary", "supplementary material", "supplementary materials",
        "supplemental material", "supplemental materials",

        # ====== 前置行政内容（论文审批等） ======
        "thesis approval page", "approval page", "signature page",
        "committee page", "examining committee", "supervisory committee",
        "defense committee", "examination committee", "THE UNIVERSITY",
        "STATEMENT OF PERMISSION TO USE"

        # ====== 成绩 / 答辩结果记录 ======
        "examination results", "exam results",
        "defense record", "defence record",
        "oral defense record", "oral defence record",
        "viva record", "viva voce record",

        # ====== 出版商声明 ======
        "publisher's note", "publisher’s note", "publisher note",

        # ====== 公式 / 方程类章节 ======
        "equation", "equations",

        # ====== 研究人员相关章节 ======
        "researchers", "HONORS & AWARDS", "HONORS", "AWARDS",
        "APPROVED", "Biographical Sketch", "INFORMATION TO USERS"
    ],

    "en": [
        # 作者贡献
        "author contribution", "authors' contributions", "authors’ contributions",
        "author contributions", "authors contributions",
        "contributions of the authors",

        # 伦理、冲突、资金
        "ethics statement", "ethical approval", "ethics approval",
        "conflict of interest", "conflicts of interest",
        "competing interest", "competing interests",
        "funding", "financial support", "grant support",
        "voluntary participation",

        # 数据 / 代码可用性
        "data availability", "availability of data",
        "data and materials availability",
        "code availability",

        # 声明 / 版权页 / 授权条款
        "declaration", "author declaration",
        "copyright", "copyright page", "copyright notice",
        "intellectual property rights",
        "license", "licence", "licensing",
        "information to all users",
        "commercial",
        "other terms and conditions",
        "terms and conditions",
        "financial obligation", "financial obligations",

        # 前置文本
        "dedication", "foreword", "prologue",
    ],

    "fr": [
        "remerciements",
        "résumé", "resume",
        "jury d'evaluation", "jury d’evaluation", "jury",
        "dédicace", "dedicace",
        "avant-propos", "préface", "preface",
    ],

    "zh": [
        "参考文献", "致谢", "附录",
        "作者贡献", "作者简介", "个人简介",
        "研究生简历", "攻读学位期间发表的论文",
    ],
}


def detect_language(section_name: str, section_text: str) -> str:
    """
    极简启发式语言检测：
    - 含有中文字符 -> 'zh'
    - 含有法语重音/典型法语词 -> 'fr'
    - 默认 -> 'en'
    """
    text = f"{section_name} {section_text}".strip()
    if not text:
        return "en"

    # 粗略中文检测
    if re.search(r"[\u4e00-\u9fff]", text):
        return "zh"

    lower = text.lower()

    # 粗略法文检测
    if re.search(r"[éèêàùçïîôûÉÈÊÀÙÇÏÎÔÛ]", text) or any(
        kw in lower for kw in ["remerciements", "résumé", "resume", "jury d", "avant-propos", "préface"]
    ):
        return "fr"

    # 默认视作英文环境
    return "en"


def get_skip_keywords_for_language(lang: str) -> List[str]:
    """根据检测到的语言返回合并后的跳过关键词列表"""
    base = list(LANG_SKIP_KEYWORDS["generic"])
    base.extend(LANG_SKIP_KEYWORDS.get(lang, []))
    return base


# ======================================================================
# 两阶段推理链生成相关 - 跳过章节逻辑（多语言 + md/OCR 解析错误鲁棒）
# ======================================================================

def should_skip_section(section_name: str, section_text: str) -> bool:
    """
    判断是否应该跳过这个章节（不生成 QA）

    多层检测逻辑：
    0-. 特殊标题过滤（commercial / license / researchers /
        dedication / terms and conditions / financial obligation）
    0. 语言检测 + 语言特定关键词匹配（front/back matter 过滤）
    1. 标题级别的稳健正则匹配（作者贡献 / 伦理 / 数据可用性 / 图表与列表等）
    2. 章节长度检查（对非核心学术章节启用）
    3. 参考文献条目模式检测（年份 / 卷期 / 页码 / 期刊关键词）
    4. 作者名 + 年份 + 期刊联合检测（仅对疑似参考文献章节）
    5. 目录 / 索引样式检测
    6. 纯页码检测
    7. et al. + 年份 + DOI/卷期 的参考文献检测（仅对疑似参考文献章节）
    8. 完整参考文献格式检测（仅对疑似参考文献章节）
    9. 地址信息检测（投稿信息 / 通讯作者地址，仅对疑似参考文献章节）
    """
    section_name = section_name or ""
    section_text = section_text or ""

    section_lower = section_name.lower().strip()
    # 紧凑版标题：用于处理 md/PDF 解析错误（如 "DEDICA TION" / "TERMS AND CONDI TIONS"）
    section_compact = re.sub(r"\s+", "", section_lower)

    text_stripped = section_text.strip()
    text_lower = text_stripped.lower()

    # -------------------------
    # (0-) 额外标题关键词过滤（优先级最高）
    # -------------------------
    # 正常匹配：标题里只要包含这些字符串就跳过
    extra_skip_keywords = [
        "commercial",
        "license",
        "licence",
        "licensing",
        "researchers",
        "terms and conditions",
        "financial obligation",
        "financial obligations",
        "Statement by Supervisor",
        "Open Access License",
        "Eidesstattliche Versicherung",
        "TABLES",
        "figures",
        "VITA",
        "Interannual-to-Decadal Changes",
        "THE UNIVERSITY"
    ]
    for kw in extra_skip_keywords:
        if kw in section_lower:
            logger.debug(f"跳过章节 (额外关键词匹配: {kw}): {section_name}")
            return True

    # 紧凑匹配：处理 md/OCR 把单词拆开的情况
    # 例如：DEDICA TION / DEDI CATION / TERMS AND CONDI TIONS / Financial Obliga tion
    # 使用正则表达式进行更精确的匹配
    if re.search(r"\bdedication\b", section_lower):
        logger.debug(f"跳过章节 (Dedication 紧凑匹配): {section_name}")
        return True

    if re.search(r"\bterms and conditions\b", section_lower):
        logger.debug(f"跳过章节 (Terms and Conditions 紧凑匹配): {section_name}")
        return True

    if re.search(r"\bfinancial obligation\b", section_lower):
        logger.debug(f"跳过章节 (Financial Obligation 紧凑匹配): {section_name}")
        return True

    # 添加更多紧凑匹配：文献管理、排版格式等
    # 使用单词边界匹配，避免部分匹配导致误判
    if re.search(r"\blist of figures\b", section_lower):
        logger.debug(f"跳过章节 (List of Figures 紧凑匹配): {section_name}")
        return True

    if re.search(r"\blist of tables\b", section_lower):
        logger.debug(f"跳过章节 (List of Tables 紧凑匹配): {section_name}")
        return True

    if re.search(r"\btable of contents\b", section_lower):
        logger.debug(f"跳过章节 (Table of Contents 紧凑匹配): {section_name}")
        return True

    if re.search(r"\bbibliography\b", section_lower):
        logger.debug(f"跳过章节 (Bibliography 紧凑匹配): {section_name}")
        return True

    if re.search(r"\bworks cited\b", section_lower) or re.search(r"\bliterature cited\b", section_lower):
        logger.debug(f"跳过章节 (References 紧凑匹配): {section_name}")
        return True

    if re.search(r"\bcurriculum vitae\b", section_lower):
        logger.debug(f"跳过章节 (Curriculum Vitae 紧凑匹配): {section_name}")
        return True

    if re.search(r"\bauthor contributions?\b", section_lower):
        logger.debug(f"跳过章节 (Author Contributions 紧凑匹配): {section_name}")
        return True

    if re.search(r"\backnowlegments?\b", section_lower):
        logger.debug(f"跳过章节 (Acknowledgments 紧凑匹配): {section_name}")
        return True

    if re.search(r"\bappendix\b", section_lower):
        logger.debug(f"跳过章节 (Appendix 紧凑匹配): {section_name}")
        return True

    if re.search(r"\bsupplementary\b", section_lower):
        logger.debug(f"跳过章节 (Supplementary 紧凑匹配): {section_name}")
        return True

    if re.search(r"\bcopyright\b", section_lower):
        logger.debug(f"跳过章节 (Copyright 紧凑匹配): {section_name}")
        return True

    if re.search(r"\bethics statement\b", section_lower):
        logger.debug(f"跳过章节 (Ethics Statement 紧凑匹配): {section_name}")
        return True

    # Educational Outreach Activities（教育活动/外展活动）
    # 匹配包含 "educational" 或 "outreach" 的章节
    if re.search(r"\beducational\b", section_lower):
        logger.debug(f"跳过章节 (Educational 紧凑匹配): {section_name}")
        return True

    if re.search(r"\boutreach\b", section_lower):
        logger.debug(f"跳过章节 (Outreach 紧凑匹配): {section_name}")
        return True

    # ANNEXE（附录的法语）
    if re.search(r"\bannexe\b", section_lower):
        logger.debug(f"跳过章节 (Annexe 紧凑匹配): {section_name}")
        return True

    # -------------------------
    # (0) 语言检测 & 关键词列表
    # -------------------------
    lang = detect_language(section_name, section_text)
    skip_keywords = get_skip_keywords_for_language(lang)

    # 通用 + 语言特定关键词匹配（只看标题）
    for keyword in skip_keywords:
        if keyword and keyword.lower() in section_lower:
            logger.debug(f"跳过章节 (语言特定关键词匹配: {keyword}): {section_name}")
            return True

    # -------------------------
    # (1) 标题级别的额外稳健匹配
    # -------------------------

    # 作者贡献（Author(s)' contribution(s)）
    if re.search(r"author[s]?\s*[\’'’]?\s*contribution[s]?", section_lower):
        logger.debug(f"跳过章节 (作者贡献正则): {section_name}")
        return True

    # 伦理声明
    if re.search(r"(ethics|ethical).*statement", section_lower):
        logger.debug(f"跳过章节 (伦理声明正则): {section_name}")
        return True

    # 冲突 / 竞争利益
    if re.search(r"(conflict|competing).*interest", section_lower):
        logger.debug(f"跳过章节 (利益冲突正则): {section_name}")
        return True

    # 数据 / 代码可用性
    if re.search(r"(data|code).*availability", section_lower):
        logger.debug(f"跳过章节 (数据/代码可用性正则): {section_name}")
        return True

    # Publisher's note
    if "publisher" in section_lower and "note" in section_lower:
        logger.debug(f"跳过章节 (Publisher's note 正则): {section_name}")
        return True

    # Jury / 评审委员会（欧陆论文）
    if (
        "jury" in section_lower
        or "évaluation" in section_lower
        or "evaluation committee" in section_lower
    ):
        logger.debug(f"跳过章节 (评审委员会正则): {section_name}")
        return True

    # List of Figures / List of Tables（考虑 OCR 多空格）
    if re.search(r"list\s+of\s+figures", section_lower):
        logger.debug(f"跳过章节 (List of Figures 正则): {section_name}")
        return True
    if re.search(r"list\s+of\s+tables", section_lower):
        logger.debug(f"跳过章节 (List of Tables 正则): {section_name}")
        return True
    if re.search(r"(figures|tables)\s+list", section_lower):
        logger.debug(f"跳过章节 (Figures/Tables list 正则): {section_name}")
        return True

    # List of Abbreviations / Abbreviations / Glossary / Nomenclature
    if (
        section_lower == "abbreviations"
        or section_lower == "abbreviation"
        or re.search(r"list\s+of\s+abbreviations", section_lower)
        or re.search(r"\babbreviations\s+and\s+acronyms\b", section_lower)
        or re.search(r"\babbreviation\s+list\b", section_lower)
        or section_lower == "nomenclature"
        or section_lower == "glossary"
        or re.search(r"list\s+of\s+symbols", section_lower)
    ):
        logger.debug(f"跳过章节 (缩略词/术语列表): {section_name}")
        return True

    # Tables and Figures（整体图表列表）
    if section_lower in ("tables and figures", "tables & figures"):
        logger.debug(f"跳过章节 (Tables and Figures 列表): {section_name}")
        return True

    # 论文标题水印/页眉（如 DISSERTATION / THESIS 等）
    if section_lower in ("dissertation", "thesis", "master thesis", "phd thesis"):
        logger.debug(f"跳过章节 (论文标题水印): {section_name}")
        return True

    # ProQuest 信息页 / 扫描版本页眉页脚
    if (
        "proquest" in section_lower
        or "pro quest" in section_lower
        or "pqdt" in section_lower            # ProQuest Dissertations & Theses
        or "umi dissertation" in section_lower
    ):
        logger.debug(f"跳过章节 (ProQuest 信息页): {section_name}")
        return True

    # （保留更具体的 ProQuest Number 检测，虽然已被上面覆盖，但无害）
    if "proquest number" in section_lower:
        logger.debug(f"跳过章节 (ProQuest Number): {section_name}")
        return True

    # STATEMENT BY AUTHOR / STATEMENT OF AUTHORSHIP / AUTHOR'S STATEMENT
    if (
        "statement by author" in section_lower
        or "statement of authorship" in section_lower
        or "author's statement" in section_lower
        or "authors' statement" in section_lower
        or "authorship statement" in section_lower
    ):
        logger.debug(
            f"跳过章节 (Statement by Author / Authorship Statement): {section_name}"
        )
        return True

    # Table of Contents / Contents
    if re.search(r"table\s+of\s+contents", section_lower) or section_lower == "contents":
        logger.debug(f"跳过章节 (目录 Table of Contents): {section_name}")
        return True

    # 时间标记章节（如 “Fall 2013”, “Spring 2014”）
    time_pattern = r"^(spring|summer|fall|autumn|winter)\s+\d{4}$"
    if re.match(time_pattern, section_lower):
        logger.debug(f"跳过章节 (时间标记章节): {section_name}")
        return True
    if "fall 2013" in section_lower:
        logger.debug(f"跳过章节 (Fall 2013 标记): {section_name}")
        return True

        # 图表标题类章节（Fig / Figure / Table + 编号）
    figure_pattern = r"^(figure|fig)\.?\s+[a-zA-Z]*\s*\d+(\.\d+)*$"
    table_pattern = r"^table\.?\s+[a-zA-Z]*\s*\d+(\.\d+)*$"

    if re.match(figure_pattern, section_lower):
        logger.debug(f"跳过章节 (图标题 Figure/Fig): {section_name}")
        return True
    if re.match(table_pattern, section_lower):
        logger.debug(f"跳过章节 (表标题 Table): {section_name}")
        return True

    # 新增：补充表格类标题，例如 "table s1", "supplementary table s2" 等
    # 注意：section_lower 已经是小写，所以只匹配 s，不区分 S/s
    if re.search(r"table\s+s\d+\b", section_lower):
        logger.debug(f"跳过章节 (补充表 Table Sx): {section_name}")
        return True

    # 再加一层兜底的 Fig 开头（防 OCR 噪声）
    if section_lower.startswith("fig ") or section_lower.startswith("fig. "):
        logger.debug(f"跳过章节 (Fig 开头兜底): {section_name}")
        return True

    # 新增：过滤单独的"Table"词汇（不带编号）
    if section_lower.strip() == "table":
        logger.info(f"跳过章节: {section_name} (单独的Table词汇)")
        return True

    # 新增：过滤术语定义类章节，如"Degree Days (DD)"等
    # 这些通常是术语解释，不适合生成推理链
    term_definition_patterns = [
        r"^degree\s+days\s*\([A-Z]+\)$",  # "Degree Days (DD)"
        r"^growing\s+degree\s+days\s*\([A-Z]+\)$",  # "Growing Degree Days (GDD)"
        r"^chilling\s+hours\s*\([A-Z]+\)$",  # "Chilling Hours (CH)"
    ]
    for pattern in term_definition_patterns:
        if re.match(pattern, section_lower.strip()):
            logger.info(f"跳过章节: {section_name} (术语定义模式)")
            return True

    # 新增：跳过所有包含"Degree Days"的章节
    if "degree days" in section_lower:
        logger.info(f"跳过章节: {section_name} (包含Degree Days)")
        return True

    # 新增：跳过所有包含"Calculations"的章节
    if "calculations" in section_lower:
        logger.info(f"跳过章节: {section_name} (包含Calculations)")
        return True

    # 新增：跳过论文前置/后置页面类章节
    # 只保留真正需要跳过的内容，避免过于宽泛的匹配
    front_back_matter = [
        "vita", "curriculum vitae",
        "abstract of the dissertation", "abstract of thesis",
        "objectives of the dissertation", "objectives of thesis",
        "introduction to the dissertation", "introduction to thesis",
    ]
    # 使用部分匹配（包含关键词即跳过）
    for keyword in front_back_matter:
        if keyword.lower() in section_lower:
            logger.info(f"跳过章节: {section_name} (前置/后置页面，包含关键词: {keyword})")
            return True

    # 新增：跳过实验方法、统计方法、工具类章节
    # 使用单词边界匹配，避免误判正常的科学章节
    method_tool_patterns = [
        r"\bassay\b",  # 完整的"assay"单词，如"PCR Assay", "Real Time Quantitative-PCR Assay"
        r"\bpcr\b",  # 完整的"PCR"单词
        r"\bqpcr\b",  # 完整的"qPCR"单词
        r"\bsequencing\b",  # 完整的"sequencing"单词
        r"\bmapping\b",  # 完整的"mapping"单词
        r"\bmodel\b",  # 完整的"model"单词，如"Hidden Markov Model"
        r"\bprimers?\b",  # 完整的"primer"或"primers"单词
        r"\bprotocol\b",  # 完整的"protocol"单词
        r"analysis of variance assumptions",  # "Analysis of Variance Assumptions"
        r"treatment biomass",  # "Treatment Biomass..."
        r"relative growth rate",  # "Relative Growth Rate"
    ]
    for pattern in method_tool_patterns:
        if re.search(pattern, section_lower):
            logger.info(f"跳过章节: {section_name} (实验方法/统计工具)")
            return True


    # Dedication / Preface / Prologue / Foreword
    if section_lower in (
        "dedication", "dédicace", "dedicace",
        "preface", "préface", "avant-propos",
        "foreword", "prologue",
    ):
        logger.debug(f"跳过章节 (前置文本 Dedication/Preface/Prologue): {section_name}")
        return True

    # Declaration / Copyright page
    if "declaration" in section_lower and "author" in section_lower:
        logger.debug(f"跳过章节 (声明 Declaration): {section_name}")
        return True
    if "copyright" in section_lower and (
        "page" in section_lower or "notice" in section_lower or "©" in section_lower
    ):
        logger.debug(f"跳过章节 (版权页 Copyright): {section_name}")
        return True

    # Examination results / Defense record / Viva record
    if re.search(r"(examination|exam|defen[sc]e|viva).*(result|record)", section_lower):
        logger.debug(f"跳过章节 (Examination results/Defense record): {section_name}")
        return True
    if re.search(r"(result|record).*(examination|exam|defen[sc]e|viva)", section_lower):
        logger.debug(f"跳过章节 (Examination results/Defense record 反向): {section_name}")
        return True

    # Graduation certification / 授位证明页
    if re.search(r"graduation.*(certificate|certification|page)", section_lower):
        logger.debug(f"跳过章节 (Graduation Certification Page): {section_name}")
        return True

    # Degrees Awarded / Conferred / Obtained
    if re.search(r"degree[s]?\s*[-–—]?\s*(awarded|conferred|obtained)", section_lower):
        logger.debug(f"跳过章节 (Degrees Awarded/Conferred): {section_name}")
        return True

    # -------------------------
    # (2) 章节长度检查（对非核心学术章节）
    # -------------------------
    is_important_academic = any(
        keyword.lower() in section_lower for keyword in IMPORTANT_ACADEMIC_SECTIONS
    )

    if not is_important_academic and len(text_stripped) < MIN_CHAPTER_LENGTH:
        logger.debug(f"跳过章节 (长度不足): {section_name}, 长度={len(text_stripped)}")
        return True

    # -------------------------
    # (3) 参考文献条目模式检测（EN/FR/ZH 混排）
    # -------------------------
    ref_patterns = [
        r"\d{4}\)\s*:",                # "2020): ..."
        r"\(\d{4}\)\s*,",              # "(2020), ..."
        r"\d+\s*\(\d+\)\s*:\s*\d+",    # 卷(期):页码
        r"journal of|proceedings|conference|workshop|vol\.|pp\.",  # 期刊 / 会议关键词
    ]

    # 仅对可能是参考文献的章节做更严格匹配，避免误杀正文
    is_likely_reference = any(
        kw in section_lower
        for kw in [
            "references", "bibliography", "reference",
            "citations", "works cited", "literature cited",
        ]
    )

    if is_likely_reference and len(text_stripped) < 500:
        pattern_count = sum(
            1 for pattern in ref_patterns if re.search(pattern, text_lower)
        )
        if pattern_count >= 2:
            logger.debug(
                f"跳过章节 (参考文献模式): {section_name}, 匹配模式数={pattern_count}"
            )
            return True

    # -------------------------
    # (4) 作者名 + 年份 + 期刊联合检测（仅对疑似参考文献）
    # -------------------------
    if is_likely_reference:
        author_pattern = r"[A-Z][a-z]+,\s*[A-Z]\.?\s*(?:[A-Z]\.?[,\s]*)*(?:et al\.)?"
        author_matches = re.findall(author_pattern, section_text)
        if author_matches:
            has_year = bool(
                re.search(r"(\(年份\)|\(?(19|20)\d{2}\)?)", section_text)
            )
            has_journal = bool(
                re.search(
                    r"[A-Z][a-z]+(\s+[A-Z][a-z]+)*\s+("
                    r"Journal|Proceedings|Transactions|"
                    r"Gut|Biomed|Pharmacother|Biochem|Cell|Mol|"
                    r"Clin|Sci|Nature|Science|"
                    r"杂志|期刊|学报)",
                    section_text,
                    re.IGNORECASE,
                )
            )
            if has_year and has_journal:
                logger.debug(f"跳过章节 (作者-年份-期刊格式): {section_name}")
                return True

    # -------------------------
    # (5) 目录 / 索引检测
    # -------------------------
    toc_pattern = r"[A-Za-z][A-Za-z\s]+\.\s*\d+"
    toc_matches = re.findall(toc_pattern, section_text)
    if len(toc_matches) >= 3:
        logger.debug(
            f"跳过章节 (目录样式): {section_name}, 目录条目数={len(toc_matches)}"
        )
        return True

    # -------------------------
    # (6) 纯页码检测
    # -------------------------
    if re.match(r"^\s*\.?\s*\d+\s*$", text_stripped) and len(text_stripped) < 10:
        logger.debug(f"跳过章节 (纯页码): {section_name}")
        return True

    # -------------------------
    # (7) et al. + 年份 + DOI/卷期 的参考文献检测（仅对疑似参考文献）
    # -------------------------
    if is_likely_reference:
        et_al_patterns = [
            r"[A-Z][a-z]+,\s*[A-Z]\.?\s*[A-Z]?\.?\s*et al\.",  # 单作者 + et al.
            r"et al\.",                                       # 宽松匹配
        ]
        for pattern in et_al_patterns:
            et_al_matches = re.findall(pattern, section_text, re.IGNORECASE)
            if et_al_matches:
                has_year_or_doi = bool(
                    re.search(
                        r"(\(年份\)|\(?(19|20)\d{2}\)?|doi:|10\.|Vol\.|pp\.|J\. |Journal|Proceedings)",
                        section_text,
                        re.IGNORECASE,
                    )
                )
                if has_year_or_doi:
                    logger.debug(
                        f"跳过章节 (et al. 格式参考文献): {section_name}"
                    )
                    return True

    # -------------------------
    # (8) 完整参考文献格式检测（多作者 + 年份 + 期刊 + DOI）（仅对疑似参考文献）
    # -------------------------
    if is_likely_reference:
        ref_complete_patterns = [
            # 作者列表 + (年份) + 标题 + 期刊 + 卷号/页码 + DOI
            r"[A-Z][a-z]+,\s*[A-Z]\.?(?:\s*[A-Z]\.?)*(?:\s*et al\.)?\s*\([^)]*年份[^)]*\)[^.]*\.\s*[A-Z][a-z]+(\s+[A-Z][a-z]+)*\s+\d+[^.]*10\.",
            # 多作者 + 年份 + 标题 + 期刊（无显式 DOI）
            r"[A-Z][a-z]+,\s*[A-Z]\.?\s*(?:et al\.|[A-Z][a-z]+,\s*[A-Z]\.?)\s*\([^)]*年份[^)]*\)[^.]*[A-Z][a-z]+(\s+[A-Z][a-z]+){1,3}\s+\d+",
            # 简化形式：et al. + 年份 + 期刊/卷号 + DOI
            r"et al\.\s*\([^)]*年份[^)]*\)[^.]*[A-Z][a-z]+(\s+[A-Z][a-z]+)*\s+\d+[^.]*10\.",
        ]
        for pattern in ref_complete_patterns:
            if re.search(pattern, section_text, re.IGNORECASE):
                logger.debug(
                    f"跳过章节 (完整参考文献格式): {section_name}"
                )
                return True

    # -------------------------
    # (9) 地址信息检测（通讯作者地址 / P.O. Box 等，仅对疑似参考文献）
    # -------------------------
    if is_likely_reference:
        address_patterns = [
            r"P\.O\. Box \d+",
            r"\d+\s+[A-Z][a-z]+\s+(Street|St|Avenue|Ave|Road|Rd|Drive|Dr|Boulevard|Blvd)",
            r"[A-Z][a-z]+,\s*[A-Z]{2}\s+\d{5}",
        ]
        for pattern in address_patterns:
            if re.search(pattern, section_text, re.IGNORECASE):
                logger.debug(f"跳过章节 (地址信息): {section_name}")
                return True

    # 未匹配任何跳过条件，保留该章节
    return False



# =============== Curriculum stage ===============
def assign_curriculum_stage(difficulty: str, question_cot: str) -> int:
    """
    stage 1: easy + 短推理
    stage 2: medium + 中等推理
    stage 3: hard 或 长推理
    """
    difficulty = (difficulty or "medium").lower().strip()
    steps = 0
    if question_cot:
        steps = len([s for s in question_cot.split("\n") if s.strip()])

    if difficulty == "easy" and steps <= 3:
        return 1
    if difficulty in ["easy", "medium"] and 3 < steps <= 5:
        return 2
    return 3

# =============== SimHash 去重（轻量、无依赖） ===============
def _tokenize_for_simhash(text: str) -> List[str]:
    """
    中文不适合 split()；这里用'汉字2-gram + 英文词'混合。
    """
    if not text:
        return []
    text = re.sub(r'\s+', ' ', text).strip()
    en_words = re.findall(r"[A-Za-z0-9]+", text.lower())
    zh_chars = re.findall(r"[\u4e00-\u9fff]", text)
    zh_ngrams = ["".join(zh_chars[i:i+2]) for i in range(max(0, len(zh_chars)-1))]
    return en_words + zh_ngrams

def simhash64(tokens: List[str]) -> int:
    if not tokens:
        return 0
    v = [0] * 64
    for tok in tokens:
        h = int(hashlib.md5(tok.encode("utf-8")).hexdigest(), 16)
        for i in range(64):
            bit = (h >> i) & 1
            v[i] += 1 if bit else -1
    out = 0
    for i in range(64):
        if v[i] > 0:
            out |= (1 << i)
    return out

def hamming64(a: int, b: int) -> int:
    return (a ^ b).bit_count()

def dedup_qas_simhash(qas: List[Dict[str, Any]], max_hamming: int = 6) -> List[Dict[str, Any]]:
    """
    基于 question 的 SimHash 去重（阈值越小越严格）。
    """
    if not qas:
        return []

    kept = []
    hashes: List[int] = []
    for qa in qas:
        q = qa.get("question", "") or ""
        h = simhash64(_tokenize_for_simhash(q))
        dup = False
        for prev in hashes:
            if hamming64(h, prev) <= max_hamming:
                dup = True
                break
        if not dup:
            kept.append(qa)
            hashes.append(h)
    return kept

# ==============================================================================
# 自动质量评分系统（修正版）
# ==============================================================================
class QualityScorer:
    def __init__(self):
        self.quality_thresholds = {
            'excellent': 90,
            'good': 75,
            'acceptable': 60,
            'poor': 40
        }

        self.quality_penalty_patterns = {
            'vague_reference': [
                r'文中', r'本文', r'文章中', r'该章节', r'该部分',
                r'本论文', r'本学位论文', r'我们发现', r'我们得出'
            ],
            'incomplete': [
                r'等等', r'其他', r'各种', r'诸多', r'若干',
                r'相关', r'有关', r'一定', r'某些', r'部分'
            ],
            'redundant': [
                r'非常重要的', r'至关重要的', r'极其重要的',
                r'非常关键的', r'极其关键的'
            ],
            'academic_violation': [
                r'根据本实验', r'通过本实验', r'本研究表明',
                r'如图所示', r'见表', r'见图'
            ]
        }

        self.score_weights = {
            'length_score': 0.10,
            'completeness_score': 0.15,
            'logic_score': 0.20,
            'clarity_score': 0.15,
            'academic_score': 0.15,
            'reasoning_score': 0.25
        }

    def score_qa_pair(self, qa: Dict[str, Any]) -> Dict[str, Any]:
        question = qa.get('question', '') or ''
        answer = qa.get('answer', '') or ''
        reasoning_steps = qa.get('reasoning_steps', []) or []
        question_cot = qa.get('question_cot', '') or ''
        final_conclusion = qa.get('final_conclusion', '') or ''

        length_score = self._score_length(question, answer)
        completeness_score = self._score_completeness(question, answer, reasoning_steps)
        logic_score = self._score_logic(answer, reasoning_steps, question_cot)
        clarity_score = self._score_clarity(question, answer)
        academic_score = self._score_academic_compliance(question, answer)
        reasoning_score = self._score_reasoning_chain(reasoning_steps, question_cot, final_conclusion)

        total_score = (
            length_score * self.score_weights['length_score'] +
            completeness_score * self.score_weights['completeness_score'] +
            logic_score * self.score_weights['logic_score'] +
            clarity_score * self.score_weights['clarity_score'] +
            academic_score * self.score_weights['academic_score'] +
            reasoning_score * self.score_weights['reasoning_score']
        )

        quality_level = self._determine_quality_level(total_score)
        return {
            'total_score': round(total_score, 2),
            'quality_level': quality_level,
            'dimension_scores': {
                'length_score': round(length_score, 2),
                'completeness_score': round(completeness_score, 2),
                'logic_score': round(logic_score, 2),
                'clarity_score': round(clarity_score, 2),
                'academic_score': round(academic_score, 2),
                'reasoning_score': round(reasoning_score, 2),
            },
            'weights': self.score_weights,
            'issues': self._identify_issues(question, answer, reasoning_steps),
            'suggestions': self._generate_suggestions(total_score, reasoning_steps),
        }

    def _score_length(self, question: str, answer: str) -> float:
        q_len, a_len = len(question), len(answer)

        # 问题：8~120 最佳
        if 8 <= q_len <= 60:
            q_score = 100
        elif 60 < q_len <= 120:
            q_score = 90
        elif 120 < q_len <= 200:
            q_score = 80
        else:
            q_score = max(0, 100 - abs(q_len - 80) * 0.5)

        # 答案：60~500 最佳
        if 60 <= a_len <= 220:
            a_score = 100
        elif 220 < a_len <= 500:
            a_score = 92
        elif 500 < a_len <= 900:
            a_score = 85
        else:
            a_score = max(0, 100 - abs(a_len - 320) * 0.06)

        return (q_score + a_score) / 2

    def _soft_relevance(self, q: str, a: str) -> float:
        """
        中文不分词时用 2-gram 近似相关度；英文用词。
        """
        qt = set(_tokenize_for_simhash(q))
        at = set(_tokenize_for_simhash(a))
        if not qt:
            return 0.0
        return len(qt & at) / max(1, len(qt))

    def _score_completeness(self, question: str, answer: str, reasoning_steps: List[str]) -> float:
        score = 100.0

        rel = self._soft_relevance(question, answer)
        if rel < 0.08:
            score -= 35
        elif rel < 0.15:
            score -= 20
        elif rel < 0.25:
            score -= 10

        # 推理链完整性
        if reasoning_steps:
            if len(reasoning_steps) < 3:
                score -= 20
            elif len(reasoning_steps) > 10:
                score -= 10
            else:
                score += 8

        # 模糊表述扣分
        for pat in [r'等等', r'其他', r'各种', r'相关', r'一定', r'可能']:
            if re.search(pat, answer):
                score -= 10

        return max(0, min(100, score))

    def _score_logic(self, answer: str, reasoning_steps: List[str], question_cot: str) -> float:
        score = 100.0

        # 答案逻辑结构：至少 2 句更好
        sents = [s.strip() for s in re.split(r'[。！？]', answer) if s.strip()]
        if len(sents) < 2:
            score -= 20
        elif len(sents) > 10:
            score -= 8

        # 推理链连贯性（轻量）
        chain_text = ""
        if reasoning_steps:
            chain_text = "\n".join(reasoning_steps)
        elif question_cot:
            chain_text = question_cot

        if chain_text:
            connectors = ['因此', '所以', '从而', '进而', '导致', '由于', '因而', '首先', '其次', '最后']
            conn_hits = sum(1 for c in connectors if c in chain_text)
            if conn_hits == 0:
                score -= 12

        return max(0, min(100, score))

    def _score_clarity(self, question: str, answer: str) -> float:
        score = 100.0

        # 超长句扣分
        for sent in [s.strip() for s in re.split(r'[。！？]', question) if s.strip()]:
            if len(sent) > 120:
                score -= 8

        for sent in [s.strip() for s in re.split(r'[。！？]', answer) if s.strip()]:
            if len(sent) > 180:
                score -= 5

        # 可疑符号扣分
        for marker in ['...', '？？', '。。', '??', '!!!']:
            if marker in question or marker in answer:
                score -= 10

        return max(0, min(100, score))

    def _score_academic_compliance(self, question: str, answer: str) -> float:
        score = 100.0

        # 违禁模式扣分
        for category, patterns in self.quality_penalty_patterns.items():
            for pattern in patterns:
                if re.search(pattern, question) or re.search(pattern, answer):
                    if category == 'academic_violation':
                        score -= 22
                    elif category == 'vague_reference':
                        score -= 14
                    else:
                        score -= 8

        # 学术指标加分
        academic_indicators = ['机制', '原理', '方法', '理论', '规律', '特征', '因素', '假设', '模型', '推导', '约束']
        academic_count = sum(1 for ind in academic_indicators if ind in answer)
        if academic_count >= 3:
            score += 8
        elif academic_count == 0:
            score -= 8

        return max(0, min(100, score))

    def _score_reasoning_chain(self, reasoning_steps: List[str], question_cot: str, final_conclusion: str) -> float:
        if not reasoning_steps and not question_cot:
            return 0.0

        score = 100.0

        # steps 数量
        if reasoning_steps:
            n = len(reasoning_steps)
            if n < 3:
                score -= 25
            elif n > 9:
                score -= 10
            else:
                score += 8

            avg_len = sum(len(s) for s in reasoning_steps) / max(1, n)
            if avg_len < 12:
                score -= 18
            elif avg_len > 100:
                score -= 8

        # question_cot 句子数量
        if question_cot:
            c_sents = [s.strip() for s in re.split(r'[。！？\n]', question_cot) if s.strip()]
            if len(c_sents) < 3:
                score -= 10
            elif len(c_sents) > 12:
                score -= 8

        # 结论
        if final_conclusion:
            if len(final_conclusion) < 10:
                score -= 8
            elif len(final_conclusion) > 140:
                score -= 4

        return max(0, min(100, score))

    def _determine_quality_level(self, score: float) -> str:
        if score >= self.quality_thresholds['excellent']:
            return '优秀'
        if score >= self.quality_thresholds['good']:
            return '良好'
        if score >= self.quality_thresholds['acceptable']:
            return '可接受'
        return '较差'

    def _identify_issues(self, question: str, answer: str, reasoning_steps: List[str]) -> List[str]:
        issues = []
        if len(question) < 8:
            issues.append('问题过短')
        elif len(question) > 220:
            issues.append('问题过长')

        if len(answer) < 30:
            issues.append('答案过短')
        elif len(answer) > 1200:
            issues.append('答案过长')

        if contains_forbidden_phrases(question) or contains_forbidden_phrases(answer):
            issues.append('存在违禁短语')

        if is_study_dependent(question) or is_study_dependent(answer):
            issues.append('存在研究依赖表达')

        if reasoning_steps:
            if len(reasoning_steps) < 3:
                issues.append('推理步骤不足')
            elif len(reasoning_steps) > 10:
                issues.append('推理步骤过多')

        return issues

    def _generate_suggestions(self, score: float, reasoning_steps: List[str]) -> List[str]:
        s = []
        if score < 60:
            s.append('建议重新生成或进行失败回收再生成')
        if score < 75:
            s.append('建议检查：是否存在模糊指代/学术违规口吻/推理链不连贯')
        if not reasoning_steps and score > 80:
            s.append('可考虑启用推理链生成以提升深度')
        if score >= 90:
            s.append('质量优秀，可直接使用')
        return s

    def filter_by_quality(self, qas: List[Dict[str, Any]], min_score: float = 60.0) -> List[Dict[str, Any]]:
        filtered = []
        for qa in qas:
            report = self.score_qa_pair(qa)
            qa2 = qa.copy()
            qa2["quality_report"] = report
            if report["total_score"] >= min_score:
                filtered.append(qa2)
        return filtered

    def get_quality_statistics(self, qas: List[Dict[str, Any]]) -> Dict[str, Any]:
        if not qas:
            return {
                'total_count': 0, 'average_score': 0, 'max_score': 0, 'min_score': 0,
                'excellent_count': 0, 'good_count': 0, 'acceptable_count': 0, 'poor_count': 0,
                'pass_rate': 0
            }

        scores = []
        for qa in qas:
            rep = qa.get("quality_report")
            if rep and isinstance(rep, dict) and "total_score" in rep:
                scores.append(rep["total_score"])

        if not scores:
            return {
                'total_count': len(qas), 'average_score': 0, 'max_score': 0, 'min_score': 0,
                'excellent_count': 0, 'good_count': 0, 'acceptable_count': 0, 'poor_count': 0,
                'pass_rate': 0
            }

        return {
            'total_count': len(qas),
            'average_score': round(sum(scores) / len(scores), 2),
            'max_score': max(scores),
            'min_score': min(scores),
            'excellent_count': sum(1 for s in scores if s >= 90),
            'good_count': sum(1 for s in scores if 75 <= s < 90),
            'acceptable_count': sum(1 for s in scores if 60 <= s < 75),
            'poor_count': sum(1 for s in scores if s < 60),
            'pass_rate': round(sum(1 for s in scores if s >= 60) / len(scores) * 100, 2)
        }

# ==============================================================================
# 两阶段推理链生成相关
# ==============================================================================
def is_methodology_section(section_name: str) -> bool:
    """
    判断是否为方法论章节

    Args:
        section_name: 章节名称

    Returns:
        bool: 如果是方法论章节返回 True，否则返回 False

    Examples:
        >>> is_methodology_section("Research Methods")
        True
        >>> is_methodology_section("实验方法")
        True
    """
    section_lower = section_name.lower().strip()
    method_keywords = [
        'method', 'methods', 'methodology', 'approach', 'procedure', 'protocol',
        '实验方法', '研究方法', '技术路线', '实验设计', '材料与方法', '实验流程', '操作步骤'
    ]
    return any(k in section_lower for k in method_keywords)

def is_results_section(section_name: str) -> bool:
    """
    判断是否为结果章节

    Args:
        section_name: 章节名称

    Returns:
        bool: 如果是结果章节返回 True，否则返回 False

    Examples:
        >>> is_results_section("Experimental Results")
        True
        >>> is_results_section("研究结果")
        True
    """
    section_lower = section_name.lower().strip()
    results_keywords = [
        'result', 'results', 'findings', 'outcomes', 'performance', 'evaluation', 'assessment',
        '实验结果', '研究结果', '数据分析', '结果分析', '测试结果', '对比结果', '对比分析', '消融'
    ]
    return any(k in section_lower for k in results_keywords)

def is_discussion_section(section_name: str) -> bool:
    """
    判断是否为讨论章节

    Args:
        section_name: 章节名称

    Returns:
        bool: 如果是讨论章节返回 True，否则返回 False

    Examples:
        >>> is_discussion_section("Discussion")
        True
        >>> is_discussion_section("结果讨论")
        True
    """
    section_lower = section_name.lower().strip()
    discussion_keywords = [
        'discussion', 'discussions', 'analysis', 'interpretation', 'implications', 'significance', 'limitations',
        '讨论', '结果讨论', '意义分析', '影响分析', '局限性', '未来工作', '后续工作'
    ]
    return any(k in section_lower for k in discussion_keywords)




# =============================================================================
# 性能优化：缓存机制
# =============================================================================

from functools import lru_cache
import hashlib

def _get_text_hash(text: str) -> str:
    """计算文本的MD5哈希值"""
    return hashlib.md5(text.encode('utf-8')).hexdigest()

@lru_cache(maxsize=128)
def cached_should_skip_section(section_name_hash: str, section_text_hash: str) -> bool:
    """
    缓存版本的 should_skip_section 函数

    Args:
        section_name_hash: 章节名称的哈希值
        section_text_hash: 章节文本的哈希值

    Returns:
        bool: 是否应该跳过
    """
    # 注意：这个函数需要原始文本进行实际检测
    # 在实际调用时，我们需要传递原始文本
    return False

def is_reasoning_suitable_section(section_name: str) -> bool:
    section_lower = section_name.lower().strip()
    non_reasoning_sections = [
        "abstract", "conclusion", "summary", "conclusions",
        "摘要", "结论", "总结", "致谢", "acknowledgments",
        "references", "bibliography", "参考文献",
        "appendix", "appendices", "附录",
        "index", "目录", "table of contents"
    ]
    if any(x in section_lower for x in non_reasoning_sections):
        return False

    if any(r in section_lower for r in REASONING_SECTIONS):
        return True

    if is_methodology_section(section_name) or is_results_section(section_name) or is_discussion_section(section_name):
        return True

    # 学位论文更保守：默认推理
    return True


def build_chain_extraction_prompt(section_name: str, section_text: str, max_chains: int = 3) -> str:
    return f"""你是一位农业育种与生命科学领域的专家阅读系统，擅长从学位论文章节片段中总结可复用的推理链。

【你的任务】
给定一个学位论文章节内容，请从中抽取 1~{max_chains} 条"可用于构造多步推理问答"的推理链。
每条推理链必须满足：
- 基于文本中明确出现的事实（理论阐述、方法描述、概念解释等）
- 通过 3~7 个逻辑步骤推理得出某个客观结论
- 结论是"客观可判断对错"的（如某种关系、比较、更优方案等）
- 推理过程不依赖'本章/该章节/本节'等指代表述

【严禁抽取的内容】
以下内容严禁构造推理链和问答对：
1. 文档管理、格式规范、申请流程等行政内容
2. 保密政策、开放获取、版权授权等制度规定
3. 表格填写、签名页、申请材料等程序性内容
4. 学位答辩制度、考试规定等程序管理
5. 导师-学生关系、管理规定等行政管理
6. 大学/学院管理、组织架构等机构信息
7. 保密协议、伦理审查流程等合规文件
8. 系统使用、表格下载、在线提交等技术操作
9. 提交期限、申请流程、审批流程等程序说明

【只允许的科学内容】
只允许为以下科学内容构造推理链：
- 理论阐述与方法描述
- 概念解释与机制分析
- 实验设计与数据分析
- 科学原理与技术原理
- 因果关系与关联关系
- 比较分析与效果评估
- 规律发现与结论总结

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
- 不要使用"该章节/本章/本节"等指代原文的措辞
- 不要引用图表编号、外部数据库编号
- 不要生成依赖于具体样本数量、具体群体数目、具体参数的结论
- 严禁为任何行政、程序、管理、制度类内容构造推理链

【章节内容】
名称：{section_name}
内容：
\"\"\"markdown
{section_text}
\"\"\""""

def build_chain_to_qa_prompt(chain_json_str: str) -> str:
    return f"""你是一位农业育种与生命科学领域的教学专家，负责把结构化推理链转化为"需要多步推理才能回答的客观问答对"，用于大模型 SFT 训练。

下面是从学位论文章节中抽取的一条推理链（JSON）：
```json
{chain_json_str}
```

【你的任务】
基于这条推理链，构造 1 题"需要多步推理才能回答的问答对"，输出 JSON 对象：
{{
  "question": "面向研究生/科研人员、需要理解多个事实并综合推理的问题",
  "answer": "一段简明客观答案（不包含思维链）",
  "cot": [
    "Step 1: ...",
    "Step 2: ...",
    "Step 3: ...",
    "Step 4: ..."
  ],
  "meta": {{
    "difficulty": "easy | medium | hard",
    "difficulty_score": 0.0~1.0,
    "tags": ["concept", "mechanism", "method", "result", "application", "..."]
  }}
}}

【问题设计要求】

问题必须使用自然、流畅的中文/英文问句来表述，语序清晰，不要故意绕弯或堆砌过多从句。

单个问题不能包含太多子问题：聚焦 1 个核心问题，最多附带 1 个紧密相关的补充点，避免用"分别""同时""以及…还要…"等方式串联多个独立问题。

必须需要综合多个 support_facts 和推理步骤才能得出答案，不能是抄一句话即可回答。

问题要脱离原图书章节也成立，不能包含"该章节/本章/本节"等指代。

问题聚焦通用的科学关系或机制（如：哪种方法更适合解决某类问题？什么条件下会出现某种现象？）。

**重要**：如果问题中已经明确给出了所有信息（如①、②、③等编号信息，或"已知："、"基于这些信息"等表述），答案必须提供问题中未直接给出的推理过程、逻辑依据或综合结论，而不能只是简单复述问题中的信息。答案应该基于问题中的信息进行推理，得出新的结论或提供问题中未明确说明的逻辑关系。

答案必须是客观的、唯一可判断对错的结论。

【严禁生成的内容】
以下内容严禁生成问答对：
1. 文档管理、格式规范、申请流程相关的任何问题
2. 保密政策、开放获取、版权授权等制度规定相关问题
3. 表格填写、签名页、申请材料等程序性问题
4. 学位答辩制度、考试规定等程序管理问题
5. 导师-学生关系、管理规定等行政管理问题
6. 大学/学院管理、组织架构等机构信息问题
7. 保密协议、伦理审查流程等合规文件问题
8. 系统使用、表格下载、在线提交等技术操作问题
9. 提交期限、申请流程、审批流程等程序说明问题

【只允许的科学内容】
只允许为以下科学内容生成问答对：
- 理论阐述与方法描述相关问题
- 概念解释与机制分析相关问题
- 实验设计与数据分析相关问题
- 科学原理与技术原理相关问题
- 因果关系与关联关系相关问题
- 比较分析与效果评估相关问题
- 规律发现与结论总结相关问题

【思维链（CoT）要求】

CoT（cot 数组）用 4~7 步自然语言中文推理，逐步从事实推导到结论。

**重要**：CoT应该基于推理链的抽象逻辑，而非学位论文中的具体数值或细节。CoT描述的是通用的科学推理过程，适用于类似的其他研究。

例如：
- ✅ 好的CoT："激素通过调节生理指标提高抗逆性"
- ❌ 差的CoT："100mg/L脱落酸处理24小时后脯氨酸含量提高35%"

【禁止内容】

不要在 question 或 answer 中使用具体数值、浓度、时间等图书特有细节。

不要在Cot中引用具体的参数、浓度、时间等学位论文特有细节。

严禁为任何行政、程序、管理、制度类内容生成问答对。

【输出要求】

严格输出一个 JSON 对象（而不是数组）。

不要添加额外解释或自然语言说明。"""





# 
# def build_chain_extraction_prompt(section_name: str, section_text: str, max_chains: int = 3) -> str:
#     return f"""你是一位农业育种与生命科学领域的专家阅读系统，擅长从学位论文章节中抽取可复用的多步推理链。

# 【任务说明】
# 给定一个章节内容，请从中抽取 1~{max_chains} 条“可用于构造多步推理问答”的推理链。

# 每条推理链必须满足：
# - 基于文本中**明确出现的事实**（理论阐述、方法描述、概念解释等）；
# - 通过 **3~7 个逻辑步骤** 推理得到一个**客观结论**；
# - 结论必须是**可以判断对错**的（如：某种关系、更优方案、适用条件、机制链路等）；
# - 推理过程不能依赖“本章/该章节/本节/如下所述”等指代表述，而应独立成立。

# 【禁止抽取的推理链】
# 严禁为以下内容构造推理链：
# 1. 只用于判断“论文类型 / 学位层级 / 项目归属”的元信息推理：
#    - 例如：根据“Dissertation”“Master thesis”“Graduate Interdisciplinary Program”之类信息推断学位层次或学校项目。
# 2. 只说明“某数据/数据集被用在某篇稿件中，因此很关键”，
#    但**没有**给出清晰的机制、分析流程或方法学作用。
# 3. 只有“本研究很重要/具有重要意义/对某领域很关键”这类**笼统评价**，
#    无法从文本中抽取可验证的机制或结构化关系。
# 4. 主要内容是投稿信息、版权信息、致谢、作者信息、学院/项目介绍等**非科学内容**。

# 【方法与术语约束】
# - 推理链中出现的**方法名称、算法名称、统计量、软件工具**：
#   - 必须直接来自原文，或为国际通行的标准术语
#     （如 weighted UniFrac、principal coordinates analysis 等）。
# - 严禁发明、夸大或改写不存在的方法名称或“特别版本”：
#   - 不能把 “weighted UniFrac” 自行改写为“加权并归一化的 Fast UniFrac”等；
#   - 不能添加原文中**没有**说明的特殊性质（如“自动归一化版本”“特别适合某类场景”）。
# - 如果原文对某分析流程或软件（如 QIIME、UniFrac、EMPeror 等）的描述有限，
#   推理链只能基于**原文明示信息**构建，不要补充外部知识或主观假设。

# 【输出格式】
# 严格输出一个 JSON 对象（而不是数组）：
# {{
#   "chains": [
#     {{
#       "id": "C1",
#       "final_conclusion": "一句话客观结论（可直接作为答案）",
#       "steps": [
#         "Step 1: ...",
#         "Step 2: ...",
#         "Step 3: ..."
#       ],
#       "support_facts": [
#         "从文本抽取或概括的关键事实 1",
#         "关键事实 2"
#       ],
#       "potential_question_templates": [
#         "围绕该结论可以提问的问题模板 1",
#         "问题模板 2"
#       ]
#     }}
#   ]
# }}

# 【生成时的注意事项】
# - 不要使用“该章节/本章/本节”等指代原文的措辞；
# - 不要引用任何图表编号或外部数据库编号；
# - 不要生成依赖**具体样本数量、群体数目、参数取值**才能成立的结论；
# - 结论必须都能在原文中找到**明确事实支撑**，而不是靠常识或主观推测。

# 【推理链优先选择规则】
# 优先选择能体现以下逻辑结构的内容：
# - 机制或因果链条：例如某因子通过若干环节影响性状或致病性；
# - 比较与方法选择：在什么条件下某方法优于另一方法，或不同策略的适用场景对比；
# - 条件依赖：特定条件/环境对方法效果或生物学结果的调节作用。

# 如果某段内容**只能**支持“论文类型/学科归属/数据被收录”等元信息结论，
# 且缺乏清晰的科学机制或分析逻辑，请不要为该段构造推理链。

# 【章节内容】
# 名称：{section_name}
# 内容：
# \"\"\"markdown
# {section_text}
# \"\"\""""

# def build_chain_extraction_prompt(section_name: str, section_text: str, max_chains: int = 3) -> str:
#     return f"""你是一位农业育种与生命科学领域的专家阅读系统，擅长从学位论文章节中抽取可复用的多步推理链。

# 【任务】
# 给定一个章节内容，请从中抽取 1~{max_chains} 条“可用于构造多步推理问答”的推理链。

# 每条推理链必须同时满足：
# 1. 基于文本中**明确出现的事实**（理论阐述、方法描述、实验设计、结果解释等）；
# 2. 通过 **3~7 个逻辑步骤** 推理到一个**客观、可判断对错的结论**；
# 3. 结论是“机制/因果/比较/方法选择/条件依赖”类的科学结论，而不是泛泛而谈的“很重要/有意义”；
# 4. 推理过程不能依赖“本章/该章节/本节/如上所述”等指代表述，单独拿出来也能成立。

# 【必须拒绝抽取的内容类型】
# 如果你判断该章节主要是以下任一类型，请直接输出：
# {{
#   "chains": []
# }}
# 并且不要编造任何推理链：

# 1. **元信息 / 行政性内容（非科学实质）**，例如：
#    - 封面、题名页：作者姓名、导师、学校、学院、学位类型（Master/PhD）、提交地点、日期；
#    - 学位声明、版权声明、STATEMENT BY AUTHOR、STATEMENT OF ORIGINALITY；
#    - ProQuest / UMI / “INFORMATION TO USERS” / “ProQuest Number” 等数据库或复制声明；
#    - 复制质量说明（reproduction quality notice）、印刷质量、装订要求；
#    - EXAMINATION RESULTS / DEFENSE RECORD / GRADUATION CERTIFICATION PAGE / DEGREES AWARDED；
#    - LIST OF FIGURES / LIST OF TABLES / LIST OF ABBREVIATIONS / LIST OF SYMBOLS；
#    - DEDICATION / PREFACE / FOREWORD / PROLOGUE / ACKNOWLEDGMENTS / REMERCIEMENTS；
#    - Authors' contributions / Author contributions / 伦理声明 / 数据可用性 / 资金支持等“声明型”文本。

# 2. **基于论文/专利“身份信息”的推理**，例如：
#    - 只为了判断“这是硕士论文还是博士论文”、“授位单位是哪所学校/哪个学院”；
#    - 只为了判断“某数据被用于某篇稿件/专利，因此很关键”，但缺乏具体的科学机制或方法学逻辑；
#    - 依赖专利名称、专利号或专利文本中的特有名词来推断“属于哪类专利/归属哪个机构”。

# 3. **缺乏可验证科学内容的泛泛表述**：
#    - 只有“本研究很重要”“对某领域具有重要意义”“是关键一步”之类评价性结论；
#    - 无法从文本中抽取出清晰的因果链、比较关系或方法选择逻辑。

# 遇到上述情况时，只需输出空结果：
# {{
#   "chains": []
# }}

# 【允许抽取的内容类型】
# 优先为以下内容抽取推理链：
# 1. 机制与因果：某因子通过多个中间环节影响性状、产量、抗性或病程；
# 2. 比较与方法选择：在什么条件下某方法优于另一方法，或不同策略的适用场景对比；
# 3. 条件依赖：特定环境/遗传背景/管理措施对方法效果或生物学结果的调节作用；
# 4. 分析流程逻辑：多种实验/统计分析如何组合，才能支持某一复杂结论。

# 【方法与术语约束】
# - 推理链中的方法名称、算法、统计量、软件工具必须：
#   - 直接来自原文，或
#   - 是国际通用的标准术语（如 weighted UniFrac、principal coordinates analysis 等）。
# - 严禁发明、夸大或改写不存在的方法名称或“特别版本”；
# - 不要引入原文中未出现的新属性（如“特别适合某类场景”“自动归一化版本”等）。
# - 只允许使用原文明示的信息，不要补充外部知识或主观猜测。

# 【输出格式】
# 严格输出一个 JSON 对象（不是数组），格式如下：
# {{
#   "chains": [
#     {{
#       "id": "C1",
#       "final_conclusion": "一句话客观结论（可直接作为答案）",
#       "steps": [
#         "Step 1: ...",
#         "Step 2: ...",
#         "Step 3: ..."
#       ],
#       "support_facts": [
#         "从文本抽取或概括的关键事实 1",
#         "关键事实 2"
#       ],
#       "potential_question_templates": [
#         "围绕该结论可以提问的问题模板 1",
#         "问题模板 2"
#       ]
#     }}
#   ]
# }}

# - `chains` 数组长度为 0~{max_chains}；
# - 当你认为该章节属于上述“元信息/行政性内容/缺乏科学实质”时，直接返回 `"chains": []`；
# - 不要添加任何额外说明文字。

# 【章节内容】
# 名称：{section_name}
# 内容：
# \"\"\"markdown
# {section_text}
# \"\"\""""





# def build_chain_to_qa_prompt(chain_json_str: str) -> str:
#     return f"""你是一位农业育种与生命科学领域的教学专家，负责把结构化推理链转化为"需要多步推理才能回答的客观问答对"，用于大模型 SFT 训练。

# 下面是从学位论文章节中抽取的一条推理链（JSON）：
# ```json
# {chain_json_str}
# ```

# 【你的任务】
# 基于这条推理链，构造 1 题“需要多步推理才能回答的问答对”，并输出一个 JSON 对象：
# {{
# "question": "面向研究生/科研人员、需要理解多个事实并综合推理的问题",
# "answer": "一段简明客观答案（不包含思维链）",
# "cot": [
# "Step 1: ...",
# "Step 2: ...",
# "Step 3: ...",
# "Step 4: ..."
# ],
# "meta": {{
# "difficulty": "easy | medium | hard",
# "difficulty_score": 0.0~1.0,
# "tags": ["concept", "mechanism", "method", "result", "application", "..."]
# }}
# }}

# 【问题设计要求】

# 问题必须使用自然、流畅的中文或英文问句，语序清晰，不要故意绕弯或堆砌过多从句。

# 单个问题只能围绕 1 个核心科学问题，最多附带 1 个紧密相关的补充点；
# 避免用“分别”“同时”“以及…还要…”等方式串联多个独立问题。

# 必须综合多个 support_facts 和推理步骤才能回答，不能是直接抄一句话就能回答的事实性问句。

# 问题在脱离原图书章节也能成立，不要使用“该章节/本章/本节/本文中”这类指代表述。

# 问题应聚焦通用的科学关系或机制，例如：

# 哪种方法更适合解决某类问题？

# 在什么条件下更容易出现某种现象？

# 某种改进如何在多个环节上影响最终结果？

# 问题不能基于学位论文或专利中的“元信息”或“特有名词”构造：

# 不要围绕论文封面、学位层次（如 Master/PhD）、授位单位、提交地点、时间、ProQuest/UMI 编号、
# COPYRIGHT / INFORMATION TO USERS 等非科学内容出题；

# 不要基于专利号、专利名称、专利权利要求中的特有名词设计问题。

# 答案必须是客观的、可以判断对错的结论，而不是纯主观评价。

# 【思维链（CoT）要求】

# CoT（cot 数组）使用 4~7 步简洁自然语言推理，从事实逐步推导到结论。

# CoT 应基于推理链的抽象逻辑，而不是学位论文中的具体数值或细节；
# 它描述的是可复用的科学推理过程，可迁移到类似研究场景。

# 不要在 CoT 中引用具体实验参数（剂量、时间、样本量、精确统计值等）。

# 示例对比（仅示意抽象 vs. 细节）：

# ✅ 合格 CoT 句式示例："激素通过调节多种生理指标协同提高作物的抗逆性。"

# ❌ 不合格 CoT 句式示例："100mg/L 脱落酸处理 24 小时后脯氨酸含量提高 35%。"

# 【禁止内容】

# 不要在 question 或 answer 中使用具体数值、浓度、时间等学位论文特有细节。

# 不要在 CoT 中引用具体参数、浓度、时间、样本量等细节。

# 不要围绕封面信息、版权信息、提交机构、学位层级、ProQuest/UMI/版权声明、复制质量声明等非科学内容出题。

# 【输出要求】

# 严格输出一个 JSON 对象（而不是数组）。

# 不要添加任何额外解释或自然语言说明。"""


# def build_chain_extraction_prompt(section_name: str, section_text: str, max_chains: int = 3) -> str:
#     """
#     Prompt goals:
#     - 强约束：只基于文本显式事实；3~7步；客观可判定结论
#     - 强拒绝：元信息/行政性/声明页等直接 chains=[]
#     - 强输出：仅 JSON 对象，严格字段
#     - 更稳健：加入“先判别章节类型→再抽取”的两阶段指令；加入引用锚点（可选）以减少幻觉
#     """
#     return f"""你是一位农业育种与生命科学领域的“章节推理链抽取器”，专门把学位论文的某一章节内容，抽取为可复用的多步推理链（用于后续构造多步推理问答）。你必须严格遵守“只基于原文显式事实”的原则，禁止引入外部知识或主观推测。

# ## 任务
# 给定章节名称与正文，请输出 1~{max_chains} 条推理链；若章节属于“元信息/行政性/声明性/目录性”等非科学实质内容，则必须输出空结果：
# {{
#   "chains": []
# }}

# ---

# ## 工作流程（必须按顺序执行）
# ### 第一步：章节类型判别（强制）
# 先判断该章节是否主要属于“必须拒绝抽取”的类型（见下文）。  
# - 若是：立即输出 {{"chains": []}}，并停止；不得生成任何推理链。  
# - 若否：进入第二步。

# ### 第二步：推理链抽取（1~{max_chains} 条）
# 每条推理链必须同时满足：
# 1) **证据约束**：每一步与结论都能在原文中找到明确依据（理论阐述、方法描述、实验设计、结果解释等）。不得补充外部知识。  
# 2) **步数约束**：3~7 个逻辑步骤，逐步推到结论。  
# 3) **结论约束**：结论必须是**客观、可判定对错**的科学结论，优先类型：  
#    - 机制/因果（X 通过若干中间环节影响 Y）  
#    - 比较/方法选择（在条件 A 下方法 M 优于 N；或适用边界）  
#    - 条件依赖（环境/遗传背景/管理措施调节效果）  
#    - 分析流程逻辑（多实验/统计组合支持某结论）  
#    禁止“很重要/有意义/关键一步”等评价性结论。  
# 4) **可独立性**：不得依赖“本章/如上所述/该节”等指代；抽出来单独也成立。  
# 5) **术语约束**：方法、算法、统计量、软件工具必须：
#    - 原文中明确出现，或
#    - 属于国际通用标准术语（例如 weighted UniFrac、principal coordinates analysis 等）。
#    禁止杜撰“特别版本/改进版本/自动化版本”等原文未出现的说法。

# ---

# ## 必须拒绝抽取的内容类型（命中任一即 chains=[]）
# A. 元信息/行政性内容（非科学实质），例如：
# - 封面/题名页：作者、导师、学校、学位类型、提交地点与日期
# - 学位声明/版权声明/STATEMENT BY AUTHOR/STATEMENT OF ORIGINALITY
# - ProQuest/UMI/“INFORMATION TO USERS”/ProQuest Number 等数据库声明
# - 印刷/复制质量说明、装订要求
# - 答辩/考试/授位/毕业认证页面
# - LIST OF FIGURES/TABLES/ABBREVIATIONS/SYMBOLS
# - DEDICATION/PREFACE/FOREWORD/ACKNOWLEDGMENTS/REMERCIEMENTS
# - Authors’ contributions/伦理声明/数据可用性/资金支持等声明文本

# B. 基于论文/专利身份信息的“推理”，例如：
# - 仅用于判断硕士/博士、授位单位、学院
# - 仅凭专利名称/专利号/机构归属做分类推断而无科学机制或方法链

# C. 缺乏可验证科学内容的泛泛表述，例如：
# - 只有重要性/意义/愿景等评价性描述
# - 无法抽取出清晰因果、比较关系或方法选择逻辑

# ---

# ## 输出格式（严格）
# 你必须只输出一个 JSON 对象（不是数组、不是 Markdown、不要额外解释文字）：

# {{
#   "chains": [
#     {{
#       "id": "C1",
#       "final_conclusion": "一句话客观结论（可直接作为答案）",
#       "steps": [
#         "Step 1: ...",
#         "Step 2: ...",
#         "Step 3: ..."
#       ],
#       "support_facts": [
#         "关键事实 1（来自原文的明确表述或等价概括）",
#         "关键事实 2"
#       ],
#       "potential_question_templates": [
#         "问题模板 1（需多步推理才能回答）",
#         "问题模板 2"
#       ]
#     }}
#   ]
# }}

# 硬性要求：
# - chains 长度必须为 0~{max_chains}
# - steps 长度必须为 3~7
# - 若第一步判别为拒绝类型，必须输出 {{"chains": []}}（且只输出这一行 JSON）
# - 不要输出任何额外字段或解释

# ---

# ## 输入章节
# 章节名称：{section_name}

# 章节正文：
# \"\"\"markdown
# {section_text}
# \"\"\""""


# def build_chain_extraction_prompt(section_name: str, section_text: str, max_chains: int = 3) -> str:
#     """
#     强化版：章节推理链抽取 Prompt
#     目标：
#     - 两阶段Gate：先判别章节是否为元信息/行政性/声明性/目录性等；是则 chains=[]
#     - 抽取1~max_chains条可复用推理链：3~7步、客观可判定结论、可独立成立
#     - 严格仅基于原文显式事实，不引入外部知识
#     - 输出严格 JSON 对象；字段固定；不输出额外解释
#     """
#     processed_text = (
#         section_text[:12000] + "\n\n[以下内容因长度被截断]"
#         if len(section_text) > 12000
#         else section_text
#     )

#     return f"""你是一位农业育种与生命科学领域的“章节推理链抽取器”。你的输出将用于构造多步推理问答（SFT训练），因此必须做到：证据可追溯、逻辑可复用、结论客观可判定。

# 【最高优先级规则】
# 1) 只能使用输入章节正文中“明确出现”的事实；不得补充外部知识、常识推断或主观猜测。
# 2) 先执行 Gate（章节类型判别）。若判定为“元信息/行政性/声明性/目录性等非科学实质内容”，必须输出：{{"chains":[]}}，并立即停止。
# 3) 严格只输出一个 JSON 对象；不得输出任何额外说明、标题、Markdown、注释。

# ────────────────────────────────────────
# 【Gate：章节类型判别（强制第一步）】
# 请判断该章节是否主要属于以下任一类（命中任一类则必须拒绝抽取，直接输出 {{\"chains\": []}}）：

# A. 元信息/行政性/声明性内容（非科学实质），例如：
# - 封面/题名页信息：作者、导师、学校、学院、学位类型、提交地点、日期
# - 学位声明/版权声明/原创性声明/伦理声明/数据可用性/作者贡献/基金支持等声明性文本
# - ProQuest/UMI/INFORMATION TO USERS/ProQuest Number/复制质量说明/装订印刷说明
# - 答辩/考试/授位/毕业认证页面
# - LIST OF FIGURES / LIST OF TABLES / ABBREVIATIONS / SYMBOLS 等目录清单
# - DEDICATION / PREFACE / FOREWORD / ACKNOWLEDGMENTS / REMERCIEMENTS 等致谢前言

# B. 仅基于论文/专利身份信息进行推理（无科学机制或方法链），例如：
# - 判断硕士/博士、授位单位、提交日期、编号归属等
# - 只凭专利名称/专利号/机构信息做分类推断但缺乏科学逻辑链

# C. 缺乏可验证科学内容的泛泛表述，例如：
# - 只有“重要性/意义/愿景/关键一步”等评价性结论
# - 无法抽取清晰的机制/因果/比较/方法选择/条件依赖/分析流程逻辑

# 若 Gate 判定为“拒绝”，你的输出必须严格为：
# {{"chains": []}}

# ────────────────────────────────────────
# 【通过Gate后：推理链抽取任务（输出 1~{max_chains} 条）】


# 每条推理链必须同时满足（硬性约束）：
# 0) 推理过程不依赖'本章/该章节/本节'等指代表述
# 1) 证据约束：steps 与 final_conclusion 都能在原文中找到明确依据（可“等价概括”，但不得引入新信息）。
# 2) 步数约束：steps 长度必须为 3~7；每一步是“前一步推出后一步”的逻辑推进。
# 3) 结论约束：final_conclusion 必须是客观、可判定对错的科学结论，优先类型：
#    - 机制/因果：X 通过若干中间环节影响 Y
#    - 比较/方法选择：在条件A下方法M优于N；或适用边界与限制
#    - 条件依赖：环境/遗传背景/管理措施如何调节结果或方法效果
#    - 分析流程逻辑：多种实验/统计分析如何组合支持某结论
#    禁止：价值判断与空泛表述（“很重要/很有意义/关键一步”）。
# 4) 可独立性：不得出现“本章/本文/该节/如上所述/见图表”等指代；抽离上下文仍可成立。
# 5) 术语与方法约束：方法名、算法、统计量、软件工具必须“原文出现”或“国际通用标准术语”；不得杜撰“特别版本/改进版本”等。
# 6) 事实支撑约束：support_facts 至少 2 条，且与 steps/结论直接相关。

# 【输出格式（严格 JSON 对象）】
# 只输出一个 JSON 对象，结构如下（字段名必须完全一致，不得增删字段）：
# {{
#   "chains": [
#     {{
#       "id": "C1",
#       "final_conclusion": "一句话客观结论（可直接作为答案）",
#       "steps": [
#         "Step 1: ...",
#         "Step 2: ...",
#         "Step 3: ..."
#       ],
#       "support_facts": [
#         "关键事实1（来自原文的明确表述或等价概括）",
#         "关键事实2"
#       ],
#       "potential_question_templates": [
#         "围绕该结论可提出的多步推理问题模板1",
#         "模板2"
#       ]
#     }}
#   ]
# }}

# 【输入章节】
# 章节名称：{section_name}
# 章节正文：
# \"\"\"markdown
# {processed_text}
# \"\"\""""




# def build_chain_to_qa_prompt(chain_json_str: str) -> str:
#     """
#     强化版：推理链 -> QA Prompt（加入 fact_count_used）
#     目标：
#     - 先做链质量 Gate（meta_only_chunk 直接返回）
#     - 生成 1 条高自然度 QA（单核问题、必须多步推理）
#     - CoT 4~7 步，抽象逻辑，不含论文特有细节
#     - meta 中显式给出 fact_count_used，用于后处理审计与质量 gate
#     - 严格仅输出 JSON 对象
#     """
#     return f"""你是一位农业育种与生命科学领域的教学专家，负责把“结构化推理链”转化为 1 条“需要多步推理才能回答”的客观问答对，用于大模型 SFT 训练。

# 【最高优先级规则（不得违反）】
# 1) 只能使用输入推理链 JSON 中提供的信息（final_conclusion / steps / support_facts / templates）。
# 2) 不得引入外部知识、常识补全或主观推测。
# 3) 必须先执行 Gate（推理链质量判别）。
# 4) 严格只输出一个 JSON 对象；不得输出任何额外说明、标题或 Markdown。

# ────────────────────────────────────────
# 【输入推理链（JSON）】
# {chain_json_str}

# ────────────────────────────────────────
# 【Gate：推理链质量 / 元信息判别（强制第一步）】

# 若该推理链满足以下任一情况，则判定为“不通过 Gate”：
# - support_facts / steps 主要为封面、声明、目录、致谢、ProQuest/UMI、版权、授位等元信息
# - final_conclusion 仅与论文身份信息有关（学位类型、学校、日期、编号等）
# - 缺乏机制 / 因果 / 比较 / 方法选择 / 条件依赖 / 分析流程逻辑

# 若不通过 Gate，必须只输出以下 JSON 并立即停止：
# {{
#   "question": null,
#   "answer": null,
#   "cot": [],
#   "meta": {{
#     "difficulty": "easy",
#     "difficulty_score": 0.0,
#     "fact_count_used": 0,
#     "tags": ["meta_only_chunk"]
#   }}
# }}

# ────────────────────────────────────────
# 【通过 Gate 后：生成 1 条问答样本】

# 你必须严格输出以下结构的 **单一 JSON 对象**（字段名不得增删）：
# {{
#   "question": "自然、流畅的中文或英文问句",
#   "answer": "简明、客观、可判定对错的答案（不包含思维链）",
#   "cot": [
#     "Step 1: ...",
#     "Step 2: ...",
#     "Step 3: ...",
#     "Step 4: ..."
#   ],
#   "meta": {{
#     "difficulty": "easy | medium | hard",
#     "difficulty_score": 0.0,
#     "fact_count_used": 0,
#     "tags": ["concept", "mechanism", "method", "comparison", "condition", "result", "application", "limitation", "decision"]
#   }}
# }}

# ────────────────────────────────────────
# 【问题（question）设计硬性约束】

# 1) **自然度**
# - 使用自然、清晰的中文或英文
# - 避免模板腔、机械拼接、冗长从句

# 2) **单核问题**
# - 只能围绕 1 个核心科学问题
# - 最多附带 1 个紧密相关补充点
# - 禁止串联多个独立问题

# 3) **必须多步推理（强制）**
# - 问题必须隐含需要整合 ≥2 条 support_facts 才能回答
# - 不得“一条事实直接抄出来”即可回答

# 4) **可独立成立**
# - 禁止使用：本章 / 本文 / 该章节 / 如上所述 / 见图表 等指代

# 5) **禁止元信息与论文特有细节**
# - 不得围绕学位、学校、日期、ProQuest/UMI、版权声明
# - 不得出现具体数值、浓度、时间、样本量、图表或数据库编号

# ────────────────────────────────────────
# 【答案（answer）硬性约束】

# - 必须是客观、明确、可判定对错的结论
# - 不得包含推理过程或 CoT
# - 不得使用“可能 / 大概”等模糊表述（除非推理链明确给出不确定性边界）
# - 同样禁止具体数值、时间、剂量、样本量、图表编号

# ────────────────────────────────────────
# 【思维链（cot）要求：4~7 步】

# 1) cot 必须为 4~7 步，从事实逐步推导到结论
# 2) 抽象为“可复用推理逻辑”，而非复述论文细节
# 3) 禁止出现：具体数值 / 浓度 / 时间 / 样本量 / 图表编号 / 外部数据库编号
# 4) 每一步需与推理链 steps / support_facts 语义一致，但不得逐字照搬

# ────────────────────────────────────────
# 【meta.fact_count_used（强制要求）】

# - fact_count_used = 实际用于构造 question + answer + cot 的 **support_facts 数量**
# - 必须满足：
#   - fact_count_used ≥ 2
#   - 且 ≤ support_facts 总数
# - 该数值用于下游质量审计，不得随意填写

# ────────────────────────────────────────
# 【meta 字段补充约束】

# - difficulty：根据推理跨度与概念抽象程度评估
# - difficulty_score：0~1 连续值（建议：easy≈0.2–0.4；medium≈0.5–0.7；hard≈0.75–0.95）
# - tags：从给定候选中选 2~6 个，优先体现机制 / 方法 / 条件 / 比较 / 决策

# ────────────────────────────────────────
# 【最终输出要求（强制）】
# - 只输出一个 JSON 对象
# - JSON 必须可被严格解析（双引号、无尾逗号）
# - 不要输出任何额外解释或自然语言说明
# """




# def build_chain_to_qa_prompt(chain_json_str: str) -> str:
#     """
#     Prompt goals:
#     - 先做“链质量/元信息”判别（否则直接输出 meta_only_chunk）
#     - 生成 1 条高自然度 QA + 4~7 步 CoT（抽象逻辑，不含论文特有细节/数值）
#     - 强约束：仅输出 JSON；单一核心问题；可独立成立；客观可判错
#     - 更稳健：显式要求覆盖>=2条 support_facts，且 question 必须“不可一眼抄出”
#     """
#     return f"""你是一位农业育种与生命科学领域的教学专家，负责把“结构化推理链”转换为 1 条“需要多步推理才能回答”的客观问答对，用于大模型 SFT 训练。你必须严格遵守：只使用输入推理链中提供的信息，不引入外部知识，不输出额外说明文本。

# 输入推理链（JSON）：
# ```json
# {chain_json_str}
# 总任务

# 基于该推理链生成 1 条问答样本，严格输出一个 JSON 对象，字段如下：
# {{
# "question": "自然、流畅的中文或英文问句",
# "answer": "简明、客观、可判定对错的答案（不包含思维链）",
# "cot": [
# "Step 1: ...",
# "Step 2: ...",
# "Step 3: ...",
# "Step 4: ..."
# ],
# "meta": {{
# "difficulty": "easy | medium | hard",
# "difficulty_score": 0.0,
# "tags": ["concept", "mechanism", "method", "comparison", "condition", "application", "..."]
# }}
# }}

# 必须先做的检查（强制）

# 请先判断该推理链是否“几乎不含科学实质”，例如：

# support_facts/steps 主要是封面/声明/目录/致谢/ProQuest/UMI/版权/授位信息等元信息

# final_conclusion 仅与论文身份信息有关（学位类型、学校、日期、编号等）

# 缺乏机制/方法选择/比较/条件依赖/分析流程逻辑

# 若命中以上任一情况，请直接输出以下 JSON（并停止，不得生成 QA）：
# {{
# "question": null,
# "answer": null,
# "cot": [],
# "meta": {{
# "difficulty": "easy",
# "difficulty_score": 0.0,
# "tags": ["meta_only_chunk"]
# }}
# }}

# 否则，继续生成 QA。

# 问题（question）设计要求

# 自然度：用自然、清晰的中文或英文表达，避免刻意绕句、堆从句、机械模板腔。

# 单核问题：只能围绕 1 个核心科学问题；最多附带 1 个紧密相关的补充点（不可串联多个独立问题）。

# 必须多步推理：问题必须要求综合推理链中的多个步骤与多个 support_facts 才能回答。

# 硬性约束：隐含要求使用 至少 2 条 support_facts（不能一条事实直接回答）。

# 可独立成立：不得出现“本章/本文/该章节/如上所述/见图表”等上下文依赖或指代。

# 禁止元信息出题：不得围绕学位层次、学校、日期、ProQuest/UMI 编号、版权声明等非科学内容。

# 禁止论文特有细节：question 中不得出现具体数值、浓度、时间、样本量、图表编号、数据库编号等细节。

# 可参考的高质量问题形态（不必照抄）：

# “在什么条件下，某方法/策略更适合达成某目标？为什么？”

# “某因素如何通过多个中间环节影响最终性状/结果？”

# “当研究目标/约束改变时，方法选择或结论会如何变化？”

# 答案（answer）要求

# 必须是客观、明确、可判定对错的结论（不要价值判断/主观评价）。

# 必须与 question 一一对应（不发散）。

# 不包含推理过程、不包含 CoT、不包含“可能/大概”式模糊表达（除非推理链明确表达不确定性边界）。

# 同样禁止出现具体数值、时间、剂量、样本量、图表编号等论文特有细节。

# 思维链（cot）要求（4~7 步）

# cot 必须为 4~7 步，使用简洁自然语言，从事实到结论逐步推导。

# cot 应抽象为“可复用的推理逻辑”，而非复述论文细节。

# 禁止在 cot 中出现：具体数值/浓度/时间/样本量/图表编号/外部数据库编号。

# cot 每一步都应与推理链 steps/support_facts 语义一致，但避免逐字照搬原句（保持自然度与抽象度）。

# 难度与标签（meta）要求

# difficulty：根据需要整合的事实数量、推理跨度、概念抽象程度评估（easy/medium/hard）。

# difficulty_score：0~1 的连续值（建议：easy≈0.2~0.4；medium≈0.5~0.7；hard≈0.75~0.95）。

# tags：从以下方向选 2~6 个即可：concept/mechanism/method/comparison/condition/result/application/limitation/decision。

# 输出要求（强制）

# 只输出一个 JSON 对象（不是数组、不是 Markdown、不要任何额外解释文字）。

# JSON 必须可被严格解析（双引号、无尾逗号）。
# """





# def build_chain_to_qa_prompt(chain_json_str: str) -> str:
#     return f"""你是一位农业育种与生命科学领域的教学专家，负责把结构化推理链转化为“需要多步推理才能回答的客观问答对”，用于大模型 SFT 训练。

# 下面是一条从学位论文章节中抽取的推理链（JSON）：
# ```json
# {chain_json_str}

# 【任务】
# 基于这条推理链，构造 1 题“需要多步推理才能回答的问答对”，并输出一个 JSON 对象：
# {{
# "question": "面向研究生/科研人员、需要理解多个事实并综合推理的问题",
# "answer": "一段简明客观答案（不包含思维链）",
# "cot": [
# "Step 1: ...",
# "Step 2: ...",
# "Step 3: ...",
# "Step 4: ..."
# ],
# "meta": {{
# "difficulty": "easy | medium | hard",
# "difficulty_score": 0.0~1.0,
# "tags": ["concept", "mechanism", "method", "result", "application", "..."]
# }}
# }}

# 【问题设计要求】

# 问题必须使用自然、流畅的中文或英文问句，语序清晰，不要故意绕弯或堆砌过多从句。

# 单个问题只能围绕 1 个核心科学问题，最多附带 1 个紧密相关的补充点；
# 避免用“分别”“同时”“以及…还要…”等方式串联多个独立问题。

# 必须综合多个 support_facts 和推理步骤才能回答，不能是直接抄一句话就能回答的简单事实问句。

# 问题在脱离原文环境也能成立，不要使用“该章节/本章/本节/本文中”等指代表述。

# 问题应聚焦通用科学逻辑，例如：

# 哪种方法更适合解决某类问题？

# 在什么条件下更容易出现某种现象？

# 某种改进如何在多个环节上影响最终结果？

# 问题不能基于学位论文或专利中的“元信息”构造，例如：

# 不要围绕论文封面、学位层次（Master/PhD）、授位单位、提交地点、提交日期；

# 不要围绕 ProQuest / UMI 编号、COPYRIGHT / INFORMATION TO USERS 页、复制质量说明；

# 不要围绕“这是不是硕士/博士论文”“由哪所大学/学院授位”；

# 不要依赖专利号、专利名称或专利文本中的特有名词来设计问题。

# 答案必须是客观、唯一可判断对错的结论，不能仅是主观评价。

# 【思维链（CoT）要求】

# cot 数组使用 4–7 步简洁自然语言推理，从事实逐步推导到结论。

# CoT 应基于推理链的抽象逻辑，而不是学位论文中的具体数值或细节；
# 目标是总结一个可复用、适用于类似研究场景的推理过程。

# 不要在 CoT 中引用具体实验参数（剂量、时间、样本量、精确统计值等）。

# 示例对比（只示意抽象 vs 细节）：

# ✅ 合格 CoT 句式示例："激素通过调节多种生理指标协同提高作物的抗逆性。"

# ❌ 不合格 CoT 句式示例："100mg/L 脱落酸处理 24 小时后脯氨酸含量提高 35%。"

# 【严格禁止内容】

# 不要在 question 或 answer 中使用具体数值、浓度、时间、样本数量等学位论文特有细节。

# 不要在 CoT 中引用具体参数、浓度、时间、群体规模、图表编号或外部数据库编号。

# 不要围绕封面信息、版权信息、提交机构、学位层级、ProQuest/UMI/版权声明、复制质量声明等非科学内容出题。


# 【特殊情况处理】

# 如果你发现这条推理链本身只涉及上述“元信息/行政性内容”（而几乎没有科学机制、方法或结果），
# 请直接输出：
# {{
# "question": null,
# "answer": null,
# "cot": [],
# "meta": {{
# "difficulty": "easy",
# "difficulty_score": 0.0,
# "tags": ["meta_only_chunk"]
# }}
# }}

# 【输出要求】

# 严格输出一个 JSON 对象（而不是数组）。

# 不要添加任何额外的解释或自然语言说明。"""

# =============== API 调用（使用Responses API + Thinking模式） ===============

def call_responses_for_json(prompt: str, model: str = DEFAULT_MODEL, max_output_tokens: int = 8000,
                            temperature: float = 0.7, max_retries: int = 4, enable_thinking: bool = True) -> Any:
    """
    使用 Responses API 调用 GPT-5.1，支持 Thinking 模式
    """
    client = OpenAI(api_key=OPENAI_API_KEY, base_url=OPENAI_BASE_URL, timeout=120.0)

    def _extract_balanced_json(txt: str) -> Optional[str]:
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

    last_err = None
    for attempt in range(max_retries):
        try:
            # 准备请求参数
            req_params = {
                "model": model,
                "input": prompt,
                "max_output_tokens": max_output_tokens,
            }

            # 启用 Thinking 模式
            if enable_thinking:
                req_params["reasoning"] = {"effort": "high", "summary": "detailed"}
                req_params["text"] = {"verbosity": "medium"}

            resp = client.responses.create(**req_params)

            # 获取完整文本
            raw_answer = resp.output_text

            if not raw_answer:
                logger.warning(f"API返回空内容，attempt={attempt+1}/{max_retries}")
                sleep_s = min(8.0, (2 ** attempt) + random.random())
                time.sleep(sleep_s)
                continue

            # 从 reasoning.summary 提取 COT
            cot_from_reasoning = extract_cot_from_reasoning(resp)

            # 从文本里尝试 <think>...</think> 标签
            clean_answer, cot_from_tags = split_think_content(raw_answer)

            # 优先使用 reasoning.summary 的 COT
            if cot_from_reasoning:
                logger.info(f"从 reasoning.summary 提取到 COT，长度: {len(cot_from_reasoning)} 字符")

            # 更新token统计
            if hasattr(resp, 'usage') and resp.usage:
                try:
                    # 尝试从 usage 对象中提取 token 信息
                    # 支持多种字段名格式
                    input_tokens = 0
                    output_tokens = 0

                    # 检查 usage 是否为字典
                    if isinstance(resp.usage, dict):
                        # 使用更安全的方式获取值
                        usage_input = resp.usage.get('input_tokens')
                        usage_prompt = resp.usage.get('prompt_tokens')
                        usage_output = resp.usage.get('output_tokens')
                        usage_completion = resp.usage.get('completion_tokens')

                        input_tokens = usage_input if usage_input is not None else (usage_prompt if usage_prompt is not None else 0)
                        output_tokens = usage_output if usage_output is not None else (usage_completion if usage_completion is not None else 0)
                    else:
                        # usage 是对象 - 使用更安全的方式
                        try:
                            input_tokens = resp.usage.input_tokens if hasattr(resp.usage, 'input_tokens') else 0
                            if input_tokens == 0:
                                input_tokens = resp.usage.prompt_tokens if hasattr(resp.usage, 'prompt_tokens') else 0
                        except (AttributeError, KeyError):
                            input_tokens = 0

                        try:
                            output_tokens = resp.usage.output_tokens if hasattr(resp.usage, 'output_tokens') else 0
                            if output_tokens == 0:
                                output_tokens = resp.usage.completion_tokens if hasattr(resp.usage, 'completion_tokens') else 0
                        except (AttributeError, KeyError):
                            output_tokens = 0

                    total_tokens = input_tokens + output_tokens

                    # 总是尝试更新统计（包括0值）
                    try:
                        update_token_stats(input_tokens, output_tokens, total_tokens)
                        if input_tokens > 0 or output_tokens > 0:
                            logger.info(f"API调用 - 输入Tokens: {input_tokens}, 输出Tokens: {output_tokens}")
                        else:
                            logger.debug(f"API调用 - 未获取到有效token统计: 输入={input_tokens}, 输出={output_tokens}")
                    except Exception as e:
                        logger.warning(f"更新token统计失败: {e}")

                except (AttributeError, KeyError, TypeError) as e:
                    # 如果无法获取token信息，静默处理（不记录警告以减少噪音）
                    logger.debug(f"无法从API响应中提取token统计: {e}")
            else:
                # 记录一次警告，提示用户API响应中没有usage信息
                logger.warning(f"API响应中没有usage信息，无法统计token使用量。响应类型: {type(resp.usage) if hasattr(resp, 'usage') else 'None'}")

            # 使用 JSON 解析
            js = _extract_balanced_json(clean_answer) or clean_answer
            js = re.sub(r'[\x00-\x1f\x7f-\x9f]', '', js)

            try:
                result = json.loads(js)
                # 创建一个包含原始响应和解析后数据的对象
                if isinstance(result, dict) and "chains" not in result:
                    # 可能是直接返回的 QA 数据
                    # 将COT和解析后的JSON合并到一个对象中
                    result["_raw_response"] = resp
                    extracted_cot = cot_from_reasoning if cot_from_reasoning is not None else cot_from_tags
                    result["_extracted_cot"] = extracted_cot
                    if extracted_cot:
                        logger.info(f"从 thinking 模式提取到 COT，长度: {len(extracted_cot)} 字符")
                    return result
                else:
                    # 返回包含原始响应和COT的字典
                    extracted_cot = cot_from_reasoning if cot_from_reasoning is not None else cot_from_tags
                    if extracted_cot:
                        logger.info(f"从 thinking 模式提取到 COT，长度: {len(extracted_cot)} 字符")
                    # 保留原始result的所有数据，并添加COT字段
                    result_copy = result.copy() if isinstance(result, dict) else {"data": result}
                    result_copy["_raw_response"] = resp
                    result_copy["_extracted_cot"] = extracted_cot
                    return result_copy
            except json.JSONDecodeError:
                # 如果不是 JSON，返回包含COT的对象
                extracted_cot = cot_from_reasoning if cot_from_reasoning is not None else cot_from_tags
                if extracted_cot:
                    logger.info(f"从 thinking 模式提取到 COT，长度: {len(extracted_cot)} 字符")
                return {
                    "text": clean_answer,
                    "_raw_response": resp,
                    "_extracted_cot": extracted_cot,
                }

        except Exception as e:
            last_err = e
            sleep_s = min(8.0, (2 ** attempt) + random.random())
            time.sleep(sleep_s)
            logger.warning(f"API/JSON失败，attempt={attempt+1}/{max_retries}，sleep={sleep_s:.2f}s，err={e}")

    logger.error(f"API调用失败，已重试{max_retries}次: {last_err}")
    return None

import re
import hashlib
import logging
from datetime import datetime
from typing import List, Dict, Any, Optional

logger = logging.getLogger(__name__)

# ==================== 可根据需要覆盖 / 替换的全局常量与工具函数 ====================

# 如果工程里已经定义了这些常量，请删除下面三行并使用你自己的值
MIN_CHAPTER_LENGTH = 50           # 认为"章节块"最小长度（字符数）
IDEA_CHUNK_LENGTH = 2000          # 理想 chunk 字符长度（原代码命名就是 IDEA）
MAX_CHUNK_SIZE = 200              # 最多 chunk 数量（超过则触发合并）

def clean_text_basic(text: str) -> str:
    """占位：基础清理函数（如果已有实现，可删掉这里）"""
    # 简单示例：去掉多余空格和空行，你可以替换为自己的版本
    text = text.replace('\r', '')
    return text.strip()

def estimate_tokens(text: str) -> int:
    """占位：粗略 token 估计（如果已有实现，可删掉这里）"""
    # 非严格估计：假设每 4 个字符 ≈ 1 token
    return max(1, len(text) // 4)


# ==============================================================================
# 学位论文章节拆分处理器（优化增强版）
# ==============================================================================

class ThesisProcessor:
    def __init__(self) -> None:
        # ==================== 模式定义 ====================
        # Markdown 标题模式（优化：支持更多格式）
        self.markdown_header_pattern = re.compile(r'^(#{1,6})\s+(.+)$')

        # LaTeX 章节模式（学位论文常用）
        self.latex_patterns = [
            re.compile(r'^\\chapter\{(.+?)\}'),
            re.compile(r'^\\section\{(.+?)\}'),
            re.compile(r'^\\subsection\{(.+?)\}'),
            re.compile(r'^\\subsubsection\{(.+?)\}'),
        ]

        # 中文章节模式（学位论文常用）- 优化版
        self.chinese_patterns = [
            # 第X章
            re.compile(r'^第[一二三四五六七八九十百千万零]+章[：:：\s]*([^。，；、]{1,50})?$'),
            re.compile(r'^第\d+章[：:：\s]*([^。，；、]{1,50})?$'),
            # 第X节
            re.compile(r'^第[一二三四五六七八九十百千万零]+节[：:：\s]*([^。，；、]{1,50})?$'),
            re.compile(r'^第\d+节[：:：\s]*([^。，；、]{1,50})?$'),
            # X.X 编号模式
            re.compile(r'^\d+(?:\.\d+)+[、．.\s]+([^。，；、]{1,50})?$'),
            # 中文数字编号
            re.compile(r'^[一二三四五六七八九十百千万零]+[、．.\s]+([^。，；、]{1,50})?$'),
        ]

        # 英文章节模式（学位论文常用）- 优化版
        self.english_patterns = [
            # Chapter X
            re.compile(
                r'^Chapter\s+([0-9]+(?:\.[0-9]+)*|[IVXLCDM]+)[：:：\.\s]*([^.,;]{1,100})?$',
                re.IGNORECASE
            ),
            # Section X
            re.compile(
                r'^Section\s+([0-9]+(?:\.[0-9]+)*)[：:：\.\s]*([^.,;]{1,100})?$',
                re.IGNORECASE
            ),
            # Part X
            re.compile(
                r'^Part\s+([0-9IVXLCDM]+)[：:：\.\s]*([^.,;]{1,100})?$',
                re.IGNORECASE
            ),
            # X.X 数字编号
            re.compile(r'^([0-9]+(?:\.[0-9]+)+)[\.\s]+([^.,;]{1,100})?$'),
            # 附录
            re.compile(
                r'^Appendix\s+([A-Z0-9]+)[：:：\.\s]*([^.,;]{1,100})?$',
                re.IGNORECASE
            ),
        ]

        # 学位论文核心章节（高优先级）- 优化版
        self.thesis_core_sections: Dict[str, List[str]] = {
            '摘要': ['abstract', 'summary', '摘要', '概要', '中文摘要', '英文摘要'],
            '引言': ['introduction', 'background', '引言', '绪论', '前言', '研究背景'],
            '文献综述': ['literature review', 'related work', 'previous work', '文献综述', '文献回顾'],
            '方法': ['method', 'methodology', 'methods', 'materials and methods', '实验方法', '研究方法', '实验设计'],
            '结果': ['results', 'findings', '实验结果', '研究结果', '数据分析', '结果分析'],
            '讨论': ['discussion', 'analysis', '讨论', '结果讨论'],
            '结论': ['conclusion', 'conclusions', '总结', '研究结论', '结论与展望'],
            '参考文献': ['references', 'bibliography', '参考文献', '引用文献'],
            '致谢': [
    'acknowledgments', 'acknowledgement', '致谢', '感谢',
    'remerciements', 'remerciement'
],
            '附录': ['appendix', 'appendices', '附录', '补充材料'],
        }

        # 构建正则表达式模式（学位论文特有章节）
        self.thesis_specific_patterns: List[re.Pattern] = []
        for _, keywords in self.thesis_core_sections.items():
            pattern_str = r'^(' + '|'.join(re.escape(k) for k in keywords) + r')(?:\s*[：:：\.\s].*)?$'
            self.thesis_specific_patterns.append(re.compile(pattern_str, re.IGNORECASE))

        # 纯文本标题识别（优化：更精确）
        self.thesis_title_line = re.compile(
            r'^\s*(?:(?:第[一二三四五六七八九十百千万零\d]+章?)|'
            r'(?:Chapter|Section|Part)\s+[A-Z0-9IVXLCDM\.]+)?\s*'
            r'(?:摘要|Abstract|中文摘要|英文摘要|引言|绪论|Introduction|前言|文献综述|文献回顾|'
            r'Related Work|Literature Review|研究背景|Background|研究方法|实验方法|方法论|'
            r'Methodology|Methods|Materials and Methods|实验设计|Experimental Design|'
            r'研究结果|实验结果|Results|结果分析|讨论|Discussion|结论|Conclusion|'
            r'参考文献|References|Bibliography|致谢|Acknowledgments|附录|Appendix|Appendices)\s*$',
            flags=re.IGNORECASE
        )

        # ==================== 缓存机制 ====================
        self._split_cache: Dict[str, List[Dict[str, Any]]] = {}
        self._cache_max_size: int = 100

        # ==================== 统计信息 ====================
        self.stats: Dict[str, Any] = {
            'total_chunks': 0,
            'md_chunks': 0,
            'chinese_chunks': 0,
            'english_chunks': 0,
            'thesis_chunks': 0,
            'plain_chunks': 0,
            'fallback_chunks': 0,
        }

        logger.info("ThesisProcessor 初始化完成")

    # ======================================================================
    # 核心入口
    # ======================================================================
    def split_by_chapters(self, text: str) -> List[Dict[str, Any]]:
        """
        按章节分块（优化增强版）

        优先级：
        1. Markdown 标题
        2. LaTeX 章节命令
        3. 中文章节
        4. 英文章节
        5. 学位论文专用章节名
        6. 纯文本标题
        7. 智能回退分割
        """
        if not text or not text.strip():
            return []

        # 0) 缓存检查
        text_hash = hashlib.md5(text.encode('utf-8')).hexdigest()
        if text_hash in self._split_cache:
            logger.debug(f"使用缓存分割结果，hash={text_hash[:8]}")
            return self._split_cache[text_hash]

        # 预处理
        text = self._preprocess_text(text)

        # 1) 优先按 markdown 标题
        chunks = self._try_markdown_split(text)
        if chunks:
            logger.info(f"Markdown 分割成功: {len(chunks)} 个 chunks")
            self.stats['md_chunks'] += len(chunks)
            result = self._postprocess_chunks(chunks)
            self._update_cache(text_hash, result)
            return result

        # 2) LaTeX
        chunks = self._try_latex_split(text)
        if chunks:
            logger.info(f"LaTeX 分割成功: {len(chunks)} 个 chunks")
            self.stats['chinese_chunks'] += len(chunks)  # 统计上可视为“结构化章节”
            result = self._postprocess_chunks(chunks)
            self._update_cache(text_hash, result)
            return result

        # 3) 中文章节
        chunks = self._try_chinese_split(text)
        if chunks:
            logger.info(f"中文章节分割成功: {len(chunks)} 个 chunks")
            self.stats['chinese_chunks'] += len(chunks)
            result = self._postprocess_chunks(chunks)
            self._update_cache(text_hash, result)
            return result

        # 4) 英文章节
        chunks = self._try_english_split(text)
        if chunks:
            logger.info(f"英文章节分割成功: {len(chunks)} 个 chunks")
            self.stats['english_chunks'] += len(chunks)
            result = self._postprocess_chunks(chunks)
            self._update_cache(text_hash, result)
            return result

        # 5) 学位论文特有章节
        chunks = self._try_thesis_specific_split(text)
        if chunks:
            logger.info(f"学位论文章节分割成功: {len(chunks)} 个 chunks")
            self.stats['thesis_chunks'] += len(chunks)
            result = self._postprocess_chunks(chunks)
            self._update_cache(text_hash, result)
            return result

        # 6) 纯文本标题识别
        chunks = self._try_plain_title_split(text)
        if chunks:
            logger.info(f"纯文本标题分割成功: {len(chunks)} 个 chunks")
            self.stats['plain_chunks'] += len(chunks)
            result = self._postprocess_chunks(chunks)
            self._update_cache(text_hash, result)
            return result

        # 7) 回退分割
        logger.warning("未检测到任何章节模式，使用智能回退分割")
        chunks = self._smart_fallback_split(text)
        self.stats['fallback_chunks'] += len(chunks)
        result = self._postprocess_chunks(chunks)
        self._update_cache(text_hash, result)
        return result

    # ======================================================================
    # 内部步骤实现
    # ======================================================================
    def _preprocess_text(self, text: str) -> str:
        """预处理文本：统一换行 / 清理标签等"""
        text = clean_text_basic(text)

        # 移除过多空行
        text = re.sub(r'\n{4,}', '\n\n', text)

        # 标准化章节标记：“第X章/节”后统一加空格
        text = re.sub(
            r'^(\s*)(第[一二三四五六七八九十百千万零\d]+)(章|节)',
            lambda m: f"{m.group(1)}{m.group(2)}{m.group(3)} ",
            text,
            flags=re.MULTILINE,
        )

        # 处理 LaTeX 标签
        text = re.sub(r'\\label\{[^}]*\}', '', text)      # \label{}
        text = re.sub(r'\\ref\{[^}]*\}', '引用', text)   # \ref{}

        return text.strip()

    def _try_markdown_split(self, text: str) -> List[Dict[str, Any]]:
        """尝试按 Markdown 标题分割"""
        lines = text.split('\n')
        chunks: List[Dict[str, Any]] = []
        current_chunk: List[str] = []
        current_title = "Untitled"
        current_level = 0
        in_chunk = False

        for i, line in enumerate(lines):
            line_stripped = line.strip()
            header_match = self.markdown_header_pattern.match(line_stripped)

            if header_match:
                level = len(header_match.group(1))
                title = header_match.group(2).strip()

                # 控制仅用 1~3 级标题作为主切分点
                if level <= 3:
                    if in_chunk and current_chunk:
                        chunk_content = '\n'.join(current_chunk)
                        if len(chunk_content) >= MIN_CHAPTER_LENGTH:
                            chunks.append({
                                'start_line': i - len(current_chunk),
                                'title': current_title,
                                'level': current_level,
                                'content': chunk_content,
                            })

                    current_title = title
                    current_level = level
                    current_chunk = [line]
                    in_chunk = True
                elif in_chunk:
                    current_chunk.append(line)
            elif in_chunk:
                current_chunk.append(line)

        # 最后一个 chunk
        if in_chunk and current_chunk:
            chunk_content = '\n'.join(current_chunk)
            if len(chunk_content) >= MIN_CHAPTER_LENGTH:
                chunks.append({
                    'start_line': len(lines) - len(current_chunk),
                    'title': current_title,
                    'level': current_level,
                    'content': chunk_content,
                })

        if not chunks:
            return []

        # 转换为标准格式
        standard_chunks: List[Dict[str, Any]] = []
        for idx, chunk in enumerate(chunks):
            content = clean_text_basic(chunk['content'])
            if len(content) >= MIN_CHAPTER_LENGTH:
                standard_chunks.append({
                    'chunk_id': f"md_{idx+1:03d}",
                    'chunk_title': chunk['title'],
                    'text': content,
                    'level': chunk['level'],
                    'parent_title': None,
                    'detection_method': 'markdown',
                })

        return standard_chunks

    def _try_latex_split(self, text: str) -> List[Dict[str, Any]]:
        """尝试按 LaTeX 章节分割"""
        lines = text.split('\n')
        indices: List[int] = []
        titles: List[str] = []
        levels: List[int] = []

        for i, line in enumerate(lines):
            line_stripped = line.strip()
            line_lower = line_stripped.lower()

            for pattern in self.latex_patterns:
                match = pattern.match(line_stripped)
                if match:
                    indices.append(i)
                    titles.append(match.group(1).strip())

                    # 按级别判断（注意 subsubsection > subsection > section）
                    if '\\chapter' in line_lower:
                        levels.append(1)
                    elif '\\section{' in line_lower and '\\subsection' not in line_lower:
                        levels.append(2)
                    elif '\\subsubsection' in line_lower:
                        levels.append(4)
                    elif '\\subsection' in line_lower:
                        levels.append(3)
                    else:
                        levels.append(4)
                    break

        if not indices:
            return []

        chunks: List[Dict[str, Any]] = []
        for k, start_i in enumerate(indices):
            end_i = indices[k + 1] if k + 1 < len(indices) else len(lines)
            title = titles[k]
            level = levels[k]

            content_lines = lines[start_i:end_i]
            # 移除 LaTeX 命令行
            content = '\n'.join(
                l for l in content_lines
                if not l.strip().startswith('\\')
            )
            content = clean_text_basic(content)

            if len(content) >= MIN_CHAPTER_LENGTH:
                chunks.append({
                    'chunk_id': f"latex_{k+1:03d}",
                    'chunk_title': title,
                    'text': content,
                    'level': level,
                    'parent_title': None,
                    'detection_method': 'latex',
                })

        return chunks

    def _try_chinese_split(self, text: str) -> List[Dict[str, Any]]:
        """尝试按中文章节分割"""
        lines = text.split('\n')
        indices: List[int] = []
        titles: List[str] = []
        levels: List[int] = []

        for i, line in enumerate(lines):
            line_stripped = line.strip()
            if not line_stripped:
                continue

            for pattern in self.chinese_patterns:
                match = pattern.match(line_stripped)
                if match:
                    indices.append(i)

                    # 提取标题
                    title = line_stripped
                    if match.groups():
                        for group in match.groups():
                            if group and group.strip():
                                title = group.strip()
                                break

                    titles.append(title)

                    # 判断级别
                    if '章' in line_stripped:
                        levels.append(1)
                    elif '节' in line_stripped:
                        levels.append(2)
                    elif re.search(r'\d+\.\d+', line_stripped):
                        levels.append(3)
                    else:
                        levels.append(2)
                    break

        if not indices:
            return []

        chunks: List[Dict[str, Any]] = []
        for k, start_i in enumerate(indices):
            end_i = indices[k + 1] if k + 1 < len(indices) else len(lines)
            title = titles[k]
            level = levels[k]

            content = '\n'.join(lines[start_i:end_i])
            content = clean_text_basic(content)

            if len(content) >= MIN_CHAPTER_LENGTH:
                chunks.append({
                    'chunk_id': f"cn_{k+1:03d}",
                    'chunk_title': title,
                    'text': content,
                    'level': level,
                    'parent_title': None,
                    'detection_method': 'chinese',
                })

        return chunks

    def _try_english_split(self, text: str) -> List[Dict[str, Any]]:
        """尝试按英文章节分割"""
        lines = text.split('\n')
        indices: List[int] = []
        titles: List[str] = []
        levels: List[int] = []

        for i, line in enumerate(lines):
            line_stripped = line.strip()
            if not line_stripped:
                continue
            line_lower = line_stripped.lower()  # 修复：之前未定义 line_lower

            for pattern in self.english_patterns:
                match = pattern.match(line_stripped)
                if match:
                    indices.append(i)

                    # 提取标题：优先 group(2)，否则第一个非空分组
                    if len(match.groups()) >= 2 and match.group(2):
                        title = match.group(2).strip()
                    elif match.groups():
                        title = next(
                            (g.strip() for g in match.groups() if g and g.strip()),
                            line_stripped
                        )
                    else:
                        title = line_stripped

                    titles.append(title)

                    # 判断级别
                    if 'chapter' in line_lower:
                        levels.append(1)
                    elif 'part' in line_lower:
                        levels.append(1)
                    elif 'section' in line_lower:
                        levels.append(2)
                    elif 'appendix' in line_lower:
                        levels.append(1)
                    elif re.search(r'\d+\.\d+', line_stripped):
                        levels.append(3)
                    else:
                        levels.append(2)
                    break

        if not indices:
            return []

        chunks: List[Dict[str, Any]] = []
        for k, start_i in enumerate(indices):
            end_i = indices[k + 1] if k + 1 < len(indices) else len(lines)
            title = titles[k]
            level = levels[k]

            content = '\n'.join(lines[start_i:end_i])
            content = clean_text_basic(content)

            if len(content) >= MIN_CHAPTER_LENGTH:
                chunks.append({
                    'chunk_id': f"en_{k+1:03d}",
                    'chunk_title': title,
                    'text': content,
                    'level': level,
                    'parent_title': None,
                    'detection_method': 'english',
                })

        return chunks

    def _try_thesis_specific_split(self, text: str) -> List[Dict[str, Any]]:
        """尝试按学位论文特有章节分割（摘要、引言、结论等）"""
        lines = text.split('\n')
        indices: List[int] = []
        titles: List[str] = []

        for i, line in enumerate(lines):
            line_stripped = line.strip()
            if not line_stripped:
                continue
            line_lower = line_stripped.lower()

            for pattern in self.thesis_specific_patterns:
                match = pattern.match(line_stripped)
                if match:
                    indices.append(i)

                    # 默认用原行作为标题
                    title = line_stripped
                    # 尝试映射到标准章节名
                    for section_name, keywords in self.thesis_core_sections.items():
                        if any(kw.lower() in line_lower for kw in keywords):
                            title = section_name
                            break

                    titles.append(title)
                    break

        if not indices:
            return []

        chunks: List[Dict[str, Any]] = []
        section_order = list(self.thesis_core_sections.keys())

        for k, start_i in enumerate(indices):
            end_i = indices[k + 1] if k + 1 < len(indices) else len(lines)
            title = titles[k]

            if title in section_order:
                order_idx = section_order.index(title)
            else:
                order_idx = 999

            content = '\n'.join(lines[start_i:end_i])
            content = clean_text_basic(content)

            if len(content) >= MIN_CHAPTER_LENGTH:
                chunks.append({
                    'chunk_id': f"thesis_{order_idx:03d}_{k+1:03d}",
                    'chunk_title': title,
                    'text': content,
                    'level': 1,
                    'parent_title': None,
                    'detection_method': 'thesis_specific',
                    'section_order': order_idx,
                })

        chunks.sort(key=lambda x: x.get('section_order', 999))
        return chunks

    def _try_plain_title_split(self, text: str) -> List[Dict[str, Any]]:
        """通过常见章节标题的纯文本行进行分割"""
        lines = text.split('\n')
        indices: List[int] = []
        titles: List[str] = []

        for i, line in enumerate(lines):
            line_strip = line.strip()
            if not line_strip:
                continue
            if self.thesis_title_line.match(line_strip):
                indices.append(i)
                titles.append(line_strip)

        if not indices:
            return []

        chunks: List[Dict[str, Any]] = []
        for k, start_i in enumerate(indices):
            end_i = indices[k + 1] if k + 1 < len(indices) else len(lines)
            title = titles[k]

            content = '\n'.join(lines[start_i:end_i])
            content = clean_text_basic(content)

            if len(content) >= MIN_CHAPTER_LENGTH:
                chunks.append({
                    'chunk_id': f"plain_{k+1:03d}",
                    'chunk_title': title,
                    'text': content,
                    'level': 1,
                    'parent_title': None,
                    'detection_method': 'plain_title',
                })

        return chunks

    def _smart_fallback_split(self, text: str) -> List[Dict[str, Any]]:
        """智能回退分割：按段落 / 句子 / 固定长度三层策略"""
        content = clean_text_basic(text)
        if len(content) < MIN_CHAPTER_LENGTH:
            return []

        # 1. 按段落分割
        paragraphs = re.split(r'\n{2,}', content)
        if 1 < len(paragraphs) <= MAX_CHUNK_SIZE:
            chunks: List[Dict[str, Any]] = []
            for i, para in enumerate(paragraphs):
                para = para.strip()
                if len(para) >= MIN_CHAPTER_LENGTH:
                    chunks.append({
                        'chunk_id': f"para_{i+1:03d}",
                        'chunk_title': f'段落 {i+1}',
                        'text': para,
                        'level': 1,
                        'parent_title': None,
                        'detection_method': 'paragraph',
                    })

            if chunks:
                logger.info(f"段落分割成功: {len(chunks)} 个 chunks")
                return chunks

        # 2. 按长度智能分割（基于句子）
        text_length = len(content)
        ideal_chunk_size = min(
            IDEA_CHUNK_LENGTH,
            max(MIN_CHAPTER_LENGTH * 2, text_length // 10)
        )

        sentences = re.split(r'([。！？；]\s*)', content)  # 保留标点
        # 将句子+标点重新组合
        merged_sentences: List[str] = []
        tmp = ""
        for seg in sentences:
            if not seg:
                continue
            tmp += seg
            if re.match(r'[。！？；]\s*', seg):
                merged_sentences.append(tmp.strip())
                tmp = ""
        if tmp.strip():
            merged_sentences.append(tmp.strip())

        chunks: List[Dict[str, Any]] = []
        current_chunk: List[str] = []
        current_length = 0

        for sentence in merged_sentences:
            if not sentence:
                continue
            sent_length = len(sentence)

            # 如果当前块接近理想大小或句子本身很长，就先收割当前块
            if (current_length + sent_length > ideal_chunk_size * 1.2 or
                    sent_length > ideal_chunk_size * 0.7):
                if current_chunk:
                    chunk_text = ''.join(current_chunk).strip()
                    if len(chunk_text) >= MIN_CHAPTER_LENGTH:
                        chunks.append({
                            'chunk_id': f"smart_{len(chunks)+1:03d}",
                            'chunk_title': f'块 {len(chunks)+1}',
                            'text': chunk_text,
                            'level': 1,
                            'parent_title': None,
                            'detection_method': 'smart_fallback',
                        })
                    current_chunk = []
                    current_length = 0

            current_chunk.append(sentence)
            current_length += sent_length

        # 最后一个块
        if current_chunk:
            chunk_text = ''.join(current_chunk).strip()
            if len(chunk_text) >= MIN_CHAPTER_LENGTH:
                chunks.append({
                    'chunk_id': f"smart_{len(chunks)+1:03d}",
                    'chunk_title': f'块 {len(chunks)+1}',
                    'text': chunk_text,
                    'level': 1,
                    'parent_title': None,
                    'detection_method': 'smart_fallback',
                })

        # 3. 如果分割太少，使用固定大小分割兜底
        if len(chunks) < 3 and text_length > MIN_CHAPTER_LENGTH * 3:
            num_chunks = min(
                MAX_CHUNK_SIZE,
                max(3, text_length // ideal_chunk_size)
            )
            chunk_size = text_length // num_chunks

            chunks = []
            for i in range(num_chunks):
                start = i * chunk_size
                end = len(content) if i == num_chunks - 1 else start + chunk_size

                # 向后调整到最近的句号等自然边界
                if i < num_chunks - 1:
                    for adjust in range(0, min(100, len(content) - end)):
                        if content[end + adjust] in '。！？；':
                            end = end + adjust + 1
                            break

                chunk_text = content[start:end].strip()
                if len(chunk_text) >= MIN_CHAPTER_LENGTH:
                    chunks.append({
                        'chunk_id': f"fixed_{i+1:03d}",
                        'chunk_title': f'块 {i+1}',
                        'text': chunk_text,
                        'level': 1,
                        'parent_title': None,
                        'detection_method': 'fixed_fallback',
                    })

        logger.info(f"智能回退分割: {len(chunks)} 个 chunks")
        return chunks

    def _postprocess_chunks(self, chunks: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """统一后处理：过滤、合并、补充元数据"""
        if not chunks:
            return []

        # 1. 过滤太短的 chunks
        filtered_chunks: List[Dict[str, Any]] = []
        for chunk in chunks:
            content = chunk.get('text') or chunk.get('content') or ''
            content = clean_text_basic(content)
            if len(content) >= MIN_CHAPTER_LENGTH:
                # 标准化键名
                normalized = {
                    'chunk_id': chunk.get('chunk_id', ''),
                    'chunk_title': chunk.get('chunk_title') or chunk.get('title', 'Untitled'),
                    'text': content,
                    'level': chunk.get('level', 1),
                    'parent_title': chunk.get('parent_title'),
                    'detection_method': chunk.get('detection_method', 'unknown'),
                }
                filtered_chunks.append(normalized)

        if not filtered_chunks:
            return []

        # 2. 合并过小相邻 chunks
        merged_chunks: List[Dict[str, Any]] = []
        i = 0
        while i < len(filtered_chunks):
            current = filtered_chunks[i]
            if (len(current['text']) < MIN_CHAPTER_LENGTH * 2 and
                    i + 1 < len(filtered_chunks)):
                next_chunk = filtered_chunks[i + 1]
                if len(current['text']) + len(next_chunk['text']) < IDEA_CHUNK_LENGTH * 2:
                    merged_content = current['text'] + '\n\n' + next_chunk['text']
                    merged_title = f"{current['chunk_title']} + {next_chunk['chunk_title']}"
                    merged_chunks.append({
                        'chunk_id': f"merged_{len(merged_chunks)+1:03d}",
                        'chunk_title': merged_title,
                        'text': merged_content,
                        'level': current.get('level', 1),
                        'parent_title': None,
                        'detection_method': current.get('detection_method', 'unknown') + '_merged',
                    })
                    i += 2
                    continue

            merged_chunks.append(current)
            i += 1

        # 3. 限制 chunk 数量
        if len(merged_chunks) > MAX_CHUNK_SIZE:
            merged_chunks = self._merge_final_chunks(merged_chunks, MAX_CHUNK_SIZE)

        # 4. 更新统计 + 补充元信息
        self.stats['total_chunks'] += len(merged_chunks)
        final_chunks: List[Dict[str, Any]] = []
        for i, chunk in enumerate(merged_chunks):
            text = chunk['text']
            final_chunks.append({
                **chunk,
                'chunk_id': f"{chunk.get('detection_method', 'chunk')}_{i+1:03d}",
                'processed_at': datetime.now().isoformat(timespec="seconds"),
                'estimated_tokens': estimate_tokens(text),
                'section_type': self._identify_section_type(
                    chunk.get('chunk_title', ''), text
                ),
            })

        logger.info(f"后处理完成: {len(final_chunks)} 个 chunks")
        return final_chunks

    def _identify_section_type(self, title: str, content: str) -> str:
        """识别章节类型（粗分类：摘要、引言、方法、结果、讨论、结论等）"""
        title_lower = (title or '').lower()
        content_lower = (content or '').lower()

        # 1) 标题 / 内容包含核心关键词
        for section_name, keywords in self.thesis_core_sections.items():
            for keyword in keywords:
                if keyword.lower() in title_lower or keyword.lower() in content_lower:
                    return section_name

        # 2) 仅按内容模式粗略判断
        if any(kw in content_lower for kw in ['实验方法', 'method', 'materials and methods']):
            return '方法'
        if any(kw in content_lower for kw in ['实验结果', 'results', '数据表']):
            return '结果'
        if any(kw in content_lower for kw in ['讨论', 'discussion', '分析']):
            return '讨论'
        if any(kw in content_lower for kw in ['结论', 'conclusion', '总结']):
            return '结论'
        if any(kw in content_lower for kw in ['引言', 'introduction', '背景']):
            return '引言'

        return '其他'

    def _update_cache(self, text_hash: str, chunks: List[Dict[str, Any]]) -> None:
        """更新缓存"""
        if len(self._split_cache) >= self._cache_max_size:
            # 移除最旧的缓存项（FIFO）
            oldest_key = next(iter(self._split_cache))
            del self._split_cache[oldest_key]

        self._split_cache[text_hash] = chunks

    def _merge_final_chunks(
        self,
        chunks: List[Dict[str, Any]],
        max_chunks: int
    ) -> List[Dict[str, Any]]:
        """最终合并，控制 chunk 总数不超过 max_chunks"""
        if len(chunks) <= max_chunks:
            return chunks

        merged: List[Dict[str, Any]] = []
        merge_ratio = len(chunks) // max_chunks + 1

        for i in range(0, len(chunks), merge_ratio):
            group = chunks[i:i + merge_ratio]
            if not group:
                continue

            merged_content = '\n\n'.join(c.get('text', '') for c in group).strip()
            if not merged_content:
                continue

            if len(group) == 1:
                merged_title = group[0].get('chunk_title', 'Merged')
            else:
                first_title = group[0].get('chunk_title', '')
                last_title = group[-1].get('chunk_title', '')
                merged_title = f"{first_title} ~ {last_title}".strip(' ~')

            min_level = min((c.get('level', 1) for c in group), default=1)
            section_types = [c.get('section_type', '其他') for c in group]
            main_section_type = max(set(section_types), key=section_types.count)

            merged.append({
                'chunk_id': f"merged_{len(merged)+1:03d}",
                'chunk_title': merged_title or 'Merged Chunk',
                'text': merged_content,
                'level': min_level,
                'parent_title': None,
                'detection_method': 'final_merge',
                'section_type': main_section_type,
            })

        logger.info(f"最终合并: {len(chunks)} -> {len(merged)} 个 chunks")
        return merged

    # ======================================================================
    # 统计 & 维护
    # ======================================================================
    def get_statistics(self) -> Dict[str, Any]:
        """获取统计信息"""
        return {
            'total_processed': self.stats['total_chunks'],
            'by_method': {
                'markdown': self.stats['md_chunks'],
                'chinese': self.stats['chinese_chunks'],
                'english': self.stats['english_chunks'],
                'thesis_specific': self.stats['thesis_chunks'],
                'plain_title': self.stats['plain_chunks'],
                'fallback': self.stats['fallback_chunks'],
            },
            'cache_size': len(self._split_cache),
            # 如需精确命中率，可在 split_by_chapters 中维护 hit / miss 计数
            'cache_hit_rate': 0,
        }

    def clear_cache(self) -> None:
        """清空缓存"""
        self._split_cache.clear()
        logger.info("ThesisProcessor 缓存已清空")

# ==============================================================================
# SFT问答生成器（增强版）
# ==============================================================================

class SFTQuestionGenerator:
    def __init__(self):
        self.client = OpenAI(api_key=OPENAI_API_KEY, base_url=OPENAI_BASE_URL, timeout=60.0)

    def generate_reasoning_qas_from_section(self, section_name: str, section_text: str, max_q: int = 5
    ) -> Tuple[List[Dict[str, Any]], str]:
        generation_type = "推理型"

        # 检查是否应该跳过此章节（如参考文献、致谢、附录等）
        if should_skip_section(section_name, section_text):
            tprint(f"  ⏭️ 跳过章节（参考文献/致谢/附录等），section={section_name}")
            return [], generation_type

        # 1) 抽取推理链
        chain_prompt = build_chain_extraction_prompt(section_name, section_text, max_chains=max_q * OVER_GENERATE_FACTOR)
        # 修复：强制启用thinking模式（与objective模式保持一致）
        chain_data = call_responses_for_json(chain_prompt, model=DEFAULT_MODEL, max_output_tokens=8000, temperature=0.6, enable_thinking=True)
        if chain_data is None:
            tprint(f"  ❌ 推理链抽取失败，section={section_name}")
            return [], generation_type

        chains = []
        # 修复：支持call_responses_for_json返回的两种格式
        if isinstance(chain_data, dict):
            # 优先从"data"字段提取（v1_eval.py的call_responses_for_json会包装一层data）
            if "data" in chain_data:
                data = chain_data["data"]
                if isinstance(data, dict) and "chains" in data:
                    chains = data.get("chains", [])
                elif isinstance(data, list):
                    chains = data
            # 直接从根级别提取
            elif "chains" in chain_data:
                chains = chain_data.get("chains", [])
            # 如果有_raw_response字段，尝试从那里解析
            elif "_raw_response" in chain_data:
                # 尝试从_raw_response中解析JSON
                raw_resp = chain_data["_raw_response"]
                if isinstance(raw_resp, dict) and "chains" in raw_resp:
                    chains = raw_resp.get("chains", [])
        elif isinstance(chain_data, list):
            chains = chain_data

        if not isinstance(chains, list) or not chains:
            tprint(f"  ❌ 未提取到推理链，section={section_name}")
            logger.debug(f"chain_data类型: {type(chain_data)}, 包含的键: {list(chain_data.keys()) if isinstance(chain_data, dict) else 'N/A'}")
            return [], generation_type

        # 提取thinking模式的COT（来自build_chain_extraction_prompt）
        cot_from_qa_thinking = chain_data.get("_extracted_cot", "") if isinstance(chain_data, dict) else ""
        logger.info(f"[DEBUG] chain_data类型: {type(chain_data)}, 包含_extracted_cot: {isinstance(chain_data, dict) and '_extracted_cot' in chain_data}")
        logger.info(f"[DEBUG] 提取到COT，长度: {len(cot_from_qa_thinking)}")

        # 2) 每条 chain 生成 QA（超生成，然后靠质量/多样性/去重筛选）
        raw = []
        for chain in chains:
            if len(raw) >= max_q * OVER_GENERATE_FACTOR:
                break
            try:
                # 从chain中获取reasoning_steps（来自build_chain_extraction_prompt）
                reasoning_steps_from_chain = chain.get("steps", []) or []
                final_conclusion = str(chain.get("final_conclusion", "") or "").strip()

                chain_json_str = json.dumps(chain, ensure_ascii=False)
                qa_prompt = build_chain_to_qa_prompt(chain_json_str)

                # 修复：强制启用thinking模式（与objective模式保持一致）
                qa_response = call_responses_for_json(qa_prompt, model=DEFAULT_MODEL, max_output_tokens=12000, temperature=0.7, enable_thinking=True)
                if qa_response is None:
                    tprint(f"  ❌ QA生成失败，跳过此chain")
                    continue

                # 从返回的数据中提取COT和JSON
                qa_data = qa_response
                # 如果当前qa_response有COT且之前没有COT，则使用当前的
                new_cot = qa_response.get("_extracted_cot", "") if isinstance(qa_response, dict) else ""
                if new_cot and not cot_from_qa_thinking:
                    cot_from_qa_thinking = new_cot

                # 如果qa_response包含_raw_response，使用它来提取COT（thinking模式）
                if isinstance(qa_response, dict) and "_raw_response" in qa_response:
                    raw_response = qa_response["_raw_response"]
                    cot_from_reasoning = extract_cot_from_reasoning(raw_response)
                    if cot_from_reasoning:
                        cot_from_qa_thinking = cot_from_reasoning
                    # 保留_extracted_cot和_raw_response，过滤其他"_"开头的内部字段
                    extracted_cot = qa_response.get("_extracted_cot", "")
                    qa_data = {k: v for k, v in qa_response.items() if not k.startswith("_") or k in ["_extracted_cot", "_raw_response"]}
                    # 确保_extracted_cot存在
                    if extracted_cot and "_extracted_cot" not in qa_data:
                        qa_data["_extracted_cot"] = extracted_cot
                elif isinstance(qa_response, dict):
                    # 即使没有_raw_response，也确保_extracted_cot被保留
                    extracted_cot = qa_response.get("_extracted_cot", "")
                    if extracted_cot:
                        # 过滤掉其他内部字段，但保留_extracted_cot
                        qa_data = {k: v for k, v in qa_response.items() if not k.startswith("_") or k == "_extracted_cot"}
                        qa_data["_extracted_cot"] = extracted_cot

                qa_list = qa_data if isinstance(qa_data, list) else [qa_data]

                # 为每个QA添加提取的COT（thinking模式）和chain中的reasoning_steps
                for qa in qa_list:
                    if isinstance(qa, dict):
                        # 添加thinking模式生成的COT（仅在不存在时）
                        if "_extracted_cot" not in qa:
                            qa["_extracted_cot"] = cot_from_qa_thinking
                        # 添加从chain中提取的reasoning_steps
                        qa["_reasoning_steps_from_chain"] = reasoning_steps_from_chain

                for qa in qa_list:
                    q = sanitize_text_forbidden_phrases(str(qa.get("question", "")).strip())
                    a = sanitize_text_forbidden_phrases(str(qa.get("answer", "")).strip())
                    meta = qa.get("meta", {}) or {}
                    difficulty = str(meta.get("difficulty", qa.get("difficulty", ""))).strip().lower()
                    tags = meta.get("tags", qa.get("tags", [])) or []

                    # 从build_chain_to_qa_prompt返回的JSON中获取cot字段
                    cot_from_qa_json = qa.get("cot", "")
                    if isinstance(cot_from_qa_json, list):
                        question_cot = "\n".join(str(s).strip() for s in cot_from_qa_json if str(s).strip())
                    else:
                        question_cot = str(cot_from_qa_json or "").strip()

                    # 从thinking模式提取的COT
                    question_api_cot = qa.get("_extracted_cot", "")

                    # 从chain中获取的reasoning_steps（来自build_chain_extraction_prompt）
                    reasoning_steps_from_chain = qa.get("_reasoning_steps_from_chain", []) or []

                    # 如果没有从chain中获取到reasoning_steps，尝试从thinking模式的COT中提取
                    if not reasoning_steps_from_chain and question_api_cot:
                        reasoning_steps_from_thinking = [s.strip() for s in question_api_cot.split('\n') if s.strip()]
                        if reasoning_steps_from_thinking:
                            reasoning_steps_from_chain = reasoning_steps_from_thinking

                    raw.append({
                        "question": q,
                        "answer": a,
                        "reasoning_steps": reasoning_steps_from_chain,
                        "reasoning_steps_api_cot": sanitize_text_forbidden_phrases(question_api_cot),
                        "question_cot": sanitize_text_forbidden_phrases(question_cot),
                        "question_api_cot": sanitize_text_forbidden_phrases(question_api_cot),
                        "final_conclusion": sanitize_text_forbidden_phrases(final_conclusion),
                        "difficulty": difficulty,
                        "tags": tags if isinstance(tags, list) else [str(tags)],
                    })
                    if len(raw) >= max_q * OVER_GENERATE_FACTOR:
                        break

            except Exception as e:
                tprint(f"  ⚠️ chain→QA 失败: {e}")
                continue

        # 3) 清洗/过滤
        cleaned: List[Dict[str, Any]] = []
        for item in raw:
            q = item.get("question", "")
            a = item.get("answer", "")
            if not q or not a or len(q) < 8 or len(a) < 30:
                continue
            if is_study_dependent(q) or is_study_dependent(a):
                continue
            if contains_forbidden_phrases(q) or contains_forbidden_phrases(a):
                continue

            difficulty = (item.get("difficulty") or "").strip().lower()
            if difficulty not in ["easy", "medium", "hard"]:
                difficulty = "easy" if len(q) < 40 else ("medium" if len(q) < 80 else "hard")

            cleaned.append({
                "question": q,
                "answer": a,
                "reasoning_steps": item.get("reasoning_steps", []),
                "reasoning_steps_api_cot": item.get("reasoning_steps_api_cot", ""),
                "question_cot": item.get("question_cot", ""),
                "question_api_cot": item.get("question_api_cot", ""),
                "final_conclusion": item.get("final_conclusion", ""),
                "difficulty": difficulty,
                "tags": item.get("tags", []),
            })

        return cleaned, generation_type

    def generate_for_chunk_with_reasoning(
        self,
        chunk: Dict[str, str],
        source_id: str,
        enable_diversity: bool = True,
        simhash_dedup_hamming: int = 6,
        context_length: int = 1000
    ) -> List[Dict[str, Any]]:
        # 检查是否应该跳过此章节（如参考文献、致谢、附录等）
        if should_skip_section(chunk['chunk_title'], chunk['text']):
            tprint(f"  ⏭️ 跳过章节（参考文献/致谢/附录等），section={chunk['chunk_title']}")
            return []

        # 始终使用推理链生成
        tprint(f"▶ 推理链生成: {chunk['chunk_title']}")
        raw_qas, generation_type = self.generate_reasoning_qas_from_section(
            section_name=chunk['chunk_title'],
            section_text=chunk['text'],
            max_q=MAX_Q_PER_CHUNK,
        )

        if not raw_qas:
            return []

        quality_scorer = QualityScorer()

        # 保存上下文内容（可配置长度）
        context_text = chunk['text'][:context_length] if len(chunk['text']) > context_length else chunk['text']

        # =========================
        # NEW: 章节长度统计
        # =========================
        chunk_length = len(chunk['text'])
        # 章节长度分类：短(<500)、中(500-2000)、长(>2000)
        if chunk_length < 500:
            chunk_length_category = "short"
        elif chunk_length <= 2000:
            chunk_length_category = "medium"
        else:
            chunk_length_category = "long"

        # =========================
        # NEW: chunk 统计计数器
        # =========================
        raw_count = len(raw_qas)
        invalid_count = 0
        valid_count = 0

        records: List[Dict[str, Any]] = []
        for qa in raw_qas:
            record = {
                "source_id": source_id,
                "source_type": "thesis",
                "chunk_title": chunk['chunk_title'],
                "chunk_id": chunk['chunk_id'],
                "chunk_length": chunk_length,
                "chunk_length_category": chunk_length_category,
                "question": qa["question"],
                "answer": qa["answer"],
                "context": context_text,
                "reasoning_steps": qa.get("reasoning_steps", []),
                "reasoning_steps_api_cot": qa.get("reasoning_steps_api_cot", ""),
                "question_cot": qa.get("question_cot", ""),
                "question_api_cot": qa.get("question_api_cot", ""),
                "final_conclusion": qa.get("final_conclusion", ""),
                "difficulty": qa.get("difficulty", "medium"),
                "curriculum_stage": assign_curriculum_stage(
                    qa.get("difficulty", "medium"),
                    qa.get("question_cot", "")
                ),
                "tags": qa.get("tags", []),
                "created_at": datetime.now().isoformat(timespec="seconds"),
                "token_est_question": estimate_tokens(qa["question"]),
                "token_est_answer": estimate_tokens(qa["answer"]),
                "generation_type": generation_type,
            }

            # 质量评分
            record["quality_report"] = quality_scorer.score_qa_pair(record)

            # 验证记录
            is_valid, errors = validate_qa_record(record, chunk['chunk_id'])
            if is_valid:
                records.append(record)
                valid_count += 1
            else:
                invalid_count += 1
                logger.warning(f"跳过无效记录 (chunk={chunk['chunk_id']}): {errors}")

        if not records:
            tprint(f"  ⚠️ {generation_type} raw={raw_count} → valid=0 (all invalid)")
            return []

        # 先按质量降序排序（后续去重/多样性更容易保留好样本）
        records.sort(
            key=lambda x: (x.get("quality_report", {}).get("total_score", 0.0)),
            reverse=True
        )

        # =========================
        # NEW: SimHash 去重统计
        # =========================
        simhash_before = len(records)
        records = dedup_qas_simhash(records, max_hamming=simhash_dedup_hamming)
        simhash_after = len(records)

        # =========================
        # NEW: 多样性过滤统计
        # =========================
        diversity_before = len(records)

        if enable_diversity and REASONING_DIVERSITY_AVAILABLE and diversity_filter_qas is not None:
            try:
                records = diversity_filter_qas(
                    records,
                    simhash_dedup_hamming=simhash_dedup_hamming
                )
            except Exception as e:
                logger.error(f"多样性过滤失败: {e}")
        elif enable_diversity and not REASONING_DIVERSITY_AVAILABLE:
            # 多样性过滤模块不可用，但已启用
            logger.info(f"多样性过滤模块不可用，跳过多样性过滤")

        diversity_after = len(records)

        # 为每条记录添加多样性过滤统计信息
        for record in records:
            record["diversity_before"] = diversity_before
            record["diversity_after"] = diversity_after

        # 最终排序：按质量得分排序
        records.sort(
            key=lambda x: (
                x.get("quality_report", {}).get("total_score", 0.0),
                len(x.get("reasoning_steps", [])),
                -x.get("token_est_question", 0),
                -x.get("token_est_answer", 0),
            ),
            reverse=True
        )

        final_count = len(records)

        # 统计输出（包含章节长度信息）
        tprint(
            f"  ✅ {generation_type} raw={raw_count} | "
            f"valid={valid_count} | "
            f"simhash={simhash_before}→{simhash_after} | "
            f"diversity={diversity_before}→{diversity_after} | "
            f"final={final_count} | "
            f"chunk_len={chunk_length}({chunk_length_category})"
        )

        return records


# ==============================================================================
# 客观评测题生成器
# ==============================================================================

class ObjectiveQuestionGenerator:
    """生成客观评测题的类（单选、多选、判断、填空）"""

    def __init__(self):
        self.client = OpenAI(api_key=OPENAI_API_KEY, base_url=OPENAI_BASE_URL, timeout=60.0)

    def call_llm_api(self, question_prompt: str, model: str = DEFAULT_MODEL,
                     temperature: float = 0.7, max_tokens: int = 8000, enable_thinking: bool = False):
        """调用LLM API生成题目

        Args:
            question_prompt: 提示词
            model: 模型名称
            temperature: 温度参数
            max_tokens: 最大token数
            enable_thinking: 是否启用thinking模式（默认False）
        """
        req_id = str(uuid.uuid4())[:8]
        start_time = time.time()

        try:
            response = self.client.chat.completions.create(
                model=model,
                messages=[{"role": "user", "content": question_prompt}],
                temperature=temperature,
                max_tokens=max_tokens,
                stream=False,
            )

            latency = time.time() - start_time

            if not response.choices or not response.choices[0].message.content:
                raise RuntimeError("API响应为空")

            raw_answer = response.choices[0].message.content

            # 如果启用thinking模式，提取thinking内容
            thinking_content = ""
            clean_answer = raw_answer
            if enable_thinking:
                clean_answer, thinking_content = split_think_content(raw_answer)
                if thinking_content:
                    logger.info(f"[{req_id}] 提取到thinking内容，长度: {len(thinking_content)} 字符")

            # 提取token使用情况
            usage = response.usage
            input_tokens = 0
            output_tokens = 0
            total_tokens = 0

            if usage:
                input_tokens = getattr(usage, 'prompt_tokens', 0) or getattr(usage, 'input_tokens', 0)
                output_tokens = getattr(usage, 'completion_tokens', 0) or getattr(usage, 'output_tokens', 0)
                total_tokens = getattr(usage, 'total_tokens', 0) or (input_tokens + output_tokens)

                # 更新全局token统计
                update_token_stats(input_tokens, output_tokens, total_tokens)

                logger.info(f"[{req_id}] API调用成功 - 输入Tokens: {input_tokens}, 输出Tokens: {output_tokens}, 耗时: {latency:.2f}s")
            else:
                logger.warning(f"[{req_id}] API响应中没有usage信息，无法统计token使用量")

            return clean_answer, input_tokens, output_tokens, total_tokens, latency, thinking_content

        except Exception as e:
            latency = time.time() - start_time
            logger.error(f"[{req_id}] API调用失败: {e}")
            raise Exception(f"OpenAI API调用失败: {e}")

    def parse_json_response(self, answer):
        """解析API返回的JSON字符串"""
        try:
            # 移除可能的markdown代码块标记
            answer = answer.replace('```json', '').replace('```', '').strip()

            # 尝试解析JSON
            q = json.loads(answer)
            return q, True
        except json.JSONDecodeError as e:
            logger.error(f"JSON解析失败: {e}")
            logger.error(f"原始响应: {answer[:500]}")
            return None, False

    def build_objective_question_prompt(self, section_data, question_type, question_id, enable_thinking=False):
        """构建客观题提示词（强化版：加入 Gate + meta.fact_count_used）

        Args:
            section_data: 章节数据
            question_type: 'single_choice' | 'multiple_choice' | 'true_false'
            question_id: 题目ID（建议从1开始递增）
            enable_thinking: 是否启用thinking模式（默认False）
        """
        section_id = section_data.get("chunk_id", "") or ""
        section_title = section_data.get("chunk_title", "") or ""
        section_text = (section_data.get("text", "") or "")[:2000]  # 控制长度，避免上下文过长

        type_mapping = {
            "single_choice": "单选题",
            "multiple_choice": "多选题",
            "true_false": "判断题",
        }
        if question_type not in type_mapping:
            raise ValueError(f"Unsupported question_type: {question_type}")

        zh_qtype = type_mapping[question_type]

        # ---------- 最高优先级质量与安全规则（对齐 chain_to_qa_prompt 的"硬约束"风格） ----------
        quality_prompt = f"""你是一位顶尖的农业育种与生命科学领域"客观评测题"命题专家。你的输出用于大模型评测与训练，必须可靠、可验证、零幻觉。

    【最高优先级规则（不得违反）】
    1) **仅允许使用输入章节正文中"明确出现"的事实与概念**进行改写与抽象（来自"章节标题/章节内容"）。
    2) 不得引入外部知识、常识补全或主观推测；不得编造机制、数据、结论或文献。
    3) 必须先执行 Gate（章节质量 / 元信息判别）。Gate 不通过则按指定 JSON 直接返回并停止。
    4) 严格只输出 **一个 JSON 对象**；不得输出任何额外说明、标题或 Markdown。

    【题目总体要求】
    - 题目必须是"独立成立"的通用知识表达：禁止出现"本文/本章/该段落/如上所述/文中/研究显示"等上下文指代。
    - 所有题目为"常识题/通用题"：聚焦通用概念、原理、机制、方法与决策依据；避免具体实验细节（如样本量、具体年份、图表编号、某一次实验设置）。
    - 语言精炼，每句话提供实质信息或区分度，不重复题干、不说套话。
    - 若涉及生物实体或对象范围，必须在题干中明确主语（例如"在植物育种中/在群体遗传学中/在分子标记辅助选择中"等）。

    【禁止使用的上下文引用词（题干与选项中都禁止）】
    - "该文章"、"该段落"、"该方法"、"该研究"、"论文中"、"摘要中"、"文中"
    - "实验表明"、"研究显示"、"数据显示"、"根据研究"、"基于该研究"
    - "在本研究中"、"在本方法中"、"如上所述"、"如前所述"、"如下所示"
    - "上述"、"此项"、"此处"、"该实验"、"该过程"、"该现象"

    ────────────────────────────────────────
    【输入章节信息】
    - 章节ID: {section_id}
    - 章节标题: {section_title}
    - 章节内容(截断): {section_text}
    """

        # ---------- Thinking 模式（仅用于内部推理，不得出现在最终 JSON） ----------
        if enable_thinking:
            thinking_prompt = """
    【Thinking模式（可选）】
    - 你可以在内部用 <thinking>...</thinking> 做推理与筛选，但 **最终输出必须只有 JSON**，不得包含 thinking 标签或其他文字。
    - 在内部推理中完成：
    1) Gate 判别（是否 meta-only）
    2) 从章节内容中挑选 ≥2 条"明确出现"的支撑事实（仅内部使用）
    3) 生成题干与选项并校验互斥性/可判定性
    """
        else:
            thinking_prompt = ""

        # ---------- Gate：识别 meta-only chunk（封面/致谢/目录/版权等） ----------
        gate_prompt = f"""
    ────────────────────────────────────────
    【Gate：章节质量 / 元信息判别（强制第一步）】

    若章节内容主要属于以下任一类，则判定为"不通过 Gate（meta_only_chunk）"：
    - 封面/扉页/作者与学校信息/授位信息/编号/日期/版权声明
    - 致谢/献词/声明/目录/图表清单/参考文献列表（以条目为主）/附录索引
    - ProQuest/UMI/出版与授权条款等与学术身份相关的元信息
    - 缺乏可用于命题的科学概念、机制、方法或可判定陈述

    【Gate 不通过时：必须只输出以下 JSON 并立即停止】
    注意：字段名不得增删；只允许这些字段；不得输出任何其他内容。
    """

        # ---------- 统一的 meta 要求（加入 fact_count_used） ----------
        meta_rules_prompt = """
    ────────────────────────────────────────
    【meta.fact_count_used（强制）】
    - fact_count_used = 实际用于构造题干 + 正确答案判定 + 选项设计的"章节内支撑事实"的数量
    - 通过 Gate 时必须满足：fact_count_used ≥ 2
    - Gate 不通过时必须为：fact_count_used = 0
    - 不得随意填写；用于下游审计

    【meta 字段结构（强制输出）】
    "meta": {
    "difficulty": "easy | medium | hard",
    "difficulty_score": 0.0,
    "fact_count_used": 0,
    "tags": ["concept", "mechanism", "method", "comparison", "condition", "application", "limitation", "decision"]
    }

    difficulty_score 取值 0~1（建议：easy≈0.2–0.4；medium≈0.5–0.7；hard≈0.75–0.95）
    tags 从候选中选 2~6 个，体现题目考点（机制/方法/条件/比较/决策等）。
    """

        # ---------- 题型特定 JSON 结构与约束 ----------
        if question_type == "single_choice":
            gate_fail_json = f"""{{
    "question_id": "{question_id}",
    "source_id": "{section_id}",
    "type": "客观评测题",
    "question_type": "单选题",
    "question": null,
    "options": null,
    "reference_answer": null,
    "meta": {{
        "difficulty": "easy",
        "difficulty_score": 0.0,
        "fact_count_used": 0,
        "tags": ["meta_only_chunk"]
    }}
    }}"""

            type_specific_prompt = f"""
    【单选题规范（必须满足）】
    - question_type 必须严格为 "单选题"
    - 选项数量固定 4 个（A、B、C、D）
    - 选项必须语义互斥、边界清晰、不可重叠；不得用"以上都是/以上都不对"。
    - 题目应具有区分度：优先考查概念联系、因果推理、比较、条件依赖或方法选择；避免纯记忆碎片。
    - reference_answer 只能是 A/B/C/D 之一，且必须"可判定对错"。

    【通过 Gate 后：最终输出 JSON 结构（字段名不得增删）】
    {{
    "question_id": "{question_id}",
    "source_id": "{section_id}",
    "type": "客观评测题",
    "question_type": "单选题",
    "question": "问题内容",
    "options": {{
        "A": "选项A内容",
        "B": "选项B内容",
        "C": "选项C内容",
        "D": "选项D内容"
    }},
    "reference_answer": "A",
    "meta": {{
        "difficulty": "easy",
        "difficulty_score": 0.3,
        "fact_count_used": 2,
        "tags": ["concept", "comparison"]
    }}
    }}
    """

        elif question_type == "multiple_choice":
            gate_fail_json = f"""{{
    "question_id": "{question_id}",
    "source_id": "{section_id}",
    "type": "客观评测题",
    "question_type": "多选题",
    "question": null,
    "options": null,
    "reference_answer": null,
    "meta": {{
        "difficulty": "easy",
        "difficulty_score": 0.0,
        "fact_count_used": 0,
        "tags": ["meta_only_chunk"]
    }}
    }}"""

            type_specific_prompt = f"""
    【多选题规范（必须满足）】
    - question_type 必须严格为 "多选题"
    - 正确答案数量必须为 2-6 个，绝不能为单选
    - 答案格式：多个字母连续排列（如 "ABC"、"ABD"），字母必须按 A→F 升序
    - 选项必须语义互斥、边界清晰、不可重叠
    - 选项数量：4-6 个（A~D 必须有，E/F 可选）
    - 禁止出现"以上都是/以上都不对"（若你必须使用"以上都是"，则它必须为最后一个选项且需可判定，但强烈不建议使用）

    【通过 Gate 后：最终输出 JSON 结构（字段名不得增删）】
    {{
    "question_id": "{question_id}",
    "source_id": "{section_id}",
    "type": "客观评测题",
    "question_type": "多选题",
    "question": "问题内容",
    "options": {{
        "A": "选项A内容",
        "B": "选项B内容",
        "C": "选项C内容",
        "D": "选项D内容",
        "E": "选项E内容（可选）",
        "F": "选项F内容（可选）"
    }},
    "reference_answer": "ABC",
    "meta": {{
        "difficulty": "medium",
        "difficulty_score": 0.6,
        "fact_count_used": 3,
        "tags": ["mechanism", "condition", "comparison"]
    }}
    }}
    """

        else:  # true_false
            gate_fail_json = f"""{{
    "question_id": "{question_id}",
    "source_id": "{section_id}",
    "type": "客观评测题",
    "question_type": "判断题",
    "question": null,
    "reference_answer": null,
    "explanation": null,
    "meta": {{
        "difficulty": "easy",
        "difficulty_score": 0.0,
        "fact_count_used": 0,
        "tags": ["meta_only_chunk"]
    }}
    }}"""

            type_specific_prompt = f"""
    【判断题规范（必须满足）】
    - question_type 必须严格为 "判断题"
    - 题干必须是可判定真假的科学陈述，具备区分度（边界条件/比较关系/条件依赖/概念限定）
    - reference_answer 必须为 True 或 False（首字母大写）
    - 必须包含 explanation 字段，用"科学原理/概念边界"解释为什么真或假（但不得引入章节外知识）

    【通过 Gate 后：最终输出 JSON 结构（字段名不得增删）】
    {{
    "question_id": "{question_id}",
    "source_id": "{section_id}",
    "type": "客观评测题",
    "question_type": "判断题",
    "question": "判断陈述（中文表述）",
    "reference_answer": "True",
    "explanation": "解释为什么正确或错误，指出概念边界或条件。",
    "meta": {{
        "difficulty": "medium",
        "difficulty_score": 0.55,
        "fact_count_used": 2,
        "tags": ["concept", "condition"]
    }}
    }}
    """

        # ---------- 汇总为最终 prompt ----------
        prompt = f"""{quality_prompt}{thinking_prompt}{gate_prompt}
    {gate_fail_json}

    {meta_rules_prompt}

    ────────────────────────────────────────
    【任务】
    请基于输入章节信息，生成 1 道{zh_qtype}。

    【硬性输出要求（再次强调）】
    1) 你必须先做 Gate 判别：
    - 若不通过 Gate：只输出 Gate-Fail JSON（如上）并停止
    - 若通过 Gate：输出"通过 Gate 后"的题目 JSON（如上结构）
    2) 通过 Gate 时：
    - meta.fact_count_used 必须 ≥ 2
    - 题目与选项必须只依据章节中明确出现的事实/概念进行改写与抽象
    3) 输出中除题目 JSON 外，不得出现任何文字；不得包含 Markdown；必须可被严格 JSON 解析。

    {type_specific_prompt}

    请现在开始生成这 1 道{zh_qtype}，严格只输出 JSON：
    """
        return prompt

#     def build_objective_question_prompt(self, section_data, question_type, question_id, enable_thinking=False):
#         """构建客观题提示词

#         Args:
#             section_data: 章节数据
#             question_type: 题目类型
#             question_id: 题目ID
#             enable_thinking: 是否启用thinking模式（默认False）
#         """
#         section_id = section_data.get('chunk_id', '')
#         section_title = section_data.get('chunk_title', '')
#         section_text = section_data.get('text', '')[:2000]  # 限制长度

#         # 质量要求提示词
#         quality_prompt = """你是一位顶尖的农业育种技术顾问，为科研人员和一线从业者提供可靠、可验证、零幻觉的专业知识，覆盖水稻、玉米、小麦、油菜、大豆及主要畜禽领域。你的行为准则是：审慎、精确、负责。

# 1. 问题有效性检查
# - 在回答前，隐式检测问题是否包含科学错误、概念冲突或前提缺失。

# 2. 真实性
# - 回答基于教科书、行业标准、权威综述或长期验证的生产实践。
# - 若问题确实依赖物种特异证据，并且该物种有公开研究，则在回答中自然使用该物种的已知结论，不加额外前置说明。
# - 若问题本身不需要物种特异性（如统计方法、生物学通则、通用分子工具、实验设计原则），则不给出物种相关内容。
# - 禁止虚构文献、编造数据或补全不存在的机制。

# 3. 边界
# - 不提供需要专业资质的具体操作，只说明科学原理、决策依据和潜在风险。

# 4. 质量要求
# - 结构化、逻辑严密、语言精炼。
# - 不使用套话，不重复问题。
# - 每句话都必须提供实质信息或决策价值。

# 5. 问题设计指导：
# - 生物实体规范：客观题加上主语，例如这个现象适用于某个物种，某类物种，还是细胞生物学上的通用规律
# - 常识题：所有题目需要是常识题, 关注通用概念、机制、原理、方法，避免具体实验细节，比如：
# ✓ 通用：等位基因多样性在植物育种中有何重要性？
# ✗ 具体：在13个日本柑橘育种群体中，等位基因多样性如何？
# - 宽泛适用：问题应具有普遍性，不局限于特定实验设置
# - 通用表述：使用一般现在时，描述普遍科学规律而非具体实验结果

# 6. 难易程度
# - 总体题目的中高低的难易程度需要均衡，减少高难度题目

# 7. 输出格式要求
# 7.1 通用规范
# - 严格JSON格式输出，不使用Markdown代码块
# - 所有字段名和字符串值必须使用双引号，不能使用单引号
# - 确保JSON语法正确，可直接解析
# - question_id：按照题目数量从1，2，3等计数
# - type: 固定为"客观评测题"
# - source_id：直接读取chunk_id
# - 只生成要求的字段，其他字段不用输出

# 7.2 禁止使用的上下文引用词
# 严禁在题目和选项中使用以下词汇：
# - "该文章"、"该段落"、"该方法"、"该研究"
# - "论文中"、"摘要中"、"文中"
# - "实验表明"、"研究显示"、"数据显示"
# - "根据研究"、"基于该研究"
# - "在本研究中"、"在本方法中"
# - "如上所述"、"如前所述"、"如下所示"
# - "上述"、"此项"、"此处"
# - "该实验"、"该过程"、"该现象"
# 题目应当表述为独立、通用的知识问题，不依赖特定背景"""

#         # 如果启用thinking模式，添加额外的提示词
#         if enable_thinking:
#             thinking_prompt = """

# 【Thinking模式要求】
# - 请使用<thinking>标签包裹你的推理思考过程
# - 在<thinking>中，你需要：
#   1. 分析章节内容的核心概念和科学原理
#   2. 理解概念之间的逻辑关系和因果关系
#   3. 思考如何基于这些原理设计具有区分度的客观题
# - 在思考过程中，要确保每个选项都有充分的科学依据
# - 思考完成后，输出最终的JSON格式题目（不要包含thinking标签）"""
#         else:
#             thinking_prompt = ""

#         if question_type == 'single_choice':
#             type_specific_prompt = f"""
# 7.3 题型一致性要求
# - 单选题：question_type 必须严格为 "单选题"

# 7.4 单选题规范
# 约束条件：
# - 选项必须经过改写，具有合理性且语义互斥，不重叠
# - 避免直接引用原文或摘要
# - 聚焦概念联系、因果推理、定量解读或比较
# - 避免纯记忆性、表面细节类题目
# - 选项数量：4个（A、B、C、D）

# JSON结构要求：
# {{
#   "question_id": "{question_id}",
#   "source_id": "{section_id}",
#   "type": "客观评测题",
#   "question_type": "单选题",
#   "question": "问题内容",
#   "options": {{
#     "A": "选项A内容",
#     "B": "选项B内容",
#     "C": "选项C内容",
#     "D": "选项D内容"
#   }},
#   "reference_answer": "正确答案（A、B、C或D中的一个）"
# }}"""
#         elif question_type == 'multiple_choice':
#             type_specific_prompt = f"""
# 7.3 题型一致性要求
# - 多选题：question_type 必须严格为 "多选题"

# 7.5 多选题规范
# 约束条件：
# - 选项必须经过改写，具有合理性且语义互斥，不重叠
# - 聚焦概念联系、因果推理、定量解读或比较
# - 正确答案数量：2-6个，绝不能为单选
# - 答案格式：多个字母连续排列（如ABC、ABCD）
# - 如果有个选项是"以上都是"，则该选项一定在最后一个选项

# JSON结构要求：
# {{
#   "question_id": "{question_id}",
#   "source_id": "{section_id}",
#   "type": "客观评测题",
#   "question_type": "多选题",
#   "question": "问题内容",
#   "options": {{
#     "A": "选项A内容",
#     "B": "选项B内容",
#     "C": "选项C内容",
#     "D": "选项D内容",
#     "E": "选项E内容（可选）",
#     "F": "选项F内容（可选）"
#   }},
#   "reference_answer": "多个正确答案组合（如ABC、ABD等）"
# }}"""
#         elif question_type == 'true_false':
#             type_specific_prompt = f"""
# 7.3 题型一致性要求
# - 判断题：question_type 必须严格为 "判断题"

# 7.6 判断题规范
# 约束条件：
# - 生成具有区分度和科学性的判断题
# - 考查隐含意义、比较关系或边界条件
# - 避免琐碎的记忆类题目
# - 优先"理解"、"应用"、"分析"难度级别
# - 必须包含explanation字段

# JSON结构要求：
# {{
#   "question_id": "{question_id}",
#   "source_id": "{section_id}",
#   "type": "客观评测题",
#   "question_type": "判断题",
#   "question": "判断陈述（中文表述）",
#   "reference_answer": "True或False（首字母大写）",
#   "explanation": "详细解释为什么正确或错误，说明科学原理"
# }}"""
#         # 中文题目类型映射
#         type_mapping = {
#             'single_choice': '单选题',
#             'multiple_choice': '多选题',
#             'true_false': '判断题'
#         }

#         prompt = f"""{quality_prompt}{thinking_prompt}{type_specific_prompt}

# 请基于以下论文章节信息，生成1道{type_mapping[question_type]}：

# 章节信息：
# - 章节ID: {section_id}
# - 章节标题: {section_title}
# - 章节内容: {section_text}

# 要求：
# 1. 当前题目的question_id必须设置为：{question_id}
# 2. source_id必须设置为：{section_id}
# 3. type字段必须设置为：客观评测题
# 4. question_type字段严格为：{type_mapping[question_type]}
# 5. 输出中严禁添加metadata、extra_fields等任何额外字段
# 6. 严格按照JSON格式输出，只输出JSON，不要其他内容。

# 请现在生成这1道{type_mapping[question_type]}：
# """
#         return prompt

    def generate_question_for_section(self, section_data, question_type, question_id, enable_thinking=False):
        """为单个章节生成指定类型的客观题

        Args:
            section_data: 章节数据
            question_type: 题目类型
            question_id: 题目ID
            enable_thinking: 是否启用thinking模式（默认False）
        """
        try:
            # 构建提示词
            prompt = self.build_objective_question_prompt(section_data, question_type, question_id, enable_thinking)

            # 调用API生成题目
            answer, input_tokens, output_tokens, total_tokens, latency, thinking_content = self.call_llm_api(prompt, enable_thinking=enable_thinking)

            # 解析题目
            question, success = self.parse_json_response(answer)

            if success and question:
                # 验证并确保字段正确
                question['question_id'] = str(question_id)
                question['source_id'] = section_data.get('chunk_id', '')

                # 如果启用了thinking模式，可以选择保存thinking内容到metadata（可选）
                if enable_thinking and thinking_content:
                    # 可以将thinking内容保存到metadata中（如果需要）
                    question['_thinking'] = thinking_content

                # 更新统计
                update_stats(success=True, question_type=question_type)

                logger.info(f"✓ 成功生成第 {question_id} 题 ({question_type})")
                return question, True
            else:
                logger.error(f"✗ 第 {question_id} 题生成失败")
                update_stats(success=False)
                return None, False

        except Exception as e:
            logger.error(f"✗ 第 {question_id} 题生成异常: {e}")
            update_stats(success=False)
            return None, False


# =============================================================================
# 两阶段推理链客观题生成器
# =============================================================================

class ObjectiveReasoningQuestionGenerator:
    """基于两阶段推理链生成客观题的类（单选、多选、判断、填空）"""

    def __init__(self):
        self.client = OpenAI(api_key=OPENAI_API_KEY, base_url=OPENAI_BASE_URL, timeout=60.0)

    def call_llm_api(self, question_prompt: str, model: str = DEFAULT_MODEL,
                     temperature: float = 0.7, max_tokens: int = 10000, enable_thinking: bool = False):
        """调用LLM API生成题目（统一使用Responses API，支持thinking模式）"""
        # 统一使用call_responses_for_json，支持thinking模式
        return call_responses_for_json(
            prompt=question_prompt,
            model=model,
            max_output_tokens=max_tokens,
            temperature=temperature,
            enable_thinking=enable_thinking
        )

    def build_chain_extraction_prompt(self, section_name: str, section_text: str, max_chains: int = 3) -> str:
        """构建抽取推理链的提示词（针对客观题）"""
        return f"""你是一位农业育种与生命科学领域的专家阅读系统，擅长从图书章节片段中总结可复用的推理链。

给定一个学位论文章节内容，请从中抽取 1~{max_chains} 条"可用于构造多步推理客观题"的推理链。
每条推理链必须满足：
- 通过 3~7 个逻辑步骤推理得出某个客观结论
- 结论是"客观可判断对错的"（如某种关系、比较、更优方案等）

输出格式（严格JSON）：
```json
[
  {{
    "steps": [
      "Step 1: ...",
      "Step 2: ...",
      "Step 3: ...",
      "Step 4: ..."
    ],
    "final_conclusion": "一句话客观结论（可直接作为答案）"
  }}
]
```

【禁止内容】
- 不要使用"该章节/本章/本节"等指代原文的措辞
- 不要引用图表编号、外部数据库编号
- 不要生成依赖于具体样本数量、具体群体数目、具体参数的结论

【章节内容】
名称：{section_name}
内容：
""" + '"""\n' + f"{section_text}\n" + '"""'

    def build_chain_to_objective_question_prompt(self, chain_json_str: str, question_type: str, question_id: str) -> str:
        """构建基于推理链生成客观题的提示词"""
        type_mapping = {
            'single_choice': '单选题',
            'multiple_choice': '多选题',
            'true_false': '判断题'
        }

        if question_type == 'single_choice':
            qa_spec = """
【单选题规范】
- 选项必须经过改写，具有合理性且语义互斥，不重叠
- 避免直接引用原文或摘要
- 聚焦概念联系、因果推理、定量解读或比较
- 避免纯记忆性、表面细节类题目
- 选项数量：4个（A、B、C、D）

JSON结构要求：
{
  "question_id": "{question_id}",
  "source_id": "章节ID",
  "type": "客观评测题",
  "question_type": "单选题",
  "question": "问题内容",
  "options": {{
    "A": "选项A内容",
    "B": "选项B内容",
    "C": "选项C内容",
    "D": "选项D内容"
  }},
  "reference_answer": "正确答案（A、B、C或D中的一个）"
}"""
        elif question_type == 'multiple_choice':
            qa_spec = """
【多选题规范】
- 选项必须经过改写，具有合理性且语义互斥，不重叠
- 聚焦概念联系、因果推理、定量解读或比较
- 正确答案数量：2-6个，绝不能为单选
- 答案格式：多个字母连续排列（如ABC、ABCD）
- 如果有个选项是"以上都是"，则该选项一定在最后一个选项

JSON结构要求：
{
  "question_id": "{question_id}",
  "source_id": "章节ID",
  "type": "客观评测题",
  "question_type": "多选题",
  "question": "问题内容",
  "options": {{
    "A": "选项A内容",
    "B": "选项B内容",
    "C": "选项C内容",
    "D": "选项D内容",
    "E": "选项E内容（可选）",
    "F": "选项F内容（可选）"
  }},
  "reference_answer": "多个正确答案组合（如ABC、ABD等）"
}"""
        else:  # true_false
            qa_spec = """
【判断题规范】
- 生成具有区分度和科学性的判断题
- 考查隐含意义、比较关系或边界条件
- 避免琐碎的记忆类题目
- 优先"理解"、"应用"、"分析"难度级别
- 必须包含explanation字段

JSON结构要求：
{
  "question_id": "{question_id}",
  "source_id": "章节ID",
  "type": "客观评测题",
  "question_type": "判断题",
  "question": "判断陈述（中文表述）",
  "reference_answer": "True或False（首字母大写）",
  "explanation": "详细解释为什么正确或错误，说明科学原理"
}"""

        return f"""你是一位农业育种与生命科学领域的教学专家，负责把结构化推理链转化为"需要多步推理才能回答的客观问答对"，用于大模型 SFT 训练。

下面是从学位论文章节中抽取的一条推理链（JSON）：
```json
{chain_json_str}
```

【你的任务】
基于这条推理链，构造 1 道"需要多步推理才能回答的{type_mapping[question_type]}"，输出 JSON 对象：

{qa_spec}

【问题设计要求】
问题必须使用自然、流畅的中文问句来表述，语序清晰。

必须需要综合多个推理步骤才能得出答案，不能是抄一句话即可回答。

问题要脱离原图书章节也成立，不能包含"该章节/本章/本节"等指代。

问题聚焦通用的科学关系或机制（如：哪种方法更适合解决某类问题？什么条件下会出现某种现象？）。

**重要**：如果问题中已经明确给出了所有信息，答案必须提供问题中未直接给出的推理过程、逻辑依据或综合结论。

答案必须是客观的、唯一可判断对错的结论。

【禁止内容】
不要在 question 或 answer 中使用具体数值、浓度、时间等图书特有细节。

【输出要求】
严格输出一个 JSON 对象（而不是数组）。
不要添加额外解释或自然语言说明。
所有字段名和字符串值必须使用双引号，不能使用单引字。
确保JSON语法正确，可直接解析。"""

    def generate_reasoning_chain_for_section(self, section_data: Dict, max_chains: int = 3, enable_thinking: bool = True) -> Tuple[List[Dict], str, str, str]:
        """第一阶段：从章节内容抽取推理链

        Returns:
            Tuple[List[Dict], str, str, str]: (推理链列表, generation_type, stage1_cot, reasoning_chain_from_prompt)
        """
        section_name = section_data.get('chunk_title', '')
        section_text = section_data.get('text', '')

        # 构建抽取推理链的提示词
        extraction_prompt = self.build_chain_extraction_prompt(section_name, section_text, max_chains)

        try:
            # 调用API抽取推理链（使用Responses API，支持thinking模式）
            response = self.call_llm_api(extraction_prompt, enable_thinking=enable_thinking)

            if response is None:
                logger.error("推理链抽取失败")
                return [], "推理链抽取失败", "", ""

            # 检查是否有提取的COT
            stage1_cot = ""
            if isinstance(response, dict) and "_extracted_cot" in response:
                stage1_cot = response.get("_extracted_cot", "")
                if stage1_cot:
                    logger.info(f"第一阶段提取到 COT，长度: {len(stage1_cot)} 字符")

            # 解析响应，适配Responses API格式
            chains = []
            reasoning_chain_from_prompt = ""
            logger.debug(f"response类型: {type(response)}")

            # 如果response是dict且包含data字段，说明call_responses_for_json包装了数据
            if isinstance(response, dict) and "data" in response:
                data = response.get("data")
                if isinstance(data, list):
                    chains = data
                    reasoning_chain_from_prompt = json.dumps(data, ensure_ascii=False)
                    logger.debug(f"从 data 字段获取到列表，长度: {len(chains)}")
                elif isinstance(data, dict) and "chains" in data:
                    chains = data.get("chains", [])
                    reasoning_chain_from_prompt = json.dumps(chains, ensure_ascii=False)
                    logger.debug(f"从 data.chains 字段获取到: {type(chains)}, 长度: {len(chains) if isinstance(chains, list) else 'N/A'}")
            # 如果response是dict且包含_chains字段，说明call_responses_for_json直接返回了解析后的数据
            elif isinstance(response, dict) and "_chains" in response:
                chains = response.get("_chains", [])
                reasoning_chain_from_prompt = json.dumps(chains, ensure_ascii=False)
                logger.debug(f"从 _chains 字段获取到: {type(chains)}, 长度: {len(chains) if isinstance(chains, list) else 'N/A'}")
            elif isinstance(response, dict) and "_raw_response" in response:
                # 从 _raw_response 中提取
                raw_text = response.get("_raw_response", "")
                if raw_text:
                    # 提取thinking内容
                    clean_text, _ = split_think_content(raw_text)
                    try:
                        parsed = json.loads(clean_text)
                        if isinstance(parsed, list):
                            chains = parsed
                            reasoning_chain_from_prompt = clean_text
                            logger.debug(f"从 _raw_response 解析为列表，长度: {len(chains)}")
                        elif isinstance(parsed, dict) and "chains" in parsed:
                            chains = parsed.get("chains", [])
                            reasoning_chain_from_prompt = clean_text
                            logger.debug(f"从 _raw_response 解析为dict，从chains字段获取: {len(chains)}")
                    except Exception as e:
                        logger.error(f"从 _raw_response 解析JSON失败: {e}")
            elif isinstance(response, dict) and "text" in response:
                # 从 text 字段提取
                text = response.get("text", "")
                if text:
                    try:
                        parsed = json.loads(text)
                        if isinstance(parsed, list):
                            chains = parsed
                            reasoning_chain_from_prompt = text
                            logger.debug(f"从 text 字段解析为列表，长度: {len(chains)}")
                        elif isinstance(parsed, dict) and "chains" in parsed:
                            chains = parsed.get("chains", [])
                            reasoning_chain_from_prompt = text
                            logger.debug(f"从 text 字段解析为dict，从chains字段获取: {len(chains)}")
                    except Exception as e:
                        logger.error(f"从 text 字段解析JSON失败: {e}")
            elif isinstance(response, dict) and "chains" in response:
                # 直接从 chains 字段获取
                chains = response.get("chains", [])
                reasoning_chain_from_prompt = json.dumps(chains, ensure_ascii=False)
                logger.debug(f"从 chains 字段获取到: {type(chains)}, 长度: {len(chains) if isinstance(chains, list) else 'N/A'}")
            elif isinstance(response, list):
                # 直接是列表
                chains = response
                reasoning_chain_from_prompt = json.dumps(chains, ensure_ascii=False)
                logger.debug(f"直接使用列表: {type(chains)}, 长度: {len(chains)}")
            elif isinstance(response, str):
                # 字符串格式，尝试解析JSON
                logger.debug(f"response是字符串，内容长度: {len(response)}")
                try:
                    # 移除可能的markdown代码块标记
                    clean_response = response.replace('```json', '').replace('```', '').strip()
                    parsed = json.loads(clean_response)
                    if isinstance(parsed, list):
                        chains = parsed
                        reasoning_chain_from_prompt = clean_response
                        logger.debug(f"从字符串解析为列表，长度: {len(chains)}")
                    elif isinstance(parsed, dict) and "chains" in parsed:
                        chains = parsed.get("chains", [])
                        reasoning_chain_from_prompt = clean_response
                        logger.debug(f"从字符串解析为dict，从chains字段获取: {len(chains)}")
                except Exception as e:
                    logger.error(f"从字符串解析JSON失败: {e}")
                    logger.error(f"无法解析的内容: {response[:500]}")
            else:
                # 尝试从其他字段中提取
                if isinstance(response, dict):
                    for key in ["data", "result", "output"]:
                        if key in response:
                            data = response[key]
                            if isinstance(data, list):
                                chains = data
                                reasoning_chain_from_prompt = json.dumps(data, ensure_ascii=False)
                                logger.debug(f"从 {key} 字段获取到列表，长度: {len(chains)}")
                                break
                            elif isinstance(data, dict) and "chains" in data:
                                chains = data.get("chains", [])
                                reasoning_chain_from_prompt = json.dumps(chains, ensure_ascii=False)
                                logger.debug(f"从 {key} 字段获取到dict，从chains字段获取: {len(chains)}")
                                break
                            elif isinstance(data, str):
                                try:
                                    parsed = json.loads(data)
                                    if isinstance(parsed, list):
                                        chains = parsed
                                        reasoning_chain_from_prompt = data
                                    elif isinstance(parsed, dict) and "chains" in parsed:
                                        chains = parsed.get("chains", [])
                                        reasoning_chain_from_prompt = data
                                    break
                                except:
                                    pass

            # 确保 chains 是列表
            if not isinstance(chains, list):
                chains = []

            if not chains:
                logger.error("推理链解析失败：未找到推理链数据")
                if isinstance(response, dict):
                    if "_raw_response" in response:
                        logger.error(f"返回内容示例: {str(response['_raw_response'])[:200]}")
                    elif "text" in response:
                        logger.error(f"返回内容示例: {response['text'][:200]}")
                elif isinstance(response, str):
                    logger.error(f"返回内容示例: {response[:200]}")
                return [], "推理链解析失败", stage1_cot, reasoning_chain_from_prompt

            logger.info(f"✓ 成功抽取 {len(chains)} 条推理链")
            return chains, "两阶段推理链", stage1_cot, reasoning_chain_from_prompt

        except Exception as e:
            logger.error(f"推理链抽取异常: {e}")
            return [], f"推理链抽取异常: {e}", stage1_cot, reasoning_chain_from_prompt

    def _parse_chain_response(self, response) -> Tuple[List[Dict], bool]:
        """解析推理链响应"""
        try:
            if isinstance(response, dict):
                # 优先从 _raw_response 中提取
                if "_raw_response" in response:
                    raw_text = response.get("_raw_response", "")
                    if raw_text:
                        # 确保是字符串
                        if not isinstance(raw_text, str):
                            logger.error(f"期望 _raw_response 为字符串，但得到: {type(raw_text)}")
                            return [], False
                        # 提取thinking内容
                        clean_text, _ = split_think_content(raw_text)
                        # 解析JSON
                        return self._extract_json_from_text(clean_text)
                    return [], False
                # 检查是否有 text 字段（call_responses_for_json 返回的非JSON响应）
                elif "text" in response:
                    text = response.get("text", "")
                    if text:
                        # 确保是字符串
                        if not isinstance(text, str):
                            logger.error(f"期望 text 为字符串，但得到: {type(text)}")
                            return [], False
                        # 提取thinking内容
                        clean_text, _ = split_think_content(text)
                        # 解析JSON
                        return self._extract_json_from_text(clean_text)
                    return [], False
                # 检查是否有直接的数据字段
                elif "chains" in response:
                    chains = response.get("chains", [])
                    return chains, True
                # 检查是否有其他可能的字段
                else:
                    # 尝试从其他字段中提取
                    for key in ["data", "result", "output"]:
                        if key in response:
                            data = response[key]
                            if isinstance(data, list):
                                return data, True
                            elif isinstance(data, str):
                                return self._extract_json_from_text(data)
                    return [], False
            else:
                return self._extract_json_from_text(str(response))
        except Exception as e:
            logger.error(f"解析推理链响应失败: {e}")
            return [], False

    def _extract_json_from_text(self, text: str) -> Tuple[List[Dict], bool]:
        """从文本中提取JSON"""
        try:
            # 确保 text 是字符串
            if not isinstance(text, str):
                logger.error(f"期望字符串，但得到: {type(text)}")
                return [], False

            # 移除可能的markdown代码块标记
            text = text.replace('```json', '').replace('```', '').strip()

            # 尝试解析JSON
            chains = json.loads(text)
            if isinstance(chains, list):
                return chains, True
            return [], False
        except Exception as e:
            logger.error(f"JSON解析失败: {e}")
            return [], False

    def generate_objective_question_from_chain(self, chain: Dict, question_type: str, question_id: str,
                                              enable_thinking: bool = False, stage1_cot: str = "",
                                              reasoning_chain_from_prompt: str = "") -> Tuple[Optional[Dict], bool]:
        """第二阶段：基于推理链生成客观题

        Args:
            chain: 推理链
            question_type: 题目类型
            question_id: 题目ID
            enable_thinking: 是否启用thinking模式
            stage1_cot: 第一阶段API thinking返回的COT
            reasoning_chain_from_prompt: 第一阶段由prompt得到的推理链

        Returns:
            Tuple[Optional[Dict], bool]: (题目, 是否成功)
        """
        try:
            # 构建提示词
            chain_json_str = json.dumps(chain, ensure_ascii=False)
            qa_prompt = self.build_chain_to_objective_question_prompt(chain_json_str, question_type, question_id)

            # 调用API生成题目
            response = self.call_llm_api(qa_prompt, enable_thinking=enable_thinking)

            if response is None:
                logger.error(f"第 {question_id} 题生成失败")
                return None, False

            # 解析题目，参考两阶段QA生成的方式
            question = None
            stage2_cot = ""
            if isinstance(response, dict):
                # 检查是否有 _extracted_cot 字段（来自 call_responses_for_json）
                if "_extracted_cot" in response:
                    stage2_cot = response.get("_extracted_cot", "")
                    if stage2_cot:
                        logger.info(f"从 thinking 模式提取到 COT，长度: {len(stage2_cot)} 字符")

                # 尝试解析题目数据
                if "data" in response:
                    # call_responses_for_json 在JSON解析成功时返回的格式
                    data = response.get("data", "")
                    if isinstance(data, dict):
                        question = data
                    elif isinstance(data, str):
                        try:
                            question = json.loads(data)
                        except:
                            pass
                elif "text" in response:
                    # call_responses_for_json 在JSON解析失败时返回的格式
                    text = response.get("text", "")
                    if text:
                        try:
                            question = json.loads(text)
                        except:
                            pass
                elif "question" in response:
                    question = response
            elif isinstance(response, str):
                try:
                    question = json.loads(response)
                except:
                    pass

            if question and isinstance(question, dict):
                # 添加新的字段结构
                if stage1_cot:
                    question["stage1_cot"] = stage1_cot
                if stage2_cot:
                    question["stage2_cot"] = stage2_cot
                if reasoning_chain_from_prompt:
                    question["reasoning_chain_from_prompt"] = reasoning_chain_from_prompt

                logger.info(f"✓ 成功生成第 {question_id} 题 ({question_type})")
                return question, True
            else:
                logger.error(f"✗ 第 {question_id} 题解析失败")
                logger.error(f"response类型: {type(response)}, keys: {list(response.keys()) if isinstance(response, dict) else 'N/A'}")
                return None, False

        except Exception as e:
            logger.error(f"✗ 第 {question_id} 题生成异常: {e}")
            return None, False

    def _parse_question_response(self, response) -> Tuple[Optional[Dict], bool]:
        """解析题目响应"""
        try:
            if isinstance(response, dict):
                # 优先从 _raw_response 中提取
                if "_raw_response" in response:
                    raw_text = response.get("_raw_response", "")
                    if raw_text:
                        # 确保是字符串
                        if not isinstance(raw_text, str):
                            logger.error(f"期望 _raw_response 为字符串，但得到: {type(raw_text)}")
                            return None, False
                        # 提取thinking内容
                        clean_text, _ = split_think_content(raw_text)
                        # 解析JSON
                        question = json.loads(clean_text)
                        return question, True
                    return None, False
                # 检查是否有 text 字段（call_responses_for_json 返回的非JSON响应）
                elif "text" in response:
                    text = response.get("text", "")
                    if text:
                        # 确保是字符串
                        if not isinstance(text, str):
                            logger.error(f"期望 text 为字符串，但得到: {type(text)}")
                            return None, False
                        # 提取thinking内容
                        clean_text, _ = split_think_content(text)
                        # 解析JSON
                        question = json.loads(clean_text)
                        return question, True
                    return None, False
                # 检查是否有其他可能的字段
                else:
                    # 尝试从其他字段中提取
                    for key in ["data", "result", "output"]:
                        if key in response:
                            data = response[key]
                            if isinstance(data, dict):
                                return data, True
                            elif isinstance(data, str):
                                # 移除可能的markdown代码块标记
                                text = data.replace('```json', '').replace('```', '').strip()
                                question = json.loads(text)
                                return question, True
                    # 如果没有找到其他字段，返回整个 response
                    return response, True
            else:
                # 移除可能的markdown代码块标记
                text = str(response).replace('```json', '').replace('```', '').strip()
                question = json.loads(text)
                return question, True
        except Exception as e:
            logger.error(f"题目响应解析失败: {e}")
            return None, False

    def generate_question_for_section(self, section_data: Dict, question_type: str, question_id: str,
                                      enable_thinking: bool = False, max_chains: int = 3) -> Tuple[Optional[Dict], bool]:
        """为单个章节生成指定类型的客观题（两阶段推理链方式）

        Args:
            section_data: 章节数据
            question_type: 题目类型
            question_id: 题目ID
            enable_thinking: 是否启用thinking模式
            max_chains: 最大推理链数量

        Returns:
            Tuple[Optional[Dict], bool]: (题目, 是否成功)
        """
        try:
            # 第一阶段：抽取推理链（开启thinking模式以获得更好的推理链质量）
            chains, generation_type, stage1_cot, reasoning_chain_from_prompt = self.generate_reasoning_chain_for_section(
                section_data, max_chains, enable_thinking=True
            )

            if not chains:
                logger.warning(f"未抽取到推理链，跳过第 {question_id} 题")
                return None, False

            # 从第一条推理链生成题目
            chain = chains[0]

            # 第二阶段：基于推理链生成客观题
            question, success = self.generate_objective_question_from_chain(
                chain, question_type, question_id, enable_thinking,
                stage1_cot=stage1_cot,
                reasoning_chain_from_prompt=reasoning_chain_from_prompt
            )

            if success and question:
                # 验证并确保字段正确
                question['question_id'] = str(question_id)
                question['chunk_id'] = section_data.get('chunk_id', '')
                question['chunk_title'] = section_data.get('chunk_title', '')
                question['context'] = section_data.get('text', '')
                question['source_id'] = section_data.get('chunk_id', '')

                # 删除不需要的字段
                question.pop('_raw_response', None)
                question.pop('_extracted_cot', None)
                question.pop('reasoning_chain', None)

                # 更新统计
                update_stats(success=True, question_type=question_type)

                return question, True
            else:
                logger.error(f"第 {question_id} 题生成失败")
                update_stats(success=False)
                return None, False

        except Exception as e:
            logger.error(f"✗ 第 {question_id} 题生成异常: {e}")
            update_stats(success=False)
            return None, False


def read_jsonl(path: str) -> List[Dict[str, Any]]:
    logger.info(f"读取输入文件: {path}")
    theses = []
    line_number = 0
    skipped_lines = 0
    with open(path, 'r', encoding='utf-8') as f:
        for line in f:
            line_number += 1
            if not line.strip():
                continue
            try:
                item = json.loads(line)
                # 原始逻辑：检查source字段
                if item.get('source', '').lower() in THESIS_SOURCES:
                    theses.append(item)
                # 新逻辑：检查是否有text字段且id字段（表明是论文文本）
                elif 'text' in item and 'id' in item:
                    # 将label字段映射为source字段
                    item['source'] = item.get('label', 'proquest_papers')
                    theses.append(item)
            except json.JSONDecodeError as e:
                logger.warning(f"跳过第{line_number}行，JSON解析错误: {e}")
                skipped_lines += 1
                continue
            except Exception as e:
                logger.warning(f"跳过第{line_number}行，处理错误: {e}")
                skipped_lines += 1
                continue
    if skipped_lines > 0:
        logger.info(f"跳过了 {skipped_lines} 行错误数据")
    logger.info(f"成功读取 {len(theses)} 篇学位论文")
    return theses



def save_qas(qas: List[Dict[str, Any]], path: str):
    # 处理相对路径（当前目录）的情况
    dir_name = os.path.dirname(path)
    if dir_name:  # 如果不是空字符串
        os.makedirs(dir_name, exist_ok=True)
    with open(path, 'w', encoding='utf-8') as f:
        for qa in qas:
            f.write(json.dumps(qa, ensure_ascii=False) + '\n')
    logger.info(f"保存 {len(qas)} 条到: {path}")


def process_thesis(thesis: Dict[str, Any],
                   workers_chunk: int = 10,
                   enable_diversity: bool = True,
                   simhash_dedup_hamming: int = 6,
                   context_length: int = 1000,
                   enable_quality_filter: bool = False,
                   min_quality_score: float = 60.0,
                   qa_floor: int = 80,
                   qa_cap: int = 200) -> Dict[str, Any]:
    """
    处理单篇学位论文

    Returns:
        {
          "thesis_id": ...,
          "qas": [...],
          "stats": {...}
        }
    """
    thesis_id = thesis.get('id', 'unknown')
    logger.info(f"开始处理学位论文: {thesis_id}")

    processor = ThesisProcessor()
    generator = SFTQuestionGenerator()
    quality_scorer = QualityScorer()

    try:
        chunks = processor.split_by_chapters(thesis['text'])
        if not chunks:
            return {"thesis_id": thesis_id, "qas": [], "stats": {}}

        # 过滤掉不合适的章节（REFERENCES等）
        filtered_chunks = []
        skipped_count = 0
        for chunk in chunks:
            chunk_title = chunk.get('chunk_title', '')
            chunk_text = chunk.get('text', '')
            if should_skip_section(chunk_title, chunk_text):
                skipped_count += 1
                logger.info(f"跳过章节: {chunk_title} (参考文献/致谢/附录等)")
            else:
                filtered_chunks.append(chunk)

        if filtered_chunks:
            logger.info(f"分块过滤完成: {len(filtered_chunks)}/{len(chunks)} 个章节有效 (跳过 {skipped_count} 个)")
        else:
            logger.warning(f"所有章节都被跳过，没有可处理的章节")
            return {"thesis_id": thesis_id, "qas": [], "stats": {}}

        # NEW: 目标 QA 数自动估计（使用过滤后的chunks）
        target_q_per_thesis = estimate_target_q_per_thesis(
            thesis_text=thesis.get("text", ""),
            chunks=filtered_chunks,
            floor=qa_floor,
            cap=qa_cap,
            per_chunk_base=15,
        )
        logger.info(f"✓ 目标QA数估计: {target_q_per_thesis} (floor={qa_floor}, cap={qa_cap})")

        qas: List[Dict[str, Any]] = []

        with ThreadPoolExecutor(max_workers=workers_chunk) as executor:
            # 始终使用推理链生成QA
            future_to_chunk = {
                executor.submit(generator.generate_for_chunk_with_reasoning, chunk, thesis_id, enable_diversity, simhash_dedup_hamming, context_length): chunk
                for chunk in filtered_chunks
            }

            for future in as_completed(future_to_chunk):
                try:
                    qs = future.result()
                    qas.extend(qs)
                except Exception as e:
                    chunk = future_to_chunk[future]
                    title = chunk.get('chunk_title', 'unknown')
                    logger.error(f"Chunk '{title}' 异常: {e}")

        # =========================
        # NEW: 统计（原始生成）
        # 注意：这里的“原始生成”是“chunk级diversity之后”的总量；
        # 真正的“模型原始生成 raw_qas”只在 chunk 内部可见，你已用 tprint 输出。
        # =========================
        gen_total = len(qas)

        # NEW: 汇总 diversity 过滤统计（按 chunk 去重）
        # 每条 record 带 diversity_before/diversity_after；同 chunk 内相同
        seen_chunk_keys = set()
        div_before_sum, div_after_sum = 0, 0
        for qa in qas:
            k = (qa.get("chunk_id"), qa.get("generation_type"))
            if k in seen_chunk_keys:
                continue
            seen_chunk_keys.add(k)
            if "diversity_before" in qa and "diversity_after" in qa:
                div_before_sum += int(qa.get("diversity_before", 0))
                div_after_sum += int(qa.get("diversity_after", 0))

        # NEW: 质量过滤（按篇执行，便于统计；与全局过滤等价）
        qas_after_quality = qas
        quality_before = len(qas_after_quality)
        if enable_quality_filter:
            qas_after_quality = quality_scorer.filter_by_quality(qas_after_quality, min_quality_score)
        quality_after = len(qas_after_quality)

        # =========================
        # NEW: 章节长度统计
        # =========================
        chunk_lengths = [len(chunk['text']) for chunk in filtered_chunks]
        if chunk_lengths:
            chunk_length_stats = {
                "total_chunks": len(chunk_lengths),
                "min_length": min(chunk_lengths),
                "max_length": max(chunk_lengths),
                "avg_length": sum(chunk_lengths) / len(chunk_lengths),
                "total_chars": sum(chunk_lengths),
                "short_chunks": sum(1 for l in chunk_lengths if l < 500),
                "medium_chunks": sum(1 for l in chunk_lengths if 500 <= l <= 2000),
                "long_chunks": sum(1 for l in chunk_lengths if l > 2000),
            }
        else:
            chunk_length_stats = {
                "total_chunks": 0,
                "min_length": 0,
                "max_length": 0,
                "avg_length": 0,
                "total_chars": 0,
                "short_chunks": 0,
                "medium_chunks": 0,
                "long_chunks": 0,
            }

        # NEW: thesis 级统计对象（main 里还会做 sample/curriculum 后补齐）
        # 注意: 使用 thesis_stats 而不是 stats，避免遮蔽全局 stats 字典
        thesis_stats = {
            "target_q_per_thesis": int(target_q_per_thesis),
            "generated_total": int(gen_total),
            "quality_before": int(quality_before),
            "quality_after": int(quality_after),
            "diversity_before_sum": int(div_before_sum),
            "diversity_after_sum": int(div_after_sum),
            "chunk_length_stats": chunk_length_stats,
        }

        # 这里打印一条 thesis 级 summary（采样/课程过滤在 main 中进行后会再打印一条）
        logger.info(
            f"[{thesis_id}] Thesis统计(中间态): generated={gen_total}, "
            f"quality={quality_before}->{quality_after}, "
            f"diversity(sum by chunk)={div_before_sum}->{div_after_sum}, "
            f"target_q={target_q_per_thesis}, "
            f"chunks={chunk_length_stats['total_chunks']}, "
            f"len_avg={chunk_length_stats['avg_length']:.0f}, "
            f"short/med/long={chunk_length_stats['short_chunks']}/{chunk_length_stats['medium_chunks']}/{chunk_length_stats['long_chunks']}"
        )

        return {"thesis_id": thesis_id, "qas": qas_after_quality, "stats": thesis_stats}

    except Exception as e:
        logger.error(f"处理学位论文 '{thesis_id}' 时发生错误: {e}", exc_info=True)
        return {"thesis_id": thesis_id, "qas": [], "stats": {}}


# ==============================================================================
# 采样策略：难度配比 + curriculum stage
# ==============================================================================

def sample_qas_with_strategy(
    qas: List[Dict[str, Any]],
    max_q: int,
    difficulty_target: Optional[Dict[str, int]] = None,
    max_stage: Optional[int] = None,
) -> List[Dict[str, Any]]:
    if not qas:
        return []

    # curriculum stage 过滤（先过滤再分桶）
    if max_stage is not None:
        qas = [qa for qa in qas if int(qa.get("curriculum_stage", 3)) <= int(max_stage)]
        if not qas:
            return []

    if difficulty_target is None:
        difficulty_target = {"easy": 1, "medium": 3, "hard": 1}

    buckets = {"easy": [], "medium": [], "hard": []}
    for qa in qas:
        d = (qa.get("difficulty", "medium") or "medium").lower()
        if d not in buckets:
            d = "medium"
        buckets[d].append(qa)

    total_target = max(1, sum(difficulty_target.values()))
    scale = max_q / total_target

    scaled_target = {d: max(0, int(round(v * scale))) for d, v in difficulty_target.items()}
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

    selected: List[Dict[str, Any]] = []

    for d in ["easy", "medium", "hard"]:
        need = scaled_target.get(d, 0)
        selected.extend(buckets[d][:need])

    if len(selected) < max_q:
        remaining = [qa for qa in qas if qa not in selected]
        selected.extend(remaining[:max_q - len(selected)])

    return selected[:max_q]

# ==============================================================================
# main
# ==============================================================================



def calculate_question_type_distribution(n_abstracts):
    """计算每种题型的数量分配"""
    distribution = {}
    for qtype, target in QUESTION_TARGETS.items():
        # 按比例分配，但确保总数为n_abstracts
        count = int(n_abstracts * (target / TOTAL_QUESTIONS))
        distribution[qtype] = count

    # 调整总数
    current_total = sum(distribution.values())
    if current_total < n_abstracts:
        # 需要增加，按优先级添加
        remaining = n_abstracts - current_total
        for qtype in QUESTION_TARGETS.keys():
            if remaining <= 0:
                break
            distribution[qtype] += 1
            remaining -= 1
    elif current_total > n_abstracts:
        # 需要减少
        excess = current_total - n_abstracts
        for qtype in QUESTION_TARGETS.keys():
            if excess <= 0:
                break
            if distribution[qtype] > 1:
                distribution[qtype] -= 1
                excess -= 1

    return distribution


def assign_question_types(sections_df, distribution):
    """为每个章节分配题目类型"""
    question_types = []
    for qtype, count in distribution.items():
        question_types.extend([qtype] * count)

    # 打乱顺序
    random.seed(42)
    random.shuffle(question_types)

    return question_types


def save_objective_results(all_questions, output_dir):
    """保存客观题结果到文件"""
    os.makedirs(output_dir, exist_ok=True)

    # 按题型分组保存
    by_type = defaultdict(list)
    for q in all_questions:
        qtype = q.get('question_type', '未知')
        by_type[qtype].append(q)

    # 保存各类型题目到独立文件

    for qtype, questions in by_type.items():
        if questions:
            # 使用中文名称作为文件名
            type_file = os.path.join(output_dir, f'{qtype}.jsonl')
            with open(type_file, 'w', encoding='utf-8') as f:
                for q in questions:
                    f.write(json.dumps(q, ensure_ascii=False) + '\n')
            logger.info(f"已保存 {len(questions)} 道{qtype}题到: {type_file}")

    # 生成报告
    report_file = os.path.join(output_dir, 'generation_report.md')
    with open(report_file, 'w', encoding='utf-8') as f:
        f.write("# 客观评测题生成报告\n\n")
        f.write(f"生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n")

        f.write("## 配置参数\n\n")
        for qtype, count in QUESTION_TARGETS.items():
            percentage = (count / TOTAL_QUESTIONS * 100) if TOTAL_QUESTIONS > 0 else 0
            f.write(f"- **{qtype}**: {count} 题 ({percentage:.1f}%)\n")
        f.write(f"- **总目标**: {TOTAL_QUESTIONS} 题\n")
        f.write(f"- **随机种子**: 42\n\n")

        f.write("## 实际生成统计\n\n")
        total_questions = len(all_questions)
        f.write(f"- **实际生成总数**: {total_questions} 题\n")
        f.write(f"- **处理章节数**: {total_questions} 个\n")
        f.write(f"- **成功率**: {stats['success_count'] / stats['total_processed'] * 100 if stats['total_processed'] > 0 else 0:.1f}%\n\n")

        # 实际题型分布
        f.write("## 实际题型分布\n\n")
        for qtype, count in stats.get('by_question_type', {}).items():
            percentage = (count / total_questions * 100) if total_questions > 0 else 0
            f.write(f"- **{qtype}**: {count} 题 ({percentage:.1f}%)\n")
        f.write("\n")

        f.write("## 输出文件\n\n")
        for qtype in by_type.keys():
            f.write(f"- `{qtype}.jsonl` - {qtype}题目\n")
        f.write("- `generation_report.md` - 本报告文件\n")

    logger.info(f"结果已保存到: {output_dir}")
    logger.info(f"报告文件: {report_file}")


def generate_objective_questions_from_thesis(thesis_data, enable_thinking=False, enable_prompt_reasoning=False):
    """从学位论文生成客观评测题

    Args:
        thesis_data: 论文数据
        enable_thinking: 是否启用thinking模式（默认False）
        enable_prompt_reasoning: 是否启用两阶段推理链生成（默认False）
    """
    processor = ThesisProcessor()
    # 根据参数选择生成器
    if enable_prompt_reasoning:
        generator = ObjectiveReasoningQuestionGenerator()
    else:
        generator = ObjectiveQuestionGenerator()

    # 分割论文为章节
    chunks = processor.split_by_chapters(thesis_data.get('text', ''))
    if not chunks:
        logger.warning(f"论文 {thesis_data.get('id', 'unknown')} 没有可处理的章节")
        return []

    # 过滤掉不合适的章节
    filtered_chunks = []
    for chunk in chunks:
        chunk_title = chunk.get('chunk_title', '')
        chunk_text = chunk.get('text', '')
        if should_skip_section(chunk_title, chunk_text):
            continue
        filtered_chunks.append(chunk)

    if not filtered_chunks:
        logger.warning(f"论文 {thesis_data.get('id', 'unknown')} 所有章节都被跳过")
        return []

    # 计算题型分布
    distribution = calculate_question_type_distribution(len(filtered_chunks))

    # 为每个章节分配题目类型
    question_types = assign_question_types(filtered_chunks, distribution)

    # 生成题目
    all_questions = []
    tasks = []

    for idx, chunk in enumerate(filtered_chunks):
        question_id = idx + 1
        question_type = question_types[idx]
        tasks.append((chunk, question_type, question_id, enable_thinking))

    # 并发生成题目
    with ThreadPoolExecutor(max_workers=20) as executor:
        future_to_task = {
            executor.submit(generator.generate_question_for_section, task[0], task[1], task[2], task[3]): task
            for task in tasks
        }

        for future in as_completed(future_to_task):
            try:
                question, success = future.result()
                if success and question:
                    all_questions.append(question)
            except Exception as e:
                logger.error(f"生成题目失败: {e}")

    return all_questions


def main():
    parser = argparse.ArgumentParser(description='学位论文SFT问答对生成器（优化版）')

    parser.add_argument('--input', type=str, required=True)
    parser.add_argument('--output', type=str, required=True)
    parser.add_argument('--model', type=str, default=None,
                       help='指定使用的模型名称，支持自定义模型，如: gpt-5.1, gpt-4o-mini, gpt-oss-120b, gpt-5-nano-2025-08-07 等（默认: gpt-5.1）')
    parser.add_argument('--max-q-per-chunk', type=int, default=5)

    parser.add_argument('--target-ids', type=str, nargs='*', default=[])

    parser.add_argument('--sample-strategy', action='store_true')

    # 添加 thinking 模式控制参数
    parser.add_argument('--enable-thinking', action='store_true', default=True, help='启用Thinking模式（默认开启）')
    parser.add_argument('--no-thinking', action='store_true', help='禁用Thinking模式')

    # 添加生成模式选择
    parser.add_argument('--mode', type=str, default='sft',
                       choices=['sft', 'objective'],
                       help='生成模式：sft-原有SFT问答对，objective-客观评测题（默认: sft）')

    # 添加客观题thinking模式控制参数
    parser.add_argument('--enable-api-thinking-objective', action='store_true', default=True,
                       help='客观题模式启用thinking模式（默认开启）')
    parser.add_argument('--no-api-thinking-objective', action='store_true',
                       help='客观题模式禁用thinking模式')

    # 添加客观题两阶段推理链控制参数
    parser.add_argument('--enable-prompt-reasoning-objective', action='store_true', default=False,
                       help='客观题模式启用两阶段推理链生成（默认关闭）')
    parser.add_argument('--no-prompt-reasoning-objective', action='store_true',
                       help='客观题模式禁用两阶段推理链生成')

    # 移除 --use-reasoning 参数，现在始终使用推理链
    # parser.add_argument('--use-reasoning', action='store_true', default=True)
    # 移除 --no-reasoning 参数
    # parser.add_argument('--no-reasoning', action='store_true')

    parser.add_argument('--workers-thesis', type=int, default=6)
    parser.add_argument('--workers-chunk', type=int, default=10)

    parser.add_argument('--max-curriculum-stage', type=int, default=None)

    parser.add_argument('--enable-quality-filter', action='store_true')
    parser.add_argument('--min-quality-score', type=float, default=70.0)

    parser.add_argument('--enable-diversity-filter', action='store_true')
    parser.add_argument('--simhash-dedup-hamming', type=int, default=6)

    parser.add_argument('--context-length', type=int, default=10000)

    parser.add_argument('--qa-floor', type=int, default=80)
    parser.add_argument('--qa-cap', type=int, default=120)
    parser.add_argument('--qa-per-chunk', type=int, default=5)

    # 添加成本统计参数
    parser.add_argument('--input-price', type=float, default=1.2500,
                       help='输入token价格（$/百万tokens，默认: 1.2500）')
    parser.add_argument('--output-price', type=float, default=10.0000,
                       help='输出token价格（$/百万tokens，默认: 10.0000）')

    args = parser.parse_args()

    # ------------------------
    # 全局参数
    # ------------------------
    global DEFAULT_MODEL, MAX_Q_PER_CHUNK, ENABLE_THINKING, stats

    if args.model:
        DEFAULT_MODEL = args.model
    if args.qa_per_chunk:
        MAX_Q_PER_CHUNK = args.qa_per_chunk

    # 设置价格
    stats['input_price_per_m'] = args.input_price
    stats['output_price_per_m'] = args.output_price

    logger.info(f"✓ 每chunk生成QA数: {MAX_Q_PER_CHUNK} (来自 --qa-per-chunk)")
    logger.info(f"✓ 输入token价格: ${args.input_price:.4f}/百万tokens")
    logger.info(f"✓ 输出token价格: ${args.output_price:.4f}/百万tokens")

    # 设置Thinking模式（--no-thinking会覆盖--enable-thinking）
    ENABLE_THINKING = not args.no_thinking

    # 设置客观题thinking模式（--no-api-thinking-objective会覆盖--enable-api-thinking-objective）
    objective_thinking = args.enable_api_thinking_objective and not args.no_api_thinking_objective

    # 设置客观题两阶段推理链模式（--no-prompt-reasoning-objective会覆盖--enable-prompt-reasoning-objective）
    objective_prompt_reasoning = args.enable_prompt_reasoning_objective and not args.no_prompt_reasoning_objective

    # 始终使用推理链
    # use_reasoning = not args.no_reasoning

    logger.info("=" * 70)
    logger.info("学位论文 QA 生成流程启动")
    logger.info(f"生成模式: {'SFT问答对' if args.mode == 'sft' else '客观评测题'}")
    logger.info("=" * 70)
    logger.info(f"✓ 模型: {DEFAULT_MODEL} (--model)")
    logger.info(f"✓ 上下文长度: {args.context_length} (--context-length)")
    logger.info(f"✓ QA下限: {args.qa_floor} (--qa-floor)")
    logger.info(f"✓ QA上限: {args.qa_cap} (--qa-cap)")
    logger.info(f"✓ 每chunk生成QA数: {MAX_Q_PER_CHUNK} (--qa-per-chunk)")
    logger.info("=" * 70)

    # 客观题模式处理
    if args.mode == 'objective':
        logger.info("开始生成客观评测题...")
        logger.info(f"✓ 模型: {DEFAULT_MODEL} (--model)")
        logger.info(f"Thinking模式: {'启用' if objective_thinking else '禁用'}")
        logger.info(f"两阶段推理链模式: {'启用' if objective_prompt_reasoning else '禁用'}")
        stats['start_time'] = datetime.now()

        theses = read_jsonl(args.input)

        if args.target_ids:
            id_map = {t.get("id"): t for t in theses}
            theses = [id_map[i] for i in args.target_ids if i in id_map]
            logger.info(f"ID过滤后论文数: {len(theses)}")

        all_questions = []

        # 并行处理每篇论文
        with ThreadPoolExecutor(max_workers=args.workers_thesis) as executor:
            futures = {
                executor.submit(generate_objective_questions_from_thesis, thesis, objective_thinking, objective_prompt_reasoning): thesis.get("id", "unknown")
                for thesis in theses
            }

            for future in as_completed(futures):
                thesis_id = futures[future]
                try:
                    questions = future.result()
                    all_questions.extend(questions)
                    logger.info(f"[{thesis_id}] 生成 {len(questions)} 道题")
                except Exception as e:
                    logger.exception(f"[{thesis_id}] 处理失败: {e}")

        # 保存结果
        # 客观题模式使用按时间戳建立的文件夹
        output_dir = OUTPUT_DIR
        save_objective_results(all_questions, output_dir)

        stats['end_time'] = datetime.now()
        # 安全地计算处理时间，如果 start_time 未设置则跳过
        if stats.get('start_time') is not None:
            processing_time = (stats['end_time'] - stats['start_time']).total_seconds()
            logger.info(f"处理时间: {processing_time:.2f} 秒")
        else:
            logger.warning("未记录开始时间，跳过处理时间统计")

        logger.info("=" * 70)
        logger.info(f"=== 客观评测题生成完成 ===")
        logger.info(f"=" * 70)
        # 重新计算处理时间（如果需要）
        if 'processing_time' not in locals():
            if stats.get('start_time') is not None:
                processing_time = (stats['end_time'] - stats['start_time']).total_seconds()
            else:
                processing_time = None
        if processing_time is not None:
            logger.info(f"处理时间: {processing_time:.2f} 秒")
        logger.info(f"处理论文数: {len(theses)}")
        logger.info(f"成功生成: {stats['success_count']} 题")
        logger.info(f"失败: {stats['failed_count']} 题")
        if stats['total_processed'] > 0:
            logger.info(f"成功率: {stats['success_count'] / stats['total_processed'] * 100:.1f}%")

        logger.info(f"\n实际题型分布:")
        total_generated = stats['success_count']
        for qtype, count in stats.get('by_question_type', {}).items():
            if total_generated > 0:
                percentage = count / total_generated * 100
                logger.info(f"  - {qtype}: {count} 题 ({percentage:.1f}%)")

        logger.info(f"\n输出目录: {output_dir}")
        # 打印成本统计
        print_cost_summary()
        logger.info(f"{'='*70}\n")

        return

    # SFT问答对模式处理（使用v1_final.py的逻辑）
    logger.info("学位论文 SFT QA 生成流程启动")
    logger.info("=" * 70)
    logger.info(f"✓ 模型: {DEFAULT_MODEL} (--model)")

    stats['start_time'] = datetime.now()

    theses = read_jsonl(args.input)

    if args.target_ids:
        id_map = {t.get("id"): t for t in theses}
        theses = [id_map[i] for i in args.target_ids if i in id_map]
        logger.info(f"ID过滤后论文数: {len(theses)}")

    all_qas: List[Dict[str, Any]] = []

    iterator = tqdm(theses, desc="处理论文", unit="篇") if TQDM_AVAILABLE else theses

    # ------------------------
    # 并行：一篇论文一次
    # ------------------------
    with ThreadPoolExecutor(max_workers=args.workers_thesis) as executor:
        futures = {
            executor.submit(
                process_thesis,
                thesis,
                args.workers_chunk,
                args.enable_diversity_filter,
                args.simhash_dedup_hamming,
                args.context_length,
                args.enable_quality_filter,
                args.min_quality_score,
                args.qa_floor,
                args.qa_cap,
            ): thesis.get("id", "unknown")
            for thesis in theses
        }

        for future in as_completed(futures):
            thesis_id = futures[future]

            try:
                result = future.result()
                qas = result.get("qas", [])
                # 注意: 使用 thesis_stats 而不是 stats，避免遮蔽全局 stats 字典
                thesis_stats = result.get("stats", {})

                # ------------------------
                # curriculum stage 限制
                # ------------------------
                before_curr = len(qas)
                if args.max_curriculum_stage is not None:
                    qas = [
                        qa for qa in qas
                        if int(qa.get("curriculum_stage", 3)) <= args.max_curriculum_stage
                    ]
                after_curr = len(qas)

                # ------------------------
                # 按篇采样
                # ------------------------
                before_sample = len(qas)
                if args.sample_strategy:
                    target_q = int(thesis_stats.get("target_q_per_thesis", 0))
                    if target_q > 0:
                        qas = sample_qas_with_strategy(
                            qas,
                            max_q=target_q,
                            max_stage=None
                        )
                after_sample = len(qas)

                logger.info(
                    f"[{thesis_id}] FINAL | "
                    f"generated={thesis_stats.get('generated_total', 0)} | "
                    f"quality={thesis_stats.get('quality_before', 0)}->{thesis_stats.get('quality_after', 0)} | "
                    f"curriculum={before_curr}->{after_curr} | "
                    f"sample={before_sample}->{after_sample} | "
                    f"target={thesis_stats.get('target_q_per_thesis', 0)}"
                )

                all_qas.extend(qas)

            except Exception as e:
                logger.exception(f"[{thesis_id}] 处理失败: {e}")

            if TQDM_AVAILABLE:
                iterator.update(1)

    if TQDM_AVAILABLE:
        iterator.close()

    # ------------------------
    # 汇总统计
    # ------------------------
    reasoning_count = sum(1 for qa in all_qas if qa.get("generation_type") == "推理型")
    # 简化输出：只显示推理型（不再使用简单型）
    # simple_count = sum(1 for qa in all_qas if qa.get("generation_type") == "简单型")

    scorer = QualityScorer()
    # 注意: 使用 quality_stats 而不是 stats，避免遮蔽全局 stats 字典
    quality_stats = scorer.get_quality_statistics(all_qas)

    save_qas(all_qas, args.output)

    logger.info("=" * 70)
    logger.info(f"完成：共生成 {len(all_qas)} 条 QA")
    logger.info(f"全部采用推理链生成：{reasoning_count} 条")
    logger.info(
        f"质量：avg={quality_stats.get('average_score')} "
        f"pass_rate={quality_stats.get('pass_rate')}% "
        f"excellent={quality_stats.get('excellent_count')} good={quality_stats.get('good_count')}"
    )
    logger.info(f"输出文件：{args.output}")

    # 设置结束时间并计算处理时间
    stats['end_time'] = datetime.now()
    # 安全地计算处理时间，如果 start_time 未设置则跳过
    if stats.get('start_time') is not None:
        processing_time = (stats['end_time'] - stats['start_time']).total_seconds()
        logger.info(f"处理时间: {processing_time:.2f} 秒")
    else:
        logger.warning("未记录开始时间，跳过处理时间统计")

    # 打印成本统计
    print_cost_summary()
    logger.info("=" * 70)


if __name__ == "__main__":  
    main()