# QA对质量验证工具

## 项目概述

QA对质量验证工具是一个基于大语言模型（LLM）的问答对质量评估系统。该工具使用Qwen3等大语言模型对问答对进行多维度、细粒度的质量评估，不仅提供评分，还生成详细的分析报告和改进建议。

### 核心价值

- **生成式评估**：不同于传统的分类器方法，使用LLM生成详细的评估报告
- **多维度评估**：从准确性、相关性、完整性、清晰度四个维度进行综合评估
- **可解释性强**：保留完整的模型评估文本，便于理解和追溯
- **工程化设计**：支持批量处理、检查点保存、统计分析等实用功能

## 主要特性

### ✨ 核心功能

1. **多维度质量评估**
   - 准确性（Accuracy）：评估答案是否正确、准确
   - 相关性（Relevance）：评估回答是否直接回应问题
   - 完整性（Completeness）：评估回答是否完整、全面
   - 清晰度（Clarity）：评估回答是否清晰、易懂

2. **智能评估流程**
   - 结构化提示工程：通过精心设计的prompt引导模型输出标准化格式
   - 自动评分提取：从模型回复中智能提取结构化评分数据
   - 思维链推理：支持启用thinking模式，提升评估质量

3. **批量处理能力**
   - 支持批量验证QA对
   - 可配置批次大小，适应不同资源环境
   - 自动进度显示

4. **数据安全保障**
   - 增量检查点机制：每处理10个样本自动保存中间结果
   - 断点续传支持：避免长时间运行导致的数据丢失
   - 完善的错误处理：单条失败不影响整体流程

5. **统计分析报告**
   - 自动生成多维度统计报告
   - 通过率分析
   - 各维度平均分统计
   - 可视化友好的报告格式

## 项目结构

```
data_quality/
├── verify_qa_local.py      # 主程序文件
├── call_api.py             # API调用封装模块
├── README.md               # 项目说明文档
├── outputs/                # 输出目录（自动创建）
│   ├── checkpoints/        # 检查点文件
│   └── qa_verification_report.json  # 统计报告
└── requirements.txt        # 依赖包列表（需创建）
```

## 安装与配置

### 环境要求

- Python 3.8+
- CUDA支持的GPU（推荐，用于本地模型推理）
- 或可访问的LLM API服务

### 安装步骤

1. **克隆或下载项目**

```bash
cd /path/to/QA_data/script/data_quality
```

2. **安装Python依赖**

```bash
# 使用 uv 安装依赖（推荐）
uv sync

# 或使用 pip
pip install -r requirements.txt
```

如果没有requirements.txt文件，可以手动安装：

```bash
pip install torch transformers tqdm jsonlines openai pathlib
```

3. **依赖包说明**

创建 `requirements.txt` 文件，包含以下内容：

```txt
torch>=2.0.0
transformers>=4.30.0
tqdm>=4.65.0
jsonlines>=3.1.0
openai>=1.0.0
```

### 配置说明

#### API配置

工具通过API调用LLM模型，需要配置以下参数：

1. **模型API地址**：修改 `verify_qa_local.py` 中的 `MODEL_PATH`
   ```python
   MODEL_PATH = "http://your-api-endpoint/v1"
   ```

2. **模型名称**：修改 `MODEL_NAME`
   ```python
   MODEL_NAME = "qwen3-30b-a3b-instruct-2507"
   ```

3. **API密钥**：如果需要，在 `Qwen3QAVerifier` 初始化时传入 `key` 参数

#### 数据格式要求

输入文件应为JSONL格式，每行一个JSON对象，包含以下字段：

```json
{
  "instruction": "问题内容",
  "output": "回答内容"
}
```

可选字段：
- `input`: 输入上下文（如果有）

## 使用方法

### 基本使用

1. **准备输入数据**

确保你的QA数据文件是JSONL格式，例如 `QA_quality_test.jsonl`：

```jsonl
{"instruction": "什么是机器学习？", "output": "机器学习是人工智能的一个分支..."}
{"instruction": "Python如何读取文件？", "output": "可以使用open()函数..."}
```

2. **使用示例数据快速测试**

```bash
uv run python verify_qa_local.py --input examples/sample_qa.jsonl --output output/verified.jsonl
```

3. **修改配置参数**

编辑 `verify_qa_local.py` 中的 `main()` 函数：

```python
MODEL_NAME=${MODEL_NAME}
MODEL_PATH=${MODEL_PATH}
QA_FILE = "/path/to/your/qa_data.jsonl"
OUTPUT_FILE = "/path/to/output/verified_qa.jsonl"
BATCH_SIZE = 3  # 根据API限制和资源调整
```

4. **运行验证**

```bash
python verify_qa_local.py
```

### 高级用法

#### 作为模块使用

```python
from verify_qa_local import Qwen3QAVerifier

# 初始化验证器
verifier = Qwen3QAVerifier(
    model_name="qwen3-30b-a3b-instruct-2507",
    model_path="http://your-api-endpoint/v1",
    key=os.getenv("OPENAI_API_KEY")
)

# 验证单个QA对
result = verifier.verify_single(
    instruction="什么是深度学习？",
    output="深度学习是机器学习的一个子领域..."
)

# 批量验证
qa_pairs = [
    {"instruction": "问题1", "output": "回答1"},
    {"instruction": "问题2", "output": "回答2"},
]
results = verifier.verify_batch(qa_pairs, batch_size=2)
```

#### 自定义评估阈值

修改 `verify_single` 方法中的通过阈值：

```python
"is_passing": scores['total'] >= 3.5  # 修改为其他阈值，如3.0或4.0
```

#### 调整生成参数

修改 `__init__` 方法中的 `generation_config`：

```python
self.generation_config = {
    "max_new_tokens": 1024,      # 最大生成token数
    "temperature": 0.3,          # 温度参数（0-1，越低越确定）
    "top_p": 0.9,                # nucleus sampling参数
    "do_sample": True,           # 是否采样
    "repetition_penalty": 1.1,   # 重复惩罚
}
```

### 输出说明

#### 验证结果格式

每个QA对的验证结果包含：

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

#### 统计报告

运行完成后会生成 `outputs/qa_verification_report.json`：

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

## 使用示例

### 示例1：评估农业领域QA数据

```python
# 配置
MODEL_NAME = "qwen3-30b-a3b-instruct-2507"
MODEL_PATH = "http://your-api-endpoint/v1"
QA_FILE = "agriculture_qa.jsonl"
OUTPUT_FILE = "agriculture_qa_verified.jsonl"
BATCH_SIZE = 5

# 运行
python verify_qa_local.py
```

### 示例2：快速测试少量样本

```python
# 在main()函数中，可以先加载少量数据进行测试
qa_pairs = []
with jsonlines.open(QA_FILE) as f:
    for i, item in enumerate(f):
        if i >= 10:  # 只处理前10条
            break
        qa_pairs.append(item)
```

## 注意事项

1. **API限制**：注意API的速率限制，适当调整 `BATCH_SIZE`
2. **网络稳定性**：确保API服务稳定，工具已包含超时和重试机制
3. **数据格式**：确保输入JSONL格式正确，字段名匹配
4. **存储空间**：检查点文件会占用一定空间，定期清理旧文件
5. **评分提取**：如果模型输出格式变化，可能需要调整 `extract_scores` 方法

## 故障排除

### 常见问题

1. **导入错误：找不到 call_api 模块**
   - 确保 `call_api.py` 在同一目录下
   - 检查Python路径配置

2. **API连接失败**
   - 检查 `MODEL_PATH` 是否正确
   - 验证网络连接和API服务状态
   - 确认API密钥是否正确

3. **评分提取失败**
   - 检查模型输出格式是否符合预期
   - 查看 `model_response` 字段确认模型回复内容
   - 可能需要调整 `extract_scores` 方法的解析逻辑

4. **内存不足**
   - 减小 `BATCH_SIZE`
   - 使用API服务而非本地模型

## 许可证

本项目采用 MIT 许可证。

## 联系方式

如有问题或建议，请通过以下方式联系：
- 邮箱：[huangbc@zhejianglab.org]
- 项目维护者：[BC Huang]

## 更新日志

### v1.0.0 (2026-01-30)
- 初始版本发布
- 支持多维度QA对质量评估
- 实现批量处理和检查点机制
- 添加统计分析功能

## 致谢

- 感谢之芽团队，感谢所有贡献者的支持。

---

**注意**：本工具依赖于外部LLM API服务，使用前请确保已正确配置API访问权限。
