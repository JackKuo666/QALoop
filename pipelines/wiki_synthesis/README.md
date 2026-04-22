# Wiki 问答对生成 Pipeline

本代码库实现了从维基百科（Wiki）语料生成农业领域基础知识问答对的自动化流程。

## 核心流程

```
全量 Wiki 语料
        ↓
   BioBERT 农业分类模型筛选
        ↓
   泛农业内容筛选（约 76 万条）
        ↓
   Qwen-flash 模型质量筛选
        ↓
   高质量内容筛选（约 1.95 万条）
        ↓
      去重处理
        ↓
   最终用于生成（约 1.94 万条）
        ↓
   GPT/LLM 生成农业领域问答对
        ↓
   约 2.9 万对问答
```

## 依赖资源

### BioBERT 模型

需要下载预训练的 BioBERT 分类模型：

```bash
# 创建模型目录
mkdir -p biobert/models
mkdir -p biobert/data

# 下载模型文件 (约 413MB)
# 将 best_model.bin 放入 biobert/models/

# 准备关键词文件
# 将 中国农业关键词.xlsx 放入 biobert/data/
```

### Wiki 数据

将预处理后的 Wiki 数据放入 `data/wiki_filtered/` 目录：

```bash
mkdir -p data/wiki_filtered
# 放置 JSON 格式的 Wiki 数据
```

## 快速开始

### 1. 环境准备

```bash
cd wiki_synthesis
uv sync

# 配置 API 密钥
cp .env.example .env
# 编辑 .env 文件，设置 OPENAI_API_KEY 和 QWEN_API_KEY
```

### 2. 运行问答生成

```bash
# 使用样本数据测试
python test_wiki_v2.py

# 使用完整数据集
python wiki_qa_bert_qw_v4.py
```

### 3. 配置数据源

修改 `wiki_qa_bert_qw_v4.py` 中的路径配置：

```python
# 数据源目录（通过环境变量配置）
WIKI_DATA_DIR = os.getenv("WIKI_DATA_DIR", "./data/wiki_filtered")

# 运行模式：stage2（跳过 Qwen 判定，直接生成 QA）
RUN_MODE = "stage2"

# 处理范围
FILE_START_INDEX = 1
FILE_END_INDEX = None  # None 表示处理全部
```

## 数据源路径

数据通过 BERT + Qwen 两阶段筛选得到，来源可以是：
- 预处理后的 Wikipedia 中文语料库
- 自定义清洗过的文本数据

配置数据目录（见 `.env.example`）：
```
WIKI_DATA_DIR=./data/wiki_filtered
```

## 输出格式

生成的问答对保存为 JSONL 格式：

```json
{
  "question": "水稻起源于哪个国家，目前主要分布在哪些地区？",
  "answer": "水稻起源于中国，已有7000年以上的栽培历史，主要分布在亚洲、非洲和美洲的热带及亚热带地区。",
  "cot": "推理过程...",
  "generation_time": "2026-04-17 16:51:09",
  "source_file": "水稻.json",
  "title": "水稻"
}
```

## 项目结构

```
wiki_synthesis/
├── wiki_qa_bert_qw_v4.py       # 主程序（BERT+Qwen筛选 → GPT生成）
├── test_wiki_v2.py             # 测试脚本（样本数据测试）
├── arg_kw.xlsx                # 关键词表
├── examples/
│   ├── sample_data_v2/        # 样本数据（水稻.json, 玉米.json, 油菜.json）
│   └── output_v2_test.jsonl   # 测试输出
├── biobert/                   # BERT 模型代码（用于预筛选）
└── README.md
```

## 核心特性

- **两阶段筛选**：BioBERT + Qwen 预筛选农业相关内容
- **高质量生成**：基于 GPT-5.1 生成带推理链的问答对
- **原子化事实**：每个问答针对单一知识点
- **真实性原则**：严格基于文本内容，严禁编造
- **断点续传**：支持配额用尽后恢复处理

## 核心创新点

### 1. 两阶段预筛选机制

| 阶段 | 方法 | 筛选目标 | 数据量 |
|------|------|---------|--------|
| 第一阶段 | BioBERT 农业分类模型 | 识别农业相关内容 | 936万 → 76万 |
| 第二阶段 | Qwen-flash 质量判定 | 筛选高质量内容 | 76万 → 1.95万 |

这种组合筛选策略在保证内容质量的同时，将数据量压缩至原始的 **0.2%**，大幅降低后续生成成本。

### 2. 专用农业分类模型

- **领域定制**：基于 BioBERT 针对农业领域微调
- **多层次分类**：支持泛农业、专业农业、超级严格等多种分类标准
- **关键词增强**：结合 5000+ 农业专业关键词，提升分类精度
- **阈值可调**：支持 0.6~0.999 可配置置信度阈值

### 3. 原子化事实提取

```
Wiki 整篇文章
    ↓ 结构化解析
原子事实列表
    ↓ 选择性展开
单个原子事实 → 单个问答对
```

- 将 Wiki 条目拆分为多个原子事实
- 每个原子事实生成一个独立问答对
- 保证问答的精确性和可验证性

### 4. 真实性约束机制

| 约束类型 | 实现方式 |
|---------|---------|
| 内容约束 | 严格基于原文内容生成 |
| 禁止编造 | 答案仅使用文本中的具体事实和数据 |
| 可验证性 | 保留 source_file 和 title 便于溯源 |

### 5. 断点续传机制

- 支持配额（quota）用尽后恢复处理
- 自动跳过已完成的文件
- 详细的处理日志便于监控进度

## QA 生成规则

1. **农业领域判定**：自动判断文本是否属于农业领域
2. **问题要求**：
   - 基于文本内容，不超出范围
   - 清晰有意义，独立可理解
   - 不使用引用性词语
3. **答案要求**：
   - 优先使用文本中的具体事实和数据
   - 可适当补充专业知识
   - 严禁编造任何信息
