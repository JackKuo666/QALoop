# QALoop

A full-lifecycle toolkit for QA data: from generation and annotation to evaluation.

## Project Structure

```
QALoop/
├── platform/      # Annotation and evaluation platform (FastAPI web app)
├── pipelines/     # QA generation pipeline collection
├── examples/      # Usage examples and sample data
├── docs/          # Documentation
└── README.md
```

## Modules

### platform/ — Annotation and Evaluation Platform

A multi-user collaborative annotation platform built on FastAPI. It supports project and dataset management, flexible annotation configurations (rating, classification, text, single/multi-select, binary), statistical analysis, and export. Optionally integrates LLM-based intelligent analysis of annotation notes.

See [platform/README.md](platform/README.md) for details.

### pipelines/ — QA Generation Pipelines

A collection of standalone QA data generation pipelines. Each pipeline generates QA pairs from a specific data source.

### examples/ — Usage Examples

Import data formats, pipeline configuration examples, and more.

### docs/ — Documentation

Architecture design, API documentation, deployment guides, and more.

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
