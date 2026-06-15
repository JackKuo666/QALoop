# Agricultural QA Dataset Generation System

## Project Overview

This project is a high-quality question-answer dataset generation system designed for the agricultural domain, providing supervised fine-tuning (SFT) training data for agricultural large language models. The system supports multiple generation strategies with intelligent deduplication, quality control, and RAG (Retrieval-Augmented Generation) integration.

## Key Features

### 🚀 Core Capabilities
- **Diverse generation strategies**: 20+ generation methods including paraphrasing, reasoning, comparative analysis, hypothetical scenarios, and more
- **Intelligent strategy selection**: Automatically selects the best generation strategy based on content characteristics
- **Multi-species coverage**: Supports corn, soybean, rice, rapeseed, wheat, livestock, synthetic biotechnology, and more
- **RAG integration**: Retrieval-augmented generation for improved answer accuracy and relevance
- **Embedding deduplication**: Intelligent deduplication based on semantic similarity
- **Quality control**: Multi-dimensional quality assessment and filtering

### 🎯 Generation Strategies
- **Paraphrase**
- **Elaboration**
- **Perspective Shift**
- **Multi-turn**
- **Cross-species**
- **Reverse Reasoning**
- **Innovative Application**
- **Comparative Analysis**
- **Future Scenario**
- **Hypothetical**
- **Counterfactual**
- **Meta Question**
- **Temporal Shift**
- **Spatial Shift**
- **Discipline Cross**
- **Scale Change**
- **Time Series**
- **Causal Chain**
- **Dialogue Variation**
- **Seed Deepening**

## Project Structure

```
agri_sft_ds/
├── src/                          # Source code
│   ├── core/                     # Core generation modules
│   │   ├── qa_generator_v2.py       # Main QA generator
│   │   ├── main_batch.py            # Batch processing entry point
│   │   └── batch_processor.py       # Batch processor
│   ├── optimization/              # Optimization and enhancement
│   │   ├── intelligent_strategy_selector.py  # Intelligent strategy selector
│   │   ├── enhanced_strategy_selector.py     # Enhanced strategy selector
│   │   ├── prompt_enhancer.py       # Prompt enhancer
│   │   ├── STRATEGY_BALANCER.py     # Strategy balancer
│   │   └── Self-awareness_dialogue_expansion.py  # Dialogue expansion optimizer
│   ├── quality/                   # Deduplication and quality control
│   │   ├── embedding_deduplicator.py   # Embedding deduplicator
│   │   ├── deduplicate_qa.py          # QA deduplication tool
│   │   └── rag_cache.py               # RAG cache system
│   └── runs/                      # Expansion and execution
│       ├── run_expansion_from_dir.py      # Directory expansion script
│       ├── run_expansion_from_expert.py   # Expert mode expansion
│       ├── rag_async_optimization.py      # RAG async optimization
│       └── rag_cache_integration.py       # RAG cache integration
│
├── config/                       # Configuration files
│   ├── config.yaml                  # Main config
│   ├── config.py                    # Config management
│   ├── generation_ratios_config.yaml # Generation ratio config
│   └── .env                         # Environment variables
│
├── data/                         # Data files
│   ├── raw/                        # Raw data
│   │   ├── agri_keywords.xlsx          # Agricultural keywords
│   │   ├── domain_task.xlsx           # Domain tasks
│   │   ├── domain_task_expert.xlsx    # Expert domain tasks
│   │   ├── domain_task_expert_updated.xlsx
│   │   ├── 专家问题_扩增CoT.xlsx       # Expert question CoT expansion
│   │   └── 单个水稻种子问题测试.xlsx    # Rice test data
│   ├── processed/                # Processed data
│   │   └── rag_cache/                # RAG cache
│   └── qa/                       # QA data files
│       ├── 油菜_answers.jsonl
│       └── 玉米_answers.jsonl
│
├── output/                       # Output files
│   ├── output_expert_expanded_*/     # Expert expansion output
│   └── output_全部物种_expanded_*/   # All-species expansion output
│
├── docs/                         # Documentation
│   ├── README.md                     # Project documentation
│   ├── run_expansion_from_dir_README.md
│   ├── run_expansion_from_expert_README.md
│   └── requirements.txt              # Dependency list
│
├── tests/                        # Tests (to be added)
│
├── scripts/                      # Utility scripts (to be added)
│
├── .gitignore                    # Git ignore config
└── MANIFEST.in                   # Package manifest
```

## Requirements

- Python 3.8+
- Dependencies (see installation below)
- OpenAI API Key or compatible API service
- RAG service (optional, for retrieval augmentation)

## Installation and Configuration

### 1. Install Dependencies

```bash
pip install -r requirements.txt
```

Main dependencies:
- `openai` - OpenAI API client
- `torch` - PyTorch deep learning framework
- `transformers` - Hugging Face Transformers
- `aiohttp` - Async HTTP client
- `pydantic` - Data validation
- `scikit-learn` - Machine learning library
- `sentence-transformers` - Sentence embeddings

### 2. Configure API Key

Edit the `.env` file and add your API key:

```bash
OPENAI_API_KEY=${OPENAI_API_KEY}
```

### 3. Configure Parameters

Edit `config.yaml` to adjust parameters as needed:

```yaml
# Model config
model_name: "gpt-5.1"
api_base: "${OPENAI_BASE_URL}"  # Set via environment variable
api_key: "${OPENAI_API_KEY}"    # Set via environment variable
max_retries: 3
request_timeout: 60

# Generation parameters
default_variants_per_seed: 2
default_batch_size: 10
temperature: 0.7

# Quality parameters
min_question_length: 10
min_answer_length: 40
max_question_length: 500
max_answer_length: 8000
```

## Usage

### Basic Usage

#### 1. Main Batch Script

```bash
python src/core/main_batch.py \
    --input_file path/to/seed_questions.json \
    --output_file output/qa_dataset.jsonl \
    --variants_per_seed 3 \
    --batch_size 10
```

#### 2. Directory Expansion

```bash
python src/runs/run_expansion_from_dir.py \
    --input_dir path/to/input_dir \
    --output_dir path/to/output_dir \
    --species corn \
    --max_qa_pairs 10000
```

#### 3. Expert Mode Expansion

```bash
python src/runs/run_expansion_from_expert.py \
    --input_dir path/to/input_dir \
    --output_dir path/to/output_dir \
    --config config/generation_ratios_config.yaml
```

### Advanced Features

#### Enable RAG Retrieval Augmentation

```python
from src.core.main_batch import RAGClient

rag_client = RAGClient()
# Configure RAG service URL
rag_config = {
    'url': 'http://localhost:9487/retrieve',
    'timeout': 300,
    'max_retries': 3
}
```

#### Custom Generation Strategies

Edit `config/generation_ratios_config.yaml` to customize subcategory weights:

```yaml
subspecies_ratios:
  基础理论问答: 1.0
  物种特异性知识问答: 1.2
  育种方案设计与评估: 1.0
  # ... more config
```

#### Embedding Deduplication

```python
from src.quality.embedding_deduplicator import get_global_deduplicator

deduplicator = get_global_deduplicator()
# Deduplicated QA pairs
unique_qa_pairs = deduplicator.deduplicate(qa_pairs)
```

## Output Format

Generated QA datasets are in JSONL format, one QA pair per line:

```json
{
  "question": "Question content",
  "answer": "Answer content",
  "metadata": {
    "category": "Category",
    "difficulty": "Difficulty",
    "tags": ["tag1", "tag2"],
    "generation_method": "Generation strategy",
    "quality_score": 0.95,
    "species": "Species",
    "subspecies": "Subcategory"
  }
}
```

## Configuration

### Generation Ratio Config

`config/generation_ratios_config.yaml` controls:
- Species weight configuration
- Subcategory weight configuration
- Generation strategy parameters
- Quality control thresholds
- Output control options

### Quality Control

Multi-level quality control:
- Length filtering (min/max character count)
- Semantic similarity deduplication
- Strategy balancer
- Intelligent quality assessment

### RAG Integration

Optional RAG service integration:
- Supports local or remote RAG services
- Async retrieval optimization
- Cache mechanism for performance
- Configurable retry strategy

## Performance Optimization

### Batch Processing
- Batch generation support
- Async concurrent processing
- Intelligent rate limiting
- Failure retry mechanism

### Memory Optimization
- Streaming for large files
- Caching mechanism
- Garbage collection optimization

## Monitoring and Logging

Detailed logging includes:
- Generation progress tracking
- Quality assessment logs
- Error diagnostics
- Performance metrics

## Troubleshooting

### Common Issues

1. **API call failures**
   - Check API key configuration
   - Verify API service URL
   - Check network connectivity

2. **Poor generation quality**
   - Adjust temperature parameter
   - Increase variants_per_seed
   - Enable RAG retrieval augmentation

3. **Out of memory**
   - Reduce batch_size
   - Enable streaming processing
   - Clear cache

4. **Suboptimal deduplication**
   - Adjust similarity threshold
   - Check embedding model
   - Verify input data quality

## Extension Development

### Adding New Generation Strategies

1. Add a new `GenerationMethod` in `src/core/qa_generator_v2.py`
2. Implement the corresponding generation logic
3. Update the `METHOD_NAME_MAP` mapping

### Custom Quality Assessment

1. Extend the `QualityConfig` class
2. Implement custom evaluation logic
3. Integrate into the generation pipeline

### Integrating New Data Sources

1. Implement a data loader
2. Support new file formats
3. Update configuration under `config/`

## License

This project is licensed under the MIT License.

## Contributing

Issues and Pull Requests are welcome.

## Contact

For questions, please use GitHub Issues.

---

**Note**: Ensure compliance with relevant data usage terms and API service agreements before use.
