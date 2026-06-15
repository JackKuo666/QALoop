# QALoop

**面向大规模农业 QA 构建与评测的人机协同闭环框架**

ICDM 论文官方代码发布。QALoop 将农业 QA 数据生产实现为**闭环系统**：异构数据源经 Pipeline 路由进入源适配 QA 合成管道，在协作标注平台上完成专家验证，结构化反馈驱动管道迭代，并通过独立 Benchmark 进行外部评测。

在植物育种案例研究中，QALoop 通过 7 条生产级管道产出 **245,958 条 QA 记录**，构建 **1,434 题的独立 Benchmark**，并对 **11 个 LLM** 进行专家打分对比。迭代式专家反馈改进了多条管道；下游对 Qwen3-8B 全参数 SFT 将育种 Benchmark 平均分从 **84.58 提升至 88.17**。

## 系统架构

![QALoop 系统架构](platform/seed/figure1.png)

上图展示了 QALoop 端到端流程：异构农业数据源经 Pipeline 路由与源适配 QA 合成管道进入候选 QA 池，随后在 **专家验证平台**（`platform/`）完成人工质检；反馈与迭代引擎形成闭环，最终输出精选训练 QA、独立评测集及下游模型评测。

## 项目结构

```
QALoop/
├── platform/      # 标注与评测平台（FastAPI Web 应用）
├── pipelines/     # QA 生成 Pipeline 集合
├── data/          # 本地数据存储（SQLite 数据库，已 gitignore）
└── LICENSE
```

## 模块说明

### platform/ — 标注与评测平台

基于 FastAPI 的多用户协作标注平台，支持项目/数据集管理、灵活的标注配置（评分、分类、文本、单选/多选、二元）、统计分析与导出。可选集成 LLM 对标注备注进行智能分析。

详见 [platform/README.md](platform/README.md)。

### pipelines/ — QA 生成 Pipeline

独立的 QA 数据生成流水线集合，每个 Pipeline 负责从特定数据源生成 QA 对。各管道目录下包含各自的 README、示例与文档。

详见 [pipelines/README.md](pipelines/README.md)。

## 发布内容说明

本仓库聚焦**可复用框架代码**，而非无限制公开全部生产数据：

| 包含 | 说明 |
|------|------|
| `platform/` | 专家验证与协作标注平台（FastAPI） |
| `pipelines/` | 11 条源适配 QA 合成管道及最小可运行示例 |
| 文档 | README、配置与部署说明 |

论文中的生产级数据集与完整独立 Benchmark **未**包含在本发布中，数据获取方式见论文说明。

## 引用

如在研究中使用 QALoop，请引用：

```bibtex
@inproceedings{kuo2026qaloop,
  title={QALoop: A Human-in-the-Loop Framework for Large-scale Agricultural QA Construction and Evaluation},
  author={...},
  booktitle={IEEE International Conference on Data Mining (ICDM)},
  year={2026}
}
```

> 作者列表与完整 BibTeX 将在正式发表后更新。

## 快速开始

### 启动标注平台

```bash
cd platform

# 安装依赖
uv sync

# 配置环境变量
cp .env.example .env
# 编辑 .env，修改 SECRET_KEY

# 创建超级用户
python scripts/create_superuser.py

# 启动
uvicorn qa_annotate.main:app --reload --host 0.0.0.0 --port 8000
```

详见 [platform/README.md](platform/README.md)。

## 环境要求

- Python >= 3.12
- [uv](https://docs.astral.sh/uv/)

## License

MIT
