# Wiki QA Pair Generation Pipeline

This repository implements an automated pipeline for generating foundational agricultural knowledge QA pairs from Wikipedia (Wiki) corpus data.

## Core Workflow

```
Full Wiki corpus
        ↓
   BioBERT agricultural classification model filtering
        ↓
   Broad agricultural content filtering (~760K entries)
        ↓
   Qwen-flash model quality filtering
        ↓
   High-quality content filtering (~19.5K entries)
        ↓
      Deduplication
        ↓
   Final generation set (~19.4K entries)
        ↓
   GPT/LLM agricultural QA pair generation
        ↓
   ~29K QA pairs
```

## Required Resources

### BioBERT Model

Download the pre-trained BioBERT classification model:

```bash
# Create model directories
mkdir -p biobert/models
mkdir -p biobert/data

# Download model file (~413MB)
# Place best_model.bin in biobert/models/

# Prepare keyword file
# Place 中国农业关键词.xlsx in biobert/data/
```

### Wiki Data

Place preprocessed Wiki data in the `data/wiki_filtered/` directory:

```bash
mkdir -p data/wiki_filtered
# Place JSON-format Wiki data
```

## Quick Start

### 1. Environment Setup

```bash
cd wiki_synthesis
uv sync

# Configure API keys
cp .env.example .env
# Edit .env and set OPENAI_API_KEY and QWEN_API_KEY
```

### 2. Run QA Generation

```bash
# Test with sample data
python test_wiki_v2.py

# Run on full dataset
python wiki_qa_bert_qw_v4.py
```

### 3. Configure Data Source

Edit path settings in `wiki_qa_bert_qw_v4.py`:

```python
# Data source directory (configured via environment variable)
WIKI_DATA_DIR = os.getenv("WIKI_DATA_DIR", "./data/wiki_filtered")

# Run mode: stage2 (skip Qwen judgment, generate QA directly)
RUN_MODE = "stage2"

# Processing range
FILE_START_INDEX = 1
FILE_END_INDEX = None  # None means process all
```

## Data Source Path

Data is obtained through a two-stage BERT + Qwen filtering pipeline. Sources may include:
- Preprocessed Chinese Wikipedia corpus
- Custom cleaned text data

Configure the data directory (see `.env.example`):
```
WIKI_DATA_DIR=./data/wiki_filtered
```

## Output Format

Generated QA pairs are saved in JSONL format:

```json
{
  "question": "水稻起源于哪个国家，目前主要分布在哪些地区？",
  "answer": "水稻起源于中国，已有7000年以上的栽培历史，主要分布在亚洲、非洲和美洲的热带及亚热带地区。",
  "cot": "推理过程...",
  "generation_time": "2026-04-17 16:51:09",
  "source_file": "水稻.json",
  "title": "水稻"
}
```

## Project Structure

```
wiki_synthesis/
├── wiki_qa_bert_qw_v4.py       # Main program (BERT+Qwen filtering → GPT generation)
├── test_wiki_v2.py             # Test script (sample data testing)
├── arg_kw.xlsx                # Keyword table
├── examples/
│   ├── sample_data_v2/        # Sample data (水稻.json, 玉米.json, 油菜.json)
│   └── output_v2_test.jsonl   # Test output
├── biobert/                   # BERT model code (for pre-filtering)
└── README.md
```

## Core Features

- **Two-stage filtering**: BioBERT + Qwen pre-filtering for agricultural content
- **High-quality generation**: GPT-5.1-based QA pairs with reasoning chains
- **Atomic facts**: Each QA pair targets a single knowledge point
- **Factual integrity**: Strictly based on source text; no fabrication allowed
- **Checkpoint/resume**: Supports resuming after quota exhaustion

## Key Innovations

### 1. Two-Stage Pre-Filtering Mechanism

| Stage | Method | Filtering Goal | Data Volume |
|------|------|---------|--------|
| Stage 1 | BioBERT agricultural classification model | Identify agricultural content | 9.36M → 760K |
| Stage 2 | Qwen-flash quality judgment | Filter high-quality content | 760K → 19.5K |

This combined filtering strategy compresses data to **0.2%** of the original volume while maintaining content quality, significantly reducing downstream generation costs.

### 2. Dedicated Agricultural Classification Model

- **Domain customization**: BioBERT fine-tuned for agriculture
- **Multi-level classification**: Supports broad agriculture, professional agriculture, ultra-strict, and other classification standards
- **Keyword enhancement**: Combines 5000+ agricultural keywords to improve classification accuracy
- **Adjustable threshold**: Configurable confidence threshold from 0.6 to 0.999

### 3. Atomic Fact Extraction

```
Full Wiki article
    ↓ Structured parsing
Atomic fact list
    ↓ Selective expansion
Single atomic fact → Single QA pair
```

- Splits Wiki entries into multiple atomic facts
- Generates one independent QA pair per atomic fact
- Ensures precision and verifiability of QA pairs

### 4. Factual Integrity Constraints

| Constraint Type | Implementation |
|---------|---------|
| Content constraint | Generate strictly from original text |
| No fabrication | Answers use only concrete facts and data from the text |
| Verifiability | Retain source_file and title for traceability |

### 5. Checkpoint/Resume Mechanism

- Supports resuming after quota exhaustion
- Automatically skips completed files
- Detailed processing logs for progress monitoring

## QA Generation Rules

1. **Agricultural domain classification**: Automatically determines whether text belongs to the agricultural domain
2. **Question requirements**:
   - Based on text content; do not exceed scope
   - Clear, meaningful, and independently understandable
   - Do not use referential wording
3. **Answer requirements**:
   - Prefer concrete facts and data from the text
   - May supplement with domain knowledge where appropriate
   - Fabrication of any information is strictly prohibited
