#!/usr/bin/env python3
"""
超高精度农业分类器启动脚本
"""
import os
import sys
import argparse
from pathlib import Path

# 添加src路径
sys.path.append(os.path.join(os.path.dirname(__file__), 'src'))

from main_classifier import AgriculturalContentClassifier

def main():
    parser = argparse.ArgumentParser(description="超高精度BioBERT农业分类器")
    parser.add_argument("--model-path", default="best_model.bin", help="模型权重文件路径")
    parser.add_argument("--data-dir", default=os.getenv("WIKI_DATA_DIR", "examples"), help="数据目录")
    parser.add_argument("--output-dir", default="output", help="输出目录")
    parser.add_argument("--threshold", type=float, default=0.999, help="分类阈值")
    parser.add_argument("--batch-size", type=float, default=2.0, help="每批处理数据大小(GB)")
    parser.add_argument("--min-keyword-hits", type=int, default=2, help="最少关键词命中数")

    args = parser.parse_args()

    # 检查输入
    if not os.path.exists(args.model_path):
        print(f"错误: 模型文件 {args.model_path} 不存在")
        sys.exit(1)

    if not os.path.exists(args.data_dir):
        print(f"错误: 数据目录 {args.data_dir} 不存在")
        sys.exit(1)

    print("🎯 超高精度农业分类器启动")
    print(f"📊 阈值: {args.threshold}")
    print(f"🔑 最少关键词命中数: {args.min_keyword_hits}")
    print(f"📦 批次大小: {args.batch_size}GB")
    print()

    # 临时修改主分类器以支持新参数
    from src.models.strict_keyword_classifier import StrictKeywordAgriculturalClassifier

    # 创建分类器并运行
    try:
        classifier = AgriculturalContentClassifier(
            model_path=args.model_path,
            data_dir=args.data_dir,
            output_dir=args.output_dir,
            threshold=args.threshold,
            batch_size_gb=args.batch_size
        )

        # 手动替换为超高精度分类器
        classifier.classifier = StrictKeywordAgriculturalClassifier(
            model_path=args.model_path,
            threshold=args.threshold,
            min_keyword_hits=args.min_keyword_hits
        )

        classifier.run_classification()

    except KeyboardInterrupt:
        print("\n用户中断分类流程")
        sys.exit(1)
    except Exception as e:
        print(f"分类流程出错: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()