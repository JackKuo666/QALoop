# ExpertQ GenerateA - 农业育种专家问答批量生成系统

## 项目简介

ExpertQ GenerateA 是一个**批量问答生成工具**，基于大语言模型（LLM）为水稻、玉米、小麦、油菜、大豆及主要畜禽领域的科研人员和一线从业者生成专业、准确的问答数据。

### 核心特性

| 特性 | 说明 |
|------|------|
| **多模型支持** | 支持 22 个主流大模型（GPT、Claude、Gemini、DeepSeek、Qwen、GLM、Grok 等） |
| **Thinking 模式** | 支持模型思考过程提取，增强推理能力 |
| **并发处理** | 支持多文件、多问题并发处理 |
| **质量保证** | 双版本答案、推理链提取、智能去重 |
| **RAG 检索增强** | 可选启用 PubMed 文献检索，提供带引用的答案 |

### 环境要求

- Python 3.10+
- uv 包管理器

### 安装

```bash
cd expertq_generatea
uv sync
```

### 配置

创建 `.env` 文件：

```bash
OPENAI_API_KEY=${OPENAI_API_KEY}
OPENAI_BASE_URL=https://api.openai.com/v1
DEFAULT_MODEL=gpt-5.1
```

### 快速开始

```bash
# 使用示例数据运行
uv run python seed_Q_generate_A_v2.py --input examples/sample_input.json --output output/
```

---

## 支持的模型

### 模型列表

| 模型名称 | 说明 | API 类型 |
|----------|------|----------|
| **GPT 系列** | | |
| `gpt-5.1` | GPT-5.1（默认） | Chat |
| `gpt-5.2` | GPT-5.2 | Responses |
| `gpt-4o` | GPT-4o | Responses |
| `gpt-oss-120b` | GPT-OSS-120B | Chat |
| **Claude 系列** | | |
| `claude-sonnet-4-5-20250929` | Claude Sonnet 4.5 | Chat |
| `claude-sonnet-4-20250514` | Claude Sonnet 4（已弃用） | Responses |
| `claude-opus-4-20250514` | Claude Opus 4（已弃用） | Responses |
| `claude-3-5-haiku-20241022` | Claude 3.5 Haiku | Responses |
| **Gemini 系列** | | |
| `gemini-2-5-pro` | Gemini 2.5 Pro | Responses |
| `gemini-2-5-flash` | Gemini 2.5 Flash | Responses |
| **DeepSeek 系列** | | |
| `deepseek-v3.2` | DeepSeek V3.2 | Chat |
| `deepseek-v3.2-thinking` | DeepSeek V3.2 Thinking | Responses |
| `deepseek-v3` | DeepSeek V3 | Responses |
| `deepseek-v2.5` | DeepSeek V2.5 | Responses |
| **GLM 系列** | | |
| `glm-4.6` | GLM-4.6 | Chat |
| **Qwen 系列** | | |
| `qwen3-30b-a3b` | Qwen3 30B A3B | Responses |
| `qwen3-30b-a3b-think` | Qwen3 30B Think | Chat |
| `qwen-max` | Qwen Max | Chat |
| `qwen-plus` | Qwen Plus | Chat |
| `qwen-turbo` | Qwen Turbo | Chat |
| **Grok 系列** | | |
| `grok-4-1-fast-reasoning` | Grok 4.1 Fast | Chat |

### 多模型批量处理

支持同时使用多个模型生成答案：

```bash
# 使用多个模型
python seed_Q_generate_A_v2.py --input data/ --output output/ --models gpt-5.1 gpt-5.2 deepseek-v3.2
```

---

## Thinking 模式

Thinking 模式可提取模型的推理过程（Chain of Thought），生成双版本答案：
- **基础版**：直接答案
- **思考版**：推理过程 + 最终答案

### Thinking 模式选项

| 选项 | 说明 |
|------|------|
| `auto` | 自动选择（根据模型自动判断） |
| `low` | 低推理强度，快速响应 |
| `medium` | 中等推理强度 |
| `high` | 高推理强度，详细推理 |

### 使用示例

```bash
# 自动选择 thinking 模式
python seed_Q_generate_A_v2.py --input examples/sample_input.json --output output/ --think-mode auto

# 中等推理强度
python seed_Q_generate_A_v2.py --input examples/sample_input.json --output output/ --think-mode medium

# 指定 thinking 模型
python seed_Q_generate_A_v2.py --input examples/sample_input.json --output output/ --model deepseek-v3.2-thinking
```

---

## RAG 检索增强（可选）

启用 RAG 后，系统会先从 PubMed 检索相关文献，再生成带文献引用的答案。

### 工作流程

```
问题 → RAG Server → PubMed 检索文献
                   ↓
         文献摘要 + 原始问题
                   ↓
              LLM 生成答案
                   ↓
         带文献引用的答案输出
```

### 启动 RAG Server

```bash
# 1. 启动 RAG Server（后台运行）
cd rag_server && python main.py &
sleep 3

# 2. 运行 QA 生成（启用 RAG）
cd ..
python seed_Q_generate_A_v2.py \
  --input examples/sample_input.json \
  --output output/ \
  --use-rag \
  --model gpt-5.1
```

### RAG 相关参数

| 参数 | 说明 | 默认值 |
|------|------|--------|
| `--use-rag` | 是否启用 RAG 检索 | False |
| `RAG_URL` | RAG Server 地址 | `http://localhost:9487/retrieve` |
| `pubmed_topk` | 检索文献数量 | 10 |
| `RAG_TIMEOUT` | RAG 请求超时时间 | 300 秒 |

---

## 质量保证

### 智能去重

系统使用 SimHash 算法进行语义去重，确保生成数据的唯一性：

```python
# utils/bio_hash.py 实现了 SimHash 去重
- Hamming distance < 5 的问答对会被标记为重复
- 支持 MD5 精确去重
```

### 双版本输出

启用 Thinking 模式时，输出包含两个版本：

```json
{
  "question": "问题内容",
  "answer_v1": "基础版答案",
  "answer_v2": "思考版答案（带推理过程）",
  "thinking": "模型推理链...",
  "reasoning_chain": {
    "step_1": "推理步骤1",
    "step_2": "推理步骤2"
  }
}
```

### 输出格式

```json
{
  "question": "油菜耐硼毒或缺硼的特异生理及分子机制是什么?",
  "answer": "油菜对硼的敏感性问题...",
  "model": "gpt-5.1",
  "thinking": "分析问题...",
  "category": "核心知识问答",
  "sub_category": "物种特异性知识问答",
  "species": "油菜",
  "metadata": {
    "使用RAG": true,
    "RAG文献数量": 5,
    "RAG参考文献": "[1] Yun Ma et al. (2015). COLD1 confers chilling tolerance..."
  }
}
```

---

## 主要参数

| 参数 | 说明 | 默认值 |
|------|------|--------|
| `--input`, `-i` | 输入问题文件路径 | required |
| `--output`, `-o` | 输出目录路径 | output/ |
| `--model` | 使用的模型 | gpt-5.1 |
| `--models` | 多模型列表 | - |
| `--max-workers` | 最大并发数 | 3 |
| `--use-rag` | 启用 RAG 检索 | False |
| `--think-mode` | Thinking 模式 | none |
| `--workers-thesis` | 问题并发数 | 10 |
| `--workers-chunk` | Chunk 并发数 | 10 |

---

## 示例

```bash
# 基础用法
python seed_Q_generate_A_v2.py --input examples/sample_input.json --output output/

# 指定模型和并发数
python seed_Q_generate_A_v2.py --input examples/sample_input.json --output output/ --model gpt-5.1 --max-workers 5

# 多模型批量处理
python seed_Q_generate_A_v2.py --input data/ --output output/ --models gpt-5.1 deepseek-v3.2

# 启用 Thinking 模式
python seed_Q_generate_A_v2.py --input examples/sample_input.json --output output/ --think-mode auto

# 启用 RAG 检索
python seed_Q_generate_A_v2.py --input examples/sample_input.json --output output/ --use-rag

# RAG + Thinking 组合
python seed_Q_generate_A_v2.py --input examples/sample_input.json --output output/ --use-rag --think-mode medium
```

---

## 提示模板

默认使用 `simple_text_prompt_v8.txt` 作为答案生成模板。

模板目录结构：
```
templates/
├── simple_text_prompt_v8.txt    # 基础提示模板
├── thinking_prompt_v1.txt       # Thinking 模式模板
└── rag_prompt_v2.txt            # RAG 增强模板
```

---

## 项目结构

```
expertq_generatea/
├── seed_Q_generate_A_v2.py     # 主入口（批量 QA 生成）
├── rag_server/                  # RAG 检索服务（ES-free）
│   ├── main.py                 # FastAPI 应用
│   ├── service/
│   │   └── pubmed_api.py      # Biopython Entrez API
│   ├── search_service/         # 搜索服务
│   └── README.md               # RAG Server 使用说明
├── utils/
│   └── bio_hash.py            # SimHash 去重算法
├── templates/                  # 提示模板
├── examples/                  # 示例数据
└── output/                    # 输出目录
```

---

## 依赖

### 主程序依赖

- openai
- httpx
- pydantic
- loguru
- tqdm
- requests

### RAG Server 依赖

- biopython >= 1.81
- fastapi >= 0.104.0
- uvicorn >= 0.24.0

完整依赖见 `pyproject.toml` 和 `rag_server/requirements.txt`。

---

## 常见问题

### Q: RAG Server 无法启动？

```bash
# 检查端口占用
lsof -i :9487

# 重新启动
cd rag_server && python main.py &
```

### Q: 模型返回 503 错误？

某些模型需要使用 Chat API，代码已自动处理。如仍有问题，尝试更换模型。

### Q: 去重不生效？

检查 `utils/bio_hash.py` 中的阈值设置，默认 Hamming distance < 5。
