# bdd_pubmed_chat_v2_1_final.py - 生物医学问答系统

## 项目概述

`bdd_pubmed_chat_v2_1_final.py` 是一个基于大语言模型的生物医学问答系统，专门针对农业育种领域（如水稻、玉米、小麦、油菜、大豆等）提供专业、准确的问答服务。该系统集成了RAG（检索增强生成）功能，能够从PubMed等文献数据库检索相关文献，并基于检索结果生成带引用的专业答案。

## 核心特性

### 1. 多模式问答
- **RAG模式**：结合文献检索的增强问答
- **纯LLM模式**：基于预训练知识的直接问答
- **流式输出**：支持实时流式显示回答内容

### 2. 推理增强
- **Chain of Thought (COT)**：支持OpenAI的thinking模式
- **自动推理强度选择**：根据问题难度自动选择minimal/low/medium/high
- **推理链提取**：从模型输出中提取完整的推理过程

### 3. 并发处理
- **同步顺序处理**：稳定但速度较慢
- **同步并发处理**：推荐模式，高效且稳定
- **文件级并发**：多文件同时处理

### 4. 文献引用
- **自动文献检索**：从PubMed等数据库检索相关文献
- **智能引用生成**：生成标准格式的参考文献
- **双版本答案**：提供带引用和不带引用的答案版本

### 5. 数据去重
- **问题去重**：基于MD5哈希的智能去重
- **相似度检测**：识别语义相似的问题

## 系统架构

### 核心模块

#### 1. RAG检索模块
- `get_rag_data(query)` - 构建RAG检索请求
- `fetch_documents(query)` - 检索文献（支持重试机制）
- `parse_stream_response(response_text)` - 解析检索响应
- `generate_context_from_documents(documents)` - 生成上下文
- `generate_reference_citations(documents)` - 生成引用

#### 2. API调用模块
- `call_llm_api_logged_single()` - 同步API调用
- `call_llm_api_streaming_single()` - 流式API调用
- `extract_cot_from_reasoning()` - 提取推理链
- `split_think_content()` - 分离思考内容

#### 3. 提示词模块
- `create_enhanced_prompt()` - 创建RAG增强提示词
- `create_prompt_without_rag()` - 创建非RAG提示词

#### 4. 答案解析模块
- `parse_dual_version_response()` - 解析双版本答案
- `generate_answer_for_item()` - 生成完整答案

#### 5. 并发处理模块
- `process_questions_concurrent()` - 问题级并发
- `process_files_concurrent()` - 文件级并发

#### 6. 数据处理模块
- `deduplicate_qa_pairs()` - QA对去重
- `calculate_question_similarity_hash()` - 计算问题相似度哈希

## 配置说明

### 环境变量
```python
# OpenAI API配置
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

# RAG API配置
RAG_URL = "rag-api-endpoint"
RAG_HEADERS = {...}

# 重试配置
RAG_RETRY_CONFIG = {
    "max_retries": 8,
    "timeout": 60,
    "retry_delay": 3,
    "exponential_backoff": True,
    "backoff_factor": 2
}
```

### Thinking模式配置
- **auto**：自动根据问题难度选择（推荐）
- **none/off**：禁用thinking模式
- **minimal/low/medium/high**：固定强度

## 使用方法

### 基本用法

1. **运行主程序**
```bash
python bdd_pubmed_chat_v2_1_final.py
```

2. **配置参数**
   - 输入目录路径（默认：`../../03_data/data/reanswer_v5d/`）
   - 处理模式（1-3）
   - 是否使用流式显示
   - 是否使用RAG检索
   - Thinking模式选择
   - 最大工作线程数

### 示例场景

#### 场景1：使用RAG的并发问答
```python
# 交互式选择
处理模式: 2 (同步并发)
使用RAG: y
Thinking模式: auto
```

#### 场景2：纯LLM问答（无RAG）
```python
# 交互式选择
处理模式: 2 (同步并发)
使用RAG: n
Thinking模式: medium
```

#### 场景3：流式输出测试
```python
# 交互式选择
处理模式: 1 (同步顺序)
使用流式: y
使用RAG: y
```

### 编程接口

#### 单个问题处理
```python
from bdd_pubmed_chat_v2_1_final import generate_answer_for_item

result = generate_answer_for_item(
    item={
        "question": "大豆抗虫育种有哪些方法？",
        "主分类": "育种技术",
        "亚类": "抗虫育种"
    },
    answer_prompt_file="./simple_text_prompt_v8.txt",
    use_streaming=False,
    use_rag=True,
    think_mode="auto"
)
```

#### 批量并发处理
```python
from bdd_pubmed_chat_v2_1_final import process_questions_concurrent

results = process_questions_concurrent(
    questions_data=questions_list,
    output_dir="./output",
    answer_prompt_file="./simple_text_prompt_v8.txt",
    use_streaming=False,
    use_rag=True,
    max_workers=50,
    think_mode="auto"
)
```

## 输入数据格式

### JSON格式
```json
{
  "question": "问题内容",
  "主分类": "主分类名称",
  "亚类": "亚类名称",
  "物种": "物种名称"
}
```

### JSONL格式
```jsonl
{"question": "问题1", "主分类": "分类1", "亚类": "子类1", "物种": "物种1"}
{"question": "问题2", "主分类": "分类2", "亚类": "子类2", "物种": "物种2"}
```

## 输出数据格式

### 主输出文件 (master.jsonl)
```json
{
  "question": "原始问题",
  "answer": "不带引用的答案",
  "api_cot": "模型思考过程",
  "qa_cot_from_prompt": "推理链",
  "reasoning_steps": ["步骤1", "步骤2"],
  "answer_with_citation": "带引用的答案",
  "metadata": {
    "主分类": "分类",
    "亚类": "子类",
    "物种": "物种",
    "生成时间": "2025-01-22 10:30:00",
    "使用模型": "gpt-5.1",
    "输入_tokens": 1500,
    "输出_tokens": 800,
    "总_tokens": 2300,
    "api处理时间_秒": 5.2,
    "使用RAG": true,
    "RAG文献数量": 5,
    "Thinking模式": "auto",
    "RAG参考文献": "参考文献内容"
  }
}
```

### Markdown报告
系统自动生成Markdown格式的详细报告，包含：
- 处理统计
- 问题与答案列表
- 推理链
- 引用信息
- 性能指标

## 性能优化

### 1. 并发配置
- **推荐线程数**：50-100（根据系统性能调整）
- **批处理大小**：线程数 × 2
- **批次延迟**：0.5-1秒（防止过载）

### 2. 重试机制
- **最大重试**：8次
- **超时设置**：60秒
- **退避策略**：指数退避（因子=2）

### 3. 内存管理
- **问题级去重**：避免重复处理
- **分批处理**：避免一次性加载过多数据
- **结果实时保存**：防止内存溢出

## 统计与监控

### 全局统计 (global_stats)
```python
global_stats = {
    "start_time": 开始时间,
    "end_time": 结束时间,
    "total_files": 总文件数,
    "total_questions": 总问题数,
    "successful_questions": 成功问题数,
    "failed_questions": 失败问题数,
    "total_input_tokens": 总输入Tokens,
    "total_output_tokens": 总输出Tokens,
    "total_tokens": 总Tokens,
    "rag_used_count": 使用RAG的问题数,
    "rag_documents_found": RAG找到的文献数,
    "rag_api_call_time": RAG API总调用时间
}
```

### 处理报告
每次处理完成后生成详细的Markdown报告，包含：
- 处理时间统计
- 成功率
- Token使用量
- RAG检索统计
- 平均处理时间

## 错误处理

### 1. API错误
- 自动重试机制
- 详细错误日志
- 超时处理

### 2. 数据错误
- JSON解析错误捕获
- 空数据检查
- 格式验证

### 3. 并发错误
- 任务超时（600秒）
- 批次延迟控制
- 异常恢复

## 日志系统

### 日志级别
- **INFO**：常规操作信息
- **WARNING**：警告信息
- **ERROR**：错误信息
- **DEBUG**：调试信息

### 日志内容
- API调用详情
- RAG检索结果
- 性能指标
- 错误堆栈

## 依赖项

### 核心依赖
```python
import openai          # OpenAI API客户端
import requests        # HTTP请求
import pandas as pd    # 数据处理
import json            # JSON处理
import time            # 时间控制
import os              # 文件操作
import logging         # 日志系统
from concurrent.futures import ThreadPoolExecutor, as_completed  # 并发处理
```

### 提示词文件
- `simple_text_prompt_v8.txt`：默认提示词模板

## 最佳实践

### 1. 问题设计
- 确保问题清晰、具体
- 包含必要的前提信息
- 避免歧义或概念混淆

### 2. 分类标注
- 准确标注主分类和亚类
- 选择正确的物种信息
- 保持分类体系的一致性

### 3. 性能优化
- 使用并发模式处理大量问题
- 合理设置线程数（建议50-100）
- 启用RAG模式提高答案准确性
- 使用auto模式自动选择thinking强度

### 4. 结果验证
- 检查成功率
- 验证引用格式
- 确认推理链完整性
- 监控Token使用量

## 常见问题

### Q1：RAG检索失败怎么办？
A：检查网络连接和RAG API配置，系统会自动重试8次。

### Q2：如何提高处理速度？
A：使用并发模式（模式2），设置合理的线程数（50-100），关闭流式输出。

### Q3：答案质量如何保证？
A：启用RAG模式获取文献支持，使用合适的thinking模式，确保问题描述清晰。

### Q4：如何处理大文件？
A：系统支持分批处理，建议单个文件不超过10000个问题。

### Q5：如何监控系统性能？
A：查看生成的processing_report.md文件，包含详细的统计信息。

## 更新日志

### v2.1 Final
- ✅ 优化并发处理性能
- ✅ 增强RAG检索稳定性
- ✅ 改进推理链提取算法
- ✅ 添加自动thinking模式
- ✅ 完善错误处理机制
- ✅ 优化内存使用

### v2.0
- 🎉 首次发布RAG增强问答功能
- 🎉 支持多模型并发处理
- 🎉 添加流式输出支持

## 许可证

本项目采用 MIT 许可证。详情请查看项目LICENSE文件。

## 贡献指南

欢迎提交Issue和Pull Request！

### 提交规范
1. Fork项目
2. 创建特性分支
3. 提交更改
4. 发起Pull Request

### 代码规范
- 遵循PEP 8
- 添加必要的注释
- 包含单元测试
- 更新文档

## 联系方式

如有问题，请通过以下方式联系：
- 项目Issue：https://github.com/your-repo/issues
- 邮箱：your-email@example.com

---

**注意**：本系统仅供学术研究和教育使用，使用时请遵守相关法律法规和学术诚信原则。
