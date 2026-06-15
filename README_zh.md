# QALoop

QA 数据全生命周期工具集：从生成、标注到评测。

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
