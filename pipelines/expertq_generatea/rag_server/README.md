# Bio RAG Server (No Elasticsearch Required)

PubMed retrieval service based on the **Biopython Entrez API** — no Elasticsearch required.

## Features

- **Direct PubMed retrieval**: Uses NCBI Entrez API, no external database needed
- **FastAPI service**: High-performance async API
- **Zero external dependencies**: No Elasticsearch, Milvus, or Redis

## Quick Start

```bash
cd rag_server
pip install -r requirements.txt
python main.py
# or
bash run.sh
```

Service runs at `http://localhost:9487`

## Using with seed_Q_generate_A_v2.py

The RAG Server provides literature retrieval support for QA generation:

```bash
# 1. Start RAG Server (background)
cd rag_server
python main.py &
sleep 3

# 2. Run QA generation (with RAG enabled)
cd ..
python seed_Q_generate_A_v2.py \
  --input examples/sample_input.json \
  --output output/ \
  --use-rag \
  --model gpt-5.1
```

### RAG Workflow

1. User question → `seed_Q_generate_A_v2.py`
2. Question → `fetch_documents()` → RAG Server (`localhost:9487`)
3. RAG Server → PubMed retrieval → Returns document list
4. Document context → LLM generates citation-backed answer

## API Endpoints

### Health Check
```bash
GET /health
# Response: {"status":"healthy","service":"bio-rag-server"}
```

### Document Retrieval
```bash
POST /retrieve
Content-Type: application/json

{
  "query": "rice breeding genetics",
  "top_k": 5,
  "search_type": "keyword",
  "data_source": ["pubmed"],
  "pubmed_topk": 10
}
```

### Response Example
```json
{
  "success": true,
  "data": [
    {
      "title": "COLD1 confers chilling tolerance in rice.",
      "abstract": "Rice is sensitive to cold...",
      "authors": "Yun Ma, Xiaoyan Dai...",
      "journal": "Cell",
      "pub_date": "2015-Mar-12",
      "url": "https://pubmed.ncbi.nlm.nih.gov/25728666"
    }
  ],
  "message": "Search completed"
}
```

### Streaming Chat (Not Yet Implemented)
```bash
POST /stream-chat
```

## Project Structure

```
rag_server/
├── main.py                 # FastAPI application entry point
├── dto/
│   └── bio_document.py     # Document data model
├── service/
│   ├── pubmed_api.py       # Biopython Entrez API
│   └── rag.py              # RAG service orchestration
├── search_service/
│   ├── base_search.py      # Search service base class
│   └── pubmed_search.py    # PubMed search implementation
├── routers/
│   └── sensor.py           # API routes
└── utils/
    ├── bio_logger.py       # Logging configuration
    └── snowflake_id.py     # ID generation
```

## Dependencies

- Python 3.10+
- Biopython >= 1.81 (Entrez API)
- FastAPI >= 0.104.0
- uvicorn >= 0.24.0

## Differences from Legacy Version

| Feature | Legacy (ES) | New (Biopython) |
|---------|-------------|-----------------|
| PubMed retrieval | Elasticsearch | NCBI Entrez API |
| External dependencies | ES + Milvus + Redis | Network only |
| Configuration complexity | High | Low |
| Startup speed | Slow | Fast |
