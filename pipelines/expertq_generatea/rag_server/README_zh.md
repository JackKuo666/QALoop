# Bio RAG Server (No Elasticsearch Required)

基于 **Biopython Entrez API** 的 PubMed 检索服务，无需 Elasticsearch。

## 特性

- **PubMed 直接检索**：使用 NCBI Entrez API，无需外部数据库
- **FastAPI 服务**：高性能异步 API
- **零外部依赖**：无需 Elasticsearch、Milvus、Redis

## 快速开始

```bash
cd rag_server
pip install -r requirements.txt
python main.py
# 或
bash run.sh
```

服务运行在 `http://localhost:9487`

## 与 seed_Q_generate_A_v2.py 配合使用

RAG Server 可为问答生成提供文献检索支持：

```bash
# 1. 启动 RAG Server（后台运行）
cd rag_server
python main.py &
sleep 3

# 2. 运行 QA 生成（启用 RAG）
cd ..
python seed_Q_generate_A_v2.py \
  --input examples/sample_input.json \
  --output output/ \
  --use-rag \
  --model gpt-5.1
```

### RAG 工作流程

1. 用户问题 → `seed_Q_generate_A_v2.py`
2. 问题 → `fetch_documents()` → RAG Server (`localhost:9487`)
3. RAG Server → PubMed 检索 → 返回文献列表
4. 文献上下文 → LLM 生成带引用的答案

## API 端点

### 健康检查
```bash
GET /health
# Response: {"status":"healthy","service":"bio-rag-server"}
```

### 文档检索
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

### 响应示例
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

### 流式聊天（待实现）
```bash
POST /stream-chat
```

## 项目结构

```
rag_server/
├── main.py                 # FastAPI 应用入口
├── dto/
│   └── bio_document.py     # 文档数据模型
├── service/
│   ├── pubmed_api.py       # Biopython Entrez API
│   └── rag.py              # RAG 服务编排
├── search_service/
│   ├── base_search.py      # 搜索服务基类
│   └── pubmed_search.py    # PubMed 搜索实现
├── routers/
│   └── sensor.py           # API 路由
└── utils/
    ├── bio_logger.py       # 日志配置
    └── snowflake_id.py     # ID 生成
```

## 依赖

- Python 3.10+
- Biopython >= 1.81 (Entrez API)
- FastAPI >= 0.104.0
- uvicorn >= 0.24.0

## 与旧版区别

| 特性 | 旧版 (ES) | 新版 (Biopython) |
|------|-----------|-------------------|
| PubMed 检索 | Elasticsearch | NCBI Entrez API |
| 外部依赖 | ES + Milvus + Redis | 仅网络 |
| 配置复杂度 | 高 | 低 |
| 启动速度 | 慢 | 快 |
