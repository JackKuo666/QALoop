# Agricultural Knowledge QA Pair Generation System

This repository contains **11 independent data pipelines** that automatically generate high-quality question-answer (QA) pairs from diverse sources (papers, patents, books, knowledge graphs, Wikipedia, germplasm reports, etc.) for LLM SFT (Supervised Fine-Tuning) training.

---

## Table of Contents

- [Quick Overview](#quick-overview)
- [Pipeline Details](#pipeline-details)
  - [1. expert_qa_augmentation](#1-expert_qa_augmentation-agricultural-qa-augmentation)
  - [2. expertq_generatea](#2-expertq_generatea-agricultural-breeding-expert-qa-batch-generation)
  - [3. gene_synthesis](#3-gene_synthesis-gene-literature-qa-pair-generation)
  - [4. kg_synthesis](#4-kg_synthesis-knowledge-graph-causal-chain-qa-generation)
  - [5. paper_synthesis](#5-paper_synthesis-academic-paper-qa-generation)
  - [6. patent_synthesis](#6-patent_synthesis-patent-qa-pair-generation)
  - [7. thesis_synthesis](#7-thesis_synthesis-thesis-sft-qa-pair-generation)
  - [8. wiki_synthesis](#8-wiki_synthesis-wikipedia-knowledge-qa)
  - [9. books_qa_generater](#9-books_qa_generater-book-chapter-qa-generation)
  - [10. qa_data_acquisition_quality](#10-qa_data_acquisition_quality-qa-quality-verification)
  - [11. seedreport_synthesis](#11-seedreport_synthesis-germplasm-report-qa-generation)
- [Cross-Pipeline Common Techniques](#cross-pipeline-common-techniques)
- [Quick Start](#quick-start)

---

## Quick Overview

| # | Pipeline | Data Source | Key Innovation | Output |
|---|----------|-------------|----------------|--------|
| 1 | [expert_qa_augmentation](#1-expert_qa_augmentation) | Seed questions | 20+ generation strategies, intelligent RAG retrieval | JSONL |
| 2 | [expertq_generatea](#2-expertq_generatea) | Seed questions | 31+ model support, Thinking mode | JSONL |
| 3 | [gene_synthesis](#3-gene_synthesis) | Gene literature | Evidence anchoring, multi-hop reasoning protocol | JSONL |
| 4 | [kg_synthesis](#4-kg_synthesis) | Knowledge graph | TopK whitelist, P3 random path fallback | JSON/JSONL |
| 5 | [paper_synthesis](#5-paper_synthesis) | Academic papers | Two-stage reasoning chain, intelligent ratio control | JSONL |
| 6 | [patent_synthesis](#6-patent_synthesis) | Patents | Evaluate-feedback-retrieve-generate loop | JSONL |
| 7 | [thesis_synthesis](#7-thesis_synthesis) | Theses | Multi-format chapter splitting, objective question generation | JSONL |
| 8 | [wiki_synthesis](#8-wiki_synthesis) | Wikipedia | BioBERT + Qwen two-stage filtering | JSONL |
| 9 | [books_qa_generater](#9-books_qa_generater) | Books | TOC-aware chapter splitting, hierarchical quality control | JSONL |
| 10 | [qa_data_acquisition_quality](#10-qa_data_acquisition_quality) | QA data | LLM generative evaluation | JSONL |
| 11 | [seedreport_synthesis](#11-seedreport_synthesis) | Germplasm reports | 8 user intent categories, zero-anaphora QA | JSONL |

---

## Pipeline Details

### 1. expert_qa_augmentation (Agricultural QA Augmentation)

**Data Source**: Seed question files (JSONL), expert question Excel files, agricultural keyword dictionary

**Key Innovations**:

| Innovation | Description |
|------------|-------------|
| **Intelligent RAG Retrieval** | Automatic Chinese-English translation (334 domain terms), multi-dimensional scoring (7 dimensions, 100-point scale) |
| **20+ Generation Strategies** | Diverse strategies including paraphrasing, reasoning, comparison, and hypothesis |
| **Embedding Semantic Deduplication** | Semantic similarity deduplication based on pretrained multilingual models |
| **Strategy Balancer** | Automatically balances usage frequency across strategies |

**Unique Techniques**: Intelligent strategy selector, prompt enhancement (extended taxonomy injection), multi-level fallback RAG, MD5 hash RAG cache, parallel + serial RAG dual mode

---

### 2. expertq_generatea (Agricultural Breeding Expert QA Batch Generation)

**Data Source**: Seed question JSON (rice/corn/wheat/rapeseed/soybean/livestock domains)

**Key Innovations**:

| Innovation | Description |
|------------|-------------|
| **31+ Model Support** | GPT/Claude/Gemini/DeepSeek/Qwen/GLM/Grok |
| **Thinking Mode** | Extracts reasoning chains (Chain of Thought), generates dual-version answers |
| **SimHash Deduplication** | Efficient deduplication with Hamming distance < 5 |
| **RAG Retrieval Augmentation** | PubMed literature retrieval with citation-backed answers |

**Unique Techniques**: Multi-model batch concurrent processing, Responses API support, automatic API type selection, Biopython Entrez API

---

### 3. gene_synthesis (Gene Literature QA Pair Generation)

**Data Source**: Gene literature in JSON format (DOI lists, PMC IDs)

**Key Innovations**:

| Innovation | Description |
|------------|-------------|
| **Evidence-Anchored Factuality** | Strictly within evidence boundaries, proportional complexity rules (Level 1-3) |
| **Multi-Hop Reasoning Protocol** | Enforces 1-2 multi-hop QAs connecting two biological dimensions |
| **Trigger Mapping** | Automatically adapts question style based on non-empty fields |
| **Exhaustive Precision** | Preserves all numerical values, P-values, and Locus IDs |

**Unique Techniques**: Three explicit reasoning paths (Path A/B/C), identifier grounding (gene symbols + Locus IDs), Data Depth Audit four-step execution protocol

---

### 4. kg_synthesis (Knowledge Graph Causal Chain QA Generation)

**Data Source**: Neo4j knowledge graph / CSV data (plant biology)

**Key Innovations**:

| Innovation | Description |
|------------|-------------|
| **TopK Whitelist Filtering** | First introduction of statistical report TopK filtering |
| **P3 Random Path Fallback** | Three-tier progressive evidence pool (P1 neighbors → P2 expansion → P3 random paths) |
| **Natural Question Constraints** | Prohibits technical terms like "graph/triple" |
| **Multi-Dimensional Validation** | Aspect validation (≥3), entity constraints, evidence citation |

**Unique Techniques**: Neo4j/NetworkX dual backend support, information factor computation, deterministic mode, merged out/in queries

---

### 5. paper_synthesis (Academic Paper QA Generation)

**Data Source**: Academic papers in Markdown format (processed by chapter)

**Key Innovations**:

| Innovation | Description |
|------------|-------------|
| **Two-Stage Reasoning Chain Generation** | Stage 1 extracts reasoning chains (3-7 steps), Stage 2 converts to Q&A |
| **Intelligent Numbered Question Ratio Control** | Default max 10%, strict quality checks |
| **Multi-Dimensional Quality Filtering** | Prohibited phrases, research dependency, author info, hypothetical condition checks |
| **Intelligent Sampling** | By difficulty ratio and label diversity |

**Unique Techniques**: Chapter merging and priority sorting, Thinking mode support, over-generation factor (1.5x) with subsequent sampling

---

### 6. patent_synthesis (Patent QA Pair Generation)

**Data Source**: Patent data in JSONL format (Chinese patents, IPC classification)

**Key Innovations**:

| Innovation | Description |
|------------|-------------|
| **Evaluate-Feedback-Retrieve-Generate Loop** | Badcase-driven continuous optimization |
| **Two-Stage Reasoning Chain** | Reasoning type (1) + non-reasoning type (3) QAs |
| **Hybrid Retrieval Strategy** | BM25 + Phrase + slop Phrase with result fusion |
| **Multi-Dimensional Quality Assessment** | Hallucination detection |

**Unique Techniques**: Elasticsearch retrieval, automatic IPC classification, chapter completeness checks, expert feedback analysis

---

### 7. thesis_synthesis (Thesis SFT QA Pair Generation)

**Data Source**: Thesis JSONL (Markdown/LaTeX/Chinese-English formats)

**Key Innovations**:

| Innovation | Description |
|------------|-------------|
| **Multi-Format Chapter Splitting** | Auto-detects Markdown/LaTeX/Chinese-English/thesis-specific structures |
| **Two-Stage Reasoning Chain** | Generate reasoning process first, then generate answers |
| **SimHash Efficient Deduplication** | Configurable Hamming distance threshold |
| **Curriculum Stage Assignment** | Auto-assigns training stages (1/2/3) by difficulty |

**Unique Techniques**: Objective question generation (single/multi-select/true-false), reasoning diversity filtering, QualityScorer multi-dimensional scoring

---

### 8. wiki_synthesis (Wikipedia Knowledge QA)

**Data Source**: Preprocessed Chinese Wikipedia corpus

**Key Innovations**:

| Innovation | Description |
|------------|-------------|
| **Two-Stage Pre-Filtering** | BioBERT agricultural classification (9.36M → 760K) + Qwen-flash quality filtering (760K → 19.5K) |
| **Dedicated Agricultural Classification Model** | Fine-tuned BioBERT with 5000+ agricultural keyword enhancement |
| **Atomic Fact Extraction** | Each atomic fact generates an independent QA pair |
| **Factuality Constraints** | Strictly based on source text, no fabrication |

**Unique Techniques**: Adjustable confidence threshold (0.6~0.999), checkpoint resume, source_file and title traceability

---

### 9. books_qa_generater (Book Chapter QA Generation)

**Data Source**: Book Markdown files

**Key Innovations**:

| Innovation | Description |
|------------|-------------|
| **TOC-Aware Chapter Splitting** | Based on Markdown heading levels (#/##/###), preserves complete chapters |
| **Book-Specific QA Templates** | Factual/principle/method/comparison QAs |
| **Hierarchical Quality Control** | Three-level control: chapter/paragraph/QA |
| **SimHash Efficient Deduplication** | O(n) time complexity for massive chapter volumes |

**Unique Techniques**: BookProcessor class, automatic Curriculum Stage assignment (1/2/3 difficulty), multi-dimensional QualityScorer

---

### 10. qa_data_acquisition_quality (QA Quality Verification)

**Data Source**: QA data pending verification (JSONL format)

**Key Innovations**:

| Innovation | Description |
|------------|-------------|
| **LLM Generative Evaluation** | Uses LLM instead of traditional classifiers, generates detailed evaluation reports |
| **Multi-Dimensional Quality Assessment** | Four-dimensional scoring: accuracy/relevance/completeness/clarity |
| **High Explainability** | Preserves complete model evaluation text |
| **Incremental Checkpoint Mechanism** | Auto-saves every 10 samples |

**Unique Techniques**: Chain-of-thought reasoning support, structured prompt engineering, automatic score extraction, statistical report generation

---

### 11. seedreport_synthesis (Germplasm Report QA Generation)

**Data Source**: Germplasm reports in JSON format (crop variety approval reports)

**Key Innovations**:

| Innovation | Description |
|------------|-------------|
| **8 User Intent Categories** | Micro-facts/type attribution/comparison/quality assessment/cultivation guide/disease-pest resistance/comprehensive traits/variety provenance |
| **Zero-Anaphora QA** | Prohibits "this variety" etc., uses full variety names |
| **Atomic Short Answers** | At least 40% within 25 characters |
| **Professional Colloquial Style** | Agricultural standard terminology + light colloquialism |

**Unique Techniques**: 8 intent category ratio requirements (10-25%), 50% questions starting with variety name, multi-dimensional coverage (at least 5 intent categories)

---

## Cross-Pipeline Common Techniques

### Deduplication

| Method | Description |
|--------|-------------|
| **SimHash** | Hamming distance deduplication, suitable for large-scale data |
| **Embedding Similarity** | Semantic similarity based on pretrained models, threshold ~0.30 |
| **MD5 Exact Deduplication** | Exact hash deduplication |

### Quality Control

| Method | Description |
|--------|-------------|
| **Multi-Dimensional Scoring** | Accuracy, relevance, completeness, clarity, etc. |
| **Threshold Filtering** | Set minimum score threshold to filter low-quality QAs |
| **Difficulty Grading** | easy/medium/hard or Curriculum Stage 1/2/3 |
| **Prohibited Word Detection** | Detects forbidden phrases or expressions |

### Reasoning Chain Generation

| Method | Description |
|--------|-------------|
| **Two-Stage Generation** | Stage 1 extracts reasoning chain, Stage 2 converts to Q&A |
| **Thinking Mode** | Extracts model reasoning process as CoT |
| **Chain of Thought** | Explicit multi-step reasoning chains |

### Engineering Features

| Feature | Description |
|---------|-------------|
| **Concurrent Processing** | ThreadPoolExecutor, semaphore control, batch processing |
| **Checkpoint Resume** | Checkpoint files, processed record JSONL |
| **Output Format** | Primarily JSONL with metadata |

---

## Quick Start

### Environment Setup

Each pipeline is an independent Python project managed with `uv`:

```bash
# Enter the target pipeline directory
cd <pipeline_name>

# Install dependencies
uv sync

# Copy environment variable template
cp .env.example .env
# Edit .env to set API keys
```

### Running Tests

```bash
# Each pipeline has sample data and test scripts
uv run python test_*.py  # or the corresponding test script

# Or run the main script directly
uv run python <main_script>.py --help
```

### Dependencies

| Dependency | Purpose |
|------------|---------|
| **openai** | LLM API calls |
| **python-dotenv** | Environment variable management |
| **tqdm** | Progress bar display |

Most pipelines only require the above basic dependencies. Specific pipelines may need additional dependencies (e.g., Neo4j, Elasticsearch); see each pipeline's README for details.
