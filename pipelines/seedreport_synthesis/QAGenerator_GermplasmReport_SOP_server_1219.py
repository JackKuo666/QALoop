#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
种质报告问答对生成器 (Seed Report QA Generator)
================================================================================

功能概述：
---------
从 JSON 格式的农作物新品种审定报告/种质报告中，使用大语言模型自动生成高质量
的问答对（QA pairs），用于 SFT (Supervised Fine-Tuning) 模型训练。

输入要求：
---------
- 输入目录结构：
    MAIN_INPUT_PATH/
    ├── {物种1}/          # 物种文件夹（如：maize, AsianRice, cotton等）
    │   ├── report1.json
    │   ├── report2.json
    │   └── ...
    ├── {物种2}/
    │   └── ...
    └── ...
- 每个JSON文件应包含完整的种质报告数据，必须包含"特征特性"字段（为空则跳过）

核心功能：
---------
1. 批量处理：自动扫描所有物种文件夹，批量处理JSON格式的种质报告
2. 智能过滤：自动跳过"特征特性"字段为空的报告，并记录到CSV文件
3. 随机抽样：支持从每个物种中随机抽取指定数量的文件进行测试
4. 并发处理：使用多线程并发处理，提高处理效率
5. 断点续传：自动记录已处理文件，支持中断后继续处理
6. 成本统计：自动计算API调用成本和tokens使用情况
7. 时间戳目录：每次运行自动创建带时间戳的输出目录，避免结果覆盖

输出格式：
---------
1. QA数据目录（每次运行自动添加时间戳：output_YYYY-MM-DD_HH-MM-SS）：
    output_2024-01-15_14-30-25/
    ├── {物种1}_qa.jsonl                    # 物种1的QA问答对数据（JSONL格式）
    ├── {物种2}_qa.jsonl                    # 物种2的QA问答对数据
    └── ...

2. 处理记录目录（固定目录，用于断点续传）：
    processing_records/
    ├── {物种1}_processed_records.jsonl    # 物种1已处理文件记录（追加模式）
    ├── {物种1}_skipped_records.jsonl      # 物种1跳过文件记录（追加模式）
    ├── {物种2}_processed_records.jsonl    # 物种2已处理文件记录
    ├── {物种2}_skipped_records.jsonl      # 物种2跳过文件记录
    └── ...

QA数据文件格式（{物种名}_qa.jsonl，每行一条JSON记录）：
    {
        "qa_pairs": [
            {
                "id": "qa_001",
                "question": "问题文本",
                "answer": "答案文本"
            },
            ...
        ],
        "meta_data": {
            "report_id": "报告ID",
            "species": "物种名称",
            "generation_time": "2024-01-15 14:30:25",
            "model_name": "gpt-5.1",
            "input_tokens": 1234,
            "output_tokens": 567,
            "total_tokens": 1801,
            "processing_time_seconds": 2.345
        },
        "context": "原始报告JSON字符串（用于上下文）"
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

- 跳过文件记录（{物种名}_skipped_records.jsonl）：
    {
        "filename": "report002.json",
        "species": "物种名称",
        "skipped_time": "2024-01-15 14:30:26",
        "reason": "特征特性为空"
    }

配置说明：
---------
所有配置参数集中在文件顶部的"可配置参数区域"，包括：
- 输入输出路径：MAIN_INPUT_PATH, OUTPUT_DIR, RECORDS_DIR
- 处理参数：MAX_Q_PER_REPORT（每个报告生成的问答对数量）
- 抽样配置：SAMPLE_SIZE（随机抽取文件数量，或"all"处理全部）
- 并发配置：MAX_WORKERS（并发线程数）
- API配置：API_BASE_URL, DEFAULT_MODEL, MAX_OUTPUT_TOKENS
- 性能配置：TIMEOUT_SECONDS, BATCH_SLEEP_SECONDS

使用方法：
---------
1. 配置环境变量：在.env文件中设置 OPENAI_API_KEY
2. 修改配置参数：在文件顶部"可配置参数区域"修改相关配置
3. 运行脚本：python SeedstockQAGenerator_v21_local_context.py
4. 查看结果：在带时间戳的输出目录中查看生成的QA文件

注意事项：
---------
- 确保输入目录结构正确，每个物种有独立的文件夹
- 建议先用少量文件测试（设置SAMPLE_SIZE），确认无误后再处理全部
- 处理记录保存在固定的 RECORDS_DIR 目录，支持断点续传和历史追踪
- 每次运行会创建新的带时间戳的输出目录，不会覆盖之前的QA数据
- 处理记录采用追加模式，保留所有历史处理信息

作者: Lijie
版本: SOP
创建日期: 2025/12/19
"""

import os
import re
import json
import time
import csv
import random
from pathlib import Path
from datetime import datetime
from openai import OpenAI
from dotenv import load_dotenv
from concurrent.futures import ThreadPoolExecutor, as_completed
import threading
from tqdm import tqdm

# ========== 0. 基本配置 ==========

# 加载环境变量（从.env文件读取API密钥等配置）
load_dotenv()
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

# ============================================================================
# ========== 可配置参数区域 ==========
# ============================================================================
# 以下所有参数都可以根据实际需求修改，集中在此处便于管理
# ============================================================================

# ---------- 输入输出输出路径配置 ----------
# 主路径：种质报告根目录（包含各个物种文件夹）
# 该目录下应包含多个子文件夹，每个子文件夹代表一个物种（如：maize, AsianRice, cotton等）
# 每个物种文件夹中包含该物种的所有JSON格式种质报告文件
# 支持环境变量 GERMPLASM_REPORT_PATH，默认为 ./examples
MAIN_INPUT_PATH = os.getenv("GERMPLASM_REPORT_PATH", "./examples")

# 输出目录：生成的QA文件将保存在此目录下
# 注意：程序运行时会自动在此目录名后添加日期时间戳（格式：YYYY-MM-DD_HH-MM-SS）
# 例如：output -> output_2024-01-15_14-30-25
# 这样可以避免不同运行的结果相互覆盖
# 每个物种会生成：
#   {物种名}_qa.jsonl - QA问答对数据
OUTPUT_DIR = os.getenv("OUTPUT_DIR", "QAGenarator")

# 处理记录目录：存放已处理文件和跳过文件的记录（固定目录，不带时间戳）
# 该目录用于记录所有运行的处理历史，支持断点续传
# 每个物种会生成两个记录文件：
#   1. {物种名}_processed_records.jsonl - 已处理文件记录（每行一条记录，包含时间戳）
#   2. {物种名}_skipped_records.jsonl - 跳过文件记录（每行一条记录，包含时间戳和原因）
RECORDS_DIR = os.getenv("RECORDS_DIR", "Processing_records")

# ---------- 处理配置 ----------
# 每个报告生成的问答对数量
MAX_Q_PER_REPORT = 8

# 随机抽取配置：
#   - 数字（如 10, 100）：从每个物种文件夹中随机抽取指定数量的文件进行处理
#   - "all"：处理该物种文件夹中的所有文件
# 用途：当文件数量很大时，可以先用少量文件测试，确认无误后再处理全部文件
# 
# 示例：
#   SAMPLE_SIZE = 10      # 从每个物种文件夹中随机抽取10个文件
#   SAMPLE_SIZE = 100     # 从每个物种文件夹中随机抽取100个文件
#   SAMPLE_SIZE = "all"   # 处理所有文件（默认值）
SAMPLE_SIZE = 1000  # 可选值：数字（如 10, 100）或 "all"

# 并发处理线程数（建议根据API限制和服务器性能调整）
# 注意：过高的并发数可能导致API限流或服务器负载过高
MAX_WORKERS = 100

# 文件匹配模式（用于筛选JSON文件）
FILE_PATTERN = "*.json"

# ---------- API配置 ----------
# API代理地址
API_BASE_URL = os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1")

# 默认使用的模型名称
DEFAULT_MODEL = "gpt-5.1"

# API最大输出tokens（限制模型生成的最大长度）
MAX_OUTPUT_TOKENS = 8000

# ---------- 超时和性能配置 ----------
# 单个文件处理超时时间（秒）
# 如果文件处理时间超过此值，会抛出超时异常
TIMEOUT_SECONDS = 900  # 15分钟

# 批次处理之间的休眠时间（秒）
# 用于避免API限流，在每批文件处理完成后休眠一段时间
BATCH_SLEEP_SECONDS = 1.0

# 异常处理时间阈值（秒）
# 如果单个报告处理时间超过此阈值，会输出警告信息
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
    
    该函数构建的提示词专门针对品种审定报告/种质报告的特点，包含：
    - 严格的禁止规则（避免生成关于审定编号、年份、地点等的问题）
    - L1/L2/L3三级信息抽取策略说明
    - 行业标准引用和术语解释要求
    - 输出格式规范（JSON数组格式）
    
    参数:
        section_name: 章节/物种名称（用于标识，如"水稻品种审定报告"）
        json_data_str: 格式化的JSON字符串（已去除null值，美化格式）
        max_q: 需要生成的最大问答对数量
    
    返回:
        (system_prompt, user_prompt) 元组，包含系统提示词和用户提示词
    """
    
    # json_data_str 已经是格式化的 JSON 字符串，直接使用
    # 如果太长，可以截断（但保持 JSON 格式完整性）
    # 注意：这里不做截断，因为 JSON 结构需要完整

    # System Prompt (系统指令)
    system_prompt = """【角色定位】

你是一个农业育种、品种审定与作物生产领域的专业知识问答生成模型。你的任务是：基于给定的品种审定报告原文，生成可直接用于模型监督微调（SFT）的高质量问答对。

【核心原则】

1.  事实准确：所有数值、描述、判断必须 100% 来自报告原文，不得引入外部经验推断。

2.  信息闭合：只有当一个问题的全部信息点都能在报告中被完整支撑时，才允许生成该 QA，否则直接放弃该问题。

3.  直接陈述：严禁在问题和答案中出现指向文本来源或行政过程的间接表述（如"根据报告"、"报告中显示"、"审定数据中"、通过审定"、"审定意见认为"、"检测机构为……"）。

4.  称呼明确：问题和答案中必须使用完整品种名称作为主语，禁止使用"该品种 / 它 / 本品种"等代词。

5.  问答对应：回答必须严格契合提问意图和专业口径。回答力求简洁、直接，可对专业术语进行自然转述，但严禁更改信息量纲或新增、推测数据。

    a. 信息粒度对齐： 回答的范围和信息主体必须与问句的查询范围精确匹配。

    b. 语义与术语对齐： 必须保证问答两端的核心专业术语语义精确对应，严禁将同义但不同范畴的术语混用。

【严格禁止】

一类：内容禁止

1.  绝对禁止询问审定编号、审定年份、审定单位、育种单位、育成单位、申请者等与组织或时间相关的行政元信息。

2.  绝对禁止询问作物的"商品名"或"命名形式"等元信息。

3.  绝对禁止询问检测、鉴定、试验机构名称。

4.  绝对禁止存在性问题或指向"报告本身"的问题（（如"报告中如何描述"、"是否提到……"、"是否有"）。

二类：表述禁止

1.  绝对禁止推断性语言：如"说明了"、"意味着"、"由此可见"。

2.  禁止两个问题针对报告中的同一个原子事实进行重复提问。

3.  绝对禁止教科书式因果解释或长铺垫说明。

【允许转化】

在不引入新事实的前提下，仅允许：

*   判断性转化：将事实转为"属于 / 为 / 是 / 否 / 不是"等

*   公式性转化：将公式转化成自然语言（如将L296×L96转化为"母本是L296，父本是L96 。"）

*   计算性转化：基于已有数值计算差值或百分比

*   结构性转化：将同类指标整理为列表

*   行业性映射：映射为公认、明确的行业分类（如熟性类型）

【问句多样性要求】

为确保 SFT 数据的语言表达丰富性，问句的生成必须遵循以下结构比例约束：

1.  以品种名开头的问句： 占总问句数量的 50%。

2.  非品种名开头的问句： 占总问句数量的 50%，可参考下述【8 大用户意图】中的启发性参考句式，也可发散句式，但内容不得重复，且要保持语言自然通顺、术语专业规范。

【8 大用户意图】

| 编号 | 用户意图           | 目标           | 启发性参考句式（鼓励更多发散句式）                                                                                                                                                                                                                                                                                                     |
| :- | :------------- | :----------- | :-------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| 1  | 微观事实查询         | 精准查询关键数值或属性  | 1. \[品种名]的株高、主茎节数和有效分枝数分别是多少？2. 请问\[品种名]从出苗到成熟大约需要多少天？3. 在苗期，我们如何通过叶鞘颜色来辨别\[品种名]？4. 如果我在长江中下游种 \[品种名]，全生育期会超过 140 天吗？5. \[品种名]在目标种植区的全生育期约为多少天？6. \[品种名]的幼苗叶鞘是什么颜色？7. 请提供 \[品种名] 的主要农艺性状数据，包括其平均株高、主茎节数及有效分枝数。8. 算上灌浆期，\[品种名]完成整个生长周期通常要多久？                                                                           |
| 2  | 类型 / 性状 / 归属确认 | 核实状态或分类归属    | 1. 根据生育期判断，\[品种名]属于特早熟还是中熟类型？2. \[品种名]的叶片夹角和分枝姿态是偏向紧凑收敛还是松散开张？3. 请确认一下，\[品种名]的结荚习性是有限还是无限？4. 在籽粒质地方面，\[品种名]属于角质类型还是粉质类型？5. 根据 \[品种名]的生长时间来看，它更适合作为前茬还是后茬作物？属于哪种熟期梯队？6. 由于\[品种名]的籽粒质地特点，它更偏向于工业加工、直接食用还是饲用？7. \[品种名]的结荚是集中在植株中下部（有限型），还是上下均匀分布（无限型）？8. 请确认\[品种名]在花期结束后，主茎顶端是否继续产生新叶（即无限习性）？                            |
| 3  | 横向对比分析         | 了解相对表现       | 1. 和对照品种相比，\[品种名]在全生育期天数上有无显著差异？2. 从播种到成熟，\[品种名]的表现与对照品种相比是高度一致，还是存在明显的时差？3. 平均到每亩地，\[品种名]比对照品种高出多少个百分点？4. 与当地主栽对照品种相比，\[品种名]的生育期是早还是晚？5. 在大面积生产示范中，\[品种名]较对照品种的实际增产贡献率是多少？6. 在生产试验中，\[品种名]较对照品种的增产幅度是多少？7. 如果要替换现有品种，\[品种名]的核心产量优势在哪里？                                                                               |
| 4  | 专业品质评估         | 核实工业或营养指标    | 1. \[品种名]的粗蛋白含量具体是多少，是否达到高蛋白品种标准？2. 请提供\[品种名]在加工品质上的核心数据：整精米率和垩白度。3. 从加工角度看，\[品种名]的整精米表现是否能支撑其作为高端米销售？4. 参照国家相关标准，\[品种名]的蛋白质水平位居哪一等级？5. 请简要描述\[品种名]的湿面筋含量。6. 根据湿面筋含量判断，\[品种名]更适合制作面包（强筋）还是饼干（弱筋）？7. \[品种名]的各项品质指标是否符合优质一等标准？                                                                                          |
| 5  | 栽培操作指南         | 获得可执行的农事操作建议 | 1. 条播\[品种名] 时，行距控制在什么范围内比较合适？2. 如果地力表现一般，种植\[品种名]时，底肥施用多少复合肥能达到养分平衡？3.为了构建合理的群体结构，\[品种名]条播时的行间距上限与下限应如何设定？4. \[品种名]的推荐播种期一般在几月份？5. 设定多大的行距最有利于\[品种名]的中后期机械化田间管理？6. 针对\[品种名]的感温感光特性，其适宜播种窗口在何时？7. 进入拔节至孕穗这一需肥关键期，\[品种名]每公顷的尿素追施强度应如何把控？8. 为了提高\[品种名]的结实率和千粒重，拔节孕穗期每公顷需要追加多少尿素？9. 针对中等肥力地块，\[品种名]的基肥（复合肥）施用定额建议为每亩多少公斤？ |
| 6  | 抗病抗虫风险         | 了解风险和局限性     | 1. \[品种名]在多雨年份对穗腐病的耐受力如何？2. 除了纹枯病，\[品种名]对白叶枯病和条锈病的具体抗性是什么？3. \[品种名]重点防治的"点蜂缘蝽"主要危害哪个生育阶段？4. 在发病区种植\[品种名]前，土壤或种子需要做哪些防病处理？5. 依据抗性鉴定结果，\[品种名]对赤霉病表现为哪种抗性类型？6. 为了有效拦截点蜂缘蝽，我们需要重点监控 \[品种名]的哪个生长节点？7. 根据国家区域试验数据，\[品种名]对赤霉病的鉴定评价等级是什么？8. \[品种名]是否属于抗赤霉病品种？其具体的抗性表现是'中抗'还是'中感'？                                             |
| 7  | 综合性状综述         | 快速了解维度全貌     | 1. 请列出\[品种名]的核心农艺性状数据，包括株高、穗位、穗长及每穗粒数。2. \[品种名]之所以高产，主要归功于哪些指标的突破？3. 在标准栽培条件下，\[品种名]的植株高度与穗部发育表现如何？4. 请综合评价 \[品种名]的田间抗逆性，重点关注其抗病、抗倒伏能力及后期熟相。5. 请详细描述\[品种名]在抗病性、抗倒性和熟相方面的表现。6. 请介绍一下\[品种名]的植株形态和籽粒外观特征。7. 我想知道\[品种名]在株高、穗长和每穗粒数方面的综合数据。                                                                                |
| 8  | 品种溯源追踪         | 追溯遗传背景       | 1. \[品种名]的母本和父本分别是什么？2. 请解析\[品种名]的遗传谱系，其双亲分别源自哪些品系？3. 我想知道\[品种名]是通过哪些亲本材料配组而成的？4. \[品种名]是由哪些基础种质资源杂交选育而成的？5. \[品种名]的选育过程涉及哪些核心亲本材料？6. \[品种名]是如何育成的？7. 请简述 \[品种名] 的选育技术路线及方法。                                                                                                                                          |

【最终输出格式要求】

模型必须且只能输出一个 JSON 数组，包含不重复的、多样化的、事实准确的问答对。

    [
      {
        "question": "问题文本",
        "answer": "答案文本"
      }
      // ... (总计 {max_q} 组)
    ]
"""

    # User Prompt (用户输入)
    user_prompt = f"""任务说明：请从以下农作物品种审定报告中抽取信息，生成 `{max_q}` 组问答对。

要求：覆盖 8 类用户意图中的至少 5 类；表达偏专业、轻微口语化；至少 40% 的 QA 为 25 字以内的原子级短回答。

品种审定报告内容\
`{json_data_str}`
"""

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
        section_name: 章节/物种名称（用于日志标识，如"水稻品种审定报告"）
        json_data_str: JSON格式的品种审定报告数据（字符串形式，已格式化）
        model: 使用的模型名称（默认：DEFAULT_MODEL）
        max_q: 每个报告生成的最大问答对数量
    
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
            qas.append(qa_item)

        return qas, tokens_info, full_prompt

    except Exception as e:
        # 打印错误信息以便调试
        print(f"❌ API调用失败: {str(e)[:200]}")
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
        json_data: 品种审定报告的JSON数据字典
    
    返回:
        格式化的JSON字符串（美化后的JSON，便于阅读，不包含null值）
        使用2个空格缩进，确保可读性
    """
    # 先删除所有 null 值
    cleaned_data = remove_null_values(json_data)
    
    # 使用 json.dumps 格式化 JSON，确保中文正确显示
    return json.dumps(cleaned_data, ensure_ascii=False, indent=2)


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
                         reason: str = "特征特性为空"):
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
):
    """
    处理单个JSON格式的种质报告文件，生成问答对并写入JSONL文件
    
    处理流程：
    1. 读取JSON文件
    2. 检查"特征特性"字段是否为空（为空则跳过并记录到固定记录文件）
    3. 调用LLM生成问答对
    4. 构建输出数据（包含meta_data和qa_pairs）
    5. 写入JSONL文件（线程安全）
    
    参数:
        json_path: JSON文件完整路径
        output_jsonl: 输出JSONL文件路径（追加模式写入）
        max_q: 每个报告生成的最大问答对数量
        model: 使用的模型名称
        file_write_lock: 文件写入锁（用于并发写入时的线程安全，如果为None则自动获取）
        skipped_record_path: 跳过文件记录的JSONL文件路径（固定目录）
        species: 物种名称
    
    返回:
        (total_qas数量, tokens_info字典, is_skipped) 元组：
        - total_qas: 成功生成的问答对数量
        - tokens_info: tokens和费用信息字典
        - is_skipped: 布尔值，True表示因特征特性为空而跳过，False表示正常处理
    """
    report_id = Path(json_path).stem  # 用于报告ID（不含扩展名）
    file_name = Path(json_path).name  # 完整文件名（含扩展名）
    
    # 记录开始时间
    start_time = time.time()
    
    try:
        with open(json_path, "r", encoding="utf-8") as f:
            json_data = json.load(f)
    except Exception as e:
        return 0, get_empty_tokens_info(), False
    
    # ========== 特征特性字段检查 ==========
    # 检查"特征特性"字段是否为空，如果为空则跳过处理
    # 原因：特征特性是生成高质量问答对的关键信息，缺少此字段的报告无法生成有效问答对
    feature_characteristics = json_data.get("特征特性", "")
    if not feature_characteristics or (isinstance(feature_characteristics, str) and not feature_characteristics.strip()):
        # 记录跳过的文件到固定记录文件（追加模式）
        if skipped_record_path:
            append_skipped_record(skipped_record_path, file_name, species, "特征特性为空")
        return 0, get_empty_tokens_info(), True
    
    # 准备 JSON 数据用于 prompt（直接使用 JSON 格式）
    json_data_str = prepare_json_for_prompt(json_data)
    
    if len(json_data_str.strip()) < 100:
        print(f"  ⚠️  报告内容过短，跳过")
        return 0, get_empty_tokens_info(), False
    
    # 获取品种名称作为标识
    variety_name = json_data.get("品种名称", report_id)
    crop_name = json_data.get("作物名称", "")
    section_name = f"{crop_name}品种审定报告" if crop_name else "品种审定报告"
    
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
        return 0, tokens_info_total, False
    
    # 直接使用模型生成的所有题目，限制数量不超过 max_q
    final_qas = qas[:max_q]
    
    if not final_qas:
        return 0, tokens_info_total, False
    
    # ========== 第一部分：获取API回答结果 ==========
    # qas 列表已经包含了 question, answer 字段
    
    # ========== 第二部分：处理得到metadata ==========
    # 从 tokens_info 中获取所有metadata信息
    input_tokens = tokens_info.get("prompt_tokens", 0)
    output_tokens = tokens_info.get("completion_tokens", 0)
    total_tokens = tokens_info.get("total_tokens", 0)
    api_latency = tokens_info.get("api_latency_seconds", 0.0)
    
    # 从 json_data 中获取"作物名称"作为"物种"
    species = json_data.get("作物名称", crop_name) or ""
    
    # 构建meta_data（按照新格式）
    meta_data = {
        "report_id": report_id,  # 如"川引稻2006002"
        "species": species,
        "generation_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "model_name": model,
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "total_tokens": total_tokens,
        "processing_time_seconds": round(api_latency, 2),
    }
    
    # ========== 第三部分：构建qa_pairs并合并数据 ==========
    qa_pairs = []
    for idx, qa in enumerate(final_qas, start=1):
        # 生成QA对的ID
        qa_id = f"qa_{idx:03d}"
        qa_pairs.append({
            "id": qa_id,
            "question": qa["question"],
            "answer": qa["answer"]
        })
    
    # 构建最终的输出数据（每个报告一条json）
    output_data = {
        "qa_pairs": qa_pairs,
        "meta_data": meta_data,
        "context": json_data_str  # 种质报告文本（JSON格式字符串）
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
):
    """
    批量处理目录下的JSON格式种质报告文件（使用多线程并发处理）
    
    该函数执行以下操作：
    1. 加载已处理文件列表，自动跳过已处理的文件
    2. 扫描输入目录，查找所有匹配pattern的JSON文件
    3. 根据sample_size参数随机抽取文件（如果需要）
    4. 使用线程池并发处理多个文件
    5. 统计处理结果和tokens使用情况
    6. 保存已处理文件列表到JSON文件
    7. 保存跳过的文件列表到CSV文件
    
    参数:
        input_dir: 输入目录路径（包含JSON文件的目录）
        output_jsonl: 输出JSONL文件路径（每个报告生成一条JSON记录）
        max_q: 每个报告生成的最大问答对数量
        model: 使用的模型名称
        pattern: 文件匹配模式（默认"*.json"）
        max_workers: 并发处理的线程数（默认10，可根据API限制调整）
        sample_size: 随机抽取的文件数量
            - 数字（如10, 100）：随机抽取指定数量的文件
            - "all"：处理所有文件
            - 如果抽取数量>=总文件数，自动处理所有文件
    
    输出:
        - JSONL文件：{output_jsonl}，包含所有成功处理的报告的QA数据（保存在带时间戳的输出目录）
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

    json_files = sorted(Path(input_dir).glob(pattern))
    total_files = len(json_files)
    
    if total_files == 0:
        print(f"❌ 在目录 {input_dir} 中未找到匹配 {pattern} 的文件")
        return
    
    # ========== 确定物种名称和记录文件路径 ==========
    # 从输出文件名中提取物种名称（如：maize_qa.jsonl -> maize）
    species_name = Path(output_jsonl).stem.replace("_qa", "")
    
    # 构建固定记录目录的文件路径
    records_dir = RECORDS_DIR
    os.makedirs(records_dir, exist_ok=True)
    processed_record_path = os.path.join(records_dir, f"{species_name}_processed_records.jsonl")
    skipped_record_path = os.path.join(records_dir, f"{species_name}_skipped_records.jsonl")
    
    # ========== 加载已处理文件列表（从固定记录目录） ==========
    processed_files = load_processed_files(processed_record_path)
    already_processed_count = len(processed_files)
    if processed_files:
        # 过滤掉已处理的文件
        json_files = [f for f in json_files if f.name not in processed_files]
    
    # ========== 随机抽取文件（可选） ==========
    # 如果sample_size不是"all"，则从所有文件中随机抽取指定数量的文件
    # 用途：当文件数量很大时，可以先用少量文件测试，确认无误后再处理全部文件
    if sample_size != "all" and isinstance(sample_size, (int, str)):
        try:
            sample_num = int(sample_size)
            if sample_num > 0 and sample_num < len(json_files):
                # 使用random.sample确保随机性且不重复
                json_files = random.sample(json_files, sample_num)
        except (ValueError, TypeError):
            pass
    
    actual_files = len(json_files)
    
    # 简洁的开始信息
    print(f"\n{'='*80}")
    print(f"物种: {species_name}")
    print(f"总文件数: {total_files} | 已处理: {already_processed_count} | 待处理: {actual_files}")
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
            )
            
            # 获取处理时间
            processing_time = tokens_info.get("processing_time", 0) if tokens_info else 0
            
            # 如果是因为特征特性为空而跳过，只更新跳过计数
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
    print(f"   成功处理: {total_reports_processed} 份报告")
    print(f"   生成问答对: {total_all_qas} 个")
    if total_skipped_count > 0:
        print(f"   跳过文件: {total_skipped_count} 个（特征特性为空）")
    
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
        
        print(f"\n📈 平均每份报告:")
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
    """
    主程序入口
    
    执行流程：
    1. 读取配置（主路径、输出目录、记录目录、随机抽取配置等）
    2. 为输出目录添加日期时间戳（格式：YYYY-MM-DD_HH-MM-SS）
    3. 创建固定的处理记录目录（用于断点续传）
    4. 扫描主路径下的所有物种文件夹
    5. 遍历每个物种文件夹，调用batch_process_json_dir处理
    6. 为每个物种生成独立的输出文件和处理记录
    
    输出文件结构：
    1. QA数据目录（每次运行创建新目录）：
        output_YYYY-MM-DD_HH-MM-SS/
        ├── {物种1}_qa.jsonl              # 物种1的QA数据
        ├── {物种2}_qa.jsonl              # 物种2的QA数据
        └── ...
    
    2. 处理记录目录（固定目录，追加模式）：
        processing_records/
        ├── {物种1}_processed_records.jsonl    # 物种1已处理文件记录
        ├── {物种1}_skipped_records.jsonl      # 物种1跳过文件记录
        ├── {物种2}_processed_records.jsonl    # 物种2已处理文件记录
        ├── {物种2}_skipped_records.jsonl      # 物种2跳过文件记录
        └── ...
    
    注意：
    - 每次运行创建新的带时间戳的QA输出目录，不覆盖之前的结果
    - 处理记录保存在固定目录，采用追加模式，保留所有历史记录
    - 支持断点续传：已处理的文件不会重复处理
    """
    # ========== 处理 JSON 格式的种质报告 ==========
    # 所有配置参数都在文件顶部的"可配置参数区域"中定义
    # 如需修改配置，请直接修改文件顶部的配置变量
    
    # 从配置区域读取参数
    main_input_path = MAIN_INPUT_PATH
    output_dir_base = OUTPUT_DIR
    max_q_per_report = MAX_Q_PER_REPORT
    sample_size = SAMPLE_SIZE
    max_workers = MAX_WORKERS
    file_pattern = FILE_PATTERN
    
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
    
    # 获取主路径下的所有子文件夹（物种文件夹）
    main_path = Path(main_input_path)
    species_dirs = [d for d in main_path.iterdir() if d.is_dir()]
    
    if not species_dirs:
        print(f"❌ 在主路径 {main_input_path} 中未找到任何子文件夹")
        exit(1)
    
    print(f"\n{'='*80}")
    print(f"开始批量处理种质报告")
    print(f"{'='*80}")
    print(f"物种数量: {len(species_dirs)}")
    print(f"输入路径: {main_input_path}")
    print(f"输出目录: {output_dir}")
    print(f"记录目录: {RECORDS_DIR}")
    print(f"每报告生成: {max_q_per_report} 个问答对")
    print(f"并发线程: {max_workers}")
    if sample_size != "all":
        print(f"抽样配置: 每物种随机抽取 {sample_size} 个文件")
    print(f"{'='*80}\n")
    
    # 遍历每个物种文件夹
    for idx, species_dir in enumerate(sorted(species_dirs), 1):
        species_name = species_dir.name
        
        # 为每个物种生成独立的输出文件
        output_jsonl = os.path.join(output_dir, f"{species_name}_qa.jsonl")
        
        # 处理当前物种文件夹（使用配置区域的参数）
        batch_process_json_dir(
            input_dir=str(species_dir),
            output_jsonl=output_jsonl,
            max_q=max_q_per_report,
            model=DEFAULT_MODEL,
            pattern=file_pattern,
            max_workers=max_workers,
            sample_size=sample_size,
        )
    
    print(f"\n{'='*80}")
    print(f"✅ 所有物种处理完成！")
    print(f"{'='*80}")
    print(f"输出目录: {output_dir}")
    print(f"记录目录: {RECORDS_DIR}")
    print(f"{'='*80}\n")

