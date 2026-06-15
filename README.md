# QALoop

A full-lifecycle toolkit for QA data: from generation and annotation to evaluation.

## System Architecture

![QALoop System Architecture](platform/seed/figure1.png)

The diagram above shows the end-to-end QALoop workflow: heterogeneous agricultural sources are routed through source-adaptive QA synthesis pipelines into a candidate QA pool, then validated on the **Expert Validation Platform** (`platform/`). A feedback and iteration engine closes the loop; outputs include curated training QA, an independent benchmark, and downstream model evaluation.

## Project Structure

```
QALoop/
├── platform/      # Annotation and evaluation platform (FastAPI web app)
├── pipelines/     # QA generation pipeline collection
├── data/          # Local data storage (SQLite database, gitignored)
└── LICENSE
```

## Modules

### platform/ — Annotation and Evaluation Platform

A multi-user collaborative annotation platform built on FastAPI. It supports project and dataset management, flexible annotation configurations (rating, classification, text, single/multi-select, binary), statistical analysis, and export. Optionally integrates LLM-based intelligent analysis of annotation notes.

See [platform/README.md](platform/README.md) for details.

### pipelines/ — QA Generation Pipelines

A collection of standalone QA data generation pipelines. Each pipeline generates QA pairs from a specific data source. Each pipeline directory contains its own README, examples, and documentation.

See [pipelines/README.md](pipelines/README.md) for details.

## Quick Start

### Launch the Annotation Platform

```bash
cd platform

# Install dependencies
uv sync

# Configure environment variables
cp .env.example .env
# Edit .env and update SECRET_KEY

# Create superuser
python scripts/create_superuser.py

# Start the server
uvicorn qa_annotate.main:app --reload --host 0.0.0.0 --port 8000
```

See [platform/README.md](platform/README.md) for details.

## Requirements

- Python >= 3.12
- [uv](https://docs.astral.sh/uv/)

## License

MIT
