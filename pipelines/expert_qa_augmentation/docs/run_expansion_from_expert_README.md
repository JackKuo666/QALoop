# run_expansion_from_expert.py 使用指南

## 脚本简介

`run_expansion_from_expert.py` 是专门处理专家问题的QA扩增脚本。它基于`专家问题_扩增CoT.xlsx`文件，按照扩展种子问题分类进行QA扩增，支持基于`domain_task_expert.xlsx`的分类映射和权重配置，具备提示词增强、种子问题深化、多分类扩增等高级功能。

## ✨ 最新更新 (2026-01-22)

### 🎯 修复内容
- ✅ **智能策略选择器**: 已修复并可用，支持专家问题的智能策略选择
- ✅ **嵌入去重器**: 默认开启，专门针对专家问题进行语义去重
- ✅ **策略平衡器**: 已修复并可用，自动平衡专家问题生成策略
- ✅ **相对路径导入**: 所有模块使用相对路径，避免导入错误
- ✅ **质量控制增强**: 改进了专家问题的质量评估机制

## 主要功能

### 🎓 专家模式特性
- **专家问题处理**: 专门处理高难度专家级别问题
- **CoT扩增**: 基于Chain-of-Thought（思维链）的扩增方法
- **提示词增强**: 将扩展分类信息添加到提示词，实现精准扩增
- **种子深化**: 保持主题一致性的深度扩增模式
- **物种一致性**: 强制扩增问题的物种与种子问题一致
- **多分类扩增**: 从多个扩展分类角度生成QA对

### 🚀 核心功能
- **智能策略选择**: 自动或手动指定生成策略 ✅
- **RAG集成**: 支持检索增强生成
- **权重配置**: 基于`generation_ratios_config.yaml`的自定义策略
- **质量控制**: 相似度阈值和难度控制
- **并行处理**: 支持异步并发处理
- **嵌入去重**: 基于语义相似度的智能去重（默认开启） ✅
- **策略平衡**: 自动平衡不同策略使用频率 ✅

## 使用方法

### 基本语法

```bash
# 从项目根目录运行
python src/runs/run_expansion_from_expert.py <Excel文件> [variants_per_seed] [选项]

# 或者使用模块方式
python -m src.runs.run_expansion_from_expert <Excel文件> [variants_per_seed] [选项]
```

### 参数说明

#### 位置参数

| 参数 | 类型 | 说明 | 默认值 |
|------|------|------|--------|
| `excel_file` | 字符串 | 专家问题Excel文件路径 | 专家问题_扩增CoT.xlsx |
| `variants_per_seed` | 整数 | 每个种子生成的变体数 | 1 |

#### 可选参数

##### 多分类扩增参数

| 参数 | 说明 | 默认值 |
|------|------|--------|
| `--variants-per-expand-class N` | 每个扩展分类生成的QA对数量 | 1 |

##### 物种一致性参数

| 参数 | 说明 | 默认值 |
|------|------|--------|
| `--enforce-species-consistency` | 强制扩增问题的物种与种子问题物种一致 | 关闭 |

##### 提示词增强参数

| 参数 | 说明 | 默认值 |
|------|------|--------|
| `--seed-deepening` | 启用种子问题深化模式，保持主题一致性 | 关闭 |
| `--no-prompt-enhancement` | 禁用提示词增强 | 启用 |

##### RAG参数

| 参数 | 说明 | 默认值 |
|------|------|--------|
| `--use-rag` | 启用RAG增强 | 关闭 |
| `--rag-url URL` | RAG服务URL | http://localhost:9487/retrieve |
| `--rag-top-k K` | RAG检索文档数量 | 5 |
| `--rag-data-source SOURCE` | RAG数据源，多个用逗号分隔 | pubmed |
| `--rag-timeout SECONDS` | RAG超时时间 | 300 |
| `--rag-enable-ratio RATIO` | RAG启用比例，0.0-1.0 | 1.0 |
| `--parallel-rag` | 启用并行模式 | 启用 |
| `--no-parallel-rag` | 禁用并行模式 | 关闭 |

##### 质量参数

| 参数 | 说明 | 默认值 |
|------|------|--------|
| `--difficulty DIFFICULTY` | QA对难度级别（easy/medium/hard） | hard |
| `--max-similarity RATIO` | 最大相似度阈值，0.0-1.0 | 0.30 |

##### 策略参数

| 参数 | 说明 |
|------|------|
| `--strategies STRATEGIES` | 指定生成策略，多个用逗号分隔 |

## 使用示例

### 1. 基本处理

```bash
# 使用默认文件（专家问题_扩增CoT.xlsx）
python src/runs/run_expansion_from_expert.py

# 指定Excel文件
python src/runs/run_expansion_from_expert.py 专家问题_扩增CoT.xlsx

# 指定每个种子生成2个变体
python src/runs/run_expansion_from_expert.py 专家问题_扩增CoT.xlsx 2
```

### 2. 启用高级功能

```bash
# 启用种子深化模式
python src/runs/run_expansion_from_expert.py \
    专家问题_扩增CoT.xlsx \
    --seed-deepening

# 启用物种一致性
python src/runs/run_expansion_from_expert.py \
    专家问题_扩增CoT.xlsx \
    --enforce-species-consistency

# 启用提示词增强
python src/runs/run_expansion_from_expert.py \
    专家问题_扩增CoT.xlsx \
    --no-prompt-enhancement
```

### 3. RAG增强

```bash
# 启用RAG增强
python src/runs/run_expansion_from_expert.py \
    专家问题_扩增CoT.xlsx \
    --use-rag

# 自定义RAG配置
python src/runs/run_expansion_from_expert.py \
    专家问题_扩增CoT.xlsx \
    --use-rag \
    --rag-url http://localhost:9487/retrieve \
    --rag-top-k 10
```

### 4. 质量控制

```bash
# 设置中等难度
python src/runs/run_expansion_from_expert.py \
    专家问题_扩增CoT.xlsx \
    --difficulty medium

# 设置相似度阈值
python src/runs/run_expansion_from_expert.py \
    专家问题_扩增CoT.xlsx \
    --max-similarity 0.50
```

### 5. 多分类扩增

```bash
# 每个扩展分类生成2个QA对
python src/runs/run_expansion_from_expert.py \
    专家问题_扩增CoT.xlsx \
    --variants-per-expand-class 2
```

### 6. 自定义策略

```bash
# 指定生成策略
python src/runs/run_expansion_from_expert.py \
    专家问题_扩增CoT.xlsx \
    --strategies PARAPHRASE,ELABORATION,COMPARATIVE_ANALYSIS
```

### 7. 完整示例

```bash
# 综合使用所有功能
python src/runs/run_expansion_from_expert.py \
    专家问题_扩增CoT.xlsx \
    2 \
    --seed-deepening \
    --enforce-species-consistency \
    --use-rag \
    --rag-url http://localhost:9487/retrieve \
    --rag-top-k 5 \
    --difficulty hard \
    --max-similarity 0.30 \
    --variants-per-expand-class 1
```

### 8. 实际项目示例

```bash
# 处理专家问题文件
python src/runs/run_expansion_from_expert.py \
    ./data/专家问题_扩增CoT.xlsx \
    2 \
    --use-rag \
    --rag-url http://localhost:9487/retrieve \
    --rag-top-k 5 \
    --difficulty hard
```

## 输入文件格式

### Excel文件结构

`专家问题_扩增CoT.xlsx`文件应包含以下列：

| 列名 | 说明 | 示例 |
|------|------|------|
| 种子问题 | 专家级别的种子问题 | "如何提高玉米的抗旱性？" |
| 答案 | 对应的问题答案 | "提高玉米抗旱性需要..." |
| 扩展分类 | 扩展分类信息 | "育种技术/分子标记" |
| 物种 | 问题的物种 | "玉米" |
| 难度 | 难度级别 | "hard" |
| 标签 | 相关标签 | ["抗旱", "分子育种"] |

### 示例数据

```excel
种子问题: "如何利用基因编辑技术改良作物抗病性？"
答案: "基因编辑技术如CRISPR/Cas9可以精准修改作物抗病基因..."
扩展分类: "生物技术/基因工程"
物种: "水稻"
难度: "hard"
标签: ["基因编辑", "抗病性", "CRISPR"]
```

## 配置文件

### generation_ratios_config.yaml

```yaml
# 专家模式配置
expert_mode:
  enable_seed_deepening: true
  enforce_species_consistency: true
  prompt_enhancement: true

# 质量控制（专家级别）
quality_control:
  min_question_length: 15
  min_answer_length: 50
  max_question_length: 500
  max_answer_length: 10000
  min_quality_score: 0.8
  max_similarity: 0.30

# 嵌入去重配置（默认开启）✅
embedding_deduplication:
  enabled: true
  similarity_threshold: 0.30
  model_name: "paraphrase-multilingual-MiniLM-L12-v2"

# 策略配置（专家问题优先使用高级策略）
generation_strategies:
  priority:
    - CAUSAL_CHAIN
    - INNOVATIVE_APPLICATION
    - COMPARATIVE_ANALYSIS
    - DISCIPLINE_CROSS
    - FUTURE_SCENARIO
```

## 输出结果

### 输出文件

脚本会在`output/`目录下创建带有时间戳的输出目录，例如：
- 输入：`data/raw/单个水稻种子问题测试.xlsx`
- 输出：`output/output_expert_expanded_20260122_143000/`

### 输出格式

生成的QA数据集为JSONL格式，每行包含一个QA对：

```json
{
  "question": "生成的问题内容",
  "answer": "生成的答案内容",
  "metadata": {
    "category": "专家问题",
    "difficulty": "hard",
    "tags": ["标签1", "标签2"],
    "generation_method": "生成策略",
    "quality_score": 0.95,
    "species": "物种",
    "subspecies": "子类别",
    "expand_class": "扩展分类",
    "seed_deepening": true,
    "species_consistency": true,
    "rag_enabled": true,
    "rag_documents": [
      {
        "title": "文档标题",
        "abstract": "文档摘要",
        "url": "文档链接"
      }
    ]
  }
}
```

## 高级功能

### 种子深化模式

启用种子深化模式后，系统会：
- 保持主题一致性
- 从多个角度深化问题
- 保持专业性和深度
- 增强专家级别的内容

### 物种一致性

启用物种一致性后：
- 强制扩增问题与种子问题物种一致
- 避免跨物种混淆
- 提高领域专业性

### 提示词增强

提示词增强功能会：
- 添加扩展分类信息到提示词
- 提供更精准的生成指导
- 提高生成质量

## 性能优化

### 并发处理

- 支持异步并发处理多个专家问题
- 可配置并发数量
- 自动负载均衡

### 内存优化

- 流式处理大文件
- 智能缓存管理
- 自动垃圾回收

### 速率限制

- API调用内置重试机制
- 可配置超时时间
- 自动错误恢复

## 监控与日志

### 日志级别

- `INFO`: 常规信息输出
- `WARNING`: 警告信息
- `ERROR`: 错误信息
- `DEBUG`: 调试信息

### 进度跟踪

脚本会显示：
- 当前处理的专家问题
- 完成的进度
- 生成统计信息
- 质量评估结果
- 智能策略选择信息
- 嵌入去重统计

### 成功日志示例

```
✅ Embedding去重器可用
✅ 策略平衡器可用
✅ 智能策略选择器可用
✅ Embedding去重: 启用
📊 专家问题处理: 10/10 (100%)
🎯 质量评估: 平均分 0.92
```

## 故障排除

### 常见问题

1. **Excel文件不存在**
   ```
   ❌ Excel文件不存在: 专家问题_扩增CoT.xlsx
   ```
   **解决方案**: 检查文件路径是否正确

2. **专家问题数据格式错误**
   ```
   ❌ 缺少必需列: 种子问题
   ```
   **解决方案**: 确保Excel文件包含所有必需列

3. **RAG服务连接失败**
   ```
   ❌ RAG服务连接失败: Connection timeout
   ```
   **解决方案**:
   - 检查RAG服务是否运行
   - 验证URL和端口
   - 调整超时时间

4. **模块导入错误** ✅ 已修复
   ```
   ❌ ModuleNotFoundError: No module named 'qa_generator_v2'
   ```
   **解决方案**: 现在使用相对路径导入，已修复此问题

5. **嵌入去重器不可用** ✅ 已修复
   ```
   ⚠️ Embedding去重器不可用，将使用字符串匹配去重
   ```
   **解决方案**: 现在默认开启嵌入去重器

### 调试技巧

1. **启用详细日志**
   ```bash
   python src/runs/run_expansion_from_expert.py \
       专家问题_扩增CoT.xlsx \
       --use-rag --verbose
   ```

2. **测试模式**
   ```bash
   # 只处理少量数据进行测试
   python src/runs/run_expansion_from_expert.py \
       专家问题_扩增CoT.xlsx \
       1 1
   ```

3. **检查Excel文件**
   ```bash
   # 使用pandas验证Excel文件
   python -c "import pandas as pd; df = pd.read_excel('专家问题_扩增CoT.xlsx'); print(df.head())"
   ```

4. **验证模块导入**
   ```bash
   # 测试模块导入
   python -c "from src.core.qa_generator_v2 import DeepSeekGenerator; print('✅ 导入成功')"
   ```

## 注意事项

1. **输入文件**: 确保Excel文件格式正确，包含所有必需列
2. **专家数据**: 专家问题应具有足够的复杂性和深度
3. **RAG服务**: 确保RAG服务正常运行
4. **API配额**: 检查API服务配额和限制
5. **系统资源**: 根据系统资源调整并发参数
6. **环境变量**: 确保`.env`文件配置正确，包含API密钥
7. **依赖安装**: 确保安装了所有必需依赖

## 相关脚本

- `run_expansion_from_dir.py`: 目录扩展脚本
- `qa_generator_v2.py`: QA生成器主文件
- `main_batch.py`: 批处理入口脚本

## 技术支持

如遇到问题，请检查：
1. Python版本（推荐3.8+）
2. 依赖包是否完整安装
3. Excel文件格式是否正确
4. 专家数据是否符合要求
5. API服务是否正常
6. 模块导入是否成功
7. 环境变量是否正确配置
