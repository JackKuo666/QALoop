# Germplasm Report QA Pair Generator (GermplasmReportQAGenerator)

An LLM-based germplasm report QA pair generator designed for crop variety approval reports. Automatically generates high-quality QA pairs from JSON-format germplasm reports for LLM SFT training.

## Core Innovations

### 1. Domain-Specific 8-Category User Intent System

A comprehensive user intent taxonomy designed for germplasm reports:

| Intent Type | Example Question | Target Share |
|---------|---------|---------|
| Micro fact lookup | How many days is the full growth period? What is plant height in cm? | 10-15% |
| Type/affiliation confirmation | Is this variety japonica or indica rice? | 10-15% |
| Horizontal comparison | How much yield increase compared to the control variety? | 15-20% |
| Quality assessment | What is the protein content? How is eating quality? | 10-15% |
| Cultivation guide | When is the best time to sow? How to fertilize? | 20-25% |
| Disease/pest resistance | What is resistance to rice blast? | 5-10% |
| Comprehensive trait summary | How does this variety perform overall? | 10-15% |
| Variety provenance tracing | What are the parental sources? | 5-10% |

### 2. Zero-Anaphora QA Generation

Avoids pronouns and deictic references such as "该品种", "本品种", "它"; uses full variety names directly:

```
❌ Forbidden: 该品种的全生育期是多少天？
✅ Correct: 川引稻2006002的全生育期是多少天？

❌ Forbidden: 它适合在哪些地区种植？
✅ Correct: 郑单958适合在哪些地区种植？
```

### 3. Atomic Short-Answer Control

Requires at least 40% of QA pairs to be atomic short answers within 25 characters, helping the model learn precise factual knowledge during SFT.

### 4. Professional yet Conversational Expression

| Dimension | Requirement |
|------|------|
| Professionalism | Use standard agricultural terms (e.g., 全生育期, 分蘖力, 千粒重) |
| Conversational tone | Slightly conversational; avoid overly formal written style |
| Question structure | 50% start with variety name, 50% other forms (e.g., "全生育期最短的是哪个？") |

### 5. Strict Content Constraints

- **Do not ask about**: Approval number, approval year, approval authority, breeding organization, and other administrative metadata
- **Do not ask about**: Commercial names, naming forms, testing organization names
- **Forbidden**: Existence questions, source-referencing phrases like "根据报告..."
- **Forbidden**: Inferential language ("说明了", "意味着")

## Features

### Generation Strategy
| Type | Covered Intents | Default Count |
|------|---------|---------|
| QA pairs | 8 user intents (micro facts, type affiliation, comparison, quality, cultivation, disease/pest, comprehensive traits, provenance) | 8 per report |

### Core Features
- **Intelligent content filtering**: Automatically skips reports with empty "特征特性" field
- **Zero-anaphora principle**: Avoids "该品种", "本品种", and similar references
- **Multi-dimensional coverage**: Covers at least 5 of the 8 intent categories
- **Professional conversational tone**: Professional with slight conversational style
- **Batch processing**: Automatically scans all species folders; supports organization by species
- **Checkpoint resume**: Supports interruption recovery; already-processed files are skipped
- **Random sampling**: Supports random sampling of a specified number of files per species for testing

### Performance Optimizations
- Concurrency increased to 100 (configurable)
- Multi-threaded concurrent processing
- Batch processing mechanism
- Fast fail and timeout control
- Thread-safe file writing

## Install Dependencies

```bash
# Install dependencies with uv (recommended)
uv sync

# Or install with pip
pip install openai python-dotenv tqdm
```

## Configuration

### Environment Variables (.env file)
```bash
cp .env.example .env
# Edit .env and set OPENAI_API_KEY

# Optional configuration
GERMPLASM_REPORT_PATH=./examples  # Germplasm report data directory
OUTPUT_DIR=QAGenarator            # Output directory
RECORDS_DIR=Processing_records     # Processing records directory
```

### Script Configuration Parameters (centralized at top of file)

| Parameter | Default | Description |
|------|-------|------|
| `MAIN_INPUT_PATH` | `./examples` | Germplasm report root directory (overridable via GERMPLASM_REPORT_PATH) |
| `OUTPUT_DIR` | `QAGenarator` | Output directory base name (timestamp appended automatically) |
| `RECORDS_DIR` | `Processing_records` | Processing records directory (fixed, for checkpoint resume) |
| `MAX_Q_PER_REPORT` | `8` | QA pairs generated per report |
| `SAMPLE_SIZE` | `1000` | Random sample file count (or "all" to process all) |
| `MAX_WORKERS` | `100` | Concurrent thread count |
| `API_BASE_URL` | `os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1")` | API URL (via environment variable) |
| `DEFAULT_MODEL` | `gpt-5.1` | Model name |
| `MAX_OUTPUT_TOKENS` | `8000` | Max API output tokens |
| `TIMEOUT_SECONDS` | `900` | Per-file processing timeout (seconds) |
| `BATCH_SLEEP_SECONDS` | `1.0` | Sleep time between batches (seconds) |

## Quick Start

### 1. Install Dependencies

```bash
cd seedreport_synthesis
uv sync
```

### 2. Configure API Key

```bash
cp .env.example .env
# Edit .env and set OPENAI_API_KEY
```

### 3. Run Tests

```bash
# Quick test with sample data
uv run python test_seedreport.py

# Or use main script (configure MAIN_INPUT_PATH first)
uv run python QAGenerator_GermplasmReport_SOP_server_1219.py
```

## Usage

### 1. Configure Environment
```bash
# Configure environment variables
cp .env.example .env

# Modify script configuration
# Edit the "configurable parameters" section at the top of the script to set input path, etc.
```

### 2. Run Script
```bash
# Basic usage (uses default configuration in script)
python QAGenerator_GermplasmReport_SOP_server_1219.py

# Test mode (set SAMPLE_SIZE to a small value first, e.g. 10)
# Edit script to set SAMPLE_SIZE = 10, then run
python QAGenerator_GermplasmReport_SOP_server_1219.py

# Production (set SAMPLE_SIZE = "all")
# Edit script to set SAMPLE_SIZE = "all", then run
python QAGenerator_GermplasmReport_SOP_server_1219.py
```

## Input Format

### Directory Structure
```
MAIN_INPUT_PATH/
├── maize/               # Corn
│   ├── report001.json
│   ├── report002.json
│   └── ...
├── AsianRice/           # Rice
│   ├── report001.json
│   └── ...
├── cotton/              # Cotton
│   └── ...
└── ...
```

### Germplasm Report File Format (JSON)
```json
{
  "品种名称": "川引稻2006002",
  "作物名称": "水稻",
  "特征特性": "[Required field; skipped if empty]",
  "审定编号": "...",
  "育种单位": "...",
  "产量表现": "...",
  "栽培技术要点": "...",
  "其他字段": "..."
}
```

**Important notes**:
- Each JSON file must contain the "特征特性" field
- If "特征特性" is empty, the file is skipped and logged
- null values are automatically filtered and do not affect processing

## Output Format

### Output Directory Structure
```
QAGenarator_2024-01-22_14-30-25/        # QA data directory (with timestamp)
├── maize_qa.jsonl                       # Corn QA data
├── AsianRice_qa.jsonl                   # Rice QA data
├── cotton_qa.jsonl                      # Cotton QA data
└── ...

Processing_records/                      # Processing records directory (fixed, no timestamp)
├── maize_processed_records.jsonl       # Corn processed file records
├── maize_skipped_records.jsonl         # Corn skipped file records
├── AsianRice_processed_records.jsonl   # Rice processed file records
├── AsianRice_skipped_records.jsonl     # Rice skipped file records
└── ...
```

### QA Data File Format ({species}_qa.jsonl)

One JSON record per line:
```json
{
  "qa_pairs": [
    {
      "id": "qa_001",
      "question": "川引稻2006002的全生育期是多少天？",
      "answer": "川引稻2006002的全生育期为142天"
    },
    {
      "id": "qa_002",
      "question": "问题文本",
      "answer": "答案文本"
    }
  ],
  "meta_data": {
    "report_id": "川引稻2006002",
    "species": "水稻",
    "generation_time": "2024-01-22 14:30:25",
    "model_name": "gpt-5.1",
    "input_tokens": 1234,
    "output_tokens": 567,
    "total_tokens": 1801,
    "processing_time_seconds": 2.35
  },
  "context": "Original report JSON string (formatted, null values removed)"
}
```

### Processing Record File Format

#### Processed File Records ({species}_processed_records.jsonl)
```json
{
  "filename": "report001.json",
  "species": "水稻",
  "processed_time": "2024-01-22 14:30:25",
  "success": true,
  "qa_count": 8,
  "input_tokens": 1234,
  "output_tokens": 567,
  "total_tokens": 1801,
  "cost_usd": 0.012345
}
```

#### Skipped File Records ({species}_skipped_records.jsonl)
```json
{
  "filename": "report002.json",
  "species": "水稻",
  "skipped_time": "2024-01-22 14:30:26",
  "reason": "特征特性为空"
}
```

## Quality Control

### QA Generation Rules
- **8 user intent coverage**: Cover at least 5 intent categories
  1. Micro fact lookup
  2. Type/trait/affiliation confirmation
  3. Horizontal comparison
  4. Professional quality assessment
  5. Cultivation guide
  6. Disease/pest resistance
  7. Comprehensive trait summary
  8. Variety provenance tracing

- **Expression requirements**:
  - Standard professional terminology
  - Slightly conversational tone
  - At least 40% of QA pairs are atomic short answers within 25 characters
  - Diverse question structures (50% start with variety name, 50% other forms)

### Strict Prohibitions
- **Content prohibitions**:
  - Do not ask about approval number, year, authority, breeding organization, etc.
  - Do not ask about commercial names or naming forms
  - Do not ask about testing, identification, or trial organization names
  - No existence questions or questions pointing at "the report itself"

- **Phrasing prohibitions**:
  - No "该品种", "本品种", "它", or similar anaphora
  - No source-referencing phrases such as "根据报告", "报告中显示", "审定数据中"
  - No inferential language such as "说明了", "意味着", "由此可见"
  - No textbook-style causal explanations or long lead-ins

### Length Validation
- Question ≥ 8 characters
- Answer ≥ 10 characters

## Checkpoint Resume

### How It Works
1. Processing records are saved in the fixed `Processing_records/` directory
2. Processed file list is automatically loaded before each run
3. Already-processed files are skipped automatically
4. After interruption, execution can continue without reprocessing

### Record File Notes
- **Append mode**: All processing records use append mode to preserve history
- **Thread-safe**: Locks protect concurrent multi-threaded writes
- **Fixed directory**: Records directory has no timestamp and is kept permanently

### Clear Processing Records
To reprocess all files, delete the corresponding record files:
```bash
# Delete processing records for one species
rm Processing_records/maize_processed_records.jsonl
rm Processing_records/maize_skipped_records.jsonl

# Or delete all processing records
rm -rf Processing_records/
```

## Cost Statistics

### Automatic Statistics
The script automatically calculates and displays:
- **Total cost**: USD
- **Total tokens**: input, output, total
- **Average cost**: average cost and tokens per report
- **Time statistics**: actual runtime, cumulative processing time, concurrency speedup ratio

### Pricing Configuration
Model pricing table configured in the script (per 1K tokens):
```python
MODEL_PRICING = {
    "gpt-5.1": {
        "input": 0.00125,   # $0.00125 per 1K input tokens
        "output": 0.01      # $0.01 per 1K output tokens
    }
}
```

### Example Output
```
💰 费用统计:
   总成本: $0.123456 USD
   总输入 tokens: 123,456
   总输出 tokens: 45,678
   总 tokens: 169,134

📈 平均每份报告:
   成本: $0.001235 USD
   输入 tokens: 1,234.6
   输出 tokens: 456.8
   总 tokens: 1,691.3
   处理时间: 2.35 秒
```

## Performance Optimization

### Concurrent Processing
- **Thread pool**: Multi-threaded concurrency via `ThreadPoolExecutor`
- **Batch processing**: Submit tasks in batches to avoid submitting too many at once
- **Batch sleep**: Sleep between batches to avoid API rate limiting

### Timeout Control
- **Per-file timeout**: Default 900 seconds (15 minutes)
- **Slow file warning**: Warning output if processing exceeds 60 seconds

### Thread Safety
- **File write locks**: Independent lock per output file
- **Statistics lock**: Lock protects shared statistics variables

## FAQ

| Issue | Solution |
|------|---------|
| API call failure | Check API key and network connection; review error messages |
| Empty QA output | Check whether report content is sufficient and "特征特性" is non-empty |
| File skipped | Check `{species}_skipped_records.jsonl` for skip reason |
| Slow processing | Increase `MAX_WORKERS` (watch for API rate limits) |
| High cost | Reduce `SAMPLE_SIZE` for testing first; process all after validation |
| Checkpoint resume failure | Check that `Processing_records/` exists and is writable |
| Output directory overwrite | Each run adds a timestamp; previous results are not overwritten |

## Debugging

### Debug Mode
Enable debug mode via environment variable:
```bash
export DEBUG_API_RESPONSE=true
python QAGenerator_GermplasmReport_SOP_server_1219.py
```

Debug mode prints the full response object structure on the first API call, useful for inspecting cost fields and other information.

## Project Info

- **Author**: Lijie
- **Version**: SOP
- **Created**: 2025/12/18
- **Last updated**: 2025/12/19

## Notes

1. **Input directory structure**: Ensure correct structure with a separate folder per species
2. **Test first**: Test with a small file set (`SAMPLE_SIZE`) before processing all
3. **Timestamped directories**: Each run creates a new timestamped output directory; previous QA data is not overwritten
4. **Append mode**: Processing records use append mode to preserve all historical processing info
5. **特征特性 field**: Must be present and non-empty; otherwise the file is skipped
6. **Concurrency**: Set concurrency based on API limits and server capacity
7. **Cost control**: Estimate cost with a small sample before large-scale processing
