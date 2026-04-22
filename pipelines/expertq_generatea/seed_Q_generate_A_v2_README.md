# expertQ_generateA_v2.py - 生物医学专家问答系统

## 项目概述

`expertQ_generateA_v2.py` 是一个基于多模型集成的生物医学专家问答系统，专门针对农业育种领域（如水稻、玉米、小麦、油菜、大豆等）提供专业、准确的问答服务。该系统支持多模型并发处理，集成了RAG（检索增强生成）功能，能够从PubMed等文献数据库检索相关文献，并基于检索结果生成带引用的专业答案。

## 核心特性

### 1. 多模型支持
- **22个预置模型**：支持GPT、Claude、Gemini、DeepSeek、Grok、GLM、Qwen等主流大模型
- **智能API选择**：自动选择Responses API或Chat Completions API
- **Thinking模式**：支持模型思考过程，增强推理能力
- **模型配置灵活**：支持自定义模型列表，动态标签生成

### 2. RAG检索增强
- **文献检索**：从PubMed等数据库检索相关文献
- **智能上下文生成**：将检索结果转换为问答上下文
- **引用格式标准化**：生成标准格式的参考文献
- **重试机制**：支持指数退避的重试策略

### 3. 并发处理
- **文件级并发**：支持多文件同时处理
- **问题级并发**：支持批量问题并发处理
- **线程池管理**：可配置最大工作线程数
- **实时进度显示**：显示处理进度和预计完成时间

### 4. 答案质量保证
- **双版本答案**：提供带引用和不带引用的答案版本
- **Chain of Thought**：支持推理链提取和展示
- **自动思考模式**：根据问题难度自动选择thinking强度
- **答案去重**：基于MD5哈希的智能去重

### 5. 输出格式多样
- **JSONL格式**：结构化数据输出
- **Markdown格式**：人类可读的详细报告
- **统计数据**：包含处理统计、性能指标、Token使用量等
- **日志系统**：详细的执行日志和错误追踪

## 系统架构

### 核心模块

#### 1. API管理模块
- `get_api_key_for_endpoint()` - 智能API Key选择
- `is_responses_api_supported()` - API支持性检查
- `client` - OpenAI客户端初始化

#### 2. 模型配置模块
- `SUPPORTED_MODELS` - 22个预置模型配置
- `MODELS_REQUIRE_CHAT_COMPLETIONS` - Chat API模型列表
- `THINKING_MODEL_SUFFIXES` - Thinking模式后缀映射

#### 3. RAG检索模块
- `get_rag_data(query)` - 构建RAG检索请求
- `fetch_documents(query)` - 检索文献（支持重试）
- `parse_stream_response()` - 解析检索响应
- `generate_context_from_documents()` - 生成上下文
- `generate_reference_citations()` - 生成引用

#### 4. API调用模块
- `call_llm_api_logged_single()` - 同步API调用
- `call_llm_api_streaming_single()` - 流式API调用
- `call_chat_completions_api()` - Chat API调用
- `extract_cot_from_reasoning()` - 提取推理链
- `split_think_content()` - 分离思考内容

#### 5. 提示词模块
- `create_enhanced_prompt()` - 创建RAG增强提示词
- `parse_dual_version_response()` - 解析双版本答案

#### 6. 并发处理模块
- `process_species_questions_with_multiple_models()` - 顺序处理
- `process_species_questions_with_multiple_models_concurrent()` - 并发处理
- `process_questions_concurrent()` - 问题级并发
- `process_files_concurrent()` - 文件级并发

#### 7. 数据处理模块
- `deduplicate_qa_pairs()` - QA对去重
- `calculate_question_similarity_hash()` - 计算问题哈希
- `get_category_value()` - 获取分类值

#### 8. 保存模块
- `save_to_jsonl()` - 保存为JSONL格式
- `save_to_markdown()` - 保存为Markdown格式
- `save_batch_results()` - 批量保存
- `generate_overall_report()` - 生成总体报告

## 配置说明

### 环境变量
```bash
# OpenAI API配置
OPENAI_API_KEY=${OPENAI_API_KEY}
DEEPSEEK_API_KEY=${DEEPSEEK_API_KEY}

# API端点配置（通过环境变量）
OPENAI_BASE_URL="https://api.openai.com/v1"
```

### 支持的模型

#### OpenAI GPT系列
- `gpt-5.1` - GPT-5.1
- `gpt-5.2` - GPT-5.2
- `gpt-4o` - GPT-4o
- `gpt-oss-120b` - GPT-OSS-120B

#### DeepSeek系列
- `deepseek-v3.2` - DeepSeek V3.2
- `deepseek-v3.2-thinking` - DeepSeek V3.2 Thinking
- `deepseek-v3` - DeepSeek V3
- `deepseek-v2.5` - DeepSeek V2.5

#### Qwen系列
- `qwen-max` - Qwen Max
- `qwen-plus` - Qwen Plus
- `qwen-turbo` - Qwen Turbo
- `qwen3-30b-a3b` - Qwen3 30B A3B
- `qwen3-30b-a3b-think` - Qwen3 30B A3B Think

#### Gemini系列
- `gemini-2-5-pro` - Gemini 2.5 Pro
- `gemini-2-5-flash` - Gemini 2.5 Flash

#### Claude系列
- `claude-sonnet-4-5-20250929` - Claude Sonnet 4.5
- `claude-sonnet-4-5-20250929-thinking` - Claude Sonnet 4.5 Thinking
- `claude-sonnet-4-20250514` - Claude Sonnet 4 (Deprecated)
- `claude-opus-4-20250514` - Claude Opus 4 (Deprecated)
- `claude-3-5-haiku-20241022` - Claude 3.5 Haiku

#### 其他模型
- `grok-4-1-fast-reasoning` - Grok 4.1 Fast (Reasoning)
- `glm-4.6` - GLM-4.6

### Thinking模式配置
- **auto**：自动根据问题难度选择（推荐）
- **minimal/low/medium/high**：固定强度
- **none/off/disable**：禁用thinking模式

### RAG配置
```python
RAG_RETRY_CONFIG = {
    "timeout": 300,
    "max_retries": 5,
    "retry_delay": 2.0,
    "exponential_backoff": True,
    "backoff_factor": 2.0,
}
```

## 使用方法

### 命令行使用

#### 基本用法
```bash
# 交互式模式（推荐）
python expertQ_generateA_v2.py

# 自动模式
python expertQ_generateA_v2.py --auto --input /path/to/input --output /path/to/output

# 指定模式和并发数
python expertQ_generateA_v2.py --mode 3 --input /path/to/input --output /path/to/output --workers 8

# 自定义模型列表
python expertQ_generateA_v2.py --mode 3 \
    --input /path/to/input \
    --output /path/to/output \
    --models gpt-5.2 gpt-oss-120b deepseek-v3.2

# 完整配置
python expertQ_generateA_v2.py --auto \
    --input /path/to/input \
    --output /path/to/output \
    --models gpt-5.2 gpt-oss-120b \
    --workers 8
```

#### 运行模式
- **模式1**：单模型处理模式
- **模式2**：多模型批量处理（顺序）
- **模式3**：多模型批量处理（文件级并发，推荐）

### 编程接口

#### 单个问题处理
```python
from expertQ_generateA_v2 import generate_answer_for_item

result = generate_answer_for_item(
    item={
        "question": "大豆抗虫育种有哪些方法？",
        "主分类": "育种技术",
        "亚类": "抗虫育种",
        "物种": "大豆"
    },
    answer_prompt_file="./simple_text_prompt_v8.txt",
    use_streaming=False,
    use_rag=True,
    think_mode="auto",
    model="gpt-5.2"
)
```

#### 批量顺序处理
```python
from expertQ_generateA_v2 import process_species_questions_with_multiple_models

models = ["gpt-5.2", "gpt-oss-120b", "deepseek-v3.2"]
process_species_questions_with_multiple_models(
    input_dir="/path/to/input",
    output_dir="/path/to/output",
    models_to_test=models
)
```

#### 批量并发处理（推荐）
```python
from expertQ_generateA_v2 import process_species_questions_with_multiple_models_concurrent

models = ["gpt-5.2", "gpt-oss-120b", "deepseek-v3.2"]
process_species_questions_with_multiple_models_concurrent(
    input_dir="/path/to/input",
    output_dir="/path/to/output",
    max_workers=8,
    models_to_test=models
)
```

#### 问题级并发处理
```python
from expertQ_generateA_v2 import process_questions_concurrent

questions_data = [...]  # 问题列表
results = process_questions_concurrent(
    questions_data=questions_data,
    output_dir="/path/to/output",
    answer_prompt_file="./simple_text_prompt_v8.txt",
    use_streaming=False,
    use_rag=True,
    max_workers=50,
    think_mode="auto",
    model="gpt-5.2"
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

### 输入目录结构
```
input_dir/
├── species1_sampled_100.json
├── species2_sampled_100.json
└── ...
```

## 输出数据格式

### 主输出文件 (master.jsonl)
```json
{
  "question": "原始问题",
  "answer": "不带引用的答案",
  "answer_with_citation": "带引用的答案",
  "metadata": {
    "主分类": "分类",
    "亚类": "子类",
    "物种": "物种",
    "生成时间": "2026-01-22 10:30:00",
    "使用模型": "gpt-5.2",
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
系统自动生成详细的Markdown报告，包含：
- 处理统计
- 问题与答案列表
- 推理链
- 引用信息
- 性能指标

### 文件命名规则
- 问题文件：`{物种名}_multi_model_answers.jsonl`
- Markdown报告：`{文件名}_answers.md`
- 主数据文件：`master.jsonl`
- 总体报告：`processing_report.md`

## 性能优化

### 并发配置
- **推荐线程数**：4-8（文件级并发）
- **问题级并发**：50-100（根据系统性能调整）
- **批处理大小**：线程数 × 2
- **批次延迟**：0.5-1秒（防止过载）

### 重试机制
- **最大重试**：8次（API调用），5次（RAG检索）
- **超时设置**：300秒（RAG），无限制（API）
- **退避策略**：指数退避（因子=1.5-2.0）

### 内存管理
- **问题级去重**：避免重复处理
- **分批处理**：避免一次性加载过多数据
- **结果实时保存**：防止内存溢出
- **深拷贝**：防止数据污染

## 统计与监控

### 全局统计 (global_stats)
```python
global_stats = {
    "total_files": 总文件数,
    "total_questions": 总问题数,
    "successful_questions": 成功问题数,
    "failed_questions": 失败问题数,
    "total_input_tokens": 总输入Tokens,
    "total_output_tokens": 总输出Tokens,
    "total_tokens": 总Tokens,
    "rag_used_count": 使用RAG的问题数,
    "rag_documents_found": RAG找到的文献数,
    "start_time": 开始时间,
    "end_time": 结束时间
}
```

### 处理报告
每次处理完成后生成详细的Markdown报告，包含：
- 处理时间统计
- 成功率
- Token使用量
- RAG检索统计
- 平均处理时间
- 并发性能指标

## 错误处理

### API错误处理
- **自动重试**：支持指数退避
- **多API端点**：主端点失败时自动切换
- **超时处理**：可配置超时时间
- **错误日志**：详细的错误信息和堆栈

### 数据错误处理
- **JSON解析错误**：跳过损坏的记录
- **空数据检查**：过滤无效问题
- **格式验证**：确保输入格式正确
- **编码处理**：UTF-8编码支持

### 并发错误处理
- **任务超时**：600秒（问题级），900秒（文件级）
- **批次延迟**：防止系统过载
- **异常恢复**：单个任务失败不影响整体
- **资源清理**：确保线程池正确释放

## 日志系统

### 日志级别
- **INFO**：常规操作信息
- **WARNING**：警告信息
- **ERROR**：错误信息
- **DEBUG**：调试信息

### 日志输出
- **文件日志**：`api_processing.log`
- **控制台输出**：实时显示处理进度
- **格式**：`时间戳 - 级别 - 消息`

### 日志内容
- API调用详情
- RAG检索结果
- 性能指标
- 错误堆栈
- 处理进度

## 依赖项

### 核心依赖
```python
openai              # OpenAI API客户端
pandas              # 数据处理
requests            # HTTP请求
concurrent.futures  # 并发处理
python-dotenv       # 环境变量管理
```

### 系统要求
- Python 3.8+
- 内存：建议8GB以上
- 存储：根据数据量确定
- 网络：稳定的互联网连接

### 提示词文件
- `simple_text_prompt_v8.txt`：默认提示词模板

## 最佳实践

### 1. 问题设计
- 确保问题清晰、具体
- 包含必要的前提信息
- 避免歧义或概念混淆
- 合理分类标注

### 2. 模型选择
- **简单问题**：使用`gpt-5.1`
- **复杂问题**：使用`gpt-5.2`或`deepseek-v3.2-thinking`
- **中文问题**：优先使用Qwen系列
- **英文问题**：可以使用GPT或Claude系列

### 3. 性能优化
- **大量数据**：使用并发模式（模式3）
- **资源受限**：减少并发数（4-8线程）
- **稳定性优先**：使用顺序模式（模式2）
- **快速测试**：启用流式输出

### 4. 结果验证
- 检查成功率
- 验证引用格式
- 确认推理链完整性
- 监控Token使用量
- 查看错误日志

### 5. 数据管理
- 定期清理临时文件
- 备份重要的输出结果
- 监控磁盘空间使用
- 归档历史数据

## 常见问题

### Q1：如何选择合适的模型？
A：根据问题复杂度选择。简单问题用轻量级模型（gpt-4o），复杂问题用高性能模型（gpt-5.2、deepseek-v3.2-thinking）。

### Q2：RAG检索失败怎么办？
A：检查网络连接和RAG API配置，系统会自动重试5次。可以尝试增加超时时间。

### Q3：如何提高处理速度？
A：使用并发模式（模式3），设置合理的线程数（4-8），关闭流式输出。

### Q4：答案质量如何保证？
A：启用RAG模式获取文献支持，使用合适的thinking模式，确保问题描述清晰。

### Q5：如何处理大文件？
A：系统支持分批处理，建议单个文件不超过10000个问题。

### Q6：如何监控系统性能？
A：查看生成的`processing_report.md`文件，包含详细的统计信息和性能指标。

### Q7：支持哪些输入格式？
A：支持JSON、JSONL、XLS、XLSX格式。建议使用JSON或JSONL格式。

### Q8：如何自定义提示词？
A：修改`simple_text_prompt_v8.txt`文件，或通过编程方式传递自定义提示词。

## API差异说明

### Responses API vs Chat Completions API

#### Responses API
- **优点**：支持thinking模式，易于提取推理链
- **适用模型**：GPT-5系列、Claude系列、DeepSeek等
- **返回格式**：结构化output，支持reasoning

#### Chat Completions API
- **优点**：兼容性好，支持更多模型
- **适用模型**：Qwen、GLM、部分Claude模型
- **返回格式**：标准chat格式

#### 自动选择逻辑
```python
# 优先级：
# 1. 如果模型在Chat API列表中 → 使用Chat API
# 2. 如果模型包含thinking后缀 → 使用Responses API
# 3. 其他情况 → 根据模型特性选择
```

## 更新日志

### v2.0
- ✅ 支持22个主流大模型
- ✅ 智能API选择（Responses/Chat）
- ✅ 并发处理优化
- ✅ RAG检索增强
- ✅ Thinking模式支持
- ✅ 双版本答案（带/不带引用）
- ✅ 动态模型配置
- ✅ 详细统计报告

### v1.0
- 🎉 初始版本
- 🎉 基础问答功能
- 🎉 RAG检索支持

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

## 致谢

感谢以下开源项目：
- OpenAI API
- Requests
- Pandas
- Python标准库

---

**注意**：本系统仅供学术研究和教育使用，使用时请遵守相关法律法规和学术诚信原则。
