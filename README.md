# QALoop

QA 数据全生命周期工具集：从生成、标注到评测。

## 项目结构

```
QALoop/
├── platform/      # 标注与评测平台（FastAPI Web 应用）
├── pipelines/     # QA 生成 Pipeline 集合
├── examples/      # 使用示例与样例数据
├── docs/          # 文档
└── README.md
```

## 模块说明

### platform/ — 标注与评测平台

基于 FastAPI 的多用户协作标注平台，支持项目/数据集管理、灵活的标注配置（评分、分类、文本、单选/多选、二元）、统计分析与导出。可选集成 LLM 对标注备注进行智能分析。

详见 [platform/README.md](platform/README.md)。

### pipelines/ — QA 生成 Pipeline

独立的 QA 数据生成流水线集合，每个 Pipeline 负责从特定数据源生成 QA 对。

### examples/ — 使用示例

导入数据格式、Pipeline 配置示例等。

### docs/ — 文档

架构设计、API 文档、部署指南等。

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

Private
