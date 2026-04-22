# 基因文献问答对生成器 (Gene QA Generator)

## 项目简介

基因文献问答对生成器（Gene_QAGenerator_dev.py）是一个基于大语言模型（LLM）的批量数据处理工具，用于从 JSON 格式的基因文献数据中自动生成高质量的问答对（QA pairs）。生成的问答对面向农业基因组学与分子育种领域，适用于 SFT（Supervised Fine-Tuning）模型训练与知识库构建。**核心采用农业基因组学专用的提示词模板（GeneKnowledge_prompt_v4_2）**，通过「证据锚定 + 多跳推理 + 触发映射」等设计，在保证事实边界内产出原子化、可独立使用的英文学术 QA。脚本支持不重复 DOI 文件列表、随机抽样、多线程并发、断点续传及成本统计等功能。

## 提示词特点与创新性

本脚本使用的系统提示词（`build_prompt`，源自 GeneKnowledge_prompt_v4_2）专为农业基因组学与分子育种场景设计，在「可控、可复现、防幻觉」方面具有明确特点与创新点。

### 核心设计理念：证据锚定事实性（Evidence-Anchored Facticity）

- **目标**：生成可作为「永恒生物律」存在的知识，且**严格不超出给定证据边界**。
- **比例复杂度规则（Proportional Complexity）**：问题深度与 JSON 数据深度一一对应。
  - **Level 1（观察）**：仅有表达/表型数据时，只问「What is the response/pattern...」。
  - **Level 2（相关）**：提到关系但未给出具体中间因子时，问「What is the regulatory relationship...」。
  - **Level 3（机制）**：仅当存在 `Regulatory_Pathway`、`Interacting_Proteins` 或 `Summary` 等具名分子节点与方向时，才问「Through what molecular pathway/mechanism...」。
- **边界意识**：若上下文只支持「时空模式」事实，不强行生成「分子机制」类问题，宁要完整浅层问答也不要残缺深层问答。
- **反幻觉**：禁止使用「likely / probably / suggests」等推测语，除非原文即如此；若数据止于「Gene A increases Gene B」，答案也止于此。
- **条件完整性**：保留实验条件（如「under 15% PEG-6000」「at 4 h post-heat stress」），去掉报道语（如「the study found」）。

### 创新点一：多跳推理协议（Multi-hop Reasoning Protocol）

- **约束**：每个基因强制生成 1–2 个「多跳」问答，要求**至少连接两个生物维度**。
- **三条显式路径**：
  - **Path A（基因型→育种）**：`Key_Variant_Site` → `Core_Phenotypic_Effect` → `Breeding_Application_Value`。
  - **Path B（验证→机制）**：`Experimental_Methods` → `Quantitative_Phenotypic_Alterations` → `Regulatory_Mechanism`。
  - **Path C（比较逻辑）**：`Variety/Experimental_Materials` → `Quantitative_Phenotypic_Alterations` → `Core_Phenotypic_Effect`。
- **答案要求**：必须显式写出逻辑链：「Step 1 (Evidence A) → Step 2 (Evidence B) → Conclusion」，便于训练可解释、可追溯的推理能力。

### 创新点二：指令多样性与触发映射（Instruction Diversity & Trigger Mapping）

- **数据驱动题型**：根据 JSON 的**非空字段**选择问题风格，避免「问无答」。
- **触发—题型对应**：
  - `Expression_Pattern` / `Subcellular_Localization` → **Pattern & Localization**（基因/蛋白何时何地发挥作用）。
  - `Quantitative_Phenotypic_Alterations` → **Phenotypic Fact**（可测量结果，含 P 值等指标）。
  - `Regulatory_Mechanism` → **Regulatory Logic**（生物实体间的方向性关系）。
- **效果**：同一文献在不同字段组合下自动适配不同维度的 QA，提高覆盖度与可用性。

### 创新点三：穷尽与精确（Exhaustiveness & Precision）

- **无遗漏**：保留所有数值、P 值（如 P < 0.05）和 Locus ID。
- **标识符落地（Identifier Grounding）**：每条 QA 至少在问题或答案中**同时出现基因符号（Gene Symbol）与 Locus ID**（如 Ghd8 ↔ Os08g07750），便于检索与知识关联。
- **时空精确**：必须标明组织、细胞类型与发育阶段，利于后续按场景筛选与复现。

### 任务执行协议（Task Execution Protocol）

提示词内嵌四步执行流程，使模型行为可预期、可复现：

1. **Data Depth Audit**：扫描 JSON，识别下游靶点、上游信号链及支持多跳的字段。
2. **Question Calibration**：选择与**当前非空数据的最高层级**匹配的问题维度。
3. **Synthesis**：起草 1–2 个多跳 QA（Level 3 或跨维度）。
4. **Final Audit**：检查答案是否超出 JSON、单位/P 值/Locus ID 是否保留、多跳逻辑链是否清晰。

### 输出规范与维度标签

- **格式**：仅输出合法 JSON 数组，无前言、无 markdown 代码块；字段：`id`, `gene_name`, `dimension`, `question`, `answer`。
- **维度（dimension）**：统一为五类——`Gene Identity`、`Regulatory Mechanisms`、`Functional Pathways`、`Phenotypic Evidence`、`Experimental Validation`，便于下游按维度统计、过滤与评估。

上述设计使生成的 QA 兼具**证据边界内的严谨性**、**多跳推理的可解释性**和**字段驱动的题型多样性**，适合作为农业基因组学与分子育种领域的 SFT 与知识库数据源。

## 主要特性

- 📂 **批量处理**：基于不重复 DOI 文件列表（CSV/TXT）或目录扫描，批量处理 JSON 基因文献
- 🎲 **随机抽样**：支持按数量随机抽取文件，便于小规模测试后再全量运行
- ⚡ **并发处理**：多线程调用 LLM API，可配置线程数，提高吞吐
- 🔄 **断点续传**：通过固定目录下的处理记录（JSONL）自动跳过已处理文件
- 💰 **成本统计**：自动汇总 input/output tokens 与 API 费用（支持从响应读取或本地价格表计算）
- 📁 **时间戳输出**：每次运行生成带时间戳的输出目录，避免覆盖历史结果
- 🧾 **多维 QA**：输出含 `gene_name`、`dimension` 等字段，便于后续筛选与评估
- 🛡️ **容错解析**：对 LLM 返回的多种 JSON 格式（含 markdown 代码块、NDJSON 等）做容错解析
- 📜 **专用提示词**：采用农业基因组学专用提示词（证据锚定 + 多跳推理 + 触发映射），保证 QA 在证据边界内、可解释、题型与数据深度匹配

## 技术架构

### 核心技术栈

- **Python 3.x** - 主要开发语言
- **OpenAI SDK** - 调用 Responses API（`client.responses.create`）生成问答
- **python-dotenv** - 从 `.env` 加载 `OPENAI_API_KEY`
- **tqdm** - 进度条展示
- **concurrent.futures** - 多线程并发

### 脚本结构概览

```
Gene_QAGenerator_dev.py
├── 可配置参数区域
│   ├── 输入输出路径（MAIN_INPUT_PATH, OUTPUT_DIR, RECORDS_DIR）
│   ├── 处理参数（MAX_Q_PER_REPORT, SAMPLE_SIZE, MAX_WORKERS）
│   ├── API 配置（API_BASE_URL, DEFAULT_MODEL, MAX_OUTPUT_TOKENS）
│   └── 超时与性能（TIMEOUT_SECONDS, BATCH_SLEEP_SECONDS）
│
├── 成本与 Tokens
│   ├── MODEL_PRICING / DEFAULT_PRICING
│   ├── calculate_cost()
│   └── get_empty_tokens_info()
│
├── LLM 调用与解析
│   ├── build_prompt()           # 系统/用户提示词（农业基因组学 QA 规范）
│   ├── call_llm_for_qa()        # 调用 API、提取 tokens/费用、多格式 JSON 解析
│   └── 输出 qa_pairs + meta_data + context
│
├── 数据处理与 IO
│   ├── remove_null_values()     # 清理 JSON 中的 null
│   ├── prepare_json_for_prompt()
│   ├── ensure_output_dir()
│   ├── load_duplicate_dois()     # 回退：重复 DOI 列表
│   ├── load_processed_files()   # 断点续传：已处理列表
│   ├── append_processed_record() / append_skipped_record()
│   └── get_file_write_lock()    # 多线程安全写同一 JSONL
│
├── 单文件与批处理
│   ├── process_single_json()    # 单文件 → 读 JSON、DOI 检查、调 LLM、写一条 JSONL
│   └── batch_process_json_dir() # 目录批处理、抽样、线程池、统计汇总
│
└── __main__                     # 时间戳输出目录、调用 batch_process_json_dir
```

## 安装与部署

### 环境要求

- Python 3.8+
- 可访问的 OpenAI 兼容 API（脚本中默认 `API_BASE_URL` 指向代理地址）

### 依赖安装

### 安装

```bash
# 使用 uv 安装依赖（推荐）
uv sync

# 或使用 pip
pip install -r requirements.txt
```

主要依赖：

- openai
- python-dotenv
- tqdm

（脚本仅使用标准库的 `os`, `re`, `json`, `time`, `csv`, `random`, `pathlib`, `datetime`, `concurrent.futures`, `threading`。）

### 配置设置

1. **环境变量**  
   在项目根目录创建 `.env`，设置：

   ```bash
   OPENAI_API_KEY=${OPENAI_API_KEY}
   ```

2. **脚本内可配置参数（文件顶部）**  
   编辑 `Gene_QAGenerator_dev.py` 中「可配置参数区域」：

   | 类别         | 参数名                   | 说明 |
   |--------------|--------------------------|------|
   | 输入输出     | `MAIN_INPUT_PATH`        | 基因文献 JSON 所在目录 |
   |              | `OUTPUT_DIR`             | 输出目录前缀（运行时会加时间戳） |
   |              | `RECORDS_DIR`            | 处理记录目录（断点续传） |
   | 处理         | `MAX_Q_PER_REPORT`       | 每个文献最多生成问答对数量 |
   |              | `SAMPLE_SIZE`            | 抽样数量（数字）或 `"all"` |
   |              | `MAX_WORKERS`            | 并发线程数 |
   | API          | `API_BASE_URL`           | API 基地址 |
   |              | `DEFAULT_MODEL`          | 模型名（如 gpt-5.1） |
   |              | `MAX_OUTPUT_TOKENS`      | 单次调用最大输出 token 数 |
   | 超时与性能   | `TIMEOUT_SECONDS`        | 单文件处理超时（秒） |
   |              | `BATCH_SLEEP_SECONDS`    | 每批之间的休眠（秒），缓解限流 |

3. **文件列表（推荐）**  
   - 使用「不重复 DOI」文件列表可避免重复文献、统一入口。  
   - 在 `__main__` 中设置 `csv_file_list`（如 `rice_plants_only.csv` 或 `excel_non_duplicate_files.csv`）。  
   - 支持 **CSV**（需包含文件名列，如「文件名」/`filename`/`Filename`）或 **TXT**（每行一个文件名）。  
   - 若列表文件不存在，脚本会回退为扫描 `MAIN_INPUT_PATH` 下所有 `*.json`；若存在 `duplicate_dois_list.csv`，会用于 DOI 重复跳过（回退逻辑）。

## 使用指南

### 快速开始（使用示例数据）

```bash
uv run python Gene_QAGenerator_dev.py --input examples/
```

### 输入要求

- **目录结构示例**：

  ```
  GeneLiterature/   (或 MAIN_INPUT_PATH 所设目录)
  ├── PMC10035410.json
  ├── PMC2565487.json
  └── ...
  ```

- 每个 JSON 需包含基因文献相关字段，如：`Title`, `DOI`, `Plant_Genes`, `Animal_Genes`, `Microbial_Genes` 等（脚本会据此判断类型并提取物种等信息）。

### 基本运行

```bash
# 确保已配置 .env 中的 OPENAI_API_KEY 和脚本内 MAIN_INPUT_PATH、文件列表等
python Gene_QAGenerator_dev.py
```

- 输出目录会自动命名为 `output_YYYY-MM-DD_HH-MM-SS`，其下生成 `gene_literature_qa.jsonl`。  
- 处理记录写入 `RECORDS_DIR`（默认 `processing_records/`）：  
  - `GeneLiterature_processed_records.jsonl`：已处理文件及 tokens/费用  
  - `GeneLiterature_skipped_records.jsonl`：跳过记录（如 DOI 重复、LLM 未返回有效 QA）

### 输出格式说明

**QA 数据文件**（`gene_literature_qa.jsonl`，每行一条 JSON）：

```json
{
  "qa_pairs": [
    {
      "id": "qa_001",
      "gene_name": "Ghd8",
      "dimension": "Phenotypic Evidence",
      "question": "...",
      "answer": "..."
    }
  ],
  "meta_data": {
    "report_id": "PMC10035410",
    "species": "Oryza sativa",
    "generation_time": "2024-01-15 14:30:25",
    "model_name": "gpt-5.1",
    "input_tokens": 1234,
    "output_tokens": 567,
    "total_tokens": 1801,
    "processing_time_seconds": 2.35
  },
  "context": "原始基因文献 JSON 字符串"
}
```

**处理记录文件**（追加式 JSONL）：

- 已处理：`filename`, `species`, `processed_time`, `success`, `qa_count`, `input_tokens`, `output_tokens`, `total_tokens`, `cost_usd`
- 跳过：`filename`, `species`, `skipped_time`, `reason`

## 运行示例

**专家问答生成工具（LPREADME 中的 demo）**：

```bash
python expertQ_generateA_v2.py --input data.jsonl --output output.jsonl
```

**本脚本（基因文献 QA 生成）**：

```bash
python Gene_QAGenerator_dev.py
```

运行后控制台会输出：文件来源、总/已处理/待处理数量、成功处理文献数、生成问答对数、跳过数、总成本、总/平均 tokens、运行时间与并发加速比等。

## 性能与优化

- **并发**：通过 `MAX_WORKERS` 和 `BATCH_SLEEP_SECONDS` 在速度和 API 限流之间平衡。  
- **断点续传**：依赖 `RECORDS_DIR` 下已处理记录，重复运行不会重复处理已成功文件。  
- **成本**：优先使用 API 返回的费用字段，若无则用脚本内 `MODEL_PRICING`/`DEFAULT_PRICING` 计算。  
- **慢请求**：单文件处理超过 `SLOW_PROCESSING_THRESHOLD`（默认 60 秒）会在进度条中告警。

## 故障排除

| 现象 | 建议 |
|------|------|
| API 报错 / 无响应 | 检查 `OPENAI_API_KEY`、`API_BASE_URL` 及网络与代理 |
| 无 tokens 或 cost | 确认 API 返回 `usage`（input_tokens/output_tokens）；可设 `DEBUG_API_RESPONSE=true` 查看响应结构 |
| 生成 QA 为空 | 查看是否被跳过（见 `*_skipped_records.jsonl`）；或检查单条 JSON 内容是否过短/格式不符 |
| 重复处理同一批文件 | 确认 `RECORDS_DIR` 与 `processed_record_path` 一致，且未手动清空记录文件 |
| 超时 | 增大 `TIMEOUT_SECONDS` 或减小 `MAX_Q_PER_REPORT`/单条文献长度 |

## 注意事项

- 输入目录需存在且包含有效 JSON；推荐使用通过 `analyze_gene_literature.py` 等得到的 `valid_non_duplicate_files.csv` 作为文件列表。  
- 建议先用小规模抽样（如 `SAMPLE_SIZE=5`）验证流程与质量，再改为 `"all"` 全量运行。  
- 处理记录保存在固定目录、以追加方式写入，便于断点续传与审计；每次运行仅 QA 输出目录带时间戳，避免覆盖。

## 许可证与贡献

- 许可证以项目仓库为准（如 MIT，见根目录 LICENSE）。  
- 欢迎通过 Issue / Pull Request 反馈问题或改进。

## 更新日志

### 当前版本（dev）
- 支持不重复 DOI 文件列表（CSV/TXT）与目录扫描回退
- 多线程并发、断点续传、时间戳输出目录
- 成本与 tokens 统计，支持 API 返回费用与本地价格表
- 农业基因组学专用提示词（GeneKnowledge_prompt_v4_2）：证据锚定事实性、多跳推理协议、触发映射、穷尽与精确、任务执行协议；输出含 `gene_name`、`dimension` 的 QA 及 `meta_data`、`context`

---

**说明**：本工具用于从基因文献中生成训练用 QA 数据，不替代专业生物信息或育种结论。涉及实际育种或应用时请结合专业意见使用。
