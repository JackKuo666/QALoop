# run_expansion_from_dir.py 使用指南

## 脚本简介

`run_expansion_from_dir.py` 是一个从合并的物种QA目录中批量提取种子问题并进行扩增的脚本。它支持异步并行处理多个物种，支持RAG（检索增强生成）功能，并基于`domain_task.xlsx`进行子类别映射和关键词匹配。

## ✨ 最新更新 (2026-01-22)

### 🎯 修复内容
- ✅ **智能策略选择器**: 已修复并可用，基于内容特点自动选择最佳生成策略
- ✅ **嵌入去重器**: 默认开启，基于预训练多语言模型进行语义去重
- ✅ **策略平衡器**: 已修复并可用，自动平衡不同策略使用频率
- ✅ **相对路径导入**: 所有模块使用相对路径，避免导入错误
- ✅ **输出目录**: 现在输出到 `output/` 目录下

## 主要功能

### 🚀 核心特性
- **批量处理**: 自动扫描目录下的所有JSON/JSONL文件
- **多物种并行**: 支持异步并发处理多个物种数据
- **RAG集成**: 支持检索增强生成，提高答案准确性
- **智能分类**: 基于domain_task.xlsx进行子类别映射
- **权重配置**: 支持`generation_ratios_config.yaml`自定义生成策略
- **难度控制**: 可设置生成的QA对难度级别
- **智能策略选择**: 基于内容特点自动选择最佳生成策略 ✅
- **嵌入去重**: 默认开启，基于语义相似度智能去重 ✅
- **策略平衡**: 自动平衡不同策略使用频率 ✅

### 🎯 支持的生成策略
脚本支持20+种生成策略，包括：
- PARAPHRASE (释义)
- ELABORATION (详细阐述)
- PERSPECTIVE_SHIFT (视角转换)
- MULTI_TURN (多轮对话)
- CROSS_SPECIES (跨物种迁移)
- REVERSE_REASONING (反向推理)
- INNOVATIVE_APPLICATION (创新应用)
- COMPARATIVE_ANALYSIS (对比分析)
- FUTURE_SCENARIO (未来情景)
- HYPOTHETICAL (假设性场景)
- COUNTERFACTUAL (反事实推理)
- META_QUESTION (元问题)
- TEMPORAL_SHIFT (时间维度变化)
- SPATIAL_SHIFT (空间维度变化)
- DISCIPLINE_CROSS (跨学科融合)
- SCALE_CHANGE (尺度变化)
- TIME_SERIES (时序分析)
- CAUSAL_CHAIN (因果链条)
- DIALOGUE_VARIATION (对话变体)
- SEED_DEEPENING (种子深化)

## 使用方法

### 基本语法

```bash
# 从项目根目录运行
python src/runs/run_expansion_from_dir.py <输入目录> [variants_per_seed] [max_concurrent] [选项]

# 或者使用模块方式
python -m src.runs.run_expansion_from_dir <输入目录> [variants_per_seed] [max_concurrent] [选项]
```

### 参数说明

#### 位置参数

| 参数 | 类型 | 说明 | 默认值 |
|------|------|------|--------|
| `input_dir` | 字符串 | 输入目录路径（必需） | - |
| `variants_per_seed` | 整数 | 每个种子生成的变体数 | 2 |
| `max_concurrent` | 整数 | 最大并发物种数 | 3 |

#### 可选参数

| 参数 | 说明 |
|------|------|
| `--use-rag` | 启用RAG增强 |
| `--rag-url URL` | RAG服务URL（默认：http://localhost:9487/retrieve） |
| `--rag-top-k K` | RAG检索文档数量（默认：5） |
| `--rag-data-source SOURCE` | RAG数据源，多个用逗号分隔（默认：pubmed） |
| `--rag-timeout SECONDS` | RAG超时时间（默认：300秒） |
| `--rag-enable-ratio RATIO` | RAG启用比例，0.0-1.0（默认：1.0全部启用） |
| `--parallel-rag` | 启用并行模式，RAG和QA生成同时进行（默认：启用） |
| `--no-parallel-rag` | 禁用并行模式，预先增强所有种子 |
| `--difficulty DIFFICULTY` | 生成的QA对难度级别（easy/medium/hard） |

## 使用示例

### 1. 基本批量处理

```bash
# 扫描目录下的所有JSON/JSONL文件，每个种子生成2个变体
python src/runs/run_expansion_from_dir.py data/qa/

# 指定每个种子生成3个变体，最大并发数为5
python src/runs/run_expansion_from_dir.py data/qa/ 3 5
```

### 2. 启用RAG增强

```bash
# 使用默认RAG设置
python src/runs/run_expansion_from_dir.py data/qa/ --use-rag

# 自定义RAG配置
python src/runs/run_expansion_from_dir.py data/qa/ \
    --use-rag \
    --rag-url http://localhost:9487/retrieve \
    --rag-top-k 5

# 只对30%的种子启用RAG
python src/runs/run_expansion_from_dir.py data/qa/ \
    --use-rag \
    --rag-enable-ratio 0.3

# 使用串行模式（预先增强所有种子）
python src/runs/run_expansion_from_dir.py data/qa/ \
    --use-rag \
    --no-parallel-rag
```

### 3. 难度控制

```bash
# 设置中等难度
python src/runs/run_expansion_from_dir.py data/qa/ --difficulty medium

# 设置困难难度并启用RAG
python src/runs/run_expansion_from_dir.py data/qa/ \
    --difficulty hard \
    --use-rag
```

### 4. 完整示例

```bash
# 综合使用：批量处理 + RAG增强 + 难度控制
python src/runs/run_expansion_from_dir.py data/qa/ \
    2 5 \
    --use-rag \
    --rag-url http://localhost:9487/retrieve \
    --rag-top-k 10 \
    --rag-data-source pubmed,arxiv \
    --rag-timeout 300 \
    --rag-enable-ratio 0.8 \
    --parallel-rag \
    --difficulty medium
```

### 5. 实际项目示例

```bash
# 处理QA数据，启用RAG增强
python src/runs/run_expansion_from_dir.py ./data/qa/ \
    2 3 \
    --use-rag \
    --rag-url http://localhost:9487/retrieve \
    --rag-top-k 5 \
    --rag-timeout 300 \
    --difficulty medium
```

## 配置文件

### generation_ratios_config.yaml

脚本会自动加载`generation_ratios_config.yaml`文件来控制生成权重和策略。

#### 配置文件示例

```yaml
# 物种权重配置
species_ratios:
  玉米: 1.0
  大豆: 1.0
  水稻: 1.0
  油菜: 1.0
  小麦: 1.0
  畜禽: 1.0
  合成生物技术: 1.0

# 子类别权重配置
subspecies_ratios:
  # 核心知识问答
  基础理论问答: 1.0
  物种特异性知识问答: 1.2
  生物技术与方法论: 1.0
  病虫草害与抗性机制: 1.0
  生理生化与代谢: 0.8

  # 场景化任务与指令遵循类语料
  育种方案设计与评估: 1.0
  数据分析与解读: 0.9
  操作规程与问题排查: 0.9
  文献与信息总结: 0.8
  生物信息学分析指令: 0.8
  决策支持与田间管理建议: 1.0

# 生成策略配置
generation_strategy:
  enable_ratio_filtering: true
  enable_ratio_sorting: true
  min_weight_threshold: 0.5
  max_weight_multiplier: 2.0

# 质量控制配置
quality_control:
  enable_weighted_quality: true
  high_priority_min_quality: 0.7
  low_priority_min_quality: 0.6

# 嵌入去重配置 (默认开启) ✅
embedding_deduplication:
  enabled: true
  similarity_threshold: 0.30
  model_name: "paraphrase-multilingual-MiniLM-L12-v2"
```

## 输入文件格式

### 支持的文件格式

脚本支持以下格式的文件：
- `.json` - JSON数组或单个JSON对象
- `.jsonl` - 每行一个JSON对象（推荐）

### JSONL格式示例

```json
{
  "question": "什么是光合作用？",
  "answer": "光合作用是植物利用光能将二氧化碳和水转化为有机物并释放氧气的过程。",
  "metadata": {
    "category": "基础理论问答",
    "species": "玉米",
    "difficulty": "easy",
    "tags": ["光合作用", "基础理论"]
  }
}
{
  "question": "如何提高水稻的产量？",
  "answer": "提高水稻产量需要综合考虑品种选择、合理密植、科学施肥、病虫害防治等因素。",
  "metadata": {
    "category": "育种方案设计与评估",
    "species": "水稻",
    "difficulty": "medium",
    "tags": ["水稻", "产量"]
  }
}
```

## RAG集成

### RAG检索增强

脚本支持集成RAG（检索增强生成）服务，通过检索相关文档来提高生成答案的准确性和相关性。

### RAG配置参数

| 参数 | 说明 | 默认值 |
|------|------|--------|
| `--rag-url` | RAG服务地址 | http://localhost:9487/retrieve |
| `--rag-top-k` | 检索文档数量 | 5 |
| `--rag-data-source` | 数据源列表 | ['pubmed'] |
| `--rag-timeout` | 超时时间（秒） | 300 |
| `--rag-enable-ratio` | 启用比例（0-1） | 1.0（全部） |
| `--parallel-rag` | 并行模式 | 启用 |
| `--no-parallel-rag` | 串行模式 | 禁用 |

### 并行模式 vs 串行模式

- **并行模式**（默认）：RAG检索和QA生成同时进行，性能更高，支持立即加载RAG检索结果
- **串行模式**：预先增强所有种子，然后进行RAG检索，内存占用较少

## 输出结果

### 输出文件

脚本会在`output/`目录下创建带有时间戳的输出目录，例如：
- 输入：`data/qa/`
- 输出：`output/output_全部物种_expanded_20260122_143000/`

### 输出格式

生成的QA数据集为JSONL格式，每行包含一个QA对：

```json
{
  "question": "生成的问题内容",
  "answer": "生成的答案内容",
  "metadata": {
    "category": "类别",
    "difficulty": "难度",
    "tags": ["标签1", "标签2"],
    "generation_method": "生成策略",
    "quality_score": 0.95,
    "species": "物种",
    "subspecies": "子类别",
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

## 性能优化

### 并发控制

- 通过`max_concurrent`参数控制并发物种数
- 默认并发数为3，可根据系统资源调整
- 建议：CPU核心数 × 2

### 内存优化

- 使用流式处理大文件
- 启用串行模式减少内存占用
- 及时清理缓存
- 嵌入去重器自动管理缓存大小

### 速率限制

- API调用内置重试机制
- 可配置超时时间
- 自动错误恢复

## 监控与日志

### 日志级别

- `INFO`: 常规信息输出
- `WARNING`: 警告信息
- `ERROR`: 错误信息

### 进度跟踪

脚本会显示：
- 当前处理的物种
- 完成的进度
- 生成统计信息
- 错误统计
- 智能策略选择信息
- 嵌入去重统计

### 成功日志示例

```
✅ Embedding去重器可用
✅ 策略平衡器可用
✅ 智能策略选择器可用
✅ Embedding去重: 启用
```

## 故障排除

### 常见问题

1. **目录不存在**
   ```
   ❌ 目录不存在: /path/to/input_dir
   ```
   **解决方案**: 检查输入目录路径是否正确

2. **RAG服务连接失败**
   ```
   ❌ RAG服务连接失败: Connection timeout
   ```
   **解决方案**:
   - 检查RAG服务是否运行
   - 验证URL和端口
   - 调整超时时间

3. **API调用失败**
   ```
   ❌ API调用失败: Rate limit exceeded
   ```
   **解决方案**:
   - 增加重试次数
   - 降低并发数
   - 检查API配额

4. **内存不足**
   ```
   ❌ 内存不足: OOM Error
   ```
   **解决方案**:
   - 降低并发数
   - 启用串行模式
   - 使用更小的批次

5. **模块导入错误** ✅ 已修复
   ```
   ❌ ModuleNotFoundError: No module named 'qa_generator_v2'
   ```
   **解决方案**: 现在使用相对路径导入，已修复此问题

6. **嵌入去重器不可用** ✅ 已修复
   ```
   ⚠️ Embedding去重器不可用，将使用字符串匹配去重
   ```
   **解决方案**: 现在默认开启嵌入去重器

### 调试技巧

1. **启用详细日志**
   ```bash
   python src/runs/run_expansion_from_dir.py data/qa/ --use-rag --verbose
   ```

2. **测试模式**
   ```bash
   # 只处理少量数据进行测试
   python src/runs/run_expansion_from_dir.py data/qa/ 1 1 --use-rag
   ```

3. **检查配置文件**
   ```bash
   # 验证YAML配置
   python -c "import yaml; yaml.safe_load(open('config/generation_ratios_config.yaml'))"
   ```

4. **验证模块导入**
   ```bash
   # 测试模块导入
   python -c "from src.core.qa_generator_v2 import DeepSeekGenerator; print('✅ 导入成功')"
   ```

## 注意事项

1. **输入目录**: 必须包含有效的JSON/JSONL文件
2. **配置文件**: `generation_ratios_config.yaml`为可选，建议使用
3. **RAG服务**: 确保RAG服务正常运行
4. **API配额**: 检查API服务配额和限制
5. **系统资源**: 根据系统资源调整并发参数
6. **环境变量**: 确保`.env`文件配置正确，包含API密钥
7. **依赖安装**: 确保安装了`sentence-transformers`用于嵌入去重

## 相关脚本

- `run_expansion_from_expert.py`: 专家模式扩增脚本
- `qa_generator_v2.py`: QA生成器主文件
- `main_batch.py`: 批处理入口脚本

## 技术支持

如遇到问题，请检查：
1. Python版本（推荐3.8+）
2. 依赖包是否完整安装
3. 配置文件格式是否正确
4. 输入数据是否符合要求
5. API服务是否正常
6. 模块导入是否成功
7. 环境变量是否正确配置
