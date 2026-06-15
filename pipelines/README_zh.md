# 农业知识问答对生成系统

[QALoop](https://github.com/JackKuo666/QALoop) 人机协同闭环框架（ICDM）中的**源适配 QA 合成管道**集合。本目录包含 **11 个独立管道**，从异构农业数据源（论文、专利、图书、知识图谱、维基百科、种质报告、基因文献、专家问题等）自动生成高质量问答对（QA pairs），用于大模型 SFT 训练。

---

## 目录

- [快速概览](#快速概览)
- [管道详情](#管道详情)
  - [1. expert_qa_augmentation](#1-expert_qa_augmentation-农业问答增强)
  - [2. expertq_generatea](#2-expertq_generatea-农业育种专家问答批量生成)
  - [3. gene_synthesis](#3-gene_synthesis-基因文献问答对生成)
  - [4. kg_synthesis](#4-kg_synthesis-知识图谱因果链qa生成)
  - [5. paper_synthesis](#5-paper_synthesis-学术论文qa生成)
  - [6. patent_synthesis](#6-patent_synthesis-专利问答对生成)
  - [7. thesis_synthesis](#7-thesis_synthesis-学位论文sft问答对生成)
  - [8. wiki_synthesis](#8-wiki_synthesis-维基百科知识问答)
  - [9. books_qa_generater](#9-books_qa_generater-图书章节qa生成)
  - [10. qa_data_acquisition_quality](#10-qa_data_acquisition_quality-qa质量验证)
  - [11. seedreport_synthesis](#11-seedreport_synthesis-种质报告qa生成)
- [跨管道通用技术](#跨管道通用技术)
- [快速开始](#快速开始)

---

## 快速概览

| # | 管道 | 数据源 | 核心创新 | 输出 |
|---|------|--------|---------|------|
| 1 | [expert_qa_augmentation](#1-expert_qa_augmentation) | 种子问题 | 20+生成策略、智能RAG检索 | JSONL |
| 2 | [expertq_generatea](#2-expertq_generatea) | 种子问题 | 31+模型支持、Thinking模式 | JSONL |
| 3 | [gene_synthesis](#3-gene_synthesis) | 基因文献 | 证据锚定、多跳推理协议 | JSONL |
| 4 | [kg_synthesis](#4-kg_synthesis) | 知识图谱 | TopK白名单、P3随机路径回退 | JSON/JSONL |
| 5 | [paper_synthesis](#5-paper_synthesis) | 学术论文 | 两阶段推理链、智能比例控制 | JSONL |
| 6 | [patent_synthesis](#6-patent_synthesis) | 专利 | 评测-反馈-检索-生成闭环 | JSONL |
| 7 | [thesis_synthesis](#7-thesis_synthesis) | 学位论文 | 多格式章节分割、客观题生成 | JSONL |
| 8 | [wiki_synthesis](#8-wiki_synthesis) | Wikipedia | BioBERT+Qwen两阶段筛选 | JSONL |
| 9 | [books_qa_generater](#9-books_qa_generater) | 图书 | 目录感知章节拆分、层次化质量控制 | JSONL |
| 10 | [qa_data_acquisition_quality](#10-qa_data_acquisition_quality) | QA数据 | LLM生成式评估 | JSONL |
| 11 | [seedreport_synthesis](#11-seedreport_synthesis) | 种质报告 | 8大用户意图体系、零指代问答 | JSONL |

---

## 管道详情

### 1. expert_qa_augmentation (农业问答增强)

**数据源**: 种子问题文件 (JSONL)、专家问题Excel、农业关键词词典

**核心创新**:

| 创新点 | 描述 |
|--------|------|
| **智能RAG检索** | 中英文自动翻译（334个专业术语），多维度评分（7维度100分制） |
| **20+种生成策略** | 释义、推理、对比、假设等多样化策略 |
| **嵌入语义去重** | 基于预训练多语言模型的语义相似度去重 |
| **策略平衡器** | 自动平衡不同策略使用频率 |

**独特技术**: 智能策略选择器、提示词增强（扩展分类信息注入）、多级降级RAG、MD5哈希RAG缓存、并行+串行RAG双模式

---

### 2. expertq_generatea (农业育种专家问答批量生成)

**数据源**: 种子问题JSON (水稻/玉米/小麦/油菜/大豆/畜禽领域)

**核心创新**:

| 创新点 | 描述 |
|--------|------|
| **31+模型支持** | GPT/Claude/Gemini/DeepSeek/Qwen/GLM/Grok |
| **Thinking模式** | 提取推理链(Chain of Thought)，生成双版本答案 |
| **SimHash去重** | Hamming距离<5的高效去重 |
| **RAG检索增强** | PubMed文献检索，带文献引用答案 |

**独特技术**: 多模型批量并发处理、Responses API支持、自动API类型选择、Biopython Entrez API

---

### 3. gene_synthesis (基因文献问答对生成)

**数据源**: JSON格式基因文献 (DOI列表、PMC号)

**核心创新**:

| 创新点 | 描述 |
|--------|------|
| **证据锚定事实性** | 严格不超出证据边界、比例复杂度规则(Level 1-3) |
| **多跳推理协议** | 强制1-2个多跳QA，连接两个生物维度 |
| **触发映射** | 根据非空字段自动适配问题风格 |
| **穷尽精确** | 保留所有数值/P值/Locus ID |

**独特技术**: 三条显式推理路径(Path A/B/C)、标识符落地(基因符号+Locus ID)、Data Depth Audit四步执行协议

---

### 4. kg_synthesis (知识图谱因果链QA生成)

**数据源**: Neo4j知识图谱 / CSV数据 (植物生物学)

**核心创新**:

| 创新点 | 描述 |
|--------|------|
| **TopK白名单过滤** | 首次引入统计报告TopK过滤 |
| **P3随机路径回退** | 三层递进证据库 (P1邻居→P2扩展→P3随机路径) |
| **自然问句约束** | 禁止"图谱/三元组"等技术术语 |
| **多维度验证** | Aspect验证(≥3)、实体约束、证据引用 |

**独特技术**: Neo4j/NetworkX双后端支持、信息因子计算、确定性模式、合并out/in查询

---

### 5. paper_synthesis (学术论文QA生成)

**数据源**: Markdown格式学术论文 (按章节处理)

**核心创新**:

| 创新点 | 描述 |
|--------|------|
| **两阶段推理链生成** | 第一阶段抽取推理链(3-7步)，第二阶段转化为问答 |
| **智能编号问题比例控制** | 默认最多10%，严格质量检查 |
| **多维度质量过滤** | 违禁短语、研究依赖性、作者信息、假设条件检查 |
| **智能采样** | 按难度配比和标签多样性 |

**独特技术**: 章节合并与优先级排序、Thinking模式支持、过生成因子(1.5x)后续采样

---

### 6. patent_synthesis (专利问答对生成)

**数据源**: JSONL格式专利数据 (中文专利、IPC分类)

**核心创新**:

| 创新点 | 描述 |
|--------|------|
| **评测-反馈-检索-生成闭环** | badcase驱动持续优化 |
| **两阶段推理链** | 推理型(1个)+非推理型(3个)QA |
| **混合检索策略** | BM25+Phrase+带间隔Phrase，结果融合 |
| **多维度质量评估** | 幻觉检测 |

**独特技术**: Elasticsearch检索、IPC自动分类、章节完整性检查、专家反馈分析

---

### 7. thesis_synthesis (学位论文SFT问答对生成)

**数据源**: 学位论文JSONL (Markdown/LaTeX/中英文格式)

**核心创新**:

| 创新点 | 描述 |
|--------|------|
| **多格式章节分割** | 自动识别Markdown/LaTeX/中英文/论文特有结构 |
| **两阶段推理链** | 先生成推理过程，再生成答案 |
| **SimHash高效去重** | Hamming距离阈值可配 |
| **Curriculum Stage分配** | 按难度自动分配训练阶段(1/2/3) |

**独特技术**: 客观题生成(单选/多选/判断)、推理多样性过滤、QualityScorer多维评分

---

### 8. wiki_synthesis (维基百科知识问答)

**数据源**: 预处理后的Wikipedia中文语料库

**核心创新**:

| 创新点 | 描述 |
|--------|------|
| **两阶段预筛选** | BioBERT农业分类(936万→76万)+Qwen-flash质量判定(76万→1.95万) |
| **专用农业分类模型** | 基于BioBERT微调，5000+农业关键词增强 |
| **原子化事实提取** | 每个原子事实生成独立问答对 |
| **真实性约束** | 严格基于原文，禁止编造 |

**独特技术**: 置信度阈值可调(0.6~0.999)、断点续传机制、source_file和title溯源

---

### 9. books_qa_generater (图书章节QA生成)

**数据源**: 图书Markdown文件

**核心创新**:

| 创新点 | 描述 |
|--------|------|
| **目录感知章节拆分** | 基于Markdown标题层级(#/##/###)，保留完整章节 |
| **图书专用问答模板** | 事实性/原理性/方法性/比较性问答 |
| **层次化质量控制** | 章节级/段落级/问答级三层控制 |
| **SimHash高效去重** | O(n)时间复杂度处理海量章节 |

**独特技术**: BookProcessor类、Curriculum Stage自动分配(1/2/3难度)、多维度QualityScorer

---

### 10. qa_data_acquisition_quality (QA质量验证)

**数据源**: 待验证的QA数据 (JSONL格式)

**核心创新**:

| 创新点 | 描述 |
|--------|------|
| **LLM生成式评估** | 使用LLM而非传统分类器，生成详细评估报告 |
| **多维度质量评估** | 准确性/相关性/完整性/清晰度四维评分 |
| **可解释性强** | 保留完整模型评估文本 |
| **增量检查点机制** | 每10个样本自动保存 |

**独特技术**: 思维链推理支持、结构化提示工程、自动评分提取、统计报告生成

---

### 11. seedreport_synthesis (种质报告QA生成)

**数据源**: JSON格式种质报告 (农作物新品种审定报告)

**核心创新**:

| 创新点 | 描述 |
|--------|------|
| **8大用户意图体系** | 微观事实/类型归属/横向对比/品质评估/栽培指南/抗病抗虫/综合性状/品种溯源 |
| **零指代问答** | 禁止"该品种"等，使用品种全名 |
| **原子化短回答** | 至少40%为25字以内 |
| **专业口语化** | 农业标准术语+轻微口语化 |

**独特技术**: 8大意图占比要求(10-25%)、50%以品种名开头问句、多维度覆盖(至少5类意图)

---

## 跨管道通用技术

### 去重技术

| 方法 | 描述 |
|------|------|
| **SimHash** | Hamming距离去重，适合大规模数据 |
| **嵌入相似度** | 基于预训练模型的语义相似度，阈值约0.30 |
| **MD5精确去重** | 精确哈希去重 |

### 质量控制

| 方法 | 描述 |
|------|------|
| **多维度评分** | 准确性/相关性/完整性/清晰度等 |
| **阈值过滤** | 设置最小分数阈值过滤低质量QA |
| **难度分级** | easy/medium/hard 或 Curriculum Stage 1/2/3 |
| **违禁词检测** | 检测禁止的短语或表述 |

### 推理链生成

| 方法 | 描述 |
|------|------|
| **两阶段生成** | 第一阶段抽取推理链，第二阶段转化为问答 |
| **Thinking模式** | 提取模型的推理过程作为CoT |
| **Chain of Thought** | 显式的多步推理链 |

### 工程特性

| 特性 | 描述 |
|------|------|
| **并发处理** | ThreadPoolExecutor、信号量控制、批次处理 |
| **断点续传** | 检查点文件、已处理记录JSONL |
| **输出格式** | JSONL为主，带metadata |

---

## 快速开始

### 环境准备

每个管道都是独立的Python项目，使用 `uv` 进行环境管理：

```bash
# 进入目标管道目录
cd <pipeline_name>

# 安装依赖
uv sync

# 复制环境变量模板
cp .env.example .env
# 编辑 .env 设置 API 密钥
```

### 运行测试

```bash
# 每个管道都有示例数据和测试脚本
uv run python test_*.py  # 或对应的测试脚本

# 或直接运行主脚本
uv run python <main_script>.py --help
```

### 依赖说明

| 依赖 | 用途 |
|------|------|
| **openai** | LLM API调用 |
| **python-dotenv** | 环境变量管理 |
| **tqdm** | 进度条显示 |

大部分管道仅需以上基础依赖。特定管道可能需要额外依赖（如 Neo4j、Elasticsearch），详见各管道README。
