# ExpertQ GenerateA - Agricultural Breeding Expert QA Batch Generation System

## Project Overview

ExpertQ GenerateA is a **batch QA generation tool** powered by large language models (LLM) that generates professional, accurate question-answer data for researchers and practitioners in rice, corn, wheat, rapeseed, soybean, and major livestock/poultry domains.

### Core Features

| Feature | Description |
|------|------|
| **Multi-model support** | Supports 22 mainstream LLMs (GPT, Claude, Gemini, DeepSeek, Qwen, GLM, Grok, etc.) |
| **Thinking mode** | Extracts model reasoning process to enhance inference capability |
| **Concurrent processing** | Supports concurrent processing across multiple files and questions |
| **Quality assurance** | Dual-version answers, reasoning chain extraction, intelligent deduplication |
| **RAG retrieval augmentation** | Optional PubMed literature retrieval for answers with citations |

### Requirements

- Python 3.10+
- uv package manager

### Installation

```bash
cd expertq_generatea
uv sync
```

### Configuration

Create a `.env` file:

```bash
OPENAI_API_KEY=${OPENAI_API_KEY}
OPENAI_BASE_URL=https://api.openai.com/v1
DEFAULT_MODEL=gpt-5.1
```

### Quick Start

```bash
# Run with sample data
uv run python seed_Q_generate_A_v2.py --input examples/sample_input.json --output output/
```

---

## Supported Models

### Model List

| Model Name | Description | API Type |
|----------|------|----------|
| **GPT Series** | | |
| `gpt-5.1` | GPT-5.1 (default) | Chat |
| `gpt-5.2` | GPT-5.2 | Responses |
| `gpt-4o` | GPT-4o | Responses |
| `gpt-oss-120b` | GPT-OSS-120B | Chat |
| **Claude Series** | | |
| `claude-sonnet-4-5-20250929` | Claude Sonnet 4.5 | Chat |
| `claude-sonnet-4-20250514` | Claude Sonnet 4 (deprecated) | Responses |
| `claude-opus-4-20250514` | Claude Opus 4 (deprecated) | Responses |
| `claude-3-5-haiku-20241022` | Claude 3.5 Haiku | Responses |
| **Gemini Series** | | |
| `gemini-2-5-pro` | Gemini 2.5 Pro | Responses |
| `gemini-2-5-flash` | Gemini 2.5 Flash | Responses |
| **DeepSeek Series** | | |
| `deepseek-v3.2` | DeepSeek V3.2 | Chat |
| `deepseek-v3.2-thinking` | DeepSeek V3.2 Thinking | Responses |
| `deepseek-v3` | DeepSeek V3 | Responses |
| `deepseek-v2.5` | DeepSeek V2.5 | Responses |
| **GLM Series** | | |
| `glm-4.6` | GLM-4.6 | Chat |
| **Qwen Series** | | |
| `qwen3-30b-a3b` | Qwen3 30B A3B | Responses |
| `qwen3-30b-a3b-think` | Qwen3 30B Think | Chat |
| `qwen-max` | Qwen Max | Chat |
| `qwen-plus` | Qwen Plus | Chat |
| `qwen-turbo` | Qwen Turbo | Chat |
| **Grok Series** | | |
| `grok-4-1-fast-reasoning` | Grok 4.1 Fast | Chat |

### Multi-Model Batch Processing

Supports generating answers with multiple models simultaneously:

```bash
# Use multiple models
python seed_Q_generate_A_v2.py --input data/ --output output/ --models gpt-5.1 gpt-5.2 deepseek-v3.2
```

---

## Thinking Mode

Thinking mode extracts the model's reasoning process (Chain of Thought) and produces dual-version answers:
- **Basic version**: Direct answer
- **Thinking version**: Reasoning process + final answer

### Thinking Mode Options

| Option | Description |
|------|------|
| `auto` | Auto-select (based on model capabilities) |
| `low` | Low reasoning intensity, fast response |
| `medium` | Medium reasoning intensity |
| `high` | High reasoning intensity, detailed reasoning |

### Usage Examples

```bash
# Auto-select thinking mode
python seed_Q_generate_A_v2.py --input examples/sample_input.json --output output/ --think-mode auto

# Medium reasoning intensity
python seed_Q_generate_A_v2.py --input examples/sample_input.json --output output/ --think-mode medium

# Specify a thinking model
python seed_Q_generate_A_v2.py --input examples/sample_input.json --output output/ --model deepseek-v3.2-thinking
```

---

## RAG Retrieval Augmentation (Optional)

When RAG is enabled, the system first retrieves relevant literature from PubMed, then generates answers with citations.

### Workflow

```
Question → RAG Server → PubMed literature retrieval
                   ↓
         Literature abstracts + original question
                   ↓
              LLM answer generation
                   ↓
         Answer output with citations
```

### Start RAG Server

```bash
# 1. Start RAG Server (background)
cd rag_server && python main.py &
sleep 3

# 2. Run QA generation (with RAG enabled)
cd ..
python seed_Q_generate_A_v2.py \
  --input examples/sample_input.json \
  --output output/ \
  --use-rag \
  --model gpt-5.1
```

### RAG Parameters

| Parameter | Description | Default |
|------|------|--------|
| `--use-rag` | Enable RAG retrieval | False |
| `RAG_URL` | RAG Server URL | `http://localhost:9487/retrieve` |
| `pubmed_topk` | Number of retrieved papers | 10 |
| `RAG_TIMEOUT` | RAG request timeout | 300 seconds |

---

## Quality Assurance

### Intelligent Deduplication

The system uses SimHash for semantic deduplication to ensure unique generated data:

```python
# utils/bio_hash.py implements SimHash deduplication
- QA pairs with Hamming distance < 5 are marked as duplicates
- Supports MD5 exact deduplication
```

### Dual-Version Output

When Thinking mode is enabled, output includes two versions:

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

### Output Format

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

## Main Parameters

| Parameter | Description | Default |
|------|------|--------|
| `--input`, `-i` | Input question file path | required |
| `--output`, `-o` | Output directory path | output/ |
| `--model` | Model to use | gpt-5.1 |
| `--models` | Multi-model list | - |
| `--max-workers` | Max concurrency | 3 |
| `--use-rag` | Enable RAG retrieval | False |
| `--think-mode` | Thinking mode | none |
| `--workers-thesis` | Question concurrency | 10 |
| `--workers-chunk` | Chunk concurrency | 10 |

---

## Examples

```bash
# Basic usage
python seed_Q_generate_A_v2.py --input examples/sample_input.json --output output/

# Specify model and concurrency
python seed_Q_generate_A_v2.py --input examples/sample_input.json --output output/ --model gpt-5.1 --max-workers 5

# Multi-model batch processing
python seed_Q_generate_A_v2.py --input data/ --output output/ --models gpt-5.1 deepseek-v3.2

# Enable Thinking mode
python seed_Q_generate_A_v2.py --input examples/sample_input.json --output output/ --think-mode auto

# Enable RAG retrieval
python seed_Q_generate_A_v2.py --input examples/sample_input.json --output output/ --use-rag

# RAG + Thinking combined
python seed_Q_generate_A_v2.py --input examples/sample_input.json --output output/ --use-rag --think-mode medium
```

---

## Prompt Templates

Default answer generation template: `simple_text_prompt_v8.txt`.

Template directory structure:
```
templates/
├── simple_text_prompt_v8.txt    # Base prompt template
├── thinking_prompt_v1.txt       # Thinking mode template
└── rag_prompt_v2.txt            # RAG-enhanced template
```

---

## Project Structure

```
expertq_generatea/
├── seed_Q_generate_A_v2.py     # Main entry (batch QA generation)
├── rag_server/                  # RAG retrieval service (ES-free)
│   ├── main.py                 # FastAPI application
│   ├── service/
│   │   └── pubmed_api.py      # Biopython Entrez API
│   ├── search_service/         # Search service
│   └── README.md               # RAG Server usage guide
├── utils/
│   └── bio_hash.py            # SimHash deduplication algorithm
├── templates/                  # Prompt templates
├── examples/                  # Sample data
└── output/                    # Output directory
```

---

## Dependencies

### Main Program Dependencies

- openai
- httpx
- pydantic
- loguru
- tqdm
- requests

### RAG Server Dependencies

- biopython >= 1.81
- fastapi >= 0.104.0
- uvicorn >= 0.24.0

See `pyproject.toml` and `rag_server/requirements.txt` for full dependencies.

---

## FAQ

### Q: RAG Server won't start?

```bash
# Check port usage
lsof -i :9487

# Restart
cd rag_server && python main.py &
```

### Q: Model returns 503 error?

Some models require the Chat API; the code handles this automatically. If issues persist, try a different model.

### Q: Deduplication not working?

Check threshold settings in `utils/bio_hash.py`; default is Hamming distance < 5.
