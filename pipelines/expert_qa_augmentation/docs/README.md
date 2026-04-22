# 农业问答数据集生成系统 (Agricultural QA Dataset Generation System)

## 项目概述

本项目是一个专为农业领域设计的高质量问答数据集生成系统，用于为农业大语言模型提供监督微调（SFT）训练数据。系统支持多种生成策略，具备智能去重、质量控制和RAG（检索增强生成）集成等功能。

## 主要特性

### 🚀 核心功能
- **多样化生成策略**: 支持 20+ 种生成方法，包括释义、推理、对比分析、假设场景等
- **智能策略选择**: 基于内容特点自动选择最佳生成策略
- **多物种覆盖**: 支持玉米、大豆、水稻、油菜、小麦、畜禽、合成生物技术等
- **RAG集成**: 支持检索增强生成，提高答案准确性和相关性
- **嵌入去重**: 基于语义相似度的智能去重机制
- **质量控制**: 多维度质量评估和过滤机制

### 🎯 生成策略
- **释义与重述** (Paraphrase)
- **详细阐述** (Elaboration)
- **视角转换** (Perspective Shift)
- **多轮对话** (Multi-turn)
- **跨物种迁移** (Cross-species)
- **反向推理** (Reverse Reasoning)
- **创新应用** (Innovative Application)
- **对比分析** (Comparative Analysis)
- **未来情景** (Future Scenario)
- **假设性场景** (Hypothetical)
- **反事实推理** (Counterfactual)
- **元问题** (Meta Question)
- **时间维度变化** (Temporal Shift)
- **空间维度变化** (Spatial Shift)
- **跨学科融合** (Discipline Cross)
- **尺度变化** (Scale Change)
- **时序分析** (Time Series)
- **因果链条** (Causal Chain)
- **对话变体** (Dialogue Variation)
- **种子深化** (Seed Deepening)

## 项目结构

```
agri_sft_ds/
├── src/                          # 源代码
│   ├── core/                     # 核心生成模块
│   │   ├── qa_generator_v2.py       # QA生成器主文件
│   │   ├── main_batch.py            # 批处理入口
│   │   └── batch_processor.py       # 批处理器
│   ├── optimization/              # 优化与增强
│   │   ├── intelligent_strategy_selector.py  # 智能策略选择器
│   │   ├── enhanced_strategy_selector.py     # 增强策略选择器
│   │   ├── prompt_enhancer.py       # 提示增强器
│   │   ├── STRATEGY_BALANCER.py     # 策略平衡器
│   │   └── Self-awareness_dialogue_expansion.py  # 对话扩展优化器
│   ├── quality/                   # 去重与质量控制
│   │   ├── embedding_deduplicator.py   # 嵌入去重器
│   │   ├── deduplicate_qa.py          # QA去重工具
│   │   └── rag_cache.py               # RAG缓存系统
│   └── runs/                      # 扩展与运行
│       ├── run_expansion_from_dir.py      # 目录扩展脚本
│       ├── run_expansion_from_expert.py   # 专家模式扩展
│       ├── rag_async_optimization.py      # RAG异步优化
│       └── rag_cache_integration.py       # RAG缓存集成
│
├── config/                       # 配置文件
│   ├── config.yaml                  # 主配置
│   ├── config.py                    # 配置管理
│   ├── generation_ratios_config.yaml # 生成比例配置
│   └── .env                         # 环境变量
│
├── data/                         # 数据文件
│   ├── raw/                        # 原始数据
│   │   ├── agri_keywords.xlsx          # 农业关键词
│   │   ├── domain_task.xlsx           # 领域任务
│   │   ├── domain_task_expert.xlsx    # 专家领域任务
│   │   ├── domain_task_expert_updated.xlsx
│   │   ├── 专家问题_扩增CoT.xlsx       # 专家问题CoT扩增
│   │   └── 单个水稻种子问题测试.xlsx    # 水稻测试数据
│   ├── processed/                # 处理后的数据
│   │   └── rag_cache/                # RAG缓存
│   └── qa/                       # QA数据文件
│       ├── 油菜_answers.jsonl
│       └── 玉米_answers.jsonl
│
├── output/                       # 输出文件
│   ├── output_expert_expanded_*/     # 专家扩展输出
│   └── output_全部物种_expanded_*/   # 全部物种扩展输出
│
├── docs/                         # 文档
│   ├── README.md                     # 项目说明文档
│   ├── run_expansion_from_dir_README.md
│   ├── run_expansion_from_expert_README.md
│   └── requirements.txt              # 依赖列表
│
├── tests/                        # 测试文件（待添加）
│
├── scripts/                      # 辅助脚本（待添加）
│
├── .gitignore                    # Git忽略配置
└── MANIFEST.in                   # 打包清单
```

## 环境要求

- Python 3.8+
- 依赖包（安装方法见下方）
- OpenAI API Key 或兼容的 API 服务
- RAG服务（可选，用于检索增强）

## 安装与配置

### 1. 安装依赖

```bash
pip install -r requirements.txt
```

主要依赖包括：
- `openai` - OpenAI API客户端
- `torch` - PyTorch深度学习框架
- `transformers` - Hugging Face Transformers
- `aiohttp` - 异步HTTP客户端
- `pydantic` - 数据验证
- `scikit-learn` - 机器学习库
- `sentence-transformers` - 句子嵌入

### 2. 配置API密钥

编辑 `.env` 文件，添加你的API密钥：

```bash
OPENAI_API_KEY=${OPENAI_API_KEY}
```

### 3. 配置参数

编辑 `config.yaml` 文件，根据需要调整参数：

```yaml
# 模型配置
model_name: "gpt-5.1"
api_base: "${OPENAI_BASE_URL}"  # 通过环境变量设置
api_key: "${OPENAI_API_KEY}"    # 通过环境变量设置
max_retries: 3
request_timeout: 60

# 生成参数
default_variants_per_seed: 2
default_batch_size: 10
temperature: 0.7

# 质量参数
min_question_length: 10
min_answer_length: 40
max_question_length: 500
max_answer_length: 8000
```

## 使用方法

### 基础使用

#### 1. 使用主批处理脚本

```bash
python src/core/main_batch.py \
    --input_file path/to/seed_questions.json \
    --output_file output/qa_dataset.jsonl \
    --variants_per_seed 3 \
    --batch_size 10
```

#### 2. 从目录扩展生成

```bash
python src/runs/run_expansion_from_dir.py \
    --input_dir path/to/input_dir \
    --output_dir path/to/output_dir \
    --species corn \
    --max_qa_pairs 10000
```

#### 3. 专家模式扩展

```bash
python src/runs/run_expansion_from_expert.py \
    --input_dir path/to/input_dir \
    --output_dir path/to/output_dir \
    --config config/generation_ratios_config.yaml
```

### 高级功能

#### 启用RAG检索增强

```python
from src.core.main_batch import RAGClient

rag_client = RAGClient()
# 配置RAG服务地址
rag_config = {
    'url': 'http://localhost:9487/retrieve',
    'timeout': 300,
    'max_retries': 3
}
```

#### 自定义生成策略

编辑 `config/generation_ratios_config.yaml` 文件，自定义各子类别权重：

```yaml
subspecies_ratios:
  基础理论问答: 1.0
  物种特异性知识问答: 1.2
  育种方案设计与评估: 1.0
  # ... 更多配置
```

#### 使用嵌入去重

```python
from src.quality.embedding_deduplicator import get_global_deduplicator

deduplicator = get_global_deduplicator()
# 去重后的QA对
unique_qa_pairs = deduplicator.deduplicate(qa_pairs)
```

## 输出格式

生成的QA数据集为JSONL格式，每行包含一个QA对：

```json
{
  "question": "问题内容",
  "answer": "答案内容",
  "metadata": {
    "category": "类别",
    "difficulty": "难度",
    "tags": ["标签1", "标签2"],
    "generation_method": "生成策略",
    "quality_score": 0.95,
    "species": "物种",
    "subspecies": "子类别"
  }
}
```

## 配置说明

### 生成比例配置

`config/generation_ratios_config.yaml` 文件控制：
- 物种权重配置
- 子类别权重配置
- 生成策略参数
- 质量控制阈值
- 输出控制选项

### 质量控制

系统提供多层次质量控制：
- 长度过滤（最小/最大字符数）
- 语义相似度去重
- 策略平衡器
- 智能质量评估

### RAG集成

可选的RAG服务集成：
- 支持本地或远程RAG服务
- 异步检索优化
- 缓存机制提升性能
- 可配置重试策略

## 性能优化

### 批处理优化
- 支持批量生成
- 异步并发处理
- 智能速率限制
- 失败重试机制

### 内存优化
- 流式处理大文件
- 缓存机制
- 垃圾回收优化

## 监控与日志

系统提供详细的日志记录：
- 生成进度跟踪
- 质量评估日志
- 错误诊断信息
- 性能指标统计

## 故障排除

### 常见问题

1. **API调用失败**
   - 检查API密钥配置
   - 验证API服务地址
   - 查看网络连接

2. **生成质量不佳**
   - 调整temperature参数
   - 增加variants_per_seed数量
   - 启用RAG检索增强

3. **内存不足**
   - 减小batch_size
   - 启用流式处理
   - 清理缓存

4. **去重效果不理想**
   - 调整相似度阈值
   - 检查嵌入模型
   - 验证输入数据质量

## 扩展开发

### 添加新的生成策略

1. 在 `src/core/qa_generator_v2.py` 中添加新的 `GenerationMethod`
2. 实现对应的生成逻辑
3. 更新 `METHOD_NAME_MAP` 映射

### 自定义质量评估

1. 继承 `QualityConfig` 类
2. 实现自定义评估逻辑
3. 在生成流程中集成

### 集成新的数据源

1. 实现数据加载器
2. 支持新的文件格式
3. 更新 `config/` 目录下的配置参数

## 许可证

本项目采用 MIT 许可证。

## 贡献指南

欢迎提交 Issue 和 Pull Request 来改进项目。

## 联系方式

如有问题，请通过 GitHub Issues 联系我们。

---

**注意**: 请确保在使用前遵守相关的数据使用条款和API服务协议。
