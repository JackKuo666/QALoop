#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
合并seed_question_RAG文件夹下的两个批次文件
"""

import os
import json
import argparse
from pathlib import Path

def merge_jsonl_files(batch1_dir: str, batch2_dir: str, output_file: str):
    """合并两个批次文件夹下的所有JSONL文件

    Args:
        batch1_dir: batch1 文件夹路径
        batch2_dir: batch2 文件夹路径
        output_file: 输出文件路径
    """
    # 创建输出目录（如果不存在）
    output_dir = os.path.dirname(output_file)
    if output_dir:
        os.makedirs(output_dir, exist_ok=True)
    
    # 获取所有JSONL文件
    batch1_files = sorted(Path(batch1_dir).glob("*.jsonl"))
    batch2_files = sorted(Path(batch2_dir).glob("*.jsonl"))
    
    print(f"找到batch1文件: {len(batch1_files)}个")
    print(f"找到batch2文件: {len(batch2_files)}个")
    
    total_count = 0
    batch1_count = 0
    batch2_count = 0
    
    # 合并文件
    with open(output_file, 'w', encoding='utf-8') as out_f:
        # 处理batch1文件
        print("\n处理batch1文件:")
        for file_path in batch1_files:
            file_count = 0
            print(f"  读取: {file_path.name}")
            with open(file_path, 'r', encoding='utf-8') as in_f:
                for line in in_f:
                    line = line.strip()
                    if line:
                        try:
                            # 验证JSON格式
                            json.loads(line)
                            out_f.write(line + '\n')
                            file_count += 1
                            total_count += 1
                            batch1_count += 1
                        except json.JSONDecodeError as e:
                            print(f"    警告: 跳过无效JSON行 - {e}")
            print(f"    → 写入 {file_count} 条记录")
        
        # 处理batch2文件
        print("\n处理batch2文件:")
        for file_path in batch2_files:
            file_count = 0
            print(f"  读取: {file_path.name}")
            with open(file_path, 'r', encoding='utf-8') as in_f:
                for line in in_f:
                    line = line.strip()
                    if line:
                        try:
                            # 验证JSON格式
                            json.loads(line)
                            out_f.write(line + '\n')
                            file_count += 1
                            total_count += 1
                            batch2_count += 1
                        except json.JSONDecodeError as e:
                            print(f"    警告: 跳过无效JSON行 - {e}")
            print(f"    → 写入 {file_count} 条记录")
    
    print(f"\n{'='*80}")
    print("合并完成!")
    print(f"{'='*80}")
    print(f"输出文件: {output_file}")
    print(f"Batch1记录数: {batch1_count}")
    print(f"Batch2记录数: {batch2_count}")
    print(f"总记录数: {total_count}")
    print(f"{'='*80}")
    
    return output_file, total_count

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="合并种子问题 JSONL 文件")
    parser.add_argument("--batch1", required=True, help="batch1 文件夹路径")
    parser.add_argument("--batch2", required=True, help="batch2 文件夹路径")
    parser.add_argument("--output", required=True, help="输出文件路径")
    args = parser.parse_args()

    merge_jsonl_files(args.batch1, args.batch2, args.output)
