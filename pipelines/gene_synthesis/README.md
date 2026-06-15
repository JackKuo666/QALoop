# Gene Literature QA Pair Generator (Gene QA Generator)

## Project Overview

The Gene Literature QA Pair Generator (`Gene_QAGenerator_dev.py`) is a batch data processing tool powered by large language models (LLM) that automatically generates high-quality question-answer pairs (QA pairs) from JSON-format gene literature data. The generated QA pairs target agricultural genomics and molecular breeding, and are suitable for SFT (Supervised Fine-Tuning) model training and knowledge base construction. **It uses the dedicated agricultural genomics prompt template (GeneKnowledge_prompt_v4_2)** with designs such as evidence anchoring, multi-hop reasoning, and trigger mapping to produce atomic, standalone English academic QA within factual boundaries. The script supports non-duplicate DOI file lists, random sampling, multi-threaded concurrency, checkpoint/resume, and cost statistics.

## Prompt Design and Innovations

The system prompt used by this script (`build_prompt`, derived from GeneKnowledge_prompt_v4_2) is designed for agricultural genomics and molecular breeding scenarios, with clear characteristics and innovations in controllability, reproducibility, and hallucination prevention.

### Core Design Principle: Evidence-Anchored Facticity

- **Goal**: Generate knowledge that can serve as "eternal biological laws" while **strictly staying within given evidence boundaries**.
- **Proportional Complexity rule**: Question depth maps one-to-one to JSON data depth.
  - **Level 1 (Observation)**: When only expression/phenotype data exists, ask only "What is the response/pattern...".
  - **Level 2 (Correlation)**: When relationships are mentioned but no specific intermediate factors are given, ask "What is the regulatory relationship...".
  - **Level 3 (Mechanism)**: Only when named molecular nodes and directions exist (e.g. `Regulatory_Pathway`, `Interacting_Proteins`, or `Summary`), ask "Through what molecular pathway/mechanism...".
- **Boundary awareness**: If context only supports spatiotemporal pattern facts, do not force molecular mechanism questions; prefer complete shallow QA over incomplete deep QA.
- **Anti-hallucination**: Do not use speculative language such as "likely / probably / suggests" unless the source text does; if data stops at "Gene A increases Gene B", the answer stops there too.
- **Condition completeness**: Preserve experimental conditions (e.g. "under 15% PEG-6000", "at 4 h post-heat stress"); remove reporting language (e.g. "the study found").

### Innovation 1: Multi-hop Reasoning Protocol

- **Constraint**: Each gene must generate 1–2 "multi-hop" QA pairs that **connect at least two biological dimensions**.
- **Three explicit paths**:
  - **Path A (Genotype → Breeding)**: `Key_Variant_Site` → `Core_Phenotypic_Effect` → `Breeding_Application_Value`.
  - **Path B (Validation → Mechanism)**: `Experimental_Methods` → `Quantitative_Phenotypic_Alterations` → `Regulatory_Mechanism`.
  - **Path C (Comparative logic)**: `Variety/Experimental_Materials` → `Quantitative_Phenotypic_Alterations` → `Core_Phenotypic_Effect`.
- **Answer requirement**: Explicitly write the logic chain: "Step 1 (Evidence A) → Step 2 (Evidence B) → Conclusion" to support interpretable, traceable reasoning for training.

### Innovation 2: Instruction Diversity & Trigger Mapping

- **Data-driven question types**: Select question style based on **non-empty JSON fields** to avoid unanswerable questions.
- **Trigger-to-question-type mapping**:
  - `Expression_Pattern` / `Subcellular_Localization` → **Pattern & Localization** (when and where genes/proteins act).
  - `Quantitative_Phenotypic_Alterations` → **Phenotypic Fact** (measurable outcomes, including P-values and related metrics).
  - `Regulatory_Mechanism` → **Regulatory Logic** (directional relationships between biological entities).
- **Effect**: The same literature automatically adapts to different QA dimensions under different field combinations, improving coverage and usability.

### Innovation 3: Exhaustiveness & Precision

- **No omissions**: Retain all numerical values, P-values (e.g. P < 0.05), and Locus IDs.
- **Identifier Grounding**: Each QA pair must include **both Gene Symbol and Locus ID** in the question or answer (e.g. Ghd8 ↔ Os08g07750) for retrieval and knowledge linking.
- **Spatiotemporal precision**: Must specify tissue, cell type, and developmental stage for downstream filtering and reproducibility.

### Task Execution Protocol

The prompt embeds a four-step execution flow for predictable, reproducible model behavior:

1. **Data Depth Audit**: Scan JSON to identify downstream targets, upstream signaling chains, and fields supporting multi-hop reasoning.
2. **Question Calibration**: Select question dimensions matching the **highest level of currently non-empty data**.
3. **Synthesis**: Draft 1–2 multi-hop QA pairs (Level 3 or cross-dimensional).
4. **Final Audit**: Verify answers do not exceed JSON scope; units/P-values/Locus IDs are preserved; multi-hop logic chains are clear.

### Output Specification and Dimension Labels

- **Format**: Output only a valid JSON array with no preamble or markdown code blocks; fields: `id`, `gene_name`, `dimension`, `question`, `answer`.
- **Dimensions**: Five unified categories — `Gene Identity`, `Regulatory Mechanisms`, `Functional Pathways`, `Phenotypic Evidence`, `Experimental Validation` — for downstream statistics, filtering, and evaluation.

This design yields QA pairs with **rigor within evidence boundaries**, **interpretable multi-hop reasoning**, and **field-driven question diversity**, suitable as SFT and knowledge base data for agricultural genomics and molecular breeding.

## Key Features

- 📂 **Batch processing**: Process JSON gene literature in bulk via non-duplicate DOI file lists (CSV/TXT) or directory scanning
- 🎲 **Random sampling**: Randomly sample files by count for small-scale testing before full runs
- ⚡ **Concurrent processing**: Multi-threaded LLM API calls with configurable worker count
- 🔄 **Checkpoint/resume**: Automatically skip processed files via processing records (JSONL) in a fixed directory
- 💰 **Cost statistics**: Aggregate input/output tokens and API costs (from API response or local pricing table)
- 📁 **Timestamped output**: Each run creates a timestamped output directory to avoid overwriting history
- 🧾 **Multi-dimensional QA**: Output includes `gene_name`, `dimension`, and other fields for filtering and evaluation
- 🛡️ **Fault-tolerant parsing**: Tolerant parsing of various LLM JSON formats (markdown code blocks, NDJSON, etc.)
- 📜 **Dedicated prompts**: Agricultural genomics prompts (evidence anchoring + multi-hop reasoning + trigger mapping) ensure QA stays within evidence boundaries, is interpretable, and matches data depth

## Technical Architecture

### Core Technology Stack

- **Python 3.x** - Primary development language
- **OpenAI SDK** - Calls Responses API (`client.responses.create`) for QA generation
- **python-dotenv** - Loads `OPENAI_API_KEY` from `.env`
- **tqdm** - Progress bar display
- **concurrent.futures** - Multi-threaded concurrency

### Script Structure Overview

```
Gene_QAGenerator_dev.py
├── Configurable parameters section
│   ├── Input/output paths (MAIN_INPUT_PATH, OUTPUT_DIR, RECORDS_DIR)
│   ├── Processing parameters (MAX_Q_PER_REPORT, SAMPLE_SIZE, MAX_WORKERS)
│   ├── API configuration (API_BASE_URL, DEFAULT_MODEL, MAX_OUTPUT_TOKENS)
│   └── Timeout and performance (TIMEOUT_SECONDS, BATCH_SLEEP_SECONDS)
│
├── Cost and Tokens
│   ├── MODEL_PRICING / DEFAULT_PRICING
│   ├── calculate_cost()
│   └── get_empty_tokens_info()
│
├── LLM invocation and parsing
│   ├── build_prompt()           # System/user prompts (agricultural genomics QA spec)
│   ├── call_llm_for_qa()        # API call, token/cost extraction, multi-format JSON parsing
│   └── Output qa_pairs + meta_data + context
│
├── Data processing and IO
│   ├── remove_null_values()     # Remove null values from JSON
│   ├── prepare_json_for_prompt()
│   ├── ensure_output_dir()
│   ├── load_duplicate_dois()     # Fallback: duplicate DOI list
│   ├── load_processed_files()   # Checkpoint/resume: processed file list
│   ├── append_processed_record() / append_skipped_record()
│   └── get_file_write_lock()    # Thread-safe writes to same JSONL
│
├── Single-file and batch processing
│   ├── process_single_json()    # Single file → read JSON, DOI check, call LLM, write one JSONL line
│   └── batch_process_json_dir() # Directory batch processing, sampling, thread pool, summary stats
│
└── __main__                     # Timestamped output dir, calls batch_process_json_dir
```

## Installation and Deployment

### Requirements

- Python 3.8+
- Accessible OpenAI-compatible API (script default `API_BASE_URL` points to a proxy endpoint)

### Dependency Installation

### Installation

```bash
# Install dependencies with uv (recommended)
uv sync

# Or use pip
pip install -r requirements.txt
```

Main dependencies:

- openai
- python-dotenv
- tqdm

(The script uses only standard library modules: `os`, `re`, `json`, `time`, `csv`, `random`, `pathlib`, `datetime`, `concurrent.futures`, `threading`.)

### Configuration

1. **Environment variables**  
   Create `.env` in the project root:

   ```bash
   OPENAI_API_KEY=${OPENAI_API_KEY}
   ```

2. **Script-level configurable parameters (top of file)**  
   Edit the "Configurable parameters section" in `Gene_QAGenerator_dev.py`:

   | Category | Parameter | Description |
   |--------------|--------------------------|------|
   | Input/Output | `MAIN_INPUT_PATH` | Directory containing gene literature JSON files |
   | | `OUTPUT_DIR` | Output directory prefix (timestamp appended at runtime) |
   | | `RECORDS_DIR` | Processing records directory (checkpoint/resume) |
   | Processing | `MAX_Q_PER_REPORT` | Max QA pairs per literature record |
   | | `SAMPLE_SIZE` | Sample count (number) or `"all"` |
   | | `MAX_WORKERS` | Concurrent thread count |
   | API | `API_BASE_URL` | API base URL |
   | | `DEFAULT_MODEL` | Model name (e.g. gpt-5.1) |
   | | `MAX_OUTPUT_TOKENS` | Max output tokens per call |
   | Timeout & Performance | `TIMEOUT_SECONDS` | Per-file processing timeout (seconds) |
   | | `BATCH_SLEEP_SECONDS` | Sleep between batches (seconds) to mitigate rate limits |

3. **File list (recommended)**  
   - Use a non-duplicate DOI file list to avoid duplicate literature and unify entry points.  
   - Set `csv_file_list` in `__main__` (e.g. `rice_plants_only.csv` or `excel_non_duplicate_files.csv`).  
   - Supports **CSV** (must include filename column, e.g. 文件名/`filename`/`Filename`) or **TXT** (one filename per line).  
   - If the list file does not exist, the script falls back to scanning all `*.json` under `MAIN_INPUT_PATH`; if `duplicate_dois_list.csv` exists, it is used for DOI duplicate skipping (fallback logic).

## Usage Guide

### Quick Start (with sample data)

```bash
uv run python Gene_QAGenerator_dev.py --input examples/
```

### Input Requirements

- **Example directory structure**:

  ```
  GeneLiterature/   (or directory set by MAIN_INPUT_PATH)
  ├── PMC10035410.json
  ├── PMC2565487.json
  └── ...
  ```

- Each JSON must contain gene literature fields such as: `Title`, `DOI`, `Plant_Genes`, `Animal_Genes`, `Microbial_Genes`, etc. (the script uses these to determine type and extract species information).

### Basic Run

```bash
# Ensure OPENAI_API_KEY in .env and MAIN_INPUT_PATH, file list, etc. in the script are configured
python Gene_QAGenerator_dev.py
```

- Output directory is automatically named `output_YYYY-MM-DD_HH-MM-SS` with `gene_literature_qa.jsonl` inside.  
- Processing records are written to `RECORDS_DIR` (default `processing_records/`):  
  - `GeneLiterature_processed_records.jsonl`: processed files with tokens/cost  
  - `GeneLiterature_skipped_records.jsonl`: skip records (e.g. duplicate DOI, LLM returned no valid QA)

### Output Format

**QA data file** (`gene_literature_qa.jsonl`, one JSON object per line):

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

**Processing record files** (append-only JSONL):

- Processed: `filename`, `species`, `processed_time`, `success`, `qa_count`, `input_tokens`, `output_tokens`, `total_tokens`, `cost_usd`
- Skipped: `filename`, `species`, `skipped_time`, `reason`

## Run Examples

**Expert QA generation tool (demo from LPREADME)**:

```bash
python expertQ_generateA_v2.py --input data.jsonl --output output.jsonl
```

**This script (gene literature QA generation)**:

```bash
python Gene_QAGenerator_dev.py
```

After running, the console outputs: file source, total/processed/pending counts, successfully processed literature count, generated QA pair count, skip count, total cost, total/average tokens, runtime, and concurrency speedup ratio.

## Performance and Optimization

- **Concurrency**: Balance speed and API rate limits via `MAX_WORKERS` and `BATCH_SLEEP_SECONDS`.  
- **Checkpoint/resume**: Relies on processed records under `RECORDS_DIR`; re-runs do not reprocess successfully completed files.  
- **Cost**: Prefer API-returned cost fields; otherwise compute using in-script `MODEL_PRICING`/`DEFAULT_PRICING`.  
- **Slow requests**: Per-file processing exceeding `SLOW_PROCESSING_THRESHOLD` (default 60 seconds) triggers a progress bar warning.

## Troubleshooting

| Symptom | Suggestion |
|------|------|
| API error / no response | Check `OPENAI_API_KEY`, `API_BASE_URL`, network, and proxy |
| Missing tokens or cost | Confirm API returns `usage` (input_tokens/output_tokens); set `DEBUG_API_RESPONSE=true` to inspect response structure |
| Empty QA generation | Check skip records (see `*_skipped_records.jsonl`); or verify single JSON content is not too short/malformed |
| Reprocessing same files | Confirm `RECORDS_DIR` matches `processed_record_path` and records were not manually cleared |
| Timeout | Increase `TIMEOUT_SECONDS` or reduce `MAX_Q_PER_REPORT`/single literature length |

## Notes

- Input directory must exist and contain valid JSON; recommend using `valid_non_duplicate_files.csv` from tools like `analyze_gene_literature.py` as the file list.  
- Run a small sample first (e.g. `SAMPLE_SIZE=5`) to validate workflow and quality before switching to `"all"` for full runs.  
- Processing records are stored in a fixed directory with append-only writes for checkpoint/resume and audit; only QA output directories are timestamped per run to avoid overwriting.

## License and Contributions

- License follows the project repository (e.g. MIT, see root LICENSE).  
- Feedback and improvements welcome via Issue / Pull Request.

## Changelog

### Current version (dev)
- Non-duplicate DOI file lists (CSV/TXT) with directory scan fallback
- Multi-threaded concurrency, checkpoint/resume, timestamped output directories
- Cost and token statistics with API-returned cost and local pricing table support
- Agricultural genomics dedicated prompts (GeneKnowledge_prompt_v4_2): evidence-anchored facticity, multi-hop reasoning protocol, trigger mapping, exhaustiveness & precision, task execution protocol; output includes `gene_name`, `dimension` QA plus `meta_data`, `context`

---

**Note**: This tool generates training QA data from gene literature and does not replace professional bioinformatics or breeding conclusions. Consult domain experts for actual breeding or application decisions.
