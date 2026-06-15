# QA Pair Quality Verification Tool

## Project Overview

The QA Pair Quality Verification Tool is a question-answer pair quality assessment system powered by large language models (LLM). It uses LLMs such as Qwen3 to perform multi-dimensional, fine-grained quality evaluation of QA pairs, providing not only scores but also detailed analysis reports and improvement suggestions.

### Core Value

- **Generative evaluation**: Unlike traditional classifier approaches, uses LLM to generate detailed evaluation reports
- **Multi-dimensional assessment**: Comprehensive evaluation across accuracy, relevance, completeness, and clarity
- **Strong interpretability**: Retains full model evaluation text for understanding and traceability
- **Production-ready design**: Supports batch processing, checkpoint saving, statistical analysis, and other practical features

## Key Features

### ✨ Core Capabilities

1. **Multi-dimensional quality assessment**
   - Accuracy: Evaluates whether answers are correct and accurate
   - Relevance: Evaluates whether responses directly address the question
   - Completeness: Evaluates whether responses are complete and comprehensive
   - Clarity: Evaluates whether responses are clear and easy to understand

2. **Intelligent evaluation workflow**
   - Structured prompt engineering: Carefully designed prompts guide standardized model output
   - Automatic score extraction: Intelligently extracts structured scoring data from model responses
   - Chain-of-thought reasoning: Supports thinking mode to improve evaluation quality

3. **Batch processing**
   - Supports batch QA pair verification
   - Configurable batch size for different resource environments
   - Automatic progress display

4. **Data safety**
   - Incremental checkpoint mechanism: Automatically saves intermediate results every 10 samples
   - Checkpoint/resume support: Prevents data loss from long-running jobs
   - Robust error handling: Single-item failures do not affect the overall workflow

5. **Statistical analysis reports**
   - Automatically generates multi-dimensional statistical reports
   - Pass rate analysis
   - Average scores per dimension
   - Visualization-friendly report format

## Project Structure

```
data_quality/
├── verify_qa_local.py      # Main program
├── call_api.py             # API call wrapper module
├── README.md               # Project documentation
├── outputs/                # Output directory (auto-created)
│   ├── checkpoints/        # Checkpoint files
│   └── qa_verification_report.json  # Statistical report
└── requirements.txt        # Dependency list (to be created)
```

## Installation and Configuration

### Requirements

- Python 3.8+
- CUDA-enabled GPU (recommended for local model inference)
- Or accessible LLM API service

### Installation Steps

1. **Clone or download the project**

```bash
cd /path/to/QA_data/script/data_quality
```

2. **Install Python dependencies**

```bash
# Install dependencies with uv (recommended)
uv sync

# Or use pip
pip install -r requirements.txt
```

If no requirements.txt exists, install manually:

```bash
pip install torch transformers tqdm jsonlines openai pathlib
```

3. **Dependency notes**

Create a `requirements.txt` file with:

```txt
torch>=2.0.0
transformers>=4.30.0
tqdm>=4.65.0
jsonlines>=3.1.0
openai>=1.0.0
```

### Configuration

#### API Configuration

The tool calls LLM models via API. Configure the following parameters:

1. **Model API endpoint**: Edit `MODEL_PATH` in `verify_qa_local.py`
   ```python
   MODEL_PATH = "http://your-api-endpoint/v1"
   ```

2. **Model name**: Edit `MODEL_NAME`
   ```python
   MODEL_NAME = "qwen3-30b-a3b-instruct-2507"
   ```

3. **API key**: If required, pass the `key` parameter when initializing `Qwen3QAVerifier`

#### Data Format Requirements

Input files should be JSONL format with one JSON object per line containing:

```json
{
  "instruction": "问题内容",
  "output": "回答内容"
}
```

Optional fields:
- `input`: Input context (if applicable)

## Usage

### Basic Usage

1. **Prepare input data**

Ensure your QA data file is JSONL format, e.g. `QA_quality_test.jsonl`:

```jsonl
{"instruction": "什么是机器学习？", "output": "机器学习是人工智能的一个分支..."}
{"instruction": "Python如何读取文件？", "output": "可以使用open()函数..."}
```

2. **Quick test with sample data**

```bash
uv run python verify_qa_local.py --input examples/sample_qa.jsonl --output output/verified.jsonl
```

3. **Modify configuration parameters**

Edit the `main()` function in `verify_qa_local.py`:

```python
MODEL_NAME=${MODEL_NAME}
MODEL_PATH=${MODEL_PATH}
QA_FILE = "/path/to/your/qa_data.jsonl"
OUTPUT_FILE = "/path/to/output/verified_qa.jsonl"
BATCH_SIZE = 3  # Adjust based on API limits and resources
```

4. **Run verification**

```bash
python verify_qa_local.py
```

### Advanced Usage

#### Use as a Module

```python
from verify_qa_local import Qwen3QAVerifier

# Initialize verifier
verifier = Qwen3QAVerifier(
    model_name="qwen3-30b-a3b-instruct-2507",
    model_path="http://your-api-endpoint/v1",
    key=os.getenv("OPENAI_API_KEY")
)

# Verify a single QA pair
result = verifier.verify_single(
    instruction="什么是深度学习？",
    output="深度学习是机器学习的一个子领域..."
)

# Batch verification
qa_pairs = [
    {"instruction": "问题1", "output": "回答1"},
    {"instruction": "问题2", "output": "回答2"},
]
results = verifier.verify_batch(qa_pairs, batch_size=2)
```

#### Custom Evaluation Threshold

Modify the pass threshold in the `verify_single` method:

```python
"is_passing": scores['total'] >= 3.5  # Change to other thresholds, e.g. 3.0 or 4.0
```

#### Adjust Generation Parameters

Modify `generation_config` in the `__init__` method:

```python
self.generation_config = {
    "max_new_tokens": 1024,      # Max generated tokens
    "temperature": 0.3,          # Temperature (0-1, lower = more deterministic)
    "top_p": 0.9,                # Nucleus sampling parameter
    "do_sample": True,           # Whether to sample
    "repetition_penalty": 1.1,   # Repetition penalty
}
```

### Output Description

#### Verification Result Format

Each QA pair verification result contains:

```json
{
  "instruction": "原始问题",
  "output": "原始回答",
  "verification": {
    "model_response": "完整的模型评估文本（包含分析、评分、建议）",
    "scores": {
      "accuracy": 4.5,
      "relevance": 4.0,
      "completeness": 3.5,
      "clarity": 4.0,
      "total": 4.0
    },
    "is_passing": true
  }
}
```

#### Statistical Report

After completion, `outputs/qa_verification_report.json` is generated:

```json
{
  "total_qa_pairs": 100,
  "valid_verifications": 98,
  "passing_rate": 0.75,
  "average_scores": {
    "accuracy": 3.8,
    "relevance": 3.9,
    "completeness": 3.6,
    "clarity": 3.7,
    "total": 3.75
  },
  "passing_count": 75,
  "failing_count": 25
}
```

## Usage Examples

### Example 1: Evaluate Agricultural QA Data

```python
# Configuration
MODEL_NAME = "qwen3-30b-a3b-instruct-2507"
MODEL_PATH = "http://your-api-endpoint/v1"
QA_FILE = "agriculture_qa.jsonl"
OUTPUT_FILE = "agriculture_qa_verified.jsonl"
BATCH_SIZE = 5

# Run
python verify_qa_local.py
```

### Example 2: Quick Test on a Small Sample

```python
# In main(), load a small subset for testing first
qa_pairs = []
with jsonlines.open(QA_FILE) as f:
    for i, item in enumerate(f):
        if i >= 10:  # Process only first 10 entries
            break
        qa_pairs.append(item)
```

## Notes

1. **API limits**: Watch API rate limits; adjust `BATCH_SIZE` accordingly
2. **Network stability**: Ensure API service is stable; the tool includes timeout and retry mechanisms
3. **Data format**: Ensure input JSONL format is correct and field names match
4. **Storage space**: Checkpoint files consume disk space; clean up old files periodically
5. **Score extraction**: If model output format changes, you may need to adjust the `extract_scores` method

## Troubleshooting

### Common Issues

1. **Import error: call_api module not found**
   - Ensure `call_api.py` is in the same directory
   - Check Python path configuration

2. **API connection failure**
   - Verify `MODEL_PATH` is correct
   - Check network connectivity and API service status
   - Confirm API key is correct

3. **Score extraction failure**
   - Check whether model output format matches expectations
   - Inspect `model_response` field to confirm model reply content
   - You may need to adjust parsing logic in the `extract_scores` method

4. **Out of memory**
   - Reduce `BATCH_SIZE`
   - Use API service instead of local model

## License

This project is licensed under the MIT License.

## Contact

For questions or suggestions, contact:
- Email: [huangbc@zhejianglab.org]
- Maintainer: [BC Huang]

## Changelog

### v1.0.0 (2026-01-30)
- Initial release
- Multi-dimensional QA pair quality assessment
- Batch processing and checkpoint mechanism
- Statistical analysis features

## Acknowledgments

- Thanks to the Zhiyá team and all contributors for their support.

---

**Note**: This tool depends on external LLM API services. Ensure API access is properly configured before use.
