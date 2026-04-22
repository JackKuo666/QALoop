#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
基因文献问答对生成器 (Gene Literature QA Generator)
================================================================================

功能概述：
---------
从 JSON 格式的基因文献数据中，使用大语言模型自动生成高质量
的问答对（QA pairs），用于 SFT (Supervised Fine-Tuning) 模型训练。

输入要求：
---------
- 输入目录结构：
    GeneLiterature/
    ├── PMC10035410.json
    ├── PMC2565487.json
    ├── PMC3310826.json
    └── ...
- 每个JSON文件应包含基因文献数据，包含Title、DOI、Plant_Genes、Animal_Genes、Microbial_Genes等字段

核心功能：
---------
1. 批量处理：使用不重复DOI文件列表（non_duplicate_files_simple.txt），批量处理JSON格式的基因文献数据
2. 随机抽样：支持随机抽取指定数量的文件进行测试
3. 并发处理：使用多线程并发处理，提高处理效率
4. 断点续传：自动记录已处理文件，支持中断后继续处理
5. 成本统计：自动计算API调用成本和tokens使用情况
6. 时间戳目录：每次运行自动创建带时间戳的输出目录，避免结果覆盖

输出格式：
---------
1. QA数据目录（每次运行自动添加时间戳：output_YYYY-MM-DD_HH-MM-SS）：
    output_2024-01-15_14-30-25/
    └── gene_literature_qa.jsonl             # 所有基因文献的QA问答对数据（JSONL格式）

2. 处理记录目录（固定目录，用于断点续传）：
    processing_records/
    ├── GeneLiterature_processed_records.jsonl    # 已处理文件记录（追加模式）
    └── GeneLiterature_skipped_records.jsonl      # 跳过文件记录（追加模式）

QA数据文件格式（gene_literature_qa.jsonl，每行一条JSON记录）：
    {
        "qa_pairs": [
            {
                "id": "qa_001",
                "question": "问题文本",
                "answer": "答案文本",
                "gene_name": "基因名称（如SULTR1;2）",
                "dimension": "维度（如基因身份、功能事实、定量表型、调控模式、实验技术、应用价值）"
            },
            ...
        ],
        "meta_data": {
            "report_id": "文献ID（文件名不含扩展名，如PMC10035410）",
            "species": "物种名称（如Arabidopsis thaliana）",
            "generation_time": "2024-01-15 14:30:25",
            "model_name": "gpt-5.1",
            "input_tokens": 1234,
            "output_tokens": 567,
            "total_tokens": 1801,
            "processing_time_seconds": 2.345
        },
        "context": "原始基因文献JSON字符串（用于上下文）"
    }

处理记录文件格式（追加式JSONL，每行一条记录）：
- 已处理文件记录（{物种名}_processed_records.jsonl）：
    {
        "filename": "report001.json",
        "species": "物种名称",
        "processed_time": "2024-01-15 14:30:25",
        "success": true,
        "qa_count": 8,
        "input_tokens": 1234,
        "output_tokens": 567,
        "total_tokens": 1801,
        "cost_usd": 0.012345
    }

- 跳过文件记录（GeneLiterature_skipped_records.jsonl）：
    {
        "filename": "PMC10035410.json",
        "species": "GeneLiterature",
        "skipped_time": "2024-01-15 14:30:26",
        "reason": "DOI重复"
    }

配置说明：
---------
所有配置参数集中在文件顶部的"可配置参数区域"，包括：
- 输入输出路径：MAIN_INPUT_PATH, OUTPUT_DIR, RECORDS_DIR
- 处理参数：MAX_Q_PER_REPORT（每个基因文献文件生成的问答对数量）
- 抽样配置：SAMPLE_SIZE（随机抽取文件数量，或"all"处理全部）
- 并发配置：MAX_WORKERS（并发线程数）
- API配置：API_BASE_URL, DEFAULT_MODEL, MAX_OUTPUT_TOKENS
- 性能配置：TIMEOUT_SECONDS, BATCH_SLEEP_SECONDS

使用方法：
---------
1. 配置环境变量：在.env文件中设置 OPENAI_API_KEY
2. 修改配置参数：在文件顶部"可配置参数区域"修改相关配置
3. 运行脚本：python QAGenerator_gene_local.py
4. 查看结果：在带时间戳的输出目录中查看生成的QA文件

注意事项：
---------
- 确保GeneLiterature文件夹存在且包含JSON格式的基因文献数据
- 推荐使用 valid_non_duplicate_files.csv（通过analyze_gene_literature.py生成）
  该文件包含有效且不重复DOI的文件列表
- 建议先用少量文件测试（设置SAMPLE_SIZE），确认无误后再处理全部
- 处理记录保存在固定的 RECORDS_DIR 目录，支持断点续传和历史追踪
- 每次运行会创建新的带时间戳的输出目录，不会覆盖之前的QA数据

作者: Lijie
创建日期: 2025/12/30
"""

import os
import re
import json
import time
import csv
import random
import argparse
from pathlib import Path
from datetime import datetime
from openai import OpenAI
from dotenv import load_dotenv
from concurrent.futures import ThreadPoolExecutor, as_completed
import threading
from tqdm import tqdm

# ========== 0. 基本配置 ==========

# 加载环境变量（从.env文件读取API密钥等配置）
load_dotenv(Path(__file__).parent / ".env")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

# ============================================================================
# ========== 可配置参数区域 ==========
# ============================================================================
# 以下所有参数都可以根据实际需求修改，集中在此处便于管理
# ============================================================================

# ---------- 输入输出输出路径配置 ----------
# 主路径：GeneLiterature文件夹，包含所有JSON格式的基因文献数据文件
# 该文件夹直接包含所有JSON文件，不再按物种分类
MAIN_INPUT_PATH = os.getenv("GENE_INPUT_PATH", "examples")

# 输出目录：生成的QA文件将保存在此目录下
# 注意：程序运行时会自动在此目录名后添加日期时间戳（格式：YYYY-MM-DD_HH-MM-SS）
# 例如：output -> output_2024-01-15_14-30-25
# 这样可以避免不同运行的结果相互覆盖
# 每个物种会生成：
#   {物种名}_qa.jsonl - QA问答对数据
OUTPUT_DIR = "output"

# 处理记录目录：存放已处理文件和跳过文件的记录（固定目录，不带时间戳）
# 该目录用于记录所有运行的处理历史，支持断点续传
# 每个物种会生成两个记录文件：
#   1. {物种名}_processed_records.jsonl - 已处理文件记录（每行一条记录，包含时间戳）
#   2. {物种名}_skipped_records.jsonl - 跳过文件记录（每行一条记录，包含时间戳和原因）
RECORDS_DIR = "processing_records"

# ---------- 处理配置 ----------
# 每个基因文献文件生成的最大问答对数量
MAX_Q_PER_REPORT = 30

# 随机抽取配置：
#   - 数字（如 10, 100）：从每个物种文件夹中随机抽取指定数量的文件进行处理
#   - "all"：处理该物种文件夹中的所有文件
# 用途：当文件数量很大时，可以先用少量文件测试，确认无误后再处理全部文件
# 
# 示例：
#   SAMPLE_SIZE = 10      # 从每个物种文件夹中随机抽取10个文件
#   SAMPLE_SIZE = 100     # 从每个物种文件夹中随机抽取100个文件
#   SAMPLE_SIZE = "all"   # 处理所有文件（默认值）
SAMPLE_SIZE = 5  # 可选值：数字（如 10, 100）或 "all"

# 并发处理线程数（建议根据API限制和服务器性能调整）
# 注意：过高的并发数可能导致API限流或服务器负载过高
MAX_WORKERS = 10

# 文件匹配模式（用于筛选JSON文件）
FILE_PATTERN = "*.json"

# ---------- API配置 ----------
# API代理地址
API_BASE_URL = os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1")

# 默认使用的模型名称
DEFAULT_MODEL = os.getenv("DEFAULT_MODEL", "gpt-5.1")

# API最大输出tokens（限制模型生成的最大长度）
MAX_OUTPUT_TOKENS = 15000

# ---------- 超时和性能配置 ----------
# 单个文件处理超时时间（秒）
# 如果文件处理时间超过此值，会抛出超时异常
TIMEOUT_SECONDS = 900  # 15分钟

# 批次处理之间的休眠时间（秒）
# 用于避免API限流，在每批文件处理完成后休眠一段时间
BATCH_SLEEP_SECONDS = 1.0

# 异常处理时间阈值（秒）
# 如果单个基因文献文件处理时间超过此阈值，会输出警告信息
SLOW_PROCESSING_THRESHOLD = 60  # 60秒

# ---------- 调试配置 ----------
# 调试模式：是否打印API响应的完整结构（用于检查费用字段）
# 启用后会在第一次API调用时打印响应对象的完整结构，便于调试
# 通过环境变量设置：DEBUG_API_RESPONSE=true
DEBUG_API_RESPONSE = os.getenv("DEBUG_API_RESPONSE", "false").lower() in ("true", "1", "yes")

# ============================================================================
# ========== 配置区域结束 ==========
# ============================================================================

# OpenAI客户端配置（使用上面的配置）
client = OpenAI(
    api_key=OPENAI_API_KEY,
    base_url=API_BASE_URL,
)

# ================== Tokens 和价格配置 ==================
# API 供应商模型价格表（每 1K tokens 的价格，单位：美元）
#
# 注意：原始价格为每百万tokens（/M），已转换为每千tokens（/1K）
# 转换公式：每M价格 ÷ 1000 = 每1K价格
#
# 用途：用于计算API调用成本，如果API响应中未提供费用信息，则使用此价格表计算
MODEL_PRICING = {
    "gpt-5.1": {
        "input": 0.00125,   # $1.2500/M = $0.00125 per 1K input tokens
        "output": 0.01      # $10.0000/M = $0.01 per 1K output tokens
    },
    "gpt-5": {
        "input": 0.00125,   # $1.2500/M = $0.00125 per 1K input tokens
        "output": 0.01      # $10.0000/M = $0.01 per 1K output tokens
    }
}

# 默认价格（如果模型不在价格表中）
# 使用 gpt-5.1 的价格作为默认值
DEFAULT_PRICING = {
    "input": 0.00125,
    "output": 0.01
}

# ========== 1. 成本计算工具 ==========

def calculate_cost(prompt_tokens: int, completion_tokens: int, model: str) -> float:
    """
    计算 API 调用的成本（美元）。
    
    Args:
        prompt_tokens: 输入 tokens 数量
        completion_tokens: 输出 tokens 数量
        model: 模型名称
    
    Returns:
        成本（美元）
    """
    pricing = MODEL_PRICING.get(model, DEFAULT_PRICING)
    input_cost = (prompt_tokens / 1000.0) * pricing["input"]
    output_cost = (completion_tokens / 1000.0) * pricing["output"]
    return input_cost + output_cost


def get_empty_tokens_info() -> dict:
    """返回空的tokens信息字典（用于错误处理）"""
    return {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0, "cost_usd": 0.0}


# ========== 2. 调用大模型生成问答对 ==========

def build_prompt(section_name: str, json_data_str: str, max_q: int = 5) -> tuple[str, str]:
    """
    构建系统提示词和用户提示词，用于生成高质量SFT问答对
    
    该函数使用 GeneKnowledge_prompt_v4_2.md 中的提示词模板，专门针对农业基因组学与分子育种领域，
    将英文科研事实转化为严谨、原子化、可独立存在的英文学术问答对。
    
    参数:
        section_name: 章节/物种名称（用于标识，如"农业基因文献数据 (Plant)"）
        json_data_str: 格式化的JSON字符串（已去除null值，美化格式）
        max_q: 需要生成的最大问答对数量
    
    返回:
        (system_prompt, user_prompt) 元组，包含系统提示词和用户提示词
    """
    
    # System Prompt (系统指令) - 来自 GeneKnowledge_prompt_v4_2.md
    system_prompt = """## Role

You are a senior Data Scientist and Lead Curator for a Global Agricultural Genomics Knowledge Base. Your mission is to transform raw JSON research data into an exhaustive, atomic, and biologically rigorous collection of professional academic Question-and-Answer (QA) pairs.

## I. Core Principle: Evidence-Anchored Facticity

The goal is to generate knowledge that exists as a "timeless biological law" while strictly respecting the boundary of the provided evidence.

1.  **Proportional Complexity Rule (CRITICAL):** The depth of the Question must be strictly proportional to the depth of the available data.

    *   **Level 1 (Observation):** If the JSON only contains expression/phenotype data, ask "What is the response/pattern..."

    *   **Level 2 (Correlation):** If a relationship is mentioned but no specific intermediate actors are named, ask "What is the regulatory relationship..."

    *   **Level 3 (Mechanism):** ONLY ask "Through what molecular pathway/mechanism..." if the `Regulatory_Pathway`, `Interacting_Proteins`, or `Summary` fields provide specific, named molecular nodes and directional effects.

2.  **Boundary Awareness:** DO NOT force a "Molecular Mechanism" question if the context only supports a "Spatiotemporal Pattern" fact. It is better to have a complete answer to a shallower question than an incomplete answer to a deep question.

3.  **Anti-Hallucination:** DO NOT use speculative language (e.g., "likely," "probably," "suggests") unless these exact words are in the input. If the data stops at "Gene A increases Gene B," the answer must stop there.

4.  **Condition Integrity:** DO NOT remove experimental parameters (e.g., "under 15% PEG-6000", "at 4 h post-heat stress"). Remove reporting language (e.g., "the study found").

## II. Multi-hop Reasoning Protocol (Mandatory: 1-2 QAs per gene)

Generate 1-2 "Multi-hop" questions that require connecting at least TWO distinct biological dimensions from the JSON.

*   **Path A (Genotype-to-Breeding):** Connect `Key_Variant_Site` -> `Core_Phenotypic_Effect` -> `Breeding_Application_Value`.

*   **Path B (Validation-to-Mechanism):** Connect `Experimental_Methods` -> `Quantitative_Phenotypic_Alterations` -> `Regulatory_Mechanism`.

*   **Path C (Comparative Logic):** Connect `Variety/Experimental_Materials` -> `Quantitative_Phenotypic_Alterations` -> `Core_Phenotypic_Effect`.

**Answer Requirement:** The answer must explicitly show the logic chain: "Step 1 (Evidence A) -> Step 2 (Evidence B) -> Conclusion."

## III. Instruction Diversity & Trigger Mapping

Select the question style based on the **non-null** fields available:

*   **Pattern & Localization (Trigger:** `Expression_Pattern`, `Subcellular_Localization`): Where and when the gene/protein acts.

*   **Phenotypic Fact (Trigger:** `Quantitative_Phenotypic_Alterations`): The measurable outcome of gene action (include P-values and metrics).

*   **Regulatory Logic (Trigger:** `Regulatory_Mechanism`): The directional relationship between biological entities.

## IV. Exhaustiveness & Precision

1.  **No Omission:** Preserve every numerical value, P-value (e.g., P < 0.05), and Locus ID.

2.  **Identifier Grounding:** Every QA must link the **Gene Symbol** (e.g., Ghd8) with its **Locus ID** (e.g., Os08g07750) at least once in the Question or Answer.

3.  **Spatiotemporal Precision:** Always specify the tissue, cell type, and developmental stage.

## V. Strict Output Format

Mandatory: Output only a valid JSON array. No preamble, no markdown code blocks. Keys: "id", "gene\_name", "dimension", "question", "answer".

Dimension: "Gene Identity", "Regulatory Mechanisms", "Functional Pathways", "Phenotypic Evidence", "Experimental Validation".

Please follow this example JSON array structure for your output:

    [
      {
        "id": "qa_001",
        "gene_name": "string",
        "dimension": "string",
        "question": "string",
        "answer": "string"
      }
    ]

## VI. Task Execution Protocol

1.  **Data Depth Audit:** Scan the JSON. Are the downstream targets named? Is the upstream signal chain identified? Identify which fields support "Multi-hop" logic.

2.  **Question Calibration:** Choose question dimensions that match the *highest* level of non-null data.

3.  **Synthesis:** 

    *   Draft 1-2 Multi-hop QAs (Level 3 or cross-dimension).

4.  **Final Audit:** * Does the answer ask for information NOT present in the JSON? (If yes, simplify).

    *   Are all units, P-values, and Locus IDs preserved?

    *   Does the Multi-hop answer clearly link the logic steps?

## VII. Input Data

{full_json_data}"""

    # User Prompt (用户输入) - 包含实际的JSON数据
    user_prompt = f"""{json_data_str}"""

    return system_prompt, user_prompt


def call_llm_for_qa(section_name: str, json_data_str: str,
                    model: str = DEFAULT_MODEL, max_q: int = 5):
    """
    调用大语言模型生成问答对
    
    该函数执行以下操作：
    1. 构建提示词（系统提示词 + 用户提示词）
    2. 调用OpenAI Responses API生成问答对
    3. 从API响应中提取tokens信息和费用信息
    4. 解析模型返回的JSON格式问答对（支持多种格式容错）
    5. 验证和清理问答对数据
    
    参数:
        section_name: 章节/物种名称（用于日志标识，如"农业基因文献数据 (Plant)"）
        json_data_str: JSON格式的基因文献数据（字符串形式，已格式化）
        model: 使用的模型名称（默认：DEFAULT_MODEL）
        max_q: 每个基因文献文件生成的最大问答对数量
    
    返回:
        (qas列表, tokens_info字典, full_prompt字符串) 元组：
        - qas列表：包含问答对的字典列表，每个字典包含：
            - question: 问题文本
            - answer: 答案文本
            - extraction_level: 信息抽取级别（L1/L2/L3）
        - tokens_info字典：包含以下字段：
            - prompt_tokens: 输入tokens数量
            - completion_tokens: 输出tokens数量
            - total_tokens: 总tokens数量
            - cost_usd: 费用（美元）
            - cost_source: 费用来源（"api_usage"/"api_response"/"api_billing"/"calculated"）
            - api_latency_seconds: API调用耗时（秒）
        - full_prompt字符串：输入给大模型的完整提示词文本
        
        如果出错，返回 ([], {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0, "cost_usd": 0.0}, full_prompt)
    """
    system_prompt, user_prompt = build_prompt(section_name, json_data_str, max_q=max_q)
    
    # 构建完整的 prompt（将 system 和 user 合并）
    full_prompt = f"{system_prompt}\n\n{user_prompt}"

    try:
        # 准备请求参数
        resp_params = {
            "model": model,
            "input": full_prompt,
            "max_output_tokens": MAX_OUTPUT_TOKENS,  # 使用配置中的值
        }
        
        # 使用 Responses API（记录开始时间）
        api_start_time = time.time()
        resp = client.responses.create(**resp_params)
        api_latency = time.time() - api_start_time
        
        # 获取完整文本
        content = resp.output_text.strip()
        
        if not content:
            raise RuntimeError("Responses API 响应为空")

        # 提取 tokens 信息（根据测试结果，Responses API 使用 input_tokens/output_tokens）
        usage = resp.usage
        
        # 根据测试结果，Responses API 的 usage 对象类型是 ResponseUsage
        # 包含字段：input_tokens, output_tokens, total_tokens
        # 以及 details: input_tokens_details, output_tokens_details
        prompt_tokens = getattr(usage, "input_tokens", 0) or 0
        completion_tokens = getattr(usage, "output_tokens", 0) or 0
        total_tokens = getattr(usage, "total_tokens", 0) or (prompt_tokens + completion_tokens)
        
        # 从API响应中获取tokens（必须成功，否则报错）
        if prompt_tokens == 0 or completion_tokens == 0:
            raise RuntimeError(f"API响应中缺少tokens信息: input_tokens={prompt_tokens}, output_tokens={completion_tokens}")
        
        # ========== 费用信息提取 ==========
        # 尝试从API响应中获取费用信息，如果未提供则使用计算值
        cost_from_api = None
        cost_source = "calculated"
        
        # 调试模式：打印API响应结构（仅第一次调用时打印）
        if DEBUG_API_RESPONSE and not hasattr(call_llm_for_qa, "_debug_printed"):
            print(f"\n🔍 [调试模式] 检查API响应结构...")
            print(f"   resp 对象类型: {type(resp)}")
            print(f"   usage 对象类型: {type(usage)}")
            if hasattr(resp, "model_dump"):
                try:
                    resp_dict = resp.model_dump()
                    print(f"   resp.model_dump() 键: {list(resp_dict.keys())}")
                except:
                    pass
            call_llm_for_qa._debug_printed = True
            print(f"🔍 [调试模式] 结构检查完成\n")
        
        # 检查 usage 对象中的费用字段
        cost_fields = ["cost", "cost_usd", "total_cost", "price", "billing_cost"]
        for field in cost_fields:
            if hasattr(usage, field):
                cost_from_api = getattr(usage, field, None)
                if cost_from_api is not None:
                    cost_source = "api_usage"
                    break
        
        # 检查 resp 对象顶层或 billing 对象中的费用字段
        if cost_from_api is None:
            for field in ["cost", "cost_usd"]:
                if hasattr(resp, field):
                    cost_from_api = getattr(resp, field, None)
                    if cost_from_api is not None:
                        cost_source = "api_response"
                        break
            if cost_from_api is None and hasattr(resp, "billing"):
                billing = getattr(resp, "billing", None)
                if billing and hasattr(billing, "cost"):
                    cost_from_api = getattr(billing, "cost", None)
                    if cost_from_api is not None:
                        cost_source = "api_billing"
        
        # 使用API费用或计算值
        if cost_from_api is not None:
            try:
                cost = float(cost_from_api)
            except (ValueError, TypeError):
                cost = calculate_cost(prompt_tokens, completion_tokens, model)
        else:
            cost = calculate_cost(prompt_tokens, completion_tokens, model)
        tokens_info = {
            "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens,
            "total_tokens": total_tokens,
            "cost_usd": cost,
            "cost_source": cost_source,  # 费用来源：api_usage/api_response/api_billing/calculated
            "api_latency_seconds": round(api_latency, 3)  # API处理时间（秒），保留3位小数
        }

        # ========== JSON解析（容错处理） ==========
        # 模型可能返回多种格式的JSON，按优先级尝试多种解析方式
        json_str = content.strip()
        data = None
        parse_error = None
        
        # 方法1: 尝试直接解析整个内容（标准JSON格式）
        if data is None:
            try:
                data = json.loads(json_str)
            except json.JSONDecodeError as e:
                parse_error = e
        
        # 方法2: 提取 markdown 代码块中的 JSON
        if data is None:
            code_block_pattern = r'```(?:json)?\s*\n(.*?)\n```'
            match = re.search(code_block_pattern, content, re.DOTALL)
            if match:
                try:
                    data = json.loads(match.group(1).strip())
                except json.JSONDecodeError:
                    pass
        
        # 方法3: 提取 JSON 数组部分（查找第一个 [ 和匹配的 ]）
        if data is None:
            m = re.search(r'\[\s*{', json_str)
            if m:
                start = m.start()
                bracket_count = 0
                for i in range(start, len(json_str)):
                    if json_str[i] == '[':
                        bracket_count += 1
                    elif json_str[i] == ']':
                        bracket_count -= 1
                        if bracket_count == 0:
                            try:
                                data = json.loads(json_str[start:i+1])
                            except json.JSONDecodeError:
                                pass
                            break
        
        # 方法4: 尝试修复并解析（删除markdown标记，补全缺失括号）
        if data is None:
            cleaned_str = re.sub(r'^```(?:json)?\s*\n?', '', json_str, flags=re.MULTILINE)
            cleaned_str = re.sub(r'\n?```\s*$', '', cleaned_str, flags=re.MULTILINE).strip()
            if cleaned_str.startswith('{') and not cleaned_str.startswith('[{'):  # 单个对象转数组
                cleaned_str = '[' + cleaned_str + ']'
            try:
                data = json.loads(cleaned_str)
            except json.JSONDecodeError:
                pass
        
        # 方法5: 解析 NDJSON 格式（使用括号匹配提取多个JSON对象）
        if data is None:
            parsed_ndjson = []
            i = 0
            while i < len(json_str):
                if json_str[i].isspace():
                    i += 1
                    continue
                if json_str[i] == '{':
                    start = i
                    brace_count = 0
                    in_string = False
                    escape_next = False
                    for j in range(i, len(json_str)):
                        char = json_str[j]
                        if escape_next:
                            escape_next = False
                            continue
                        if char == '\\':
                            escape_next = True
                            continue
                        if char == '"' and not escape_next:
                            in_string = not in_string
                            continue
                        if not in_string:
                            if char == '{':
                                brace_count += 1
                            elif char == '}':
                                brace_count -= 1
                                if brace_count == 0:
                                    try:
                                        obj = json.loads(json_str[start:j+1].strip())
                                        if isinstance(obj, dict) and "question" in obj:
                                            parsed_ndjson.append(obj)
                                    except json.JSONDecodeError:
                                        pass
                                    i = j + 1
                                    break
                    if brace_count != 0:
                        i += 1
                else:
                    i += 1
            if parsed_ndjson:
                data = parsed_ndjson
        
        # 方法6: 从文本格式解析（编号列表格式）
        if data is None:
            parsed_qas = []
            pattern = r'\d+\.\s*(?:\n\s*)?(?:问[题]?|Q)[：:]\s*(.*?)\s*(?:答[案]?|A)[：:]\s*(.*?)(?=\n\s*\d+\.|$)'
            for match in re.finditer(pattern, content, re.DOTALL | re.MULTILINE):
                q = ' '.join(match.group(1).strip().split())
                a = ' '.join(match.group(2).strip().split())
                q = q.strip('"\'`。、，').strip()
                a = a.strip('"\'`。、，').strip()
                if len(q) >= 8 and len(a) >= 10:
                    parsed_qas.append({
                        "question": q,
                        "answer": a,
                        "extraction_level": "L2"
                    })
            if parsed_qas:
                data = parsed_qas
        
        # 如果所有方法都失败，返回空结果（不打印详细错误）
        if data is None:
            return [], tokens_info, full_prompt

        if isinstance(data, dict):
            if "qas" in data and isinstance(data["qas"], list):
                data = data["qas"]
            else:
                data = [data]

        if not isinstance(data, list):
            return [], tokens_info, full_prompt

        qas = []
        for item in data:
            q = str(item.get("question", "")).strip()
            a = str(item.get("answer", "")).strip()
            gene_name = str(item.get("gene_name", "")).strip()
            dimension = str(item.get("dimension", "")).strip()
            extraction_level = str(item.get("extraction_level", "")).strip().upper()

            if not q or not a or len(q) < 8 or len(a) < 10:
                continue

            # 规范 extraction_level（新格式可能不包含此字段，使用推断逻辑）
            if extraction_level not in ["L1", "L2", "L3"]:
                # 根据答案长度和复杂度推断级别
                if len(a) < 50 and "," not in a and "。" not in a:
                    extraction_level = "L1"
                elif "根据" in a or "标准" in a or "规范" in a:
                    extraction_level = "L3"
                else:
                    extraction_level = "L2"

            qa_item = {
                "question": q,
                "answer": a,
                "extraction_level": extraction_level,
            }
            # 如果新格式包含 gene_name 和 dimension，则添加到结果中
            if gene_name:
                qa_item["gene_name"] = gene_name
            if dimension:
                qa_item["dimension"] = dimension
            qas.append(qa_item)

        return qas, tokens_info, full_prompt

    except Exception as e:
        # 处理错误，打印简短信息
        print(f"  ⚠️  LLM调用异常: {str(e)[:100]}")
        return [], get_empty_tokens_info(), full_prompt


# ========== 4. 主流程：单文件与批处理 ==========

def ensure_output_dir(output_path: str) -> None:
    """
    确保输出文件所在的目录存在
    
    如果目录不存在，会自动创建（包括所有父目录）
    
    参数:
        output_path: 输出文件的完整路径
    """
    output_dir = os.path.dirname(output_path)
    if output_dir:
        os.makedirs(output_dir, exist_ok=True)


def remove_null_values(data):
    """
    递归删除字典和列表中值为 None/null 的项
    
    该函数用于清理JSON数据，去除所有null值，以减少prompt长度并提高可读性。
    支持嵌套的字典和列表结构。
    
    参数:
        data: 可以是 dict、list 或其他类型
    
    返回:
        清理后的数据（不包含 None/null 值）
        如果输入是其他类型，直接返回原值
    """
    if isinstance(data, dict):
        # 如果是字典，递归处理每个值，并删除值为 None 的键
        cleaned = {}
        for key, value in data.items():
            cleaned_value = remove_null_values(value)
            # 只保留非 None 的值
            if cleaned_value is not None:
                cleaned[key] = cleaned_value
        return cleaned
    elif isinstance(data, list):
        # 如果是列表，递归处理每个元素，并过滤掉 None 值
        cleaned = []
        for item in data:
            cleaned_item = remove_null_values(item)
            if cleaned_item is not None:
                cleaned.append(cleaned_item)
        return cleaned
    else:
        # 其他类型直接返回
        return data


def prepare_json_for_prompt(json_data: dict) -> str:
    """
    准备JSON数据用于构建prompt
    
    该函数执行以下操作：
    1. 删除所有值为null的字段（调用remove_null_values）
    2. 将字典格式化为美化的JSON字符串
    3. 确保中文字符正确显示（使用ensure_ascii=False）
    
    参数:
        json_data: 基因文献的JSON数据字典
    
    返回:
        格式化的JSON字符串（美化后的JSON，便于阅读，不包含null值）
        使用2个空格缩进，确保可读性
    """
    # 先删除所有 null 值
    cleaned_data = remove_null_values(json_data)
    
    # 使用 json.dumps 格式化 JSON，确保中文正确显示
    return json.dumps(cleaned_data, ensure_ascii=False, indent=2)


# ========== 重复DOI列表加载（回退机制）==========
def load_duplicate_dois(csv_file_path: str = "duplicate_dois_list.csv") -> set:
    """
    从 duplicate_dois_list.csv 文件中加载所有重复的 DOI
    仅在 non_duplicate_files_simple.txt 不存在时使用（回退机制）
    
    参数:
        csv_file_path: CSV文件路径
    
    返回:
        DOI集合（set）：包含所有重复的DOI
    """
    duplicate_dois = set()
    
    if not os.path.exists(csv_file_path):
        print(f"⚠️  重复DOI列表文件不存在: {csv_file_path}")
        return duplicate_dois
    
    try:
        with open(csv_file_path, 'r', encoding='utf-8-sig') as f:
            reader = csv.DictReader(f)
            for row in reader:
                doi = row.get('DOI', '').strip()
                if doi:
                    duplicate_dois.add(doi)
        
        print(f"✓ 已加载 {len(duplicate_dois)} 个重复DOI（回退模式）")
    except Exception as e:
        print(f"⚠️  读取重复DOI列表文件失败: {e}")
    
    return duplicate_dois

# ========== 线程安全工具 ==========
# 全局文件写入锁字典（用于并发写入时的线程安全）
# 每个输出文件对应一个锁，确保多线程环境下文件写入的安全性
_file_write_locks: dict[str, threading.Lock] = {}
_file_write_locks_lock = threading.Lock()  # 保护锁字典本身的锁

def get_file_write_lock(file_path: str) -> threading.Lock:
    """
    获取指定文件的写入锁（线程安全）
    
    在并发处理多个文件时，每个输出文件需要一个独立的锁来保护写入操作。
    该函数确保每个文件路径对应唯一的锁对象。
    
    参数:
        file_path: 文件路径（用作锁的键）
    
    返回:
        该文件对应的线程锁对象
    """
    with _file_write_locks_lock:
        if file_path not in _file_write_locks:
            _file_write_locks[file_path] = threading.Lock()
        return _file_write_locks[file_path]


def load_processed_files(processed_file_path: str) -> set:
    """
    加载已处理文件列表（从JSONL格式的记录文件中读取）
    
    从JSONL文件中读取已处理的文件名集合。每行是一条处理记录，包含文件名和时间戳。
    如果文件不存在，返回空集合。
    
    参数:
        processed_file_path: 已处理文件记录的JSONL文件路径
    
    返回:
        已处理文件名的集合（set）
    """
    if os.path.exists(processed_file_path):
        try:
            processed_files = set()
            with open(processed_file_path, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        record = json.loads(line)
                        filename = record.get("filename")
                        if filename:
                            processed_files.add(filename)
                    except json.JSONDecodeError:
                        continue
            return processed_files
        except Exception as e:
            print(f"⚠️  读取已处理文件记录失败: {e}，将重新处理所有文件")
            return set()
    return set()


def append_processed_record(processed_file_path: str, filename: str, species: str = "", 
                           success: bool = True, qa_count: int = 0, tokens_info: dict = None):
    """
    追加已处理文件记录（追加模式，不覆盖原有记录）
    
    将新处理的文件记录追加到JSONL文件中，每条记录包含文件名、处理时间等信息。
    如果目录不存在，会自动创建。
    
    参数:
        processed_file_path: 已处理文件记录的JSONL文件路径
        filename: 文件名
        species: 物种名称
        success: 是否成功处理
        qa_count: 生成的QA数量
        tokens_info: tokens和费用信息
    """
    try:
        ensure_output_dir(processed_file_path)
        
        # 构建记录
        record = {
            "filename": filename,
            "species": species,
            "processed_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "success": success,
            "qa_count": qa_count
        }
        
        # 添加tokens信息（如果有）
        if tokens_info:
            record["input_tokens"] = tokens_info.get("prompt_tokens", 0)
            record["output_tokens"] = tokens_info.get("completion_tokens", 0)
            record["total_tokens"] = tokens_info.get("total_tokens", 0)
            record["cost_usd"] = tokens_info.get("cost_usd", 0.0)
        
        # 追加到文件
        with open(processed_file_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")
    except Exception as e:
        print(f"⚠️  追加已处理文件记录失败: {e}")


def append_skipped_record(skipped_file_path: str, filename: str, species: str = "", 
                         reason: str = "DOI重复"):
    """
    追加跳过文件记录（追加模式，不覆盖原有记录）
    
    将跳过的文件记录追加到JSONL文件中，每条记录包含文件名、跳过原因、时间等信息。
    如果目录不存在，会自动创建。
    
    参数:
        skipped_file_path: 跳过文件记录的JSONL文件路径
        filename: 文件名
        species: 物种名称
        reason: 跳过原因
    """
    try:
        ensure_output_dir(skipped_file_path)
        
        # 构建记录
        record = {
            "filename": filename,
            "species": species,
            "skipped_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "reason": reason
        }
        
        # 追加到文件
        with open(skipped_file_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")
    except Exception as e:
        print(f"⚠️  追加跳过文件记录失败: {e}")


def process_single_json(
    json_path: str,
    output_jsonl: str,
    max_q: int = 5,
    model: str = DEFAULT_MODEL,
    file_write_lock: threading.Lock = None,
    skipped_record_path: str = None,
    species: str = "",
    duplicate_dois: set = None,
):
    """
    处理单个JSON格式的基因文献文件，生成问答对并写入JSONL文件
    
    处理流程：
    1. 读取JSON文件
    2. 检查DOI是否重复（重复则跳过并记录到固定记录文件）
    3. 准备JSON数据并调用LLM生成问答对
    4. 构建输出数据（包含meta_data和qa_pairs，保留gene_name和dimension字段）
    5. 写入JSONL文件（线程安全）
    
    参数:
        json_path: JSON文件完整路径
        output_jsonl: 输出JSONL文件路径（追加模式写入）
        max_q: 每个基因文献文件生成的最大问答对数量
        model: 使用的模型名称
        file_write_lock: 文件写入锁（用于并发写入时的线程安全，如果为None则自动获取）
        skipped_record_path: 跳过文件记录的JSONL文件路径（固定目录）
        species: 物种名称
    
    返回:
        (total_qas数量, tokens_info字典, is_skipped) 元组：
        - total_qas: 成功生成的问答对数量
        - tokens_info: tokens和费用信息字典
        - is_skipped: 布尔值，True表示因DOI重复而跳过，False表示正常处理
    """
    report_id = Path(json_path).stem  # 用于文献ID（不含扩展名，如PMC10035410）
    file_name = Path(json_path).name  # 完整文件名（含扩展名）
    
    # 记录开始时间
    start_time = time.time()
    
    try:
        with open(json_path, "r", encoding="utf-8") as f:
            json_data = json.load(f)
    except Exception as e:
        return 0, get_empty_tokens_info(), False
    
    # ========== 重复DOI检查（仅回退模式）==========
    if duplicate_dois is not None and len(duplicate_dois) > 0:
        file_doi = json_data.get("DOI", "")
        if file_doi:
            file_doi = file_doi.strip()
            if file_doi in duplicate_dois:
                if skipped_record_path:
                    append_skipped_record(skipped_record_path, file_name, species, f"DOI重复: {file_doi}")
                print(f"  ⚠️  跳过重复DOI: {file_name}")
                return 0, get_empty_tokens_info(), True
    
    # 准备 JSON 数据用于 prompt（直接使用 JSON 格式）
    json_data_str = prepare_json_for_prompt(json_data)
    
    if len(json_data_str.strip()) < 100:
        print(f"  ⚠️  文献内容过短，跳过")
        return 0, get_empty_tokens_info(), False
    
    # 获取基因数据（用于确定类型和物种信息）
    plant_genes = json_data.get("Plant_Genes", [])
    animal_genes = json_data.get("Animal_Genes", [])
    microbial_genes = json_data.get("Microbial_Genes", [])
    
    # 获取文献信息作为标识
    title = json_data.get("Title", "")
    doi = json_data.get("DOI", "")
    # 确定基因类型（优先使用Plant_Genes，如果有的话）
    if isinstance(plant_genes, list) and len(plant_genes) > 0:
        gene_type = "Plant"
    elif isinstance(animal_genes, list) and len(animal_genes) > 0:
        gene_type = "Animal"
    elif isinstance(microbial_genes, list) and len(microbial_genes) > 0:
        gene_type = "Microbial"
    else:
        gene_type = "Unknown"
    
    section_name = f"农业基因文献数据 ({gene_type})"
    
    ensure_output_dir(output_jsonl)
    
    total_qas = 0
    tokens_info_total = {
        "prompt_tokens": 0,
        "completion_tokens": 0,
        "total_tokens": 0,
        "cost_usd": 0.0
    }
    
    # 如果没有提供锁，则自动获取
    if file_write_lock is None:
        file_write_lock = get_file_write_lock(output_jsonl)
    
    qas, tokens_info, full_prompt = call_llm_for_qa(
        section_name, json_data_str, model=model, max_q=max_q
    )
    
    # 累计tokens和费用
    if tokens_info:
        tokens_info_total["prompt_tokens"] += tokens_info.get("prompt_tokens", 0)
        tokens_info_total["completion_tokens"] += tokens_info.get("completion_tokens", 0)
        tokens_info_total["total_tokens"] += tokens_info.get("total_tokens", 0)
        tokens_info_total["cost_usd"] += tokens_info.get("cost_usd", 0.0)
    
    if not qas:
        print(f"  ⚠️  LLM未返回QA对: {Path(json_path).name}")
        return 0, tokens_info_total, False
    
    # 直接使用模型生成的所有题目，限制数量不超过 max_q
    final_qas = qas[:max_q]
    
    if not final_qas:
        print(f"  ⚠️  过滤后无有效QA: {Path(json_path).name}")
        return 0, tokens_info_total, False
    
    # ========== 构建输出数据 ==========
    # qas 列表已经包含了 question, answer 字段，可能还包含 gene_name 和 dimension 字段
    
    # ========== 提取metadata信息 ==========
    # 从 tokens_info 中获取所有metadata信息
    input_tokens = tokens_info.get("prompt_tokens", 0)
    output_tokens = tokens_info.get("completion_tokens", 0)
    total_tokens = tokens_info.get("total_tokens", 0)
    api_latency = tokens_info.get("api_latency_seconds", 0.0)
    
    # 从 json_data 中获取物种信息
    # 优先从第一个基因对象中获取物种信息
    species = ""
    if isinstance(plant_genes, list) and len(plant_genes) > 0:
        first_gene = plant_genes[0]
        species = first_gene.get("Species_Latin_Name", "") or first_gene.get("Species", "") or ""
    elif isinstance(animal_genes, list) and len(animal_genes) > 0:
        first_gene = animal_genes[0]
        species = first_gene.get("Species_Latin_Name", "") or first_gene.get("Species", "") or ""
    elif isinstance(microbial_genes, list) and len(microbial_genes) > 0:
        first_gene = microbial_genes[0]
        species = first_gene.get("Species_Latin_Name", "") or first_gene.get("Species", "") or ""
    
    if not species:
        species = gene_type
    
    # 构建meta_data（按照最终格式.md中的字段顺序）
    meta_data = {}
    meta_data["report_id"] = report_id  # 文献ID（文件名不含扩展名，如PMC10035410）
    meta_data["species"] = species
    meta_data["generation_time"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    meta_data["model_name"] = model
    meta_data["input_tokens"] = input_tokens
    meta_data["output_tokens"] = output_tokens
    meta_data["total_tokens"] = total_tokens
    meta_data["processing_time_seconds"] = round(api_latency, 2)
    
    # ========== 构建qa_pairs ==========
    # 保留LLM返回的gene_name和dimension字段（如果存在）
    # 按照最终输出格式.md中的字段顺序：id, gene_name, dimension, question, answer
    qa_pairs = []
    for idx, qa in enumerate(final_qas, start=1):
        # 生成QA对的ID
        qa_id = f"qa_{idx:03d}"
        # 按照指定顺序构建qa_item（使用普通字典，Python 3.7+保持插入顺序）
        qa_item = {}
        qa_item["id"] = qa_id
        # gene_name和dimension放在前面
        if "gene_name" in qa:
            qa_item["gene_name"] = qa["gene_name"]
        if "dimension" in qa:
            qa_item["dimension"] = qa["dimension"]
        # question和answer放在后面
        qa_item["question"] = qa["question"]
        qa_item["answer"] = qa["answer"]
        qa_pairs.append(qa_item)
    
    # 构建最终的输出数据（每个基因文献文件一条JSON记录）
    output_data = {
        "qa_pairs": qa_pairs,
        "meta_data": meta_data,
        "context": json_data_str  # 基因文献文本（JSON格式字符串）
    }
    
    # 使用锁保护文件写入操作
    with file_write_lock:
        with open(output_jsonl, "a", encoding="utf-8") as fout:
            fout.write(json.dumps(output_data, ensure_ascii=False) + "\n")
    
    total_qas += len(final_qas)
    
    # 计算处理时间
    processing_time = time.time() - start_time
    
    # 返回时包含处理时间
    tokens_info_total["processing_time"] = processing_time
    
    return total_qas, tokens_info_total, False


def batch_process_json_dir(
    input_dir: str,
    output_jsonl: str,
    max_q: int = MAX_Q_PER_REPORT,
    model: str = DEFAULT_MODEL,
    pattern: str = FILE_PATTERN,
    max_workers: int = MAX_WORKERS,
    sample_size = SAMPLE_SIZE,  # 可以是 int 或 "all"
    duplicate_dois: set = None,
    non_duplicate_file_list: str = None,  # 新增参数：不重复文件列表
):
    """
    批量处理目录下的JSON格式基因文献文件（使用多线程并发处理）
    
    该函数执行以下操作：
    1. 从non_duplicate_file_list读取不重复DOI的文件列表（推荐方式）
    2. 加载已处理文件列表，自动跳过已处理的文件
    3. 根据sample_size参数随机抽取文件（如果需要）
    4. 使用线程池并发处理多个文件
    5. 统计处理结果和tokens使用情况
    6. 保存已处理文件记录到JSONL文件（追加模式）
    
    参数:
        input_dir: 输入目录路径（包含JSON文件的目录）
        output_jsonl: 输出JSONL文件路径（每个基因文献文件生成一条JSON记录）
        max_q: 每个基因文献文件生成的最大问答对数量
        model: 使用的模型名称
        pattern: 文件匹配模式（默认"*.json"）
        max_workers: 并发处理的线程数（默认10，可根据API限制调整）
        sample_size: 随机抽取的文件数量
            - 数字（如10, 100）：随机抽取指定数量的文件
            - "all"：处理所有文件
            - 如果抽取数量>=总文件数，自动处理所有文件
        duplicate_dois: 重复DOI集合（用于内容检查，可选）
        non_duplicate_file_list: 不重复文件列表的路径（txt文件，每行一个文件名）
    
    输出:
        - JSONL文件：{output_jsonl}，包含所有成功处理的基因文献的QA数据（保存在带时间戳的输出目录）
        - 处理记录：保存在固定的记录目录（RECORDS_DIR）中
            - {物种名}_processed_records.jsonl - 已处理文件记录（追加模式）
            - {物种名}_skipped_records.jsonl - 跳过文件记录（追加模式）
        - 控制台输出：处理进度、统计信息和tokens使用情况
        
    注意：QA数据保存在带时间戳的输出目录，处理记录保存在固定的记录目录，用于断点续传
    """
    ensure_output_dir(output_jsonl)

    if not os.path.exists(input_dir):
        print(f"❌ 输入目录不存在: {input_dir}")
        return

    # ========== 获取JSON文件列表 ==========
    if non_duplicate_file_list and os.path.exists(non_duplicate_file_list):
        # 推荐方式：从不重复文件列表读取
        file_names = []
        
        # 判断文件类型（CSV或TXT）
        if non_duplicate_file_list.endswith('.csv'):
            # 从CSV文件读取（提取第一列：文件名）
            import csv
            with open(non_duplicate_file_list, 'r', encoding='utf-8-sig') as f:
                reader = csv.DictReader(f)
                for row in reader:
                    # 尝试多个可能的列名
                    filename = row.get('文件名') or row.get('filename') or row.get('Filename')
                    if filename:
                        file_names.append(filename.strip())
        else:
            # 从TXT文件读取（每行一个文件名）
            with open(non_duplicate_file_list, 'r', encoding='utf-8') as f:
                file_names = [line.strip() for line in f if line.strip()]
        
        input_path = Path(input_dir)
        json_files = [input_path / fn for fn in file_names if (input_path / fn).exists()]
        total_files = len(file_names)
        missing_files = total_files - len(json_files)
        
        if missing_files > 0:
            print(f"⚠️  {missing_files} 个文件不存在于目录中")
        
        file_type = "CSV" if non_duplicate_file_list.endswith('.csv') else "TXT"
        print(f"✓ 从{file_type}加载 {len(json_files)} 个有效文件")
    else:
        # 回退方式：扫描目录
        if non_duplicate_file_list:
            print(f"⚠️  {non_duplicate_file_list} 不存在，使用回退模式")
        
        json_files = sorted(Path(input_dir).glob(pattern))
        total_files = len(json_files)
        print(f"✓ 扫描到 {total_files} 个JSON文件")
    
    if len(json_files) == 0:
        print(f"❌ 没有可处理的文件")
        return
    
    # ========== 确定物种名称和记录文件路径 ==========
    # 对于GeneLiterature文件夹，使用固定名称
    species_name = "GeneLiterature"
    
    # 构建固定记录目录的文件路径
    records_dir = RECORDS_DIR
    os.makedirs(records_dir, exist_ok=True)
    processed_record_path = os.path.join(records_dir, f"{species_name}_processed_records.jsonl")
    skipped_record_path = os.path.join(records_dir, f"{species_name}_skipped_records.jsonl")
    
    # ========== 加载已处理文件列表（断点续传）==========
    processed_files = load_processed_files(processed_record_path)
    already_processed_count = len(processed_files)
    if processed_files:
        json_files = [f for f in json_files if f.name not in processed_files]
    
    # ========== 随机抽取文件（可选）==========
    if sample_size != "all" and isinstance(sample_size, (int, str)):
        try:
            sample_num = int(sample_size)
            if sample_num > 0 and sample_num < len(json_files):
                # 使用random.sample确保随机性且不重复
                json_files = random.sample(json_files, sample_num)
        except (ValueError, TypeError):
            pass
    
    actual_files = len(json_files)
    
    # 处理信息
    print(f"\n{'='*80}")
    if non_duplicate_file_list and os.path.exists(non_duplicate_file_list):
        file_type = "CSV" if non_duplicate_file_list.endswith('.csv') else "TXT"
        print(f"来源: {non_duplicate_file_list} ({file_type})")
    print(f"总文件: {total_files} | 已处理: {already_processed_count} | 待处理: {actual_files}")
    print(f"{'='*80}")

    # 线程安全的统计变量
    stats_lock = threading.Lock()
    file_write_lock = get_file_write_lock(output_jsonl)
    processed_files_set = processed_files.copy()  # 已处理文件集合（线程安全，使用锁保护）
    total_reports_processed = 0
    total_all_qas = 0
    total_skipped_count = 0  # 跳过的文件数量统计
    total_processing_time = 0.0  # 总处理时间（累计所有文件的处理时间）
    total_tokens_stats = {
        "prompt_tokens": 0,
        "completion_tokens": 0,
        "total_tokens": 0,
        "cost_usd": 0.0
    }
    
    # 记录实际开始时间（墙上时钟时间）
    wall_clock_start = time.time()
    
    # 创建进度条
    pbar = tqdm(total=actual_files, desc=f"处理 {species_name}", 
                unit="文件", ncols=100, position=0, leave=True)
    
    def process_file_with_stats(json_file, file_index):
        """处理单个文件并更新统计信息"""
        nonlocal total_reports_processed, total_all_qas, total_skipped_count, total_processing_time
        
        try:
            report_qas, tokens_info, is_skipped = process_single_json(
                json_path=str(json_file),
                output_jsonl=output_jsonl,
                max_q=max_q,
                model=model,
                file_write_lock=file_write_lock,
                skipped_record_path=skipped_record_path,
                species=species_name,
                duplicate_dois=duplicate_dois,
            )
            
            # 获取处理时间
            processing_time = tokens_info.get("processing_time", 0) if tokens_info else 0
            
            # 如果是因为DOI重复而跳过，只更新跳过计数
            if is_skipped:
                with stats_lock:
                    total_skipped_count += 1
                pbar.update(1)
                return {
                    "file": json_file.name,
                    "success": False,
                    "qas": 0,
                    "tokens_info": tokens_info,
                    "skipped": True,
                    "processing_time": processing_time
                }
            
            # 线程安全地更新统计信息
            with stats_lock:
                # 累计tokens和费用统计（无论是否成功生成问答对，API调用都会产生费用）
                if tokens_info:
                    total_tokens_stats["prompt_tokens"] += tokens_info.get("prompt_tokens", 0)
                    total_tokens_stats["completion_tokens"] += tokens_info.get("completion_tokens", 0)
                    total_tokens_stats["total_tokens"] += tokens_info.get("total_tokens", 0)
                    total_tokens_stats["cost_usd"] += tokens_info.get("cost_usd", 0.0)
                    total_processing_time += processing_time
                
                if report_qas > 0:
                    total_all_qas += report_qas
                    total_reports_processed += 1
                    # 追加已处理文件记录到固定记录文件（线程安全）
                    processed_files_set.add(json_file.name)
                    append_processed_record(
                        processed_record_path, 
                        json_file.name, 
                        species_name,
                        success=True,
                        qa_count=report_qas,
                        tokens_info=tokens_info
                    )
                else:
                    # LLM没有返回有效的QA对
                    pbar.write(f"⚠️  未生成QA: {json_file.name} - LLM返回空结果")
                    if skipped_record_path:
                        append_skipped_record(skipped_record_path, json_file.name, species_name, "LLM返回空结果")
            
            # 检查是否处理时间过长
            if processing_time > SLOW_PROCESSING_THRESHOLD:
                pbar.write(f"⚠️  慢速文件: {json_file.name} - 耗时 {processing_time:.1f}秒")
            
            pbar.update(1)
            
            return {
                "file": json_file.name,
                "success": report_qas > 0,
                "qas": report_qas,
                "tokens_info": tokens_info,
                "skipped": False,
                "processing_time": processing_time
            }
        except Exception as e:
            pbar.write(f"❌ 处理失败: {json_file.name} | 错误: {str(e)[:100]}")
            pbar.update(1)
            return {
                "file": json_file.name,
                "success": False,
                "qas": 0,
                "tokens_info": None,
                "error": str(e),
                "skipped": False,
                "processing_time": 0
            }

    # 使用线程池并发处理（批次处理方式）
    with ThreadPoolExecutor(max_workers=max_workers, thread_name_prefix="File-Worker") as executor:
        batch_size = max(2, max_workers)
        
        # 分批处理文件
        for i in range(0, len(json_files), batch_size):
            batch = json_files[i : i + batch_size]
            
            # 提交当前批次的所有任务
            batch_futures = {
                executor.submit(process_file_with_stats, json_file, i + idx + 1): json_file
                for idx, json_file in enumerate(batch)
            }
            
            # 等待当前批次的所有任务完成
            for future in as_completed(batch_futures):
                try:
                    future.result(timeout=TIMEOUT_SECONDS)  # 使用配置中的超时时间
                except Exception as e:
                    pass  # 错误已在 process_file_with_stats 中处理
            
            # 如果不是最后一批，在批次之间添加短暂休眠（避免API限流）
            if i + batch_size < len(json_files):
                time.sleep(BATCH_SLEEP_SECONDS)  # 使用配置中的休眠时间
    
    # 关闭进度条
    pbar.close()
    
    # 计算实际运行时间（墙上时钟时间）
    wall_clock_time = time.time() - wall_clock_start

    # 输出物种处理统计信息
    print(f"\n{'='*80}")
    print(f"物种 {species_name} 处理完成")
    print(f"{'='*80}")
    print(f"📊 处理统计:")
    print(f"   成功处理: {total_reports_processed} 份文献")
    print(f"   生成问答对: {total_all_qas} 个")
    if total_skipped_count > 0:
        print(f"   跳过文件: {total_skipped_count} 个（DOI重复）")
    
    print(f"\n💰 费用统计:")
    print(f"   总成本: ${total_tokens_stats['cost_usd']:.6f} USD")
    print(f"   总输入 tokens: {total_tokens_stats['prompt_tokens']:,}")
    print(f"   总输出 tokens: {total_tokens_stats['completion_tokens']:,}")
    print(f"   总 tokens: {total_tokens_stats['total_tokens']:,}")
    
    print(f"\n⏱️  时间统计:")
    print(f"   实际运行时间: {wall_clock_time:.2f} 秒 ({wall_clock_time/60:.2f} 分钟)")
    print(f"   累计处理时间: {total_processing_time:.2f} 秒 ({total_processing_time/60:.2f} 分钟)")
    print(f"   并发加速比: {total_processing_time/wall_clock_time:.2f}x")
    
    if total_reports_processed > 0:
        avg_cost = total_tokens_stats['cost_usd'] / total_reports_processed
        avg_prompt = total_tokens_stats['prompt_tokens'] / total_reports_processed
        avg_completion = total_tokens_stats['completion_tokens'] / total_reports_processed
        avg_total = total_tokens_stats['total_tokens'] / total_reports_processed
        avg_time = total_processing_time / total_reports_processed
        
        print(f"\n📈 平均每个文件:")
        print(f"   成本: ${avg_cost:.6f} USD")
        print(f"   输入 tokens: {avg_prompt:,.1f}")
        print(f"   输出 tokens: {avg_completion:,.1f}")
        print(f"   总 tokens: {avg_total:,.1f}")
        print(f"   处理时间: {avg_time:.2f} 秒")
    
    print(f"\n💾 记录文件:")
    print(f"   已处理: {processed_record_path}")
    if total_skipped_count > 0:
        print(f"   已跳过: {skipped_record_path}")
    print(f"{'='*80}\n")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="基因文献QA生成器")
    parser.add_argument("--input", default=None, help="输入目录路径（包含JSON基因文献文件）")
    parser.add_argument("--output", default=None, help="输出目录前缀（自动追加时间戳）")
    parser.add_argument("--sample-size", type=int, default=None, help="随机抽取文件数量（默认使用脚本内配置）")
    parser.add_argument("--max-workers", type=int, default=None, help="并发线程数")
    args = parser.parse_args()

    if args.input:
        MAIN_INPUT_PATH = args.input
    if args.output:
        OUTPUT_DIR = args.output
    if args.sample_size is not None:
        SAMPLE_SIZE = args.sample_size
    if args.max_workers is not None:
        MAX_WORKERS = args.max_workers

    # ========== 处理 JSON 格式的基因文献 ==========
    # 所有配置参数都在文件顶部的"可配置参数区域"中定义
    # 如需修改配置，请直接修改文件顶部的配置变量
    
    # 从配置区域读取参数
    main_input_path = MAIN_INPUT_PATH
    output_dir_base = OUTPUT_DIR
    max_q_per_report = MAX_Q_PER_REPORT
    sample_size = SAMPLE_SIZE
    max_workers = MAX_WORKERS
    file_pattern = FILE_PATTERN
    
    # 设置文件列表路径（优先使用CSV，然后尝试TXT）
    csv_file_list = "rice_plants_only.csv" # excel_non_duplicate_files.csv
    non_duplicate_file_list = None
    duplicate_dois = None

    # 按优先级检查文件列表
    if os.path.exists(csv_file_list):
        non_duplicate_file_list = csv_file_list
        print(f"✓ 使用文件列表: {non_duplicate_file_list} (CSV格式)")

    
    # 为输出目录添加日期时间戳（格式：YYYY-MM-DD_HH-MM-SS）
    # 这样可以避免不同运行的结果相互覆盖，每次运行都会创建新的输出目录
    timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    output_dir = f"{output_dir_base}_{timestamp}"
    
    # 确保输出目录存在
    os.makedirs(output_dir, exist_ok=True)
    
    # 检查主路径是否存在
    if not os.path.exists(main_input_path):
        print(f"❌ 主路径不存在: {main_input_path}")
        exit(1)
    
    # 获取主路径下的所有JSON文件
    main_path = Path(main_input_path)
    json_files = sorted(main_path.glob(file_pattern))
    
    if not json_files:
        print(f"❌ 在主路径 {main_input_path} 中未找到任何JSON文件")
        exit(1)
    
    # 生成单个输出文件（所有文件处理到同一个输出文件）
    output_jsonl = os.path.join(output_dir, "gene_literature_qa.jsonl")
    
    # 确定物种名称（用于记录文件命名）
    species_name = "GeneLiterature"
    
    print(f"\n{'='*80}")
    print(f"开始批量处理基因文献数据")
    print(f"{'='*80}")
    if non_duplicate_file_list and os.path.exists(non_duplicate_file_list):
        file_type = "CSV" if non_duplicate_file_list.endswith('.csv') else "TXT"
        print(f"文件来源: {non_duplicate_file_list} ({file_type}格式)")
    else:
        print(f"输入路径: {main_input_path} (扫描目录)")
    print(f"输出文件: {output_jsonl}")
    print(f"记录目录: {RECORDS_DIR}")
    print(f"每文件生成: {max_q_per_report} 个问答对")
    print(f"并发线程: {max_workers}")
    if sample_size != "all":
        print(f"抽样配置: 随机抽取 {sample_size} 个文件")
    print(f"{'='*80}\n")
    
    # 处理所有JSON文件（使用batch_process_json_dir函数，但传入主路径）
    batch_process_json_dir(
        input_dir=str(main_path),
        output_jsonl=output_jsonl,
        max_q=max_q_per_report,
        model=DEFAULT_MODEL,
        pattern=file_pattern,
        max_workers=max_workers,
        sample_size=sample_size,
        duplicate_dois=duplicate_dois,
        non_duplicate_file_list=non_duplicate_file_list if (non_duplicate_file_list and os.path.exists(non_duplicate_file_list)) else None,
    )
    
    print(f"\n{'='*80}")
    print(f"✅ 所有文件处理完成！")
    print(f"{'='*80}")
    print(f"输出目录: {output_dir}")
    print(f"输出文件: {output_jsonl}")
    print(f"记录目录: {RECORDS_DIR}")
    print(f"{'='*80}\n")

