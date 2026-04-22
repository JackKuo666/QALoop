#!/bin/bash

# BioBERT农业内容分类器启动脚本

echo "=== BioBERT农业内容分类器 ==="
echo "开始处理维基百科文档..."
echo

# 检查GPU状态
echo "检查GPU状态:"
nvidia-smi --query-gpu=index,name,memory.total,memory.used --format=csv,noheader,nounits
echo

# 检查模型文件
if [ ! -f "best_model.bin" ]; then
    echo "错误: best_model.bin 模型文件不存在!"
    exit 1
fi

# 数据目录（可通过环境变量配置）
DATA_DIR="${WIKI_DATA_DIR:-./data/wiki}"
if [ ! -d "$DATA_DIR" ]; then
    echo "错误: 数据目录 $DATA_DIR 不存在!"
    echo "请设置 WIKI_DATA_DIR 环境变量指向数据目录"
    exit 1
fi

# 设置参数
MODEL_PATH="best_model.bin"
OUTPUT_DIR="output"
THRESHOLD=0.6
BATCH_SIZE=2.0

echo "配置参数:"
echo "  模型文件: $MODEL_PATH"
echo "  数据目录: $DATA_DIR"
echo "  输出目录: $OUTPUT_DIR"
echo "  分类阈值: $THRESHOLD"
echo "  批处理大小: ${BATCH_SIZE}GB"
echo

# 创建输出目录
mkdir -p "$OUTPUT_DIR"

# 运行分类器
echo "开始运行分类器..."
python main_classifier.py \
    --model-path "$MODEL_PATH" \
    --data-dir "$DATA_DIR" \
    --output-dir "$OUTPUT_DIR" \
    --threshold "$THRESHOLD" \
    --batch-size "$BATCH_SIZE"

if [ $? -eq 0 ]; then
    echo
    echo "=== 分类完成! ==="
    echo "结果保存在: $OUTPUT_DIR/"
    echo "  - agricultural_content/: 农业相关文档"
    echo "  - statistics/: 统计信息"
    echo "  - processing_logs/: 处理日志"
else
    echo "分类过程中出现错误!"
    exit 1
fi
