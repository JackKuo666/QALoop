#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
章节提取脚本
调用chapter_statistics.py的处理逻辑，提取章节并输出为JSON格式
"""

import os
import re
import sys
import logging
import json
from typing import List, Dict, Optional, Any
import pandas as pd
from pathlib import Path

# 导入chapter_statistics模块
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import chapter_statistics

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# 注意：BookProcessor 和相关函数现在从 chapter_statistics 模块导入


def read_excel_paths(excel_path: str, sheet_name: str = "OCR", column_index: int = 3) -> List[str]:
    """
    从Excel文件读取指定sheet的指定列（D列，索引为3）

    Args:
        excel_path: Excel文件路径
        sheet_name: Sheet名称
        column_index: 列索引（D列为3，从0开始）

    Returns:
        路径列表
    """
    try:
        df = pd.read_excel(excel_path, sheet_name=sheet_name)
        # D列是第4列，索引为3（从0开始）
        paths = df.iloc[:, column_index].dropna().astype(str).tolist()
        # 过滤空字符串
        paths = [p.strip() for p in paths if p.strip() and p.strip().lower() != 'nan']
        return paths
    except Exception as e:
        logger.error(f"读取Excel文件失败: {e}")
        raise


def find_file_path(file_path_in_excel: str) -> Optional[str]:
    """
    根据Excel中的文件路径，找到实际文件

    例如：./data/books/OCR/Agri/20260108/9787040470406.md
    则去 ./data/books/OCR/Agri/20260108/ 下找 9787040470406.md
    """
    if not file_path_in_excel or not file_path_in_excel.strip():
        return None

    file_path_in_excel = file_path_in_excel.strip()

    # 如果路径已经是完整路径且文件存在，直接返回
    if os.path.exists(file_path_in_excel):
        return file_path_in_excel

    # 提取目录和文件名
    # 例如：./data/books/OCR/Agri/20260108/9787040470406.md
    # 目录：./data/books/OCR/Agri/20260108/
    # 文件名：9787040470406.md
    dir_path = os.path.dirname(file_path_in_excel)
    file_name = os.path.basename(file_path_in_excel)

    # 在目录下查找文件
    if dir_path and os.path.isdir(dir_path):
        full_path = os.path.join(dir_path, file_name)
        if os.path.exists(full_path):
            return full_path

    # 如果找不到，尝试直接使用原路径
    logger.warning(f"未找到文件: {file_path_in_excel}")
    return None


def process_file(file_path: str) -> List[Dict[str, Any]]:
    """
    处理单个文件，调用chapter_statistics.py的处理逻辑，返回章节信息

    Returns:
        [{'books_ID': '文件名', 'chapter_title': '章节标题', 'context': '文本内容', 'length': 长度}, ...]
    """
    file_name = os.path.basename(file_path)
    books_id = os.path.splitext(file_name)[0]  # 去掉扩展名

    try:
        # 读取文件内容
        with open(file_path, 'r', encoding='utf-8') as f:
            text = f.read()

        # 使用chapter_statistics模块中的BookProcessor拆分章节
        processor = chapter_statistics.BookProcessor()
        chapters = processor.split_by_chapters(text)

        # 构建结果列表，保持现有输出格式
        results = []
        for chapter in chapters:
            chapter_title = chapter.get('chunk_title', '未知章节')
            chapter_text = chapter.get('text', '')
            chapter_length = len(chapter_text)

            results.append({
                'books_ID': books_id,
                'chapter_title': chapter_title,
                'context': chapter_text,
                'length': chapter_length
            })

        logger.info(f"处理文件 {file_name}: 找到 {len(results)} 个章节")
        return results

    except Exception as e:
        logger.error(f"处理文件 {file_path} 时出错: {e}")
        # 即使出错，也返回一个记录
        return [{
            'books_ID': books_id,
            'chapter_title': f'错误: {str(e)[:50]}',
            'context': '',
            'length': 0
        }]


def save_to_json(results: List[Dict[str, Any]], output_file: str):
    """
    将结果保存到JSON文件，每个标题一行（JSONL格式）
    
    Args:
        results: 章节结果列表
        output_file: 输出文件路径
    """
    os.makedirs(os.path.dirname(output_file), exist_ok=True)
    
    with open(output_file, 'w', encoding='utf-8') as f:
        # 每个标题一行，使用JSON格式（JSONL格式）
        for result in results:
            # 每个标题一行，使用JSON格式
            json_line = json.dumps(result, ensure_ascii=False)
            f.write(json_line + '\n')
    
    logger.info(f"结果已保存到: {output_file} (共 {len(results)} 条记录)")


def main():
    """主函数"""
    # 输出目录
    output_dir = os.getenv("BOOKS_OUTPUT_DIR", "output/books_ChapterSection")
    
    # 获取输入文件列表
    # 方式1: 从命令行参数获取文件列表
    if len(sys.argv) > 1:
        input_files = sys.argv[1:]
    else:
        # 方式2: 直接调用 chapter_statistics.py 中的默认输入文件路径
        # 从 chapter_statistics 模块导入 DEFAULT_INPUT_FILE，实现真正的"调用"
        default_input_file = chapter_statistics.DEFAULT_INPUT_FILE
        input_files = [default_input_file]

    logger.info("=" * 60)
    logger.info("开始章节提取并输出到JSON")
    logger.info("=" * 60)
    logger.info(f"将处理 {len(input_files)} 个文件")

    # 处理每个文件
    processed_count = 0
    for input_file in input_files:
        # 检查输入文件是否存在
        if not os.path.exists(input_file):
            logger.error(f"输入文件不存在: {input_file}")
            continue

        # 根据输入文件名生成输出路径
        input_file_name = os.path.basename(input_file)
        input_file_name_without_ext = os.path.splitext(input_file_name)[0]
        output_json = os.path.join(output_dir, f"{input_file_name_without_ext}.json")

        logger.info(f"处理文件: {input_file}")
        logger.info(f"输出JSON: {output_json}")

        # 处理文件
        try:
            results = process_file(input_file)
            logger.info(f"处理完成: 共提取 {len(results)} 个章节")

            # 保存结果到JSON
            if results:
                save_to_json(results, output_json)
                processed_count += 1
            else:
                logger.warning("没有结果可保存")
        except Exception as e:
            logger.error(f"处理文件 {input_file} 失败: {e}")
            continue

    logger.info("=" * 60)
    logger.info(f"所有文件处理完成，成功处理 {processed_count}/{len(input_files)} 个文件")
    logger.info("=" * 60)


if __name__ == "__main__":
    main()
