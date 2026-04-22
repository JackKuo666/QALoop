#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
章节统计脚本
统计Excel文件中列出的markdown文件的章节数量和各个章节的长度
"""

import os
import re
import sys
import logging
from typing import List, Dict, Optional, Any
import pandas as pd
from pathlib import Path

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# 结束标记关键词（从参考脚本中提取）
END_SECTION_KEYWORDS = ["参考文献", "References", "REFERENCES", "附录", "Appendix", "APPENDIX"]

# 最小章节长度（从参考脚本中提取）
MIN_CHAPTER_LENGTH = 200


def clean_text_basic(text: str) -> str:
    """基础文本清理"""
    if not text:
        return ""
    # 去除多余空白
    text = re.sub(r'\s+', ' ', text)
    text = text.strip()
    return text


class BookProcessor:
    """图书处理器，从参考脚本中提取"""

    def __init__(self):
        self.chinese_patterns = [
            re.compile(r'^第[一二三四五六七八九十百千万]+章[：:：\s]*(.+)?'),
            re.compile(r'^第[0-9]+章[：:：\s]*(.+)?'),
            re.compile(r'^第[一二三四五六七八九十百千万]+节[：:：\s]*(.+)?'),
            re.compile(r'^第[0-9]+节[：:：\s]*(.+)?'),
            re.compile(r'^[一二三四五六七八九十百千万]+[、．.]\s*(.+)?'),
            re.compile(r'^[0-9]+[、．.]\s*(.+)?'),
        ]
        self.english_patterns = [
            re.compile(r'^Chapter\s+([0-9]+(?:\.[0-9]+)*)[：:：\s]*(.+)?', re.IGNORECASE),
            re.compile(r'^Chapter\s+([IVX]+)[：:：\s]*(.+)?', re.IGNORECASE),
            re.compile(r'^Section\s+([0-9]+(?:\.[0-9]+)*)[：:：\s]*(.+)?', re.IGNORECASE),
            re.compile(r'^Part\s+[0-9IVX]+[：:：\s]*(.+)?', re.IGNORECASE),
            re.compile(r'^([0-9]+(?:\.[0-9]+)*)[\.\s]+(.+)?'),
        ]
        self.markdown_header_pattern = re.compile(r'^(#{1,6})\s+(.+)$')

    def _detect_numeric_level(self, raw_title: str) -> Optional[int]:
        """检测数字层级格式的标题级别"""
        numeric_pattern = re.compile(r'^([0-9]+(?:\.[0-9]+)*)')
        match = numeric_pattern.match(raw_title.strip())
        if match:
            numeric_part = match.group(1)
            level = numeric_part.count('.') + 1
            return level
        return None

    def _clean_title_text(self, title: str, remove_numeric_prefix: bool = False) -> str:
        """清理标题文本"""
        title_clean = title.strip()
        # 去除 >> 前缀（如果存在）
        title_clean = re.sub(r'^>>\s*', '', title_clean).strip()
        if remove_numeric_prefix:
            title_clean = re.sub(r'^[0-9]+(?:\.[0-9]+)*\s+', '', title_clean).strip()
            title_clean = re.sub(r'^([0-9]+(?:\.[0-9]+)*)([^\d\s])', r'\2', title_clean).strip()
        title_clean = re.sub(r'\s+[0-9]+\s*$', '', title_clean).strip()
        title_clean = re.sub(r'[．…]+.*$', '', title_clean).strip()
        title_clean = re.sub(r'[（(]([^）)]*)[）)]', r'\1', title_clean).strip()
        title_clean = re.sub(r'\s+', ' ', title_clean).strip()
        return title_clean

    def _is_only_numbers_and_symbols(self, line_stripped: str) -> bool:
        """
        检查一行是否仅包含数字、符号等，不包含有意义的文本内容

        例如：
        - "# 73" -> True (仅包含markdown符号和数字)
        - "73" -> True (仅包含数字)
        - "第一节 标题" -> False (包含有意义的文本)
        - "# 第一节 标题" -> False (包含有意义的文本)
        - "# 8" -> True (仅包含markdown符号和数字)

        Args:
            line_stripped: 去除首尾空白的行

        Returns:
            bool: 如果仅包含数字和符号，返回True；否则返回False
        """
        if not line_stripped:
            return True  # 空行视为仅包含符号

        # 去除markdown标记（如"# "、"## "等）
        line_no_markdown = re.sub(r'^#+\s*', '', line_stripped).strip()
        if not line_no_markdown:
            return True  # 去除markdown标记后为空，视为仅包含符号

        # 去除所有空白字符
        line_no_space = re.sub(r'\s+', '', line_no_markdown)
        if not line_no_space:
            return True  # 去除空白后为空，视为仅包含符号

        # 检查是否包含中文字符或英文字母（有意义的文本）
        has_chinese = bool(re.search(r'[\u4e00-\u9fa5]', line_no_space))
        has_english = bool(re.search(r'[a-zA-Z]', line_no_space))

        # 如果包含中文字符或英文字母，肯定不是仅包含数字和符号
        if has_chinese or has_english:
            return False

        # 如果去除所有数字、标点符号、特殊符号后，没有任何字符，则认为是仅包含数字和符号
        # 允许的符号：数字、空格、常见标点符号
        text_without_symbols = re.sub(r'[0-9\s\.\,\;\:\!\?\#\-\_\(\)\[\]\{\}\.\。\，\；\：\！\？\…\·\•\•\、\．]+', '', line_no_space)

        # 如果去除数字和符号后没有任何字符，认为是仅包含数字和符号
        if not text_without_symbols or len(text_without_symbols) == 0:
            return True

        # 如果去除数字和符号后，剩余文本长度很短（<=1个字符），且原始行主要是数字和符号，也认为是仅包含数字和符号
        if len(text_without_symbols) <= 1 and len(line_no_space) > 3:
            return True

        return False

    def _check_end_section_keyword(self, line_stripped: str) -> Optional[str]:
        """检查是否遇到结束标记关键词"""
        is_title_format = (
            self.markdown_header_pattern.match(line_stripped) is not None or
            any(pattern.match(line_stripped) for pattern in self.chinese_patterns + self.english_patterns)
        )

        if not is_title_format:
            return None

        for end_keyword in END_SECTION_KEYWORDS:
            title_text = line_stripped
            header_match = self.markdown_header_pattern.match(line_stripped)
            if header_match:
                title_text = header_match.group(2).strip()
            else:
                for pattern in self.chinese_patterns + self.english_patterns:
                    match = pattern.match(line_stripped)
                    if match:
                        if len(match.groups()) > 1 and match.group(2):
                            title_text = match.group(2).strip()
                        elif len(match.groups()) > 0 and match.group(1):
                            title_text = match.group(1).strip()
                        break
                title_text = re.sub(r'^[0-9]+(?:\.[0-9]+)*\s+', '', title_text).strip()

            if end_keyword in title_text:
                return end_keyword
        return None

    def _is_in_sub_toc(self, lines: List[str], current_line_idx: int, look_back: int = 40, look_ahead: int = 40) -> bool:
        """
        检查当前位置是否在小目录区域内

        小目录的特征（基于实际文件分析）：
        1. 标题密度非常高（>70%）
        2. 连续标题很多（>=10个）
        3. 标题之间只有空行或很短的文本
        4. 小目录后面会有真正的正文标题和正文内容
        5. 正文中连续四行以上的目录格式内容才被定义为小目录

        Args:
            lines: 所有行
            current_line_idx: 当前行索引
            look_back: 向前查看的行数
            look_ahead: 向后查看的行数

        Returns:
            bool: 是否在小目录区域内
        """
        # 关键检查：如果当前行是非markdown格式的标题，且后面不远处有相同内容的markdown格式标题，则是小目录
        # 例如："实验15.1 标题"（非markdown）后面有"# 实验15.1 标题"（markdown），则"实验15.1 标题"是小目录
        current_line = lines[current_line_idx].strip()
        if current_line and not current_line.startswith('#'):
            # 当前行不是markdown格式，检查是否是标题
            current_title_info = self._extract_title_from_line(current_line)
            if current_title_info and current_title_info.get('is_title'):
                # 提取当前行的核心文本
                current_core_title = self._extract_core_title(current_line)
                # 检查后续30行内是否有相同核心文本的markdown格式标题
                for i in range(current_line_idx + 1, min(current_line_idx + 30, len(lines))):
                    next_line = lines[i].strip()
                    if not next_line:
                        continue
                    # 检查是否是markdown格式的标题
                    if next_line.startswith('#'):
                        next_title_info = self._extract_title_from_line(next_line)
                        if next_title_info and next_title_info.get('is_title'):
                            next_core_title = self._extract_core_title(next_line)
                            # 比较核心文本（去除标点符号和空格）
                            current_clean = re.sub(r'[^\u4e00-\u9fa5a-zA-Z0-9]', '', current_core_title)
                            next_clean = re.sub(r'[^\u4e00-\u9fa5a-zA-Z0-9]', '', next_core_title)
                            # 如果核心文本匹配，且markdown标题后面有正文内容，则当前行是小目录
                            if current_clean == next_clean and len(current_clean) >= 3:
                                # 检查markdown标题后面是否有正文（长文本行）
                                for j in range(i + 1, min(i + 5, len(lines))):
                                    body_line = lines[j].strip()
                                    if body_line and len(body_line) > 50:
                                        body_title_info = self._extract_title_from_line(body_line)
                                        if not body_title_info or not body_title_info.get('is_title'):
                                            # 找到正文内容，确认当前行是小目录
                                            return True

        # 首先检查：正文中连续四行以上的目录格式内容才被定义为小目录
        # 检查当前位置前后是否有连续4行以上的目录格式内容
        consecutive_title_count = 0
        max_consecutive = 0
        check_start = max(0, current_line_idx - 10)
        check_end = min(len(lines), current_line_idx + 10)

        for i in range(check_start, check_end):
            line_stripped = lines[i].strip()
            if not line_stripped:
                consecutive_title_count = 0
                continue

            # 检查是否是目录格式的标题行（标题行，且只包含标题内容）
            title_info = self._extract_title_from_line(line_stripped)
            if title_info and title_info.get('is_title'):
                if self._is_title_only_line(line_stripped, title_info):
                    consecutive_title_count += 1
                    max_consecutive = max(max_consecutive, consecutive_title_count)
                else:
                    consecutive_title_count = 0
            else:
                # 如果遇到非标题行，但行很短（可能是目录中的分隔），不算中断
                if len(line_stripped) <= 10:
                    continue
                else:
                    consecutive_title_count = 0

        # 如果连续目录格式内容少于4行，不认为是小目录
        if max_consecutive < 4:
            return False

        # 重要检查：如果当前标题后面有明显的正文内容（长文本行），不应该被判定为小目录
        # 检查后续20行内是否有长文本（>100字符的非标题行）
        has_long_text_after = False
        for i in range(current_line_idx + 1, min(current_line_idx + 20, len(lines))):
            line = lines[i].strip()
            if not line:
                continue
            if len(line) > 100:
                title_info = self._extract_title_from_line(line)
                if not title_info or not title_info.get('is_title'):
                    has_long_text_after = True
                    break
        # 如果后面有明显的正文内容，不应该被判定为小目录
        if has_long_text_after:
            return False

        # 额外检查：如果当前行是markdown格式的标题（#开头），且后面有明显的正文内容，不应该被判定为小目录
        # 这是为了处理"本章小目录"后面紧跟着正文标题的情况
        current_line = lines[current_line_idx].strip()
        if current_line.startswith('#'):
            # 检查后续10行内是否有长文本（>80字符的非标题行）
            has_text_after_markdown = False
            for i in range(current_line_idx + 1, min(current_line_idx + 10, len(lines))):
                line = lines[i].strip()
                if not line:
                    continue
                if len(line) > 80:
                    title_info = self._extract_title_from_line(line)
                    if not title_info or not title_info.get('is_title'):
                        has_text_after_markdown = True
                        break
            # 如果markdown标题后面有明显的正文内容，不应该被判定为小目录
            if has_text_after_markdown:
                return False

        # 首先检查当前行是否在目录区域内（通过检测目录区域）
        # 如果当前行在目录区域之后，且是markdown格式的章节标题，不应该被认为是小目录
        # 因为这是正文开始处的标题
        try:
            toc_start, toc_end = self._detect_toc_without_title(lines)
            if toc_start != -1 and toc_end != -1:
                # 如果当前行在目录区域之后，且是markdown格式的章节标题
                if current_line_idx > toc_end:
                    line_stripped = lines[current_line_idx].strip()
                    if line_stripped.startswith('#'):
                        title_info = self._extract_title_from_line(line_stripped)
                        if title_info and title_info.get('is_title'):
                            # 检查是否是章节标题（包含"第X章"、"第X节"等，或者是单独的标题）
                            title_clean = title_info.get('title_clean', '')
                            # 如果是"第X章"、"第X节"格式，或者是单独的标题（没有页码），很可能是正文开始
                            if re.search(r'^第[一二三四五六七八九十百千万0-9]+[章节]', title_clean):
                                # 如果前面不远处（30行内）有正文内容（长文本行，>100字符），说明这是正文标题
                                for j in range(max(0, current_line_idx - 30), current_line_idx):
                                    prev_line = lines[j].strip()
                                    if prev_line and len(prev_line) > 100:
                                        prev_title_info = self._extract_title_from_line(prev_line)
                                        if not prev_title_info or not prev_title_info.get('is_title'):
                                            # 这是正文开始处的标题，不应该被认为是小目录
                                            logger.debug(f"  _is_in_sub_toc: 行{current_line_idx+1}前面有正文内容（行{j+1}），判定为正文标题，不是小目录")
                                            return False
                                # 如果前面有"绪论"、"前言"等章节标题，说明这是正文中的章节标题，不是小目录
                                for j in range(max(0, current_line_idx - 10), current_line_idx):
                                    prev_line = lines[j].strip()
                                    if prev_line.startswith('#') and ('绪论' in prev_line or '前言' in prev_line or 'Preface' in prev_line or 'Introduction' in prev_line):
                                        return False
                            elif not re.search(r'\s+[0-9]+\s*$', line_stripped) and len(title_clean) > 2:
                                # 对于其他格式的标题，如果前面有正文内容，也不应该是小目录
                                for j in range(max(0, current_line_idx - 30), current_line_idx):
                                    prev_line = lines[j].strip()
                                    if prev_line and len(prev_line) > 100:
                                        prev_title_info = self._extract_title_from_line(prev_line)
                                        if not prev_title_info or not prev_title_info.get('is_title'):
                                            return False
        except:
            pass  # 如果检测失败，继续使用原有逻辑
        # 方法1: 检查是否包含明显的目录关键词
        sub_toc_keywords = ['## 目录', '## Contents', '## 本章目录', '## 本章内容',
                           '## 章节目录', '## 内容提要', '## 本章要点', '### 目录', '### Contents']

        # 向前查找目录关键词（最多向前30行）
        for i in range(max(0, current_line_idx - 30), current_line_idx + 1):
            line = lines[i].strip()
            for keyword in sub_toc_keywords:
                if keyword in line:
                    # 找到目录关键词，检查后续是否有连续的标题
                    title_count = 0
                    non_empty_count = 0
                    for j in range(i + 1, min(i + 40, len(lines))):
                        check_line = lines[j].strip()
                        if not check_line:
                            continue
                        non_empty_count += 1
                        title_info = self._extract_title_from_line(check_line)
                        if title_info and title_info['is_title']:
                            title_count += 1

                    # 如果标题密度超过30%，且当前行在关键词之后，认为是小目录
                    if non_empty_count > 0 and title_count / non_empty_count > 0.3:
                        if current_line_idx >= i:
                            # 进一步确认：检查后续是否有正文（超过60字符的非标题行）
                            has_body_after = False
                            for j in range(i + 1, min(i + 80, len(lines))):
                                check_line = lines[j].strip()
                                if not check_line:
                                    continue
                                if len(check_line) > 60:
                                    title_info = self._extract_title_from_line(check_line)
                                    if not title_info or not title_info['is_title']:
                                        has_body_after = True
                                        break

                            if has_body_after:
                                return True

        # 方法2: 检查标题密度（基于实际文件：标题密度>70%，连续标题>=10个）
        # 检查当前位置周围40行的标题密度
        start_idx = max(0, current_line_idx - 20)
        end_idx = min(len(lines), current_line_idx + 20)

        title_count = 0
        non_empty_count = 0
        consecutive_titles = 0
        max_consecutive = 0

        for i in range(start_idx, end_idx):
            line = lines[i].strip()
            if not line:
                continue
            non_empty_count += 1

            title_info = self._extract_title_from_line(line)
            if title_info and title_info['is_title']:
                # 只统计真正的标题行（只包含标题内容，无其他文字）
                is_title_only = self._is_title_only_line(line, title_info)
                if is_title_only:
                    title_count += 1
                    consecutive_titles += 1
                    max_consecutive = max(max_consecutive, consecutive_titles)
            else:
                consecutive_titles = 0

        # 如果标题密度很高（>60%）且连续标题很多（>=8个），可能是小目录
        if non_empty_count > 0:
            title_density = title_count / non_empty_count
            if title_density > 0.6 and max_consecutive >= 8:
                # 进一步确认：检查后续是否有正文（超过60字符的非标题行）
                has_body_after = False
                for i in range(current_line_idx + 1, min(current_line_idx + 80, len(lines))):
                    line = lines[i].strip()
                    if not line:
                        continue
                    if len(line) > 60:
                        title_info = self._extract_title_from_line(line)
                        if not title_info or not title_info['is_title']:
                            has_body_after = True
                            break

                # 如果后面有正文，且当前位置标题密度高，可能是小目录
                # 但是，如果当前标题是正文开始处的标题（前面没有很多标题），不应该认为是小目录
                # 检查前面是否有足够的标题（至少5个）来确认这是小目录区域
                titles_before = 0
                for i in range(max(0, current_line_idx - 30), current_line_idx):
                    line = lines[i].strip()
                    if not line:
                        continue
                    title_info = self._extract_title_from_line(line)
                    if title_info and title_info['is_title']:
                        is_title_only = self._is_title_only_line(line, title_info)
                        if is_title_only:
                            titles_before += 1

                # 如果前面有足够的标题（>=5个），且满足其他条件，才认为是小目录
                if has_body_after and titles_before >= 5:
                    return True

        return False

    def _extract_numeric_prefix(self, raw_title: str) -> Optional[str]:
        """提取标题中的数字前缀（如从"1.1 标题"中提取"1.1"）
        也支持中文章节标识：如"第一章"、"第一节"等
        支持实验编号格式：如"实验3-1"、"生物信息学 3-1"、"植物学 3-2"中提取"3-1"、"3-2"等
        """
        title_clean = raw_title.strip()
        title_clean = re.sub(r'^#+\s*', '', title_clean)
        title_clean = re.sub(r'^>>\s*', '', title_clean)  # 去除 >> 前缀
        title_clean = re.sub(r'^>\s*', '', title_clean)  # 去除 > 前缀

        # 先尝试提取数字前缀（如1.1, 1.1.2）
        title_no_space = re.sub(r'\s+', '', title_clean)
        numeric_pattern = re.compile(r'^([0-9]+(?:\.[0-9]+)*)')
        match = numeric_pattern.match(title_no_space)
        if match:
            return match.group(1)

        # 尝试提取纯"数字-数字"格式（如"3-1"、"4-1"等，在行首）
        # 匹配模式：行首的数字-数字格式
        dash_number_pattern = re.compile(r'^([0-9]+-[0-9]+)')
        dash_match = dash_number_pattern.match(title_clean)
        if dash_match:
            return dash_match.group(1)

        # 尝试提取通用编号格式（如"实验3-1"、"生物信息学 3-1"、"植物学 3-2"中的"3-1"、"3-2"）
        # 匹配模式：任意中文字符+可选空格+数字-数字
        # 例如：实验3-1、生物信息学 3-1、植物学 3-2
        general_number_pattern = re.compile(r'[\u4e00-\u9fa5]+\s*([0-9]+-[0-9]+)')
        gen_match = general_number_pattern.search(title_clean)
        if gen_match:
            return gen_match.group(1)

        # 尝试提取中文章节标识（如"第一章"、"第一节"、"第一周"等）
        chinese_chapter_match = re.match(r'^(第[一二三四五六七八九十百千万0-9]+[章节周])', title_clean)
        if chinese_chapter_match:
            return chinese_chapter_match.group(1)

        # 尝试提取中文序号格式（如"一、"、"二、"等）
        chinese_number_match = re.match(r'^([一二三四五六七八九十百千万]+)[、．.]', title_clean)
        if chinese_number_match:
            return chinese_number_match.group(1) + '、'

        # 尝试提取"实验X.Y"格式（如"实验5.1 标题"中的"5.1"）
        experiment_dot_match = re.match(r'^实验([0-9]+\.[0-9]+)', title_clean)
        if experiment_dot_match:
            return experiment_dot_match.group(1)  # "5.1"、"15.2"等

        # 尝试提取"实验一"、"附录一"等格式（如"实验一 标题"中的"实验一"）
        experiment_chinese_match = re.match(r'^(实验|附录)([一二三四五六七八九十百千万]+)', title_clean)
        if experiment_chinese_match:
            prefix_type = experiment_chinese_match.group(1)  # "实验"或"附录"
            chinese_number = experiment_chinese_match.group(2)  # 中文数字
            return f"{prefix_type}{chinese_number}"

        # 尝试提取"实验I-X-Y"格式（如"实验I-4-5 标题"中的"I-4-5"）
        experiment_roman_dash_match = re.match(r'^实验([IVX]+-[0-9]+-[0-9]+)', title_clean)
        if experiment_roman_dash_match:
            return experiment_roman_dash_match.group(1)  # "I-4-5"、"II-3-2"等

        # 尝试提取"项目X"格式（如"项目1 果树育苗"中的"项目1"）
        project_match = re.match(r'^项目([0-9]+)', title_clean)
        if project_match:
            return f"项目{project_match.group(1)}"

        # 尝试提取"任务X.X"格式（如"任务1.1 苗圃地的建立"中的"1.1"）
        task_match = re.match(r'^任务([0-9]+\.[0-9]+)', title_clean)
        if task_match:
            return task_match.group(1)  # "1.1"、"2.3"等

        return None

    def _extract_core_title(self, title: str) -> str:
        """
        从标题中提取核心文本部分（去除前缀、页码、省略号等）

        例如：
        - "第一章 贾昕晔" -> "贾昕晔"
        - "1.1 贾昕晔" -> "贾昕晔"
        - "第一章 贾昕晔 (123)" -> "贾昕晔"
        - "1.1 贾昕晔 ………………………………………… (123)" -> "贾昕晔"
        - "实验3-1 常用实验样品的收集制备" -> "常用实验样品的收集制备"
        - "# >>实验3-1 常用实验样品的收集制备" -> "常用实验样品的收集制备"

        Args:
            title: 原始标题

        Returns:
            核心标题文本（去除所有前缀、页码、省略号、空格等）
        """
        # 去除markdown标记和 >> 前缀以及 > 前缀
        title_clean = re.sub(r'^#+\s*', '', title.strip())
        title_clean = re.sub(r'^>>\s*', '', title_clean)
        title_clean = re.sub(r'^>\s*', '', title_clean)  # 去除 > 前缀（如">0.1 标题"）

        # 去除页码+章节编号格式（如"0011 1 "、"003 1.1.1 "等）
        # 匹配模式：数字（页码）+ 空格 + 数字或数字.数字（章节编号）+ 空格
        title_clean = re.sub(r'^[0-9]+\s+[0-9]+(?:\.[0-9]+)*\s+', '', title_clean)

        # 去除通用编号前缀（如"实验3-1 "、"生物信息学 3-1 "、"植物学 3-2 "等）
        # 匹配模式：任意中文字符+可选空格+数字-数字+空格
        title_clean = re.sub(r'^[\u4e00-\u9fa5]+\s*[0-9]+-[0-9]+\s+', '', title_clean)
        # 去除"实验I-X-Y"格式的前缀（如"实验I-4-5 "等）
        # 匹配模式：实验 + 罗马数字-数字-数字 + 空格
        title_clean = re.sub(r'^实验[IVX]+-[0-9]+-[0-9]+\s+', '', title_clean)

        # 去除"任务X.X"格式的前缀（如"任务1.1 "、"任务3.2 "等）
        # 匹配模式：任务 + 数字.数字 + 空格
        title_clean = re.sub(r'^任务[0-9]+\.[0-9]+\s+', '', title_clean)
        # 去除"项目X"格式的前缀（如"项目1 "、"项目2 "等）
        # 匹配模式：项目 + 数字 + 空格
        title_clean = re.sub(r'^项目[0-9]+\s+', '', title_clean)

        # 去除数字前缀（如"1.1 "、"1.1.1 "、"3. "等）
        # 支持"3 . "、"3. "、"3 "等格式
        title_clean = re.sub(r'^[0-9]+(?:\.[0-9]+)*\s*\.?\s+', '', title_clean)

        # 去除罗马数字前缀（如"I "、"II "、"III "等，但只匹配单独的罗马数字+空格，不匹配"I绪论"这种）
        # 匹配模式：单独的罗马数字（I, II, III, IV, V等）+ 空格 + 中文
        title_clean = re.sub(r'^([IVX]+)\s+([\u4e00-\u9fa5])', r'\2', title_clean)
        # 也处理"I绪论"这种格式（罗马数字直接连接中文，没有空格）
        title_clean = re.sub(r'^([IVX]+)([\u4e00-\u9fa5])', r'\2', title_clean)

        # 去除中文章节前缀（如"第一章 "、"第一节 "、"第一周 "等）
        # 注意：要匹配"章"、"节"和"周"
        title_clean = re.sub(r'^第[一二三四五六七八九十百千万0-9]+[章节周]\s+', '', title_clean)

        # 去除中文序号前缀（如"一、"、"二、"等）
        title_clean = re.sub(r'^[一二三四五六七八九十百千万]+[、．.]\s+', '', title_clean)

        # 去除"实验X"、"附录X"等格式的前缀（如"实验十二 "、"实验一 "、"附录一 "等）
        # 匹配模式：实验/附录 + 中文数字（一、二、三...十一、十二等）+ 空格
        # 使用循环确保去除所有重复的前缀
        while re.match(r'^(实验|附录)[一二三四五六七八九十百千万]+\s+', title_clean):
            title_clean = re.sub(r'^(实验|附录)[一二三四五六七八九十百千万]+\s+', '', title_clean)
        # 去除"实习X"、"综合实习X"等格式的前缀（如"实习一 "、"综合实习一 "等）
        # 匹配模式：实习/综合实习 + 中文数字（一、二、三...十一、十二等）+ 空格
        # 使用循环确保去除所有重复的前缀
        while re.match(r'^(实习|综合实习)[一二三四五六七八九十百千万]+\s+', title_clean):
            title_clean = re.sub(r'^(实习|综合实习)[一二三四五六七八九十百千万]+\s+', '', title_clean)
        # 去除"实验X.Y"格式的前缀（如"实验5.1 "、"实验15.2 "等）
        # 匹配模式：实验 + 数字.数字 + 空格
        title_clean = re.sub(r'^实验[0-9]+\.[0-9]+\s+', '', title_clean)
        # 去除"实验X"格式的前缀（如"实验1 "、"实验2 "、"实验 1 "等，但不包括"实验X.Y"）
        # 匹配模式：实验 + 可选空格 + 数字 + 空格（但后面不是点号）
        title_clean = re.sub(r'^实验\s*[0-9]+\s+(?!\d)', '', title_clean)

        # 去除页码（如"(123)"、"123"、"支原体58"中的"58"等）
        # 先去除括号中的页码（如"(123)"）
        title_clean = re.sub(r'\s*\([0-9]+\)\s*$', '', title_clean)
        # 去除省略号、点号等符号后的页码（如"……3"、"… 23"、"· 51"等）
        title_clean = re.sub(r'[…·•]\s*[0-9]+\s*$', '', title_clean)
        # 去除有空格分隔的页码（如" 123"、" 58"、"支原体 58"）
        title_clean = re.sub(r'\s+[0-9]+\s*$', '', title_clean)
        # 去除直接跟在中文或字母后面的页码（如"支原体58"、"梭菌纲59"中的"58"、"59"）
        # 匹配模式：中文字符或英文字母后直接跟数字（行末），保留前面的字符
        # 注意：这应该在去除空格分隔的页码之后执行
        title_clean = re.sub(r'([\u4e00-\u9fa5a-zA-Z])[0-9]+\s*$', r'\1', title_clean)

        # 去除空格后的人名、页码等内容（如" 杨洪全/593"、" 作者名"、" /123"、" 孙卫宁/059"等）
        # 匹配模式：空格 + 一个或多个短的中文姓名（2-4个字符，用空格分隔）+ " /页码"或"/页码"
        # 例如：" 杨洪全/593"、" 张三/123"、" 孙卫宁/059"、" 徐麟 黄海/041"、" 谢婉滢 李刚 彭佳师 朱永官 龚继明 /679"
        # 注意：只匹配短的中文姓名（2-4个字符），避免误删标题中的中文部分
        # 先处理多个作者的情况，支持" /页码"（空格+斜杠+页码）和"/页码"（直接斜杠+页码）两种格式
        # 匹配：一个或多个作者名（每个2-4个中文字符，用空格分隔），最后是" /页码"或"/页码"
        # 使用更灵活的模式：匹配末尾的"作者名列表 + 可选空格 + /页码"
        # 例如：" 谢婉滢 李刚 彭佳师 朱永官 龚继明 /679" 或 " 徐云远 邢立静 张景昱 种 康/659"
        title_clean = re.sub(r'\s+(?:[\u4e00-\u9fa5]{2,4}\s+){1,}[\u4e00-\u9fa5]{2,4}\s*/[0-9]+\s*$', '', title_clean)
        # 再处理单个作者的情况（如" 孙卫宁/059"）
        title_clean = re.sub(r'\s+[\u4e00-\u9fa5]{2,4}/[0-9]+\s*$', '', title_clean)
        # 处理只有作者名没有页码的情况（如" 作者名"）
        title_clean = re.sub(r'\s+[\u4e00-\u9fa5]{2,4}\s*$', '', title_clean)
        # 处理只有" /页码"的情况（如" /123"、" /679"）- 注意斜杠前可能有空格
        title_clean = re.sub(r'\s+\s*/[0-9]+\s*$', '', title_clean)
        # 处理只有"/页码"的情况（如"/123"）- 斜杠前没有空格
        title_clean = re.sub(r'\s*/[0-9]+\s*$', '', title_clean)
        # 处理只有页码的情况（如" 123"）
        title_clean = re.sub(r'\s+[0-9]+\s*$', '', title_clean)

        # 去除省略号
        title_clean = re.sub(r'…+', '', title_clean)
        title_clean = re.sub(r'\.{3,}', '', title_clean)

        # 去除多余空格
        title_clean = re.sub(r'\s+', '', title_clean)

        # 去除所有标点符号和特殊字符，只保留中文字符、英文字母和数字
        # 包括：·、•、。、，、：、；、！、？、.、,、:、;、!、?等
        title_clean = re.sub(r'[^\u4e00-\u9fa5a-zA-Z0-9]', '', title_clean)

        return title_clean

    def _is_title_only_line(self, line_stripped: str, title_info: Dict[str, Any]) -> bool:
        """
        检查该行是否只包含标题内容，无其他文字

        标题行的特征：
        1. 只包含标题文本（可能包含前缀如"# "、"3.2.2 "等）
        2. 可能包含页码（行末的数字）
        3. 可能包含省略号等格式字符
        4. 不应该包含其他描述性文字

        Args:
            line_stripped: 去除首尾空白的行
            title_info: 从该行提取的标题信息

        Returns:
            bool: 如果该行只包含标题内容，返回True；否则返回False
        """
        if not title_info or not title_info.get('is_title'):
            return False

        # 提取核心文本（去除前缀、页码等）
        core_title = self._extract_core_title(line_stripped)
        if not core_title:
            return False

        # 简化逻辑：直接使用 _extract_core_title 提取核心文本
        # 如果行的核心文本与提取的核心文本匹配，且行中没有其他描述性文字，就是标题行

        # 去除markdown标记
        line_no_markdown = re.sub(r'^#+\s*', '', line_stripped).strip()
        if not line_no_markdown:
            return False

        # 去除数字前缀（如"3.2.2 "、"1.1.1 "等）
        text_after_prefix = re.sub(r'^[0-9]+(?:\.[0-9]+)*\s+', '', line_no_markdown)

        # 去除中文章节前缀（如"第一章 "、"第一节 "等）
        text_after_chapter = re.sub(r'^第[一二三四五六七八九十百千万0-9]+[章节]\s+', '', text_after_prefix)

        # 去除"实验X"、"附录X"等格式的前缀（如"实验十二 "、"附录一 "等）
        while re.match(r'^(实验|附录)[一二三四五六七八九十百千万]+\s+', text_after_chapter):
            text_after_chapter = re.sub(r'^(实验|附录)[一二三四五六七八九十百千万]+\s+', '', text_after_chapter)

        # 去除"实习X"、"综合实习X"等格式的前缀
        while re.match(r'^(实习|综合实习)[一二三四五六七八九十百千万]+\s+', text_after_chapter):
            text_after_chapter = re.sub(r'^(实习|综合实习)[一二三四五六七八九十百千万]+\s+', '', text_after_chapter)

        # 去除通用编号前缀（如"实验3-1 "等）
        text_after_general = re.sub(r'^[\u4e00-\u9fa5]+\s*[0-9]+-[0-9]+\s+', '', text_after_chapter)
        # 去除"实验I-X-Y"格式的前缀（如"实验I-15-2 "等）
        text_after_general = re.sub(r'^实验[IVX]+-[0-9]+-[0-9]+\s+', '', text_after_general)
        # 去除"实验X"格式的前缀（如"实验1 "、"实验 2 "等，X是数字）
        # 支持"实验1"和"实验 1"两种格式
        text_after_general = re.sub(r'^实验\s*[0-9]+\s+', '', text_after_general)

        # 去除页码（行末的数字，如" 56"）
        text_after_page = re.sub(r'\s+[0-9]+\s*$', '', text_after_general)

        # 去除省略号等格式字符
        text_after_format = re.sub(r'[．…\.]{2,}', '', text_after_page)
        text_after_format = re.sub(r'[·•]', '', text_after_format)

        # 去除所有空格和标点符号，只保留字符
        text_clean = re.sub(r'\s+', '', text_after_format)
        text_clean = re.sub(r'[^\u4e00-\u9fa5a-zA-Z0-9]', '', text_clean)

        # core_title 已经通过 _extract_core_title 去除了所有标点符号
        core_title_clean = core_title  # _extract_core_title 已经去除了所有标点符号

        # 如果清理后的文本完全等于核心标题文本，肯定是标题行
        if text_clean == core_title_clean:
            return True

        # 如果核心标题文本在清理后的文本中，且占比足够高
        if core_title_clean and text_clean and core_title_clean in text_clean:
            title_ratio = len(core_title_clean) / len(text_clean) if text_clean else 0
            if title_ratio >= 0.7:
                return True

        # 对于markdown标题，如果整行匹配标题模式，进一步检查
        if title_info.get('is_markdown'):
            markdown_pattern = r'^#+\s+.+$'
            if re.match(markdown_pattern, line_stripped):
                # 去除markdown标记和可能的页码后，检查是否只包含标题文本
                title_without_markdown = re.sub(r'^#+\s+', '', line_stripped).strip()
                title_without_page = re.sub(r'\s+[0-9]+\s*$', '', title_without_markdown)
                title_without_page_clean = re.sub(r'\s+', '', title_without_page)
                title_without_page_clean = re.sub(r'[^\u4e00-\u9fa5a-zA-Z0-9]', '', title_without_page_clean)

                if core_title_clean and title_without_page_clean:
                    if core_title_clean in title_without_page_clean:
                        ratio = len(core_title_clean) / len(title_without_page_clean) if title_without_page_clean else 0
                        if ratio >= 0.7:
                            return True

        return False

    def _extract_title_from_line(self, line_stripped: str) -> Optional[Dict[str, Any]]:
        """从一行文本中提取标题信息"""
        if not line_stripped:
            return None

        # 检查markdown标题
        header_match = self.markdown_header_pattern.match(line_stripped)
        if header_match:
            title = header_match.group(2).strip()
            # 对于markdown标题，先清理标题文本（去除页码等），但保留前缀
            # 前缀会在 _extract_core_title 中去除
            title_clean = self._clean_title_text(title, remove_numeric_prefix=False)
            line_numeric = self._extract_numeric_prefix(line_stripped)
            level = len(header_match.group(1))
            return {
                'is_title': True,
                'title_clean': title_clean,
                'line_numeric': line_numeric,
                'level': level,
                'is_markdown': True
            }

        # 检查以">"开头的数字前缀格式（如">0.1 标题"、">1.1 标题"等）
        quote_numeric_match = re.match(r'^>\s*([0-9]+(?:\.[0-9]+)*)\s+(.+)$', line_stripped)
        if quote_numeric_match:
            numeric_prefix = quote_numeric_match.group(1)
            title = quote_numeric_match.group(2).strip()
            title_clean = self._clean_title_text(title, remove_numeric_prefix=False)
            numeric_level = self._detect_numeric_level(line_stripped)
            level = numeric_level if numeric_level is not None else 2
            return {
                'is_title': True,
                'title_clean': title_clean,
                'line_numeric': numeric_prefix,
                'level': level,
                'is_markdown': False
            }

        # 检查纯数字前缀格式（支持"3 . 标题"和"3. 标题"格式）
        # 匹配模式：数字 + 可选空格 + 可选点号 + 空格 + 标题
        numeric_prefix_match = re.match(r'^([0-9]+(?:\.[0-9]+)*)\s*\.?\s+(.+)$', line_stripped)
        if numeric_prefix_match:
            numeric_prefix = numeric_prefix_match.group(1)
            title = numeric_prefix_match.group(2).strip()
            # 去除标题开头的点号和空格
            title = re.sub(r'^\.\s*', '', title).strip()
            title_clean = self._clean_title_text(title, remove_numeric_prefix=False)
            numeric_level = self._detect_numeric_level(line_stripped)
            level = numeric_level if numeric_level is not None else 2
            return {
                'is_title': True,
                'title_clean': title_clean,
                'line_numeric': numeric_prefix,
                'level': level,
                'is_markdown': False
            }

        # 检查"实验X.Y"格式（如"实验5.1 标题"、"实验15.2 标题"等）
        # 匹配模式：实验 + 数字.数字 + 空格 + 标题 + 可选页码
        experiment_dot_match = re.match(r'^(实验)([0-9]+\.[0-9]+)\s+(.+?)(?:\s+[0-9]+)?\s*$', line_stripped)
        if experiment_dot_match:
            prefix_type = experiment_dot_match.group(1)  # "实验"
            numeric_prefix = experiment_dot_match.group(2)  # "5.1"、"15.2"等
            title = experiment_dot_match.group(3).strip()  # 标题文本
            title_clean = self._clean_title_text(title, remove_numeric_prefix=False)
            # 保留完整标题格式：实验5.1 标题
            full_title = f"{prefix_type}{numeric_prefix} {title_clean}".strip()
            # 检测层级：根据数字前缀的层级（如5.1是2级，5.1.1是3级）
            numeric_level = self._detect_numeric_level(f"{numeric_prefix} {title}")
            level = numeric_level if numeric_level is not None else 3
            return {
                'is_title': True,
                'title_clean': full_title,
                'line_numeric': numeric_prefix,
                'level': level,
                'is_markdown': False
            }

        # 检查"实验一"、"实验二"、"附录一"、"附录二"等格式（如"实验一 植物组织培养MS培养基的配制 3"）
        # 匹配模式：实验/附录 + 中文数字（一、二、三...十一、十二等）+ 空格 + 标题 + 可选页码
        experiment_chinese_match = re.match(r'^(实验|附录)([一二三四五六七八九十百千万]+)\s+(.+?)(?:\s+[0-9]+)?\s*$', line_stripped)
        if experiment_chinese_match:
            prefix_type = experiment_chinese_match.group(1)  # "实验"或"附录"
            chinese_number = experiment_chinese_match.group(2)  # 中文数字
            title = experiment_chinese_match.group(3).strip()  # 标题文本
            title_clean = self._clean_title_text(title, remove_numeric_prefix=False)
            # 保留完整标题格式：实验一 标题 或 附录一 标题
            full_title = f"{prefix_type}{chinese_number} {title_clean}".strip()
            # 作为前缀保存：实验一、附录一等
            numeric_prefix = f"{prefix_type}{chinese_number}"
            # "实验X"格式通常作为2级标题，"附录X"格式也作为2级标题
            level = 2
            return {
                'is_title': True,
                'title_clean': full_title,
                'line_numeric': numeric_prefix,
                'level': level,
                'is_markdown': False
            }

        # 检查"实验I-X-Y"格式（如"实验I-4-5 霉菌子囊壳、子囊和子囊孢子的观察 62"等）
        # 匹配模式：实验 + 罗马数字-数字-数字 + 空格 + 标题 + 可选页码
        experiment_roman_dash_match = re.match(r'^实验([IVX]+-[0-9]+-[0-9]+)\s+(.+?)(?:\s+[0-9]+)?\s*$', line_stripped)
        if experiment_roman_dash_match:
            numeric_prefix = experiment_roman_dash_match.group(1)  # "I-4-5"、"II-3-2"等
            title = experiment_roman_dash_match.group(2).strip()  # 标题文本
            title_clean = self._clean_title_text(title, remove_numeric_prefix=False)
            # 保留完整标题格式：实验I-4-5 标题
            full_title = f"实验{numeric_prefix} {title_clean}".strip()
            # "实验I-X-Y"格式通常作为3级标题
            level = 3
            return {
                'is_title': True,
                'title_clean': full_title,
                'line_numeric': numeric_prefix,
                'level': level,
                'is_markdown': False
            }

        # 检查"任务X.X"格式（如"任务1.1 苗圃地的建立"、"任务2.3 标题"等）
        # 匹配模式：任务 + 数字.数字 + 空格 + 标题 + 可选页码
        task_match = re.match(r'^任务([0-9]+\.[0-9]+)\s+(.+?)(?:\s+[0-9]+)?\s*$', line_stripped)
        if task_match:
            numeric_prefix = task_match.group(1)  # "1.1"、"2.3"等
            title = task_match.group(2).strip()  # 标题文本
            title_clean = self._clean_title_text(title, remove_numeric_prefix=False)
            # 保留完整标题格式：任务1.1 标题
            full_title = f"任务{numeric_prefix} {title_clean}".strip()
            # 检测层级：根据数字前缀的层级（如1.1是2级）
            numeric_level = self._detect_numeric_level(f"{numeric_prefix} {title}")
            level = numeric_level if numeric_level is not None else 2
            return {
                'is_title': True,
                'title_clean': full_title,
                'line_numeric': numeric_prefix,
                'level': level,
                'is_markdown': False
            }

        # 检查通用编号格式（如"实验3-1"、"生物信息学 3-1"、"植物学 3-2"等）
        # 匹配模式：任意中文字符+可选空格+数字-数字+空格+标题
        general_number_match = re.match(r'^([\u4e00-\u9fa5]+)\s*([0-9]+-[0-9]+)\s+(.+)$', line_stripped)
        if general_number_match:
            subject_name = general_number_match.group(1)  # 学科名
            numeric_prefix = general_number_match.group(2)  # 编号
            title = general_number_match.group(3).strip()  # 标题文本
            title_clean = self._clean_title_text(title, remove_numeric_prefix=False)
            # 通用编号格式通常作为3级标题
            level = 3
            # 保留完整标题格式：学科名编号 标题
            full_title = f"{subject_name}{numeric_prefix} {title_clean}".strip()
            return {
                'is_title': True,
                'title_clean': full_title,
                'line_numeric': numeric_prefix,
                'level': level,
                'is_markdown': False
            }

        # 检查章节标题模式
        for pattern in self.chinese_patterns + self.english_patterns:
            match = pattern.match(line_stripped)
            if match:
                if len(match.groups()) > 1 and match.group(2):
                    title = match.group(2).strip()
                elif len(match.groups()) > 0 and match.group(1):
                    title = match.group(1).strip()
                else:
                    title = line_stripped

                if not title:
                    title = line_stripped

                title_clean = self._clean_title_text(title)
                line_numeric = self._extract_numeric_prefix(line_stripped)

                numeric_level = self._detect_numeric_level(line_stripped)
                if numeric_level is not None:
                    level = numeric_level
                elif '节' in line_stripped:
                    level = 2
                elif '章' in line_stripped:
                    level = 1
                else:
                    level = 2

                return {
                    'is_title': True,
                    'title_clean': title_clean,
                    'line_numeric': line_numeric,
                    'level': level,
                    'is_markdown': False
                }

        return None

    def _split_from_body(self, lines: List[str], search_start: int) -> List[Dict[str, str]]:
        """从正文中直接提取章节"""
        logger.info("从正文中搜索章节标题")
        headers = []

        for i in range(search_start, len(lines)):
            line_stripped = lines[i].strip()
            if not line_stripped:
                continue

            title_info = self._extract_title_from_line(line_stripped)
            if title_info and title_info['is_title']:
                title_clean = title_info['title_clean']
                if title_clean.strip() in ["目录", "Contents", "CONTENTS", "目  录", "目　录", "目 录"]:
                    continue

                headers.append({
                    'line_num': i,
                    'level': title_info['level'],
                    'title': title_clean,
                    'raw_title': line_stripped,
                    'numeric_prefix': title_info['line_numeric'],
                    'is_markdown': title_info['is_markdown']
                })

        if not headers:
            logger.warning("正文中未找到任何章节标题，使用回退策略")
            return self._fallback_split('\n'.join(lines[search_start:]))

        final_chunks = []
        global_counter = 1

        for idx, header in enumerate(headers):
            start_line = header['line_num']
            end_line = len(lines)

            if idx + 1 < len(headers):
                end_line = headers[idx + 1]['line_num']

            if end_line <= start_line:
                continue

            if start_line + 1 >= len(lines):
                continue

            section_lines = lines[start_line + 1:end_line]
            section_content = '\n'.join(section_lines)
            section_content = clean_text_basic(section_content)

            # 不再过滤短章节，提取所有章节

            chunk_id = f"chunk_{idx+1:03d}_{global_counter:03d}"
            chunk_title = header['title']

            final_chunks.append({
                'chunk_id': chunk_id,
                'chunk_title': chunk_title,
                'text': section_content,
                'level': header['level'],
                'parent_title': None
            })
            global_counter += 1

        logger.info(f"从正文中提取到 {len(final_chunks)} 个章节")
        return final_chunks

    def _fallback_split(self, text: str) -> List[Dict[str, str]]:
        """回退策略：如果无法识别章节，将整个文本作为一个章节"""
        text_clean = clean_text_basic(text)
        # 不再过滤短文本，返回所有内容
        return [{
            'chunk_id': 'chunk_001_001',
            'chunk_title': '全文',
            'text': text_clean,
            'level': 1,
            'parent_title': None
        }]

    def _detect_toc_without_title(self, lines: List[str], start_search: int = 0, max_search: int = 500) -> tuple[int, int]:
        """
        检测没有"目录"标题的目录区域

        目录特征：
        1. 高密度的标题行（连续多行都是标题格式）
        2. 标题行后面通常有页码（数字）
        3. 目录区域结束后，会有明显的正文开始标志

        Args:
            lines: 所有行
            start_search: 开始搜索的行号
            max_search: 最大搜索行数（避免搜索整个文件）

        Returns:
            (toc_start, toc_end): 目录开始和结束行号，如果未找到返回(-1, -1)
        """
        # 目录结束标志
        toc_end_keywords = ['中英文名词对照索引', '参考文献', '主要参考文献', 'References', 'REFERENCES',
                           '附录', 'Appendix', 'APPENDIX', '索引', 'Index']

        # 从start_search开始，最多搜索max_search行
        search_end = min(start_search + max_search, len(lines))

        # 查找第一个标题行作为目录开始候选
        toc_start_candidate = -1
        for i in range(start_search, search_end):
            line_stripped = lines[i].strip()
            if not line_stripped:
                continue

            # 检查是否是标题（markdown标题或章节标题）
            title_info = self._extract_title_from_line(line_stripped)
            if title_info and title_info['is_title']:
                # 跳过明显的非目录标题（如"前言"、"序"、"内容简介"等，但保留"第一篇"、"第X章"、"第一部分"等）
                title_clean = title_info['title_clean']
                # 跳过明显的非目录标题
                skip_keywords = ['前言', '序', '内容简介', '图书在版编目', '数字课程', '编委会']
                should_skip = False
                for keyword in skip_keywords:
                    if keyword in title_clean or keyword in line_stripped:
                        should_skip = True
                        break
                if should_skip:
                    continue

                # 如果是"第X篇"、"第X章"、"第一部分"、"第二部分"等格式，很可能是目录开始
                if re.search(r'^第[一二三四五六七八九十百千万0-9]+[篇章]', line_stripped) or \
                   re.search(r'^#\s*第[一二三四五六七八九十百千万0-9]+[篇章]', line_stripped) or \
                   re.search(r'^第[一二三四五六七八九十百千万0-9]+部分', line_stripped) or \
                   re.search(r'^#\s*第[一二三四五六七八九十百千万0-9]+部分', line_stripped):
                    toc_start_candidate = i
                    break
                # 如果是"绪论"、"Introduction"等常见章节标题，且是markdown格式，也可能是目录开始
                if line_stripped.startswith('#') and ('绪论' in title_clean or 'Introduction' in title_clean):
                    # 检查后续是否有高密度的标题（目录特征）
                    # 先记录为候选，继续检查后续行的标题密度
                    if toc_start_candidate == -1:
                        toc_start_candidate = i
                # 或者如果标题密度足够高，也可能是目录
                # 先记录，继续检查后续行的标题密度
                elif toc_start_candidate == -1:
                    toc_start_candidate = i

        if toc_start_candidate == -1:
            return (-1, -1)

        # 从候选开始位置，检查后续区域的标题密度
        window_size = 600  # 检查窗口大小（扩大以覆盖更多目录内容，支持长目录）
        min_title_density = 0.15  # 最小标题密度（15%，降低要求以适配更多格式）
        min_toc_length = 5  # 最小目录长度（行数，降低要求）

        # 统计从候选位置开始的标题密度
        title_count = 0
        total_non_empty = 0
        page_number_count = 0
        markdown_title_count = 0  # markdown格式标题数量

        window_end = min(toc_start_candidate + window_size, search_end)
        for i in range(toc_start_candidate, window_end):
            line_stripped = lines[i].strip()
            if not line_stripped:
                continue

            total_non_empty += 1

            # 检查是否是标题
            title_info = self._extract_title_from_line(line_stripped)
            if title_info and title_info['is_title']:
                title_count += 1
                # 检查是否是markdown格式标题
                if line_stripped.startswith('#'):
                    markdown_title_count += 1
                # 检查是否有页码（行末的数字）
                if re.search(r'\s+[0-9]+\s*$', line_stripped):
                    page_number_count += 1

        # 如果标题密度不够，不是目录
        if total_non_empty == 0 or title_count < min_toc_length:
            return (-1, -1)

        title_density = title_count / total_non_empty
        # 如果标题密度足够高，或者有足够多的markdown标题和页码，认为是目录
        if title_density >= min_title_density:
            # 标题密度足够，认为是目录
            pass
        elif markdown_title_count >= 5 and page_number_count >= 3:
            # 即使标题密度不够，如果有足够多的markdown标题和页码，也认为是目录
            pass
        else:
            return (-1, -1)

        # 找到目录开始位置（第一个标题行）
        toc_start = toc_start_candidate

        # 查找目录结束位置
        toc_end = -1
        # 从窗口结束位置继续向后查找
        # 优先查找markdown格式的结束标志（如"# 参考文献"）
        for i in range(window_end, min(window_end + 300, len(lines))):
            line_stripped = lines[i].strip()
            if not line_stripped:
                continue

            # 优先检查markdown格式的结束标志（如"# 参考文献"）
            if line_stripped.startswith('#'):
                for end_keyword in toc_end_keywords:
                    if end_keyword in line_stripped:
                        # 确认这是markdown标题格式的结束标志
                        toc_end = i
                        break
                if toc_end != -1:
                    break

            # 检查是否遇到目录结束标志（非markdown格式）
            if toc_end == -1:
                for end_keyword in toc_end_keywords:
                    if end_keyword in line_stripped:
                        # 但需要确保不在目录开始之前（避免匹配到前言中的"参考文献"）
                        # 对于"主要参考文献"等，即使不是markdown格式，也应该识别
                        if i > toc_start + 50:  # 确保在目录区域内
                            toc_end = i
                            break

            if toc_end != -1:
                break

            # 检查是否遇到正文开始标志
            # 1. 检查是否是markdown格式的章节标题（如"# 第一章"、"# 植物生产与环境"）
            # 如果遇到这种标题，且前面有足够的目录内容，说明目录已经结束
            if line_stripped.startswith('#'):
                title_info = self._extract_title_from_line(line_stripped)
                if title_info and title_info.get('is_title'):
                    # 检查是否是章节标题（包含"第X章"、"第X节"等，或者是单独的标题）
                    title_clean = title_info.get('title_clean', '')
                    # 如果是"第X章"格式，或者是单独的标题（没有页码），很可能是正文开始
                    if re.search(r'^第[一二三四五六七八九十百千万0-9]+[章节]', title_clean) or \
                       (not re.search(r'\s+[0-9]+\s*$', line_stripped) and i > toc_start + min_toc_length):
                        # 检查前面是否有足够的目录内容
                        # 如果当前标题前面有足够的目录行，且当前标题不在目录区域内，说明目录已结束
                        # 目录结束位置应该在当前标题之前
                        if i > toc_start + min_toc_length:
                            # 向前查找最后一个目录行（通常是有页码的标题行）
                            for j in range(i - 1, max(toc_start, i - 50), -1):
                                prev_line = lines[j].strip()
                                if not prev_line:
                                    continue
                                # 如果找到有页码的标题行，或者找到明显的目录结束标志
                                if re.search(r'\s+[0-9]+\s*$', prev_line):
                                    toc_end = j + 1  # 目录结束在最后一个有页码的行之后
                                    break
                            if toc_end == -1:
                                toc_end = i  # 如果没找到，目录结束在当前标题之前
                            break

            # 2. 检查是否遇到大段正文（非标题的长行，且不是图片）
            if len(line_stripped) > 100 and not line_stripped.startswith('!['):
                title_info = self._extract_title_from_line(line_stripped)
                if not title_info or not title_info['is_title']:
                    # 找到正文开始，目录结束在当前行之前
                    # 但需要确认前面确实有足够的标题
                    if i > toc_start + min_toc_length:
                        toc_end = i
                        break

        if toc_end == -1:
            # 如果没找到明确的结束标志，使用窗口结束位置
            toc_end = window_end

        return (toc_start, toc_end)

    def split_by_chapters(self, text: str) -> List[Dict[str, str]]:
        """拆分章节（从参考脚本中提取的核心方法）"""
        lines = text.split("\n")

        # 1. 提取目录信息（更精确地匹配）
        toc_keywords = ['目录', 'Contents', 'CONTENTS', '目  录', '目　录', '目 录', '日录']
        toc_start = -1
        toc_end = -1

        def is_toc_title(text: str) -> bool:
            """检查文本是否为目录标题（支持各种空格变体和错别字）"""
            if not text:
                return False
            # 去除所有空格后比较
            text_no_space = re.sub(r'\s+', '', text)
            toc_keywords_no_space = [re.sub(r'\s+', '', kw) for kw in toc_keywords]
            return text_no_space in toc_keywords_no_space or text_no_space == '目录' or text_no_space == '日录'

        for i, line in enumerate(lines):
            line_stripped = line.strip()
            if toc_start == -1:
                # 优先匹配精确的"# 目录"格式
                header_match = self.markdown_header_pattern.match(line_stripped)
                if header_match:
                    title = header_match.group(2).strip()
                    # 使用灵活匹配：支持各种空格变体
                    if is_toc_title(title):
                        toc_start = i
                        # 不要break，继续检查目录结束
                # 如果没有markdown格式，检查是否是单独的"目录"行
                elif is_toc_title(line_stripped):
                    toc_start = i
                    # 不要break，继续检查目录结束
            elif toc_end == -1:
                # 目录结束判断：查找目录中的最后一个标题行
                # 当遇到标题行后，检查后续是否有大段正文，如果有则目录结束
                title_info = self._extract_title_from_line(line_stripped)
                if title_info and title_info['is_title']:
                    title_clean = title_info['title_clean']
                    # 跳过目录标题本身
                    if title_clean.strip() in toc_keywords or title_clean.strip() == '日录':
                        continue

                    # 检查是否遇到明确的目录结束标志（如"附录"、"参考文献"等）
                    toc_end_keywords = ['附录', 'Appendix', 'APPENDIX', '参考文献', 'References', 'REFERENCES']
                    for end_keyword in toc_end_keywords:
                        if end_keyword in title_clean:
                            # 检查后续是否还有目录内容（标题行），如果没有则目录结束
                            has_more_toc = False
                            for j in range(i + 1, min(i + 50, len(lines))):
                                next_line = lines[j].strip()
                                if not next_line:
                                    continue
                                next_title_info = self._extract_title_from_line(next_line)
                                if next_title_info and next_title_info.get('is_title'):
                                    # 检查是否是章节级别的标题（如"第X章"、"实验X"等）
                                    next_title = next_title_info.get('title_clean', '')
                                    # 也检查"实验X"格式（X是数字），这些可能是正文标题
                                    if (re.search(r'^第[0-9一二三四五六七八九十]+章', next_title) or
                                        re.search(r'^实验[一二三四五六七八九十]+', next_title) or
                                        re.search(r'^实验[0-9]+', next_title) or  # 添加对"实验1"、"实验2"等格式的检查
                                        re.search(r'^实习[一二三四五六七八九十]+', next_title) or
                                        re.search(r'^综合实习[一二三四五六七八九十]+', next_title)):
                                        # 如果后续有markdown格式的"实验X"标题，且后面有正文，则可能是正文标题，目录应该结束
                                        if next_line.startswith('#') and re.search(r'^#\s*实验[0-9]+', next_line):
                                            # 检查markdown标题后面是否有正文（长文本行）
                                            for k in range(j + 1, min(j + 5, len(lines))):
                                                body_line = lines[k].strip()
                                                if body_line and len(body_line) > 100:
                                                    # 有正文，说明这是正文标题，目录应该结束
                                                    has_more_toc = False
                                                    break
                                            if not has_more_toc:
                                                break
                                        else:
                                            # 如果后续有"实验X"格式的标题，但不是markdown格式，或者没有正文，继续检查
                                            has_more_toc = True
                                        if has_more_toc:
                                            break
                            if not has_more_toc:
                                toc_end = i + 1
                                break

                    # 如果还没找到结束位置，检查后续是否有大段正文（非标题行）
                    if toc_end == -1:
                        # 跳过目录中的章节标题（如"# 上篇"、"# 下篇"等），这些不是目录结束标志
                        if re.search(r'^(上篇|下篇|上编|下编|第一部分|第二部分|第三部分)', title_clean):
                            continue  # 跳过这些章节标题，继续查找

                        # 需要跳过可能的子标题（如"一、"、"二、"等三级标题）
                        look_ahead = 30  # 扩大搜索范围，确保能跳过三级标题
                        has_body = False
                        consecutive_titles = 0  # 连续标题计数
                        for j in range(i + 1, min(i + 1 + look_ahead, len(lines))):
                            if j < len(lines):
                                next_line = lines[j].strip()
                                if not next_line:
                                    continue
                                # 检查是否是标题（包括三级标题）
                                next_title_info = self._extract_title_from_line(next_line)
                                if next_title_info and next_title_info.get('is_title'):
                                    consecutive_titles += 1
                                    # 检查是否是目录中的章节标题（如"# 上篇"、"# 下篇"等）
                                    next_title_clean = next_title_info.get('title_clean', '')
                                    if re.search(r'^(上篇|下篇|上编|下编|第一部分|第二部分|第三部分)', next_title_clean):
                                        consecutive_titles += 1  # 这些也是标题，继续计数
                                    continue  # 如果是标题，继续查找
                                # 如果遇到非标题的长行（>150字符），且前面没有足够的标题，说明是正文
                                if len(next_line) > 150:
                                    # 需要确保不是连续的标题（至少跳过5个可能的子标题）
                                    if consecutive_titles < 5:
                                        has_body = True
                                        break

                        if has_body:
                            # 找到正文开始，目录结束在当前标题行之后
                            # 但要确保包含所有子标题，所以结束位置要向后移动
                            toc_end = i + 1 + consecutive_titles
                            break

        # 如果找到了目录开始但没有找到结束，尝试查找目录结束标志
        if toc_start != -1 and toc_end == -1:
            # 从目录开始位置向后查找，寻找目录结束标志
            # 目录结束标志：遇到"参考文献"、"附录"等，或者遇到大段正文
            for i in range(toc_start + 1, min(toc_start + 1000, len(lines))):
                line_stripped = lines[i].strip()
                if not line_stripped:
                    continue
                # 检查是否是目录结束标志
                toc_end_keywords = ['附录', 'Appendix', 'APPENDIX', '参考文献', 'References', 'REFERENCES']
                for end_keyword in toc_end_keywords:
                    if end_keyword in line_stripped:
                        # 检查后续是否有markdown格式的"实验X"标题（可能是正文标题）
                        # 如果后续有"# 实验X"格式的标题，且后面有正文，目录应该在"参考文献"行结束
                        has_experiment_title_after = False
                        for j in range(i + 1, min(i + 10, len(lines))):
                            next_line = lines[j].strip()
                            if next_line.startswith('#') and re.search(r'^#\s*实验[0-9]+', next_line):
                                # 检查markdown标题后面是否有正文（长文本行）
                                for k in range(j + 1, min(j + 5, len(lines))):
                                    body_line = lines[k].strip()
                                    if body_line and len(body_line) > 100:
                                        # 有正文，说明这是正文标题，目录应该在"参考文献"行结束
                                        has_experiment_title_after = True
                                        break
                                if has_experiment_title_after:
                                    break
                        # 如果后续有正文标题，目录在"参考文献"行结束；否则在markdown格式的结束标志行结束
                        if has_experiment_title_after:
                            toc_end = i + 1  # 目录在"参考文献"行之后结束
                        elif line_stripped.startswith('#'):
                            toc_end = i
                        else:
                            toc_end = i + 1  # 非markdown格式的"参考文献"行，目录在该行之后结束
                        break
                if toc_end != -1:
                    break
                # 检查是否遇到大段正文（非标题的长行，且不是图片）
                if len(line_stripped) > 200 and not line_stripped.startswith('!['):
                    title_info = self._extract_title_from_line(line_stripped)
                    if not title_info or not title_info['is_title']:
                        # 找到正文开始，目录结束在当前行之前
                        # 但需要确认前面确实有足够的目录内容
                        if i > toc_start + 50:  # 确保有足够的目录内容
                            # 向前查找最后一个目录行（通常是有页码的标题行）
                            for j in range(i - 1, max(toc_start, i - 100), -1):
                                prev_line = lines[j].strip()
                                if not prev_line:
                                    continue
                                # 如果找到有页码的标题行，目录结束在该行之后
                                if re.search(r'\s+[0-9]+\s*$', prev_line):
                                    toc_end = j + 1
                                    break
                            if toc_end == -1:
                                toc_end = i
                            break

        # 如果没有找到带"目录"标题的目录，检查是否是无目录书籍
        # 对于无目录书籍，应该直接按照与"绪论"同级别的正文标题进行提取
        if toc_start == -1 or toc_end == -1:
            # 检查文件开头是否有"绪论"或"第一篇"等章节标题（说明是无目录书籍）
            has_chapter_titles_at_start = False
            for i in range(min(100, len(lines))):  # 检查前100行
                line_stripped = lines[i].strip()
                if line_stripped.startswith('# '):
                    title_text = line_stripped[2:].strip()
                    title_text_no_space = re.sub(r'\s+', '', title_text)
                    # 检查是否是章节级别的标题
                    if (re.search(r'^绪论', title_text_no_space) or
                        re.search(r'^第[一二三四五六七八九十百千万0-9]+[篇章]', title_text) or
                        re.search(r'^第[一二三四五六七八九十百千万0-9]+篇', title_text)):
                        has_chapter_titles_at_start = True
                        break

            if has_chapter_titles_at_start:
                logger.info("检测到无目录书籍，将按照与'绪论'同级别的正文标题进行提取")
                # 不进行目录检测，直接返回空列表，让后续逻辑处理
                toc_start = -1
                toc_end = -1
            else:
                logger.info("未检测到带'目录'标题的目录区域，尝试检测无标题的目录区域")
                # 先尝试查找"# 绪论"作为目录开始标志（常见格式）
                toc_end_candidate = -1  # 在循环外初始化
                for i, line in enumerate(lines[:1200]):  # 在前1200行中搜索
                    line_stripped = line.strip()
                    if line_stripped == '# 绪论' or line_stripped.startswith('# 绪论'):
                        # 找到"# 绪论"，作为目录开始候选
                        # 查找目录结束标志（"# 参考文献"等）
                        toc_end_candidate = -1
                        for j in range(i + 1, min(i + 600, len(lines))):  # 在后续600行中查找结束标志
                            next_line = lines[j].strip()
                            if next_line.startswith('#') and ('参考文献' in next_line or 'References' in next_line or 'REFERENCES' in next_line):
                                toc_end_candidate = j
                                break
                        if toc_end_candidate != -1:
                            toc_start = i
                            toc_end = toc_end_candidate
                            logger.info(f"通过'# 绪论'检测到目录区域：第 {toc_start+1} 行到第 {toc_end+1} 行")
                            break

                # 如果通过"# 绪论"没有找到，使用通用的无标题目录检测方法
                if toc_start == -1 or toc_end == -1:
                    # 扩大搜索范围，从前1200行开始搜索（通常目录在文件前部，但可能较靠后）
                    auto_toc_start, auto_toc_end = self._detect_toc_without_title(lines, start_search=0, max_search=1200)
                    if auto_toc_start != -1 and auto_toc_end != -1:
                        toc_start = auto_toc_start
                        toc_end = auto_toc_end
                        logger.info(f"自动检测到目录区域：第 {toc_start+1} 行到第 {toc_end+1} 行")

        # 设置目录行和搜索起始位置
        if toc_start != -1 and toc_end != -1:
            toc_lines = lines[toc_start:toc_end]
            search_start = toc_end
        else:
            logger.info("未检测到明确的目录区域，将在全文中搜索章节标题")
            toc_lines = []
            search_start = 0

        # 2. 从目录中提取章节标题信息（只提取真正的章节标题，必须有前缀或后缀）
        toc_headers = []
        if toc_lines:
            logger.info(f"开始从目录区域提取标题（共 {len(toc_lines)} 行）")
            for i, line in enumerate(toc_lines):
                line_stripped = line.strip()
                if not line_stripped:
                    continue

                # 跳过目录标题本身
                if line_stripped in ['# 目录', '目录', 'Contents', 'CONTENTS', '目  录', '目　录', '目 录', '# 目 录', '# 日录', '日录']:
                    continue

                # 跳过仅包含数字和符号的行（如"# 73"、"73"等）
                if self._is_only_numbers_and_symbols(line_stripped):
                    continue

                # 过滤子标题：跳过以"图"、"表"、"图X-X"、"表X-X"开头的行
                if re.match(r'^#*\s*(图|表|图[0-9]+-[0-9]+|表[0-9]+-[0-9]+)', line_stripped):
                    continue

                # 过滤子标题：跳过以"数字. "或"数字 ."开头的短标题（通常是步骤或子项）
                # 但保留章节级别的标题（如"第1章"、"实验一"等）
                if re.match(r'^#*\s*([0-9]+)\s*[\.。]\s*', line_stripped):
                    # 检查是否是章节级别的标题
                    is_chapter_level = bool(
                        re.search(r'第[0-9一二三四五六七八九十]+章', line_stripped) or
                        re.search(r'实验[一二三四五六七八九十]+', line_stripped) or
                        re.search(r'实习[一二三四五六七八九十]+', line_stripped) or
                        re.search(r'综合实习[一二三四五六七八九十]+', line_stripped)
                    )
                    if not is_chapter_level:
                        # 检查标题长度，如果太短（<10字符），很可能是子标题
                        title_part = re.sub(r'^#*\s*[0-9]+\s*[\.。]\s*', '', line_stripped).strip()
                        title_part = re.sub(r'\s+[0-9]+\s*$', '', title_part).strip()  # 去除页码
                        if len(title_part) < 10:
                            continue

                # 仅提取目录中的章节/节标题：
                # - “第*章”“第*节”
                # - 纯数字编号（如“1 …”“1.1 …”“2.3.4 …”）
                # - “绪论”
                chapter_or_section_re = r'^第[一二三四五六七八九十百千万0-9]+[章节]\b'
                numeric_heading_re = r'^[0-9]+(?:\.[0-9]+)*\b'

                header_match = self.markdown_header_pattern.match(line_stripped)
                if header_match:
                    level = len(header_match.group(1))
                    title = header_match.group(2).strip()
                    # 去除markdown标题中的页码和特殊符号（如"# 1 绪论 3"中的"3"，"# 第四周 标题· 51"中的"· 51"）
                    # 先去除省略号、点号等符号后的页码
                    title = re.sub(r'[…·•]\s*[0-9]+\s*$', '', title)
                    # 去除有空格分隔的页码
                    title = re.sub(r'\s+[0-9]+\s*$', '', title)
                    # 去除末尾的省略号、点号等符号
                    title = re.sub(r'[…·•]+\s*$', '', title).strip()

                    final_title = None
                    actual_level = level
                    numeric_prefix = None

                    if re.match(chapter_or_section_re, title):
                        # “第*章/第*节”
                        final_title = self._clean_title_text(title, remove_numeric_prefix=False)
                        actual_level = 1 if '章' in final_title else 2
                    elif re.match(numeric_heading_re, title):
                        # 纯数字编号（含多级）
                        num_match = re.match(numeric_heading_re, title)
                        numeric_prefix = num_match.group()
                        rest = title[len(numeric_prefix):].strip()
                        rest = re.sub(r'\s+[0-9]+\s*$', '', rest).strip()
                        rest_clean = self._clean_title_text(rest, remove_numeric_prefix=False)
                        # 保留编号+标题
                        final_title = f"{numeric_prefix} {rest_clean}".strip()
                        actual_level = numeric_prefix.count('.') + 1
                    elif '绪论' in title:
                        final_title = self._clean_title_text(title, remove_numeric_prefix=False)
                        actual_level = 1
                    else:
                        continue

                    # 只添加有意义的标题（不是纯页码、不是太短的标题）
                    if len(final_title) > 1 and not re.match(r'^[0-9\s\(\)]+$', final_title):
                        toc_headers.append({
                            'level': actual_level,
                            'title': final_title,
                            'raw_title': line_stripped,
                            'numeric_prefix': numeric_prefix,
                            'is_markdown': True,
                            'toc_line': i + toc_start
                        })
                else:
                    # 非markdown目录行：支持“第*章/节”或纯数字编号，以及“绪论”
                    plain = re.sub(r'\s+', ' ', line_stripped).strip()
                    plain_no_page = re.sub(r'\s+[0-9]+\s*$', '', plain).strip()
                    final_title = None
                    actual_level = None
                    numeric_prefix = None

                    if re.match(chapter_or_section_re, plain_no_page):
                        final_title = self._clean_title_text(plain_no_page, remove_numeric_prefix=False)
                        actual_level = 1 if '章' in final_title else 2
                    elif re.match(numeric_heading_re, plain_no_page):
                        num_match = re.match(numeric_heading_re, plain_no_page)
                        numeric_prefix = num_match.group()
                        rest = plain_no_page[len(numeric_prefix):].strip()
                        rest_clean = self._clean_title_text(rest, remove_numeric_prefix=False)
                        final_title = f"{numeric_prefix} {rest_clean}".strip()
                        actual_level = numeric_prefix.count('.') + 1
                    elif '绪论' in plain_no_page:
                        final_title = self._clean_title_text(plain_no_page, remove_numeric_prefix=False)
                        actual_level = 1

                    if final_title and len(final_title) > 1:
                        toc_headers.append({
                            'level': actual_level,
                            'title': final_title,
                            'raw_title': line_stripped,
                            'numeric_prefix': numeric_prefix,
                            'is_markdown': False,
                            'toc_line': i + toc_start
                        })
                    continue

        # 3. 严格按照目录中的标题在正文中查找并分割
                    # 检查是否是"实验X"格式（如"实验1"、"实验2"等）
                    is_experiment_format = bool(re.match(r'^实验[0-9]+\s+', line_stripped))
                    # 检查是否是"实验一"、"附录一"等格式（如"实验一 标题"、"附录一 标题"）
                    is_experiment_chinese_format = bool(re.match(r'^(实验|附录)[一二三四五六七八九十百千万]+\s+', line_stripped))
                    # 检查是否是"实习一"、"综合实习一"等格式
                    is_practice_chinese_format = bool(re.match(r'^(实习|综合实习)[一二三四五六七八九十百千万]+\s+', line_stripped))
                    # 检查是否是纯"数字-数字"格式（如"3-1"、"4-1"等）
                    is_dash_number_format = bool(re.match(r'^[0-9]+-[0-9]+\s+', line_stripped))
                    # 检查是否是"一、"、"二、"等中文序号格式
                    is_chinese_number_format = bool(re.match(r'^[一二三四五六七八九十百千万]+[、．.]\s*', line_stripped))
                    # 检查是否是"项目X"格式（如"项目1 果树育苗"等）
                    is_project_format = bool(re.match(r'^项目[0-9]+\s+', line_stripped))
                    # 检查是否是"任务X.X"格式（如"任务1.1 苗圃地的建立"等）
                    is_task_format = bool(re.match(r'^任务[0-9]+\.[0-9]+\s+', line_stripped))
                    has_chapter_marker = bool(
                        re.search(r'第[一二三四五六七八九十百千万0-9]+[章节]', line_stripped) or
                        re.search(r'Chapter\s+[0-9IVX]+', line_stripped, re.IGNORECASE) or
                        re.search(r'Section\s+[0-9]+', line_stripped, re.IGNORECASE) or
                        numeric_prefix or  # 有数字前缀（如1.1, 1.1.2, 3-1, 项目1, 任务1.1）
                        is_general_number_format or  # 通用编号格式（学科名+数字-数字）
                        is_experiment_dot_format or  # "实验X.Y"格式
                        is_experiment_format or  # "实验X"格式
                        is_experiment_chinese_format or  # "实验一"、"附录一"格式
                        is_practice_chinese_format or  # "实习一"、"综合实习一"格式
                        is_dash_number_format or  # 纯"数字-数字"格式
                        is_chinese_number_format or  # 中文序号格式（一、二、三等）
                        is_project_format or  # "项目X"格式
                        is_task_format  # "任务X.X"格式
                    )

                    # 特殊处理：允许提取"绪论"、"前言"等常见无前缀标题
                    is_special_title = bool(
                        '绪论' in line_stripped or '前言' in line_stripped or
                        'Preface' in line_stripped or 'Introduction' in line_stripped
                    )

                    # 只提取有前缀或特殊标题
                    if not has_chapter_marker and not is_special_title:
                        continue

                    # 处理通用编号格式（如"实验3-1 常用实验样品的收集制备 025"、"生物信息学 3-1 标题"等）
                    # 匹配模式：任意中文字符+可选空格+数字-数字+空格+标题+可选页码
                    general_number_match = re.match(r'([\u4e00-\u9fa5]+)\s*([0-9]+-[0-9]+)\s+(.+?)(?:\s+[0-9]+)?\s*$', line_stripped)
                    if general_number_match:
                        subject_name = general_number_match.group(1)  # 学科名（如"实验"、"生物信息学"、"植物学"）
                        numeric_prefix = general_number_match.group(2)  # 编号（如"3-1"）
                        title = general_number_match.group(3).strip()  # 标题文本
                        # 清理标题（去除页码、省略号等）
                        title_clean = self._clean_title_text(title, remove_numeric_prefix=False)
                        # 通用编号格式通常作为3级标题
                        level = 3
                        # 保留学科名和编号，格式：学科名编号 标题（如"实验3-1 常用实验样品的收集制备"）
                        final_title = f"{subject_name}{numeric_prefix} {title_clean}".strip()
                        # 只添加有意义的标题
                        if len(final_title) > 1:
                            toc_headers.append({
                                "level": level,
                                "title": final_title,
                                "raw_title": line_stripped,
                                "numeric_prefix": numeric_prefix,
                                "is_markdown": False,
                                "toc_line": i + toc_start
                            })
                        continue

                    # 处理"项目X"格式（如"项目1 果树育苗 11"）
                    # 匹配模式：项目 + 数字 + 空格 + 标题 + 可选页码
                    project_match = re.match(r'^(项目)([0-9]+)\s+(.+?)(?:\s+[0-9]+)?\s*$', line_stripped)
                    if project_match:
                        prefix_type = project_match.group(1)  # "项目"
                        numeric_prefix = project_match.group(2)  # "1"、"2"等
                        title = project_match.group(3).strip()  # 标题文本
                        # 清理标题（去除页码、省略号等）
                        title_clean = self._clean_title_text(title, remove_numeric_prefix=False)
                        # 保留完整标题格式：项目1 标题
                        final_title = f"{prefix_type}{numeric_prefix} {title_clean}".strip()
                        # "项目X"格式通常作为1级标题
                        level = 1
                        # 只添加有意义的标题
                        if len(final_title) > 1:
                            toc_headers.append({
                                "level": level,
                                "title": final_title,
                                "raw_title": line_stripped,
                                "numeric_prefix": f"{prefix_type}{numeric_prefix}",
                                "is_markdown": False,
                                "toc_line": i + toc_start
                            })
                        continue

                    # 处理"任务X.X"格式（如"任务1.1 苗圃地的建立 11"）
                    # 匹配模式：任务 + 数字.数字 + 空格 + 标题 + 可选页码
                    task_match = re.match(r'^(任务)([0-9]+\.[0-9]+)\s+(.+?)(?:\s+[0-9]+)?\s*$', line_stripped)
                    if task_match:
                        prefix_type = task_match.group(1)  # "任务"
                        numeric_prefix = task_match.group(2)  # "1.1"、"2.3"等
                        title = task_match.group(3).strip()  # 标题文本
                        # 清理标题（去除页码、省略号等）
                        title_clean = self._clean_title_text(title, remove_numeric_prefix=False)
                        # 保留完整标题格式：任务1.1 标题
                        final_title = f"{prefix_type}{numeric_prefix} {title_clean}".strip()
                        # 检测层级：根据数字前缀的层级（如1.1是2级）
                        numeric_level = self._detect_numeric_level(f"{numeric_prefix} {title}")
                        level = numeric_level if numeric_level is not None else 2
                        # 只添加有意义的标题
                        if len(final_title) > 1:
                            toc_headers.append({
                                "level": level,
                                "title": final_title,
                                "raw_title": line_stripped,
                                "numeric_prefix": numeric_prefix,
                                "is_markdown": False,
                                "toc_line": i + toc_start
                            })
                        continue

                    # 处理"实验X.Y"格式（如"实验5.1 蛙坐骨神经－腓肠肌标本制备和刺激强度对肌肉收缩的影响 66"）
                    # 匹配模式：实验 + 数字.数字 + 空格 + 标题 + 可选页码
                    experiment_dot_match = re.match(r'^(实验)([0-9]+\.[0-9]+)\s+(.+?)(?:\s+[0-9]+)?\s*$', line_stripped)
                    if experiment_dot_match:
                        prefix_type = experiment_dot_match.group(1)  # "实验"
                        numeric_prefix = experiment_dot_match.group(2)  # "5.1"、"15.2"等
                        title = experiment_dot_match.group(3).strip()  # 标题文本
                        # 清理标题（去除页码、省略号等）
                        title_clean = self._clean_title_text(title, remove_numeric_prefix=False)
                        # 保留完整标题格式：实验5.1 标题
                        final_title = f"{prefix_type}{numeric_prefix} {title_clean}".strip()
                        # 检测层级：根据数字前缀的层级（如5.1是2级，5.1.1是3级）
                        numeric_level = self._detect_numeric_level(f"{numeric_prefix} {title}")
                        level = numeric_level if numeric_level is not None else 3
                        # 只添加有意义的标题
                        if len(final_title) > 1:
                            toc_headers.append({
                                "level": level,
                                "title": final_title,
                                "raw_title": line_stripped,
                                "numeric_prefix": numeric_prefix,
                                "is_markdown": False,
                                "toc_line": i + toc_start
                            })
                        continue

                    # 处理"实习一"、"综合实习一"等格式（如"实习一 药用植物栽培农事基本操作综合实习· 69"）
                    # 匹配模式：实习/综合实习 + 中文数字（一、二、三...十一、十二等）+ 空格 + 标题 + 可选页码
                    practice_chinese_match = re.match(r'^(实习|综合实习)([一二三四五六七八九十百千万]+)\s+(.+?)(?:\s+[0-9]+)?\s*$', line_stripped)
                    if practice_chinese_match:
                        prefix_type = practice_chinese_match.group(1)  # "实习"或"综合实习"
                        chinese_number = practice_chinese_match.group(2)  # 中文数字
                        title = practice_chinese_match.group(3).strip()  # 标题文本
                        # 清理标题（去除页码、省略号、·符号等）
                        title_clean = self._clean_title_text(title, remove_numeric_prefix=False)
                        # 去除·符号
                        title_clean = re.sub(r'[·•]', '', title_clean).strip()
                        # 检查标题文本是否已经包含了前缀（避免重复添加）
                        # 如果标题文本以"实习X"或"综合实习X"开头，去除这个前缀
                        prefix_pattern = re.match(r'^(实习|综合实习)([一二三四五六七八九十百千万]+)\s+(.+)$', title_clean)
                        if prefix_pattern:
                            # 如果标题文本已经包含了前缀，只使用后面的部分
                            title_clean = prefix_pattern.group(3).strip()
                        # 保留完整标题格式：实习一 标题 或 综合实习一 标题
                        final_title = f"{prefix_type}{chinese_number} {title_clean}".strip()
                        # 作为前缀保存：实习一、综合实习一等
                        numeric_prefix = f"{prefix_type}{chinese_number}"
                        # "实习X"和"综合实习X"格式通常作为2级标题
                        level = 2
                        # 只添加有意义的标题
                        if len(final_title) > 1:
                            toc_headers.append({
                                "level": level,
                                "title": final_title,
                                "raw_title": line_stripped,
                                "numeric_prefix": numeric_prefix,
                                "is_markdown": False,
                                "toc_line": i + toc_start
                            })
                        continue

                    # 处理"实验一"、"附录一"等格式（如"实验一 植物组织培养MS培养基的配制 3"）
                    # 匹配模式：实验/附录 + 中文数字（一、二、三...十一、十二等）+ 空格 + 标题 + 可选页码
                    experiment_chinese_match = re.match(r'^(实验|附录)([一二三四五六七八九十百千万]+)\s+(.+?)(?:\s+[0-9]+)?\s*$', line_stripped)
                    if experiment_chinese_match:
                        prefix_type = experiment_chinese_match.group(1)  # "实验"或"附录"
                        chinese_number = experiment_chinese_match.group(2)  # 中文数字
                        title = experiment_chinese_match.group(3).strip()  # 标题文本
                        # 清理标题（去除页码、省略号、·符号等）
                        title_clean = self._clean_title_text(title, remove_numeric_prefix=False)
                        # 去除·符号
                        title_clean = re.sub(r'[·•]', '', title_clean).strip()
                        # 检查标题文本是否已经包含了前缀（避免重复添加）
                        # 如果标题文本以"实验X"或"附录X"开头，去除这个前缀
                        prefix_pattern = re.match(r'^(实验|附录)([一二三四五六七八九十百千万]+)\s+(.+)$', title_clean)
                        if prefix_pattern:
                            # 如果标题文本已经包含了前缀，只使用后面的部分
                            title_clean = prefix_pattern.group(3).strip()
                        # 保留完整标题格式：实验一 标题 或 附录一 标题
                        final_title = f"{prefix_type}{chinese_number} {title_clean}".strip()
                        # 作为前缀保存：实验一、附录一等
                        numeric_prefix = f"{prefix_type}{chinese_number}"
                        # "实验X"格式通常作为2级标题，"附录X"格式也作为2级标题
                        level = 2
                        # 只添加有意义的标题
                        if len(final_title) > 1:
                            toc_headers.append({
                                "level": level,
                                "title": final_title,
                                "raw_title": line_stripped,
                                "numeric_prefix": numeric_prefix,
                                "is_markdown": False,
                                "toc_line": i + toc_start
                            })
                        continue

                    # 处理"实验X"格式（如"实验1坐骨神经－腓肠肌标本制备 43"）
                    # 匹配模式：实验 + 数字 + 标题 + 可选页码
                    experiment_match = re.match(r'^(实验[0-9]+)\s*(.+?)(?:\s+[0-9]+)?\s*$', line_stripped)
                    if experiment_match:
                        numeric_prefix = experiment_match.group(1)  # "实验1"
                        title = experiment_match.group(2).strip()  # 标题文本
                        # 清理标题（去除省略号等）
                        title_clean = self._clean_title_text(title, remove_numeric_prefix=False)
                        # "实验X"格式通常作为2级标题
                        level = 2
                        final_title = f"{numeric_prefix} {title_clean}".strip()
                        # 只添加有意义的标题
                        if len(final_title) > 1:
                            toc_headers.append({
                                "level": level,
                                "title": final_title,
                                "raw_title": line_stripped,
                                "numeric_prefix": numeric_prefix,
                                "is_markdown": False,
                                "toc_line": i + toc_start
                            })
                        continue

                    # 处理纯"数字-数字"格式（如"3-1 吸管法 10"、"4-1 人工筛分法 18"等）
                    # 匹配模式：数字-数字 + 空格 + 标题 + 可选页码
                    dash_number_match = re.match(r'^([0-9]+-[0-9]+)\s+(.+?)(?:\s+[0-9]+)?\s*$', line_stripped)
                    if dash_number_match:
                        numeric_prefix = dash_number_match.group(1)  # "3-1"
                        title = dash_number_match.group(2).strip()  # 标题文本
                        # 清理标题（去除页码、省略号等）
                        title_clean = self._clean_title_text(title, remove_numeric_prefix=False)
                        # "数字-数字"格式通常作为3级标题
                        level = 3
                        final_title = f"{numeric_prefix} {title_clean}".strip()
                        # 只添加有意义的标题
                        if len(final_title) > 1:
                            toc_headers.append({
                                "level": level,
                                "title": final_title,
                                "raw_title": line_stripped,
                                "numeric_prefix": numeric_prefix,
                                "is_markdown": False,
                                "toc_line": i + toc_start
                            })
                        continue

                    # 处理数字前缀格式（如"1.1 标题 3"、"1.1.2 标题"等）
                    # 先去除行末的页码，再匹配
                    line_for_match = re.sub(r'\s+[0-9]+\s*$', '', line_stripped)  # 去除行末页码
                    numeric_prefix_match = re.match(r'^([0-9]+(?:\.[0-9]+)*)\s+(.+)$', line_for_match)
                    if numeric_prefix_match:
                        numeric_prefix = numeric_prefix_match.group(1)
                        title = numeric_prefix_match.group(2).strip()
                        # 清理标题（去除页码、省略号等）
                        title_clean = self._clean_title_text(title, remove_numeric_prefix=False)
                        numeric_level = self._detect_numeric_level(line_stripped)
                        if numeric_level is not None:
                            level = numeric_level
                        else:
                            level = 2
                        final_title = f"{numeric_prefix} {title_clean}".strip()
                        # 只添加有意义的标题
                        if len(final_title) > 1:
                            toc_headers.append({
                                "level": level,
                                "title": final_title,
                                "raw_title": line_stripped,
                                "numeric_prefix": numeric_prefix,
                                "is_markdown": False,
                                "toc_line": i + toc_start
                            })
                    else:
                        for pattern in self.chinese_patterns + self.english_patterns:
                            match = pattern.match(line_stripped)
                            if match:
                                if len(match.groups()) > 1 and match.group(2):
                                    title = match.group(2).strip()
                                elif len(match.groups()) > 0 and match.group(1):
                                    title = match.group(1).strip()
                                else:
                                    title = line_stripped

                                if not title:
                                    title = line_stripped

                                title_clean = self._clean_title_text(title, remove_numeric_prefix=True)

                                # 检查是否是"一、"、"二、"等中文序号格式（三级标题）
                                is_chinese_number_format = bool(re.match(r'^[一二三四五六七八九十百千万]+[、．.]\s*', line_stripped))

                                if '节' in line_stripped:
                                    level = 2
                                elif '章' in line_stripped:
                                    level = 1
                                elif is_chinese_number_format:
                                    level = 3  # "一、"、"二、"等格式为三级标题
                                else:
                                    numeric_level = self._detect_numeric_level(line_stripped)
                                    if numeric_level is not None:
                                        level = numeric_level
                                    else:
                                        level = 2

                                numeric_prefix = self._extract_numeric_prefix(line_stripped)
                                if numeric_prefix:
                                    final_title = f"{numeric_prefix} {title_clean}".strip()
                                else:
                                    final_title = title_clean

                                # 只添加有意义的标题
                                if len(final_title) > 1:
                                    toc_headers.append({
                                        "level": level,
                                        "title": final_title,
                                        "raw_title": line_stripped,
                                        "numeric_prefix": numeric_prefix,
                                        "is_markdown": False,
                                        "toc_line": i + toc_start
                                    })
                                break

        # 3. 严格按照目录中的标题在正文中查找并分割
        # 如果没有目录，按照与"绪论"同级别的正文标题进行提取
        logger.info(f"从目录中提取到 {len(toc_headers)} 个标题")
        if len(toc_headers) > 0:
            logger.info(f"前10个提取的标题: {[h['title'] for h in toc_headers[:10]]}")
        if not toc_headers:
            logger.warning("未找到目录，尝试按照与'绪论'同级别的正文标题进行提取")
            # 查找所有1级markdown标题（与"绪论"同级别）
            # 只识别"绪论"和"第*篇"格式的标题，忽略其他标题
            level1_headers = []
            for i, line in enumerate(lines):
                line_stripped = line.strip()
                if not line_stripped:
                    continue

                # 检查是否是1级markdown标题（# 开头，且只有一个#）
                if line_stripped.startswith('# ') and not line_stripped.startswith('##'):
                    title_text = line_stripped[2:].strip()  # 去除"# "

                    # 只识别"绪论"和"第*篇"格式的标题
                    # 去除空格后检查
                    title_text_no_space = re.sub(r'\s+', '', title_text)
                    is_chapter_level = bool(
                        re.search(r'^绪论', title_text_no_space) or
                        re.search(r'^第[一二三四五六七八九十百千万0-9]+篇', title_text)
                    )

                    if is_chapter_level:
                        # 对于章节级别的1级标题，直接接受，不需要检查是否是纯标题行
                        level1_headers.append({
                            'level': 1,
                            'title': title_text,
                            'raw_title': line_stripped,
                            'numeric_prefix': None,
                            'is_markdown': True,
                            'toc_line': i,
                            'line_num': i
                        })

            if level1_headers:
                logger.info(f"找到 {len(level1_headers)} 个与'绪论'同级别的正文标题: {[h['title'] for h in level1_headers]}")
                # 将这些标题作为目录标题使用
                toc_headers = level1_headers
            else:
                logger.warning("未找到与'绪论'同级别的正文标题，无法提取章节")
                return []

        # 过滤掉目录标题本身（如"目录"、"Contents"等）
        filtered_toc_headers = []
        for toc_header in toc_headers:
            title_clean = toc_header['title'].strip()
            # 跳过目录标题本身
            if title_clean in ["目录", "Contents", "CONTENTS", "目  录", "目　录", "目 录"]:
                continue
            filtered_toc_headers.append(toc_header)

        if not filtered_toc_headers:
            logger.warning("目录中只有目录标题本身，没有实际章节标题")
            return []

        # 在正文中按顺序查找目录中的每个标题，并记录其行号
        # 关键：必须按照目录顺序，从前到后依次查找，每次从上次找到的位置之后开始
        toc_title_positions = []  # [(line_num, toc_header, original_index), ...]
        last_found_line = search_start - 1  # 上次找到的位置，初始为目录结束位置之前

        for original_index, toc_header in enumerate(filtered_toc_headers):
            title_to_find = toc_header['title']
            numeric_prefix = toc_header.get('numeric_prefix')

            # 如果标题已经有line_num字段（从正文中直接提取的），直接使用
            if 'line_num' in toc_header:
                found_line = toc_header['line_num']
                toc_title_positions.append((found_line, toc_header, original_index))
                last_found_line = found_line
                logger.info(f"使用正文中直接提取的标题位置: {title_to_find} (行{found_line+1})")
                continue

            # 提取目录标题的核心文本（去除前缀、页码、省略号等）
            core_title_to_find = self._extract_core_title(title_to_find)

            # 调试信息：记录前几个标题的匹配过程，以及特定标题的匹配过程
            should_debug = len(toc_title_positions) < 3 or "4.1.2" in title_to_find or "猪的遗传资源" in title_to_find or "3.1.2" in title_to_find or "家畜性别决定和伴性遗传" in title_to_find or "3.3.1" in title_to_find or "家畜生殖系统与生殖激素" in title_to_find or "1.1" in title_to_find or "1.2" in title_to_find or "1.3" in title_to_find or "动物生理学" in title_to_find or "绪论" in title_to_find
            if should_debug:
                logger.debug(f"查找目录标题: {title_to_find}, 核心文本: {core_title_to_find}, 前缀: {numeric_prefix}, 搜索起始: {search_start}, last_found_line: {last_found_line}")

            # 在正文中查找该标题（从上次找到的位置之后开始，确保按顺序）
            # 重要：必须从目录结束位置之后开始搜索，不提取目录前的内容
            found_line = -1
            # 如果前面的标题都没找到，适当推进搜索起始位置，避免搜索范围受限
            # 但不要推进太多，保持按顺序搜索的原则
            if last_found_line < search_start:
                # 如果还没找到任何标题，从目录结束位置开始搜索
                search_from = search_start
            else:
                # 如果已经找到过标题，从上次找到的位置之后开始搜索
                # 但是，如果目录顺序和正文顺序不一致（比如当前标题在目录中更靠前），
                # 应该允许从 search_start 开始搜索，但只搜索到 last_found_line 之前
                # 这里先尝试从 last_found_line + 1 开始搜索（正常情况）
                search_from = last_found_line + 1
            # 确保搜索起始位置不小于目录结束位置
            search_from = max(search_start, search_from)

            # 如果从 search_from 开始搜索没找到，且 search_from > search_start，
            # 说明可能是目录顺序和正文顺序不一致，尝试从 search_start 开始搜索到 search_from 之前
            search_backward = False
            if search_from > search_start:
                search_backward = True

            for i in range(search_from, len(lines)):
                # 确保不在目录区域内（双重保险）
                if toc_start != -1 and toc_end != -1 and toc_start <= i < toc_end:
                    continue  # 跳过目录区域内的内容

                line_stripped = lines[i].strip()
                if not line_stripped:
                    continue

                # 第一步：提取正文中该行的核心文本，与目录标题的核心文本进行匹配
                # 不需要先判断是否是标题或纯标题行，直接提取核心文本进行匹配
                line_core_title = self._extract_core_title(line_stripped)

                # 调试：前几个标题时记录匹配过程，以及特定标题的匹配过程
                # 对于特定标题，扩大搜索范围以便调试
                debug_range = 50 if len(toc_title_positions) < 3 else 200
                if should_debug and i < search_from + debug_range:
                    logger.debug(f"  行{i+1}: {line_stripped[:50]}, 核心文本: {line_core_title}")

                # 核心文本匹配：只匹配核心文本部分（忽略前缀、页码、省略号等）
                # 核心文本必须完全匹配（只比较字符，忽略标点符号和空格）
                match_success = False
                if core_title_to_find and line_core_title:
                    # 去除标点符号和空格进行比较（只保留中文字符、英文字母和数字）
                    core1_clean = re.sub(r'[^\u4e00-\u9fa5a-zA-Z0-9]', '', core_title_to_find)
                    core2_clean = re.sub(r'[^\u4e00-\u9fa5a-zA-Z0-9]', '', line_core_title)

                    # 调试：前几个标题时记录匹配尝试，以及特定标题的匹配过程
                    # 对于特定标题，扩大搜索范围以便调试
                    debug_range = 50 if len(toc_title_positions) < 3 else 200
                    if should_debug and i < search_from + debug_range:
                        logger.debug(f"  核心文本匹配尝试: 目录核心='{core_title_to_find}' -> 正文核心='{line_core_title}' (行{i+1}), 清理后: '{core1_clean}' vs '{core2_clean}', 匹配: {core1_clean == core2_clean}")

                    # 完全匹配（忽略空格和标点符号）
                    if core1_clean == core2_clean and len(core1_clean) >= 1:
                        match_success = True
                    # 如果完全匹配失败，尝试模糊匹配（对于短标题，允许部分匹配）
                    elif len(core1_clean) >= 2 and len(core2_clean) >= 2:
                        # 如果核心文本长度>=2，且一个包含另一个，且长度差异不大，认为是匹配
                        if (core1_clean in core2_clean or core2_clean in core1_clean) and abs(len(core1_clean) - len(core2_clean)) <= 2:
                            match_success = True
                        # 对于较长的标题，如果相似度很高（允许少量字符差异，处理OCR错误）
                        elif len(core1_clean) >= 4 and len(core2_clean) >= 4:
                            # 计算公共字符集合的重叠率
                            set1 = set(core1_clean)
                            set2 = set(core2_clean)
                            common_chars = set1 & set2
                            if len(common_chars) >= min(len(set1), len(set2)) * 0.8:
                                # 如果字符集合重叠率>=80%，且长度差异<=3，认为是匹配
                                if abs(len(core1_clean) - len(core2_clean)) <= 3:
                                    match_success = True

                # 第二步：如果核心文本匹配成功，先判断是否在小目录区域
                if match_success:
                    # 检查匹配到的标题是否在小目录区域
                    is_in_sub_toc = self._is_in_sub_toc(lines, i)
                    if is_in_sub_toc:
                        # 调试：前几个标题时记录，以及特定标题的匹配过程
                        if should_debug:
                            logger.warning(f"  核心文本匹配成功但被判定为小目录，跳过: 行{i+1}, {line_stripped[:80]}")
                        # 如果在小目录区域，跳过这个匹配，继续查找下一个匹配
                        continue

                    # 第三步：如果不在小目录区域，判断该核心文本在正文中是否单独一行
                    # （可有前缀（章节标志）及符号如"#"等，但没有其他文字内容）
                    title_info = self._extract_title_from_line(line_stripped)
                    if not title_info or not title_info['is_title']:
                        # 如果不是标题格式，跳过
                        if should_debug:
                            logger.debug(f"  核心文本匹配但行{i+1}不是标题格式，跳过: {line_stripped[:50]}")
                        continue

                    # 判断是否是纯标题行（只包含标题内容，可有前缀和符号，但没有其他文字内容）
                    if not self._is_title_only_line(line_stripped, title_info):
                        # 如果不是纯标题行，跳过
                        if should_debug:
                            logger.debug(f"  核心文本匹配但行{i+1}不是纯标题行，跳过: {line_stripped[:50]}")
                        continue

                    # 第四步：所有条件都满足，接受匹配
                    found_line = i
                    if should_debug:
                        logger.info(f"  匹配成功并接受: 行{i+1}, {line_stripped[:50]}")
                    break

            # 如果从 search_from 开始搜索没找到，且允许向后搜索，尝试从 search_start 开始搜索到 search_from 之前
            if found_line == -1 and search_backward:
                if should_debug:
                    logger.debug(f"  从 search_from={search_from} 开始搜索未找到，尝试从 search_start={search_start} 向后搜索到 {search_from-1}")
                for i in range(search_start, search_from):
                    # 确保不在目录区域内（双重保险）
                    if toc_start != -1 and toc_end != -1 and toc_start <= i < toc_end:
                        continue  # 跳过目录区域内的内容

                    line_stripped = lines[i].strip()
                    if not line_stripped:
                        continue

                    # 第一步：提取正文中该行的核心文本，与目录标题的核心文本进行匹配
                    line_core_title = self._extract_core_title(line_stripped)

                    # 调试：前几个标题时记录匹配过程，以及特定标题的匹配过程
                    if should_debug:
                        logger.debug(f"  向后搜索 行{i+1}: {line_stripped[:50]}, 核心文本: {line_core_title}")

                    # 核心文本匹配：只匹配核心文本部分（忽略前缀、页码、省略号等）
                    match_success = False
                    if core_title_to_find and line_core_title:
                        # 去除标点符号和空格进行比较（只保留中文字符、英文字母和数字）
                        core1_clean = re.sub(r'[^\u4e00-\u9fa5a-zA-Z0-9]', '', core_title_to_find)
                        core2_clean = re.sub(r'[^\u4e00-\u9fa5a-zA-Z0-9]', '', line_core_title)

                        # 完全匹配（忽略空格和标点符号）
                        if core1_clean == core2_clean and len(core1_clean) >= 1:
                            match_success = True
                        # 如果完全匹配失败，尝试模糊匹配
                        elif len(core1_clean) >= 2 and len(core2_clean) >= 2:
                            if (core1_clean in core2_clean or core2_clean in core1_clean) and abs(len(core1_clean) - len(core2_clean)) <= 2:
                                match_success = True
                            elif len(core1_clean) >= 4 and len(core2_clean) >= 4:
                                set1 = set(core1_clean)
                                set2 = set(core2_clean)
                                common_chars = set1 & set2
                                if len(common_chars) >= min(len(set1), len(set2)) * 0.8:
                                    if abs(len(core1_clean) - len(core2_clean)) <= 3:
                                        match_success = True

                    # 第二步：如果核心文本匹配成功，先判断是否在小目录区域
                    if match_success:
                        is_in_sub_toc = self._is_in_sub_toc(lines, i)
                        if is_in_sub_toc:
                            if should_debug:
                                logger.warning(f"  向后搜索：核心文本匹配成功但被判定为小目录，跳过: 行{i+1}, {line_stripped[:80]}")
                            continue

                        # 第三步：如果不在小目录区域，判断该核心文本在正文中是否单独一行
                        title_info = self._extract_title_from_line(line_stripped)
                        if not title_info or not title_info['is_title']:
                            if should_debug:
                                logger.debug(f"  向后搜索：核心文本匹配但行{i+1}不是标题格式，跳过: {line_stripped[:50]}")
                            continue

                        if not self._is_title_only_line(line_stripped, title_info):
                            if should_debug:
                                logger.debug(f"  向后搜索：核心文本匹配但行{i+1}不是纯标题行，跳过: {line_stripped[:50]}")
                            continue

                        # 第四步：所有条件都满足，接受匹配
                        found_line = i
                        if should_debug:
                            logger.info(f"  向后搜索匹配成功并接受: 行{i+1}, {line_stripped[:50]}")
                        break

            # 如果核心文本匹配失败，尝试匹配完整标题（包含前缀）
            if found_line == -1:
                # 对于目录中的"第一节 标题"格式，尝试在正文中匹配"# 第一节 标题"或"第一节 标题"
                # 提取完整标题（包含前缀）
                full_title_to_find = title_to_find.strip()
                # 去除可能的页码
                full_title_to_find = re.sub(r'\s+[0-9]+\s*$', '', full_title_to_find)

                # 扩大搜索范围，从目录结束位置到文件末尾
                for i in range(search_from, len(lines)):
                    if toc_start != -1 and toc_end != -1 and toc_start <= i < toc_end:
                        continue

                    line_stripped = lines[i].strip()
                    if not line_stripped:
                        continue

                    # 第一步：提取正文中的完整标题（去除markdown标记和页码），与目录完整标题进行匹配
                    line_title_clean = line_stripped
                    line_title_clean = re.sub(r'^#+\s*', '', line_title_clean)  # 去除markdown标记
                    line_title_clean = re.sub(r'^\*\s*', '', line_title_clean)  # 去除星号（选修标记）
                    line_title_clean = re.sub(r'\s+[0-9]+\s*$', '', line_title_clean)  # 去除页码
                    line_title_clean = line_title_clean.strip()

                    # 比较完整标题（去除所有空格和标点符号）
                    full1_clean = re.sub(r'[^\u4e00-\u9fa5a-zA-Z0-9]', '', full_title_to_find)
                    full2_clean = re.sub(r'[^\u4e00-\u9fa5a-zA-Z0-9]', '', line_title_clean)

                    # 调试：前几个标题时记录匹配尝试，以及特定标题的匹配过程
                    if should_debug and i < search_from + 50:
                        logger.debug(f"  完整标题匹配尝试: 目录='{full_title_to_find}' -> 正文='{line_title_clean}' (行{i+1}), 清理后: '{full1_clean}' vs '{full2_clean}', 匹配: {full1_clean == full2_clean}")

                    # 如果完整标题匹配成功
                    if full1_clean == full2_clean and len(full1_clean) >= 3:
                        # 第二步：先判断是否在小目录区域
                        is_in_sub_toc = self._is_in_sub_toc(lines, i)
                        if is_in_sub_toc:
                            if should_debug:
                                logger.warning(f"完整标题匹配成功但被判定为小目录，跳过: 行{i+1}, {line_stripped[:80]}")
                            continue

                        # 第三步：如果不在小目录区域，判断是否是纯标题行
                        title_info = self._extract_title_from_line(line_stripped)
                        if not title_info or not title_info['is_title']:
                            if should_debug:
                                logger.debug(f"完整标题匹配但行{i+1}不是标题格式，跳过: {line_stripped[:50]}")
                            continue

                        if not self._is_title_only_line(line_stripped, title_info):
                            if should_debug:
                                logger.debug(f"完整标题匹配但行{i+1}不是纯标题行，跳过: {line_stripped[:50]}")
                            continue

                        # 第四步：所有条件都满足，接受匹配
                        found_line = i
                        if should_debug:
                            logger.info(f"通过完整标题匹配找到: {title_to_find} -> {line_stripped[:50]}")
                        break
                    # 调试信息：如果接近匹配但没完全匹配
                    elif len(full1_clean) >= 5 and len(full2_clean) >= 5:
                        # 计算相似度
                        common_len = 0
                        min_len = min(len(full1_clean), len(full2_clean))
                        for j in range(min_len):
                            if full1_clean[j] == full2_clean[j]:
                                common_len += 1
                        if common_len >= min_len * 0.8 and len(toc_title_positions) < 3:
                            logger.debug(f"  接近匹配 (相似度{common_len/min_len:.2f}): 目录='{full_title_to_find}' vs 正文='{line_title_clean}' (行{i+1})")

            # 如果核心文本和完整标题匹配都失败，尝试匹配拆分标题（如目录中是"第1章 实验部分"，正文中是"# 第1章"和"# 实验部分"两行）
            if found_line == -1 and core_title_to_find:
                # 检查是否是"第X章 标题"格式，正文中可能拆分为两行
                chapter_title_match = re.match(r'^(第[0-9一二三四五六七八九十]+章)\s+(.+)$', title_to_find)
                if chapter_title_match:
                    chapter_part = chapter_title_match.group(1)  # "第1章"
                    title_part = chapter_title_match.group(2).strip()  # "实验部分"
                    title_part_core = self._extract_core_title(title_part)

                    # 在正文中查找：先找"第X章"，然后在其后几行内找标题部分
                    for i in range(search_from, min(search_from + 500, len(lines))):
                        if toc_start != -1 and toc_end != -1 and toc_start <= i < toc_end:
                            continue

                        line_stripped = lines[i].strip()
                        if not line_stripped:
                            continue

                        # 检查是否是"# 第X章"格式（完全匹配或包含）
                        if line_stripped.startswith('#'):
                            # 提取这一行的核心文本
                            line_core = self._extract_core_title(line_stripped)
                            chapter_part_core = self._extract_core_title(chapter_part)

                            # 检查是否匹配章节部分（完全匹配或包含）
                            if line_core == chapter_part_core or chapter_part in line_stripped:
                                # 在后续5行内查找标题部分
                                for j in range(i + 1, min(i + 6, len(lines))):
                                    next_line = lines[j].strip()
                                    if not next_line:
                                        continue

                                    next_core = self._extract_core_title(next_line)
                                    if next_core and title_part_core:
                                        core1_clean = re.sub(r'[^\u4e00-\u9fa5a-zA-Z0-9]', '', title_part_core)
                                        core2_clean = re.sub(r'[^\u4e00-\u9fa5a-zA-Z0-9]', '', next_core)

                                        if core1_clean == core2_clean and len(core1_clean) >= 1:
                                            # 检查是否是标题格式
                                            next_title_info = self._extract_title_from_line(next_line)
                                            if next_title_info and next_title_info.get('is_title'):
                                                if not self._is_in_sub_toc(lines, j):
                                                    if self._is_title_only_line(next_line, next_title_info):
                                                        found_line = j
                                                        if should_debug:
                                                            logger.info(f"通过拆分标题匹配找到: {title_to_find} -> {line_stripped} + {next_line[:50]}")
                                                        break
                                if found_line != -1:
                                    break

            # 如果核心文本和完整标题匹配都失败，尝试模糊匹配（对于"第X章 标题"或"第X节 标题"格式，尝试只匹配标题部分）
            if found_line == -1 and core_title_to_find:
                # 检查是否是"第X章 标题"或"第X节 标题"格式
                chapter_pattern = re.compile(r'^第[一二三四五六七八九十百千万0-9]+[章节]\s*(.+)$')
                match_chapter = chapter_pattern.match(title_to_find)
                if match_chapter:
                    # 提取章节后的标题部分
                    title_after_chapter = match_chapter.group(1).strip()
                    core_title_after_chapter = self._extract_core_title(title_after_chapter)
                    if core_title_after_chapter:
                        # 重新搜索，使用章节后的标题部分
                        for i in range(search_from, len(lines)):
                            if toc_start != -1 and toc_end != -1 and toc_start <= i < toc_end:
                                continue

                            line_stripped = lines[i].strip()
                            if not line_stripped:
                                continue

                            # 第一步：提取核心文本进行匹配
                            line_core_title = self._extract_core_title(line_stripped)

                            # 匹配章节后的标题部分
                            core1_clean = re.sub(r'[^\u4e00-\u9fa5a-zA-Z0-9]', '', core_title_after_chapter)
                            core2_clean = re.sub(r'[^\u4e00-\u9fa5a-zA-Z0-9]', '', line_core_title)

                            if core1_clean == core2_clean and len(core1_clean) >= 1:
                                # 第二步：先判断是否在小目录区域
                                is_in_sub_toc = self._is_in_sub_toc(lines, i)
                                if is_in_sub_toc:
                                    continue

                                # 第三步：如果不在小目录区域，判断是否是纯标题行
                                title_info = self._extract_title_from_line(line_stripped)
                                if not title_info or not title_info['is_title']:
                                    continue

                                if not self._is_title_only_line(line_stripped, title_info):
                                    continue

                                # 第四步：所有条件都满足，接受匹配
                                found_line = i
                                break

                # 如果还是没找到，尝试更宽松的匹配（处理OCR错误，允许部分字符差异）
                if found_line == -1 and len(core_title_to_find) >= 4:
                    # 计算相似度匹配（允许少量字符差异，处理OCR错误）
                    for i in range(search_from, len(lines)):  # 搜索到文件末尾
                        if toc_start != -1 and toc_end != -1 and toc_start <= i < toc_end:
                            continue

                        line_stripped = lines[i].strip()
                        if not line_stripped:
                            continue

                        # 第一步：提取核心文本进行匹配
                        line_core_title = self._extract_core_title(line_stripped)
                        if not line_core_title:
                            continue

                        core1_clean = re.sub(r'[^\u4e00-\u9fa5a-zA-Z0-9]', '', core_title_to_find)
                        core2_clean = re.sub(r'[^\u4e00-\u9fa5a-zA-Z0-9]', '', line_core_title)

                        # 计算相似度：如果两个字符串长度相近，且其中一个包含另一个的大部分内容
                        if len(core1_clean) >= 4 and len(core2_clean) >= 4:
                            # 计算公共子串长度
                            min_len = min(len(core1_clean), len(core2_clean))
                            max_len = max(len(core1_clean), len(core2_clean))

                            # 如果较短字符串在较长字符串中，或者长度差异很小
                            if (core1_clean in core2_clean or core2_clean in core1_clean) and max_len - min_len <= 3:
                                # 进一步检查：计算字符重叠率
                                common_chars = set(core1_clean) & set(core2_clean)
                                if len(common_chars) >= min(len(set(core1_clean)), len(set(core2_clean))) * 0.7:
                                    # 第二步：先判断是否在小目录区域
                                    is_in_sub_toc = self._is_in_sub_toc(lines, i)
                                    if is_in_sub_toc:
                                        continue

                                    # 第三步：如果不在小目录区域，判断是否是纯标题行
                                    title_info = self._extract_title_from_line(line_stripped)
                                    if not title_info or not title_info['is_title']:
                                        continue

                                    if not self._is_title_only_line(line_stripped, title_info):
                                        continue

                                    # 第四步：所有条件都满足，接受匹配
                                    found_line = i
                                    if should_debug:
                                        logger.info(f"通过宽松匹配找到标题: {title_to_find} -> {line_stripped[:50]}")
                                    break

            if found_line != -1:
                toc_title_positions.append((found_line, toc_header, original_index))
                last_found_line = found_line  # 更新上次找到的位置
            else:
                # 提供更详细的调试信息
                logger.warning(f"未在正文中找到目录标题: {title_to_find} (核心文本: {core_title_to_find}, 前缀: {numeric_prefix})")
                logger.warning(f"  搜索范围: search_start={search_start}, search_from={search_from}, last_found_line={last_found_line}")
                # 扩大搜索范围，在整个文件中查找相似的标题
                similar_titles = []
                # 搜索整个文件，但跳过目录区域
                for i in range(search_start, len(lines)):
                    if toc_start != -1 and toc_end != -1 and toc_start <= i < toc_end:
                        continue
                    line_stripped = lines[i].strip()
                    if not line_stripped:
                        continue
                    # 直接提取核心文本进行匹配，不需要先判断是否是标题
                    line_core_title = self._extract_core_title(line_stripped)
                    if line_core_title and core_title_to_find:
                        # 检查核心文本是否匹配
                        core1_clean = re.sub(r'[^\u4e00-\u9fa5a-zA-Z0-9]', '', core_title_to_find)
                        core2_clean = re.sub(r'[^\u4e00-\u9fa5a-zA-Z0-9]', '', line_core_title)
                        if core1_clean == core2_clean or (len(core1_clean) >= 3 and core1_clean in core2_clean) or (len(core2_clean) >= 3 and core2_clean in core1_clean):
                            # 检查是否在小目录中
                            is_in_sub_toc = self._is_in_sub_toc(lines, i)
                            title_info = self._extract_title_from_line(line_stripped)
                            is_title = title_info and title_info.get('is_title')
                            is_title_only = is_title and self._is_title_only_line(line_stripped, title_info) if is_title else False
                            status = []
                            if is_in_sub_toc:
                                status.append("小目录")
                            if not is_title:
                                status.append("非标题格式")
                            elif not is_title_only:
                                status.append("非纯标题行")
                            else:
                                status.append("符合条件")
                            similar_titles.append(f"第{i+1}行: {line_stripped[:80]} [{', '.join(status)}]")
                            if len(similar_titles) >= 10:  # 找前10个相似标题
                                break
                if similar_titles:
                    logger.warning(f"  找到相似标题: {similar_titles}")
                # 即使没找到，也要更新搜索起始位置，避免后续搜索范围受限
                # 但不要更新太多，只更新到当前搜索位置之后一定范围
                if last_found_line < search_from + 200:
                    # 如果上次找到的位置太靠前，适当推进搜索起始位置
                    pass  # 保持原逻辑，不强制推进

        if not toc_title_positions:
            logger.warning("未在正文中找到任何目录中的标题")
            return []

        # 先按照正文中的行号排序，确定每个标题的内容范围
        toc_title_positions_by_line = sorted(toc_title_positions, key=lambda x: x[0])

        # 为每个标题确定内容范围（基于正文中的实际位置）
        title_content_ranges = {}  # {original_index: (start_line, end_line)}
        for idx, (found_line, toc_header, original_index) in enumerate(toc_title_positions_by_line):
            if idx + 1 < len(toc_title_positions_by_line):
                # 下一个在正文中匹配到的标题位置
                end_line = toc_title_positions_by_line[idx + 1][0]
            else:
                # 最后一个章节：检查是否遇到结束标记（如"参考文献"）
                end_line = len(lines)
                for i in range(found_line + 1, len(lines)):
                    line_stripped = lines[i].strip()
                    if not line_stripped:
                        continue
                    end_keyword = self._check_end_section_keyword(line_stripped)
                    if end_keyword:
                        end_line = i
                        break
            title_content_ranges[original_index] = (found_line, end_line)

        # 按照目录中的原始顺序排序（保持目录顺序输出）
        toc_title_positions.sort(key=lambda x: x[2])

        # 提取章节内容：按照目录顺序输出，但使用基于正文位置确定的内容范围
        final_chunks = []
        global_counter = 1

        for idx in range(len(toc_title_positions)):
            found_line, toc_header, original_index = toc_title_positions[idx]

            # 使用基于正文位置确定的内容范围
            if original_index in title_content_ranges:
                found_line, end_line = title_content_ranges[original_index]
            else:
                # 最后一个章节：检查是否遇到结束标记（如"参考文献"）
                end_line = len(lines)
                for i in range(found_line + 1, len(lines)):
                    line_stripped = lines[i].strip()
                    if not line_stripped:
                        continue
                    end_keyword = self._check_end_section_keyword(line_stripped)
                    if end_keyword:
                        end_line = i
                        break

            # 提取章节内容（从标题行的下一行开始，到下一个标题行之前）
            if end_line <= found_line:
                continue

            if found_line + 1 >= len(lines):
                continue

            section_lines = lines[found_line + 1:end_line]
            section_content = '\n'.join(section_lines)
            section_content = clean_text_basic(section_content)

            # 不再过滤短章节，提取所有章节

            chunk_id = f"chunk_{idx+1:03d}_{global_counter:03d}"
            # 构建完整标题（包含前缀）
            numeric_prefix = toc_header.get('numeric_prefix')
            title_clean = toc_header['title']

            # 如果标题中已经包含前缀，直接使用；否则添加前缀
            # 注意：对于"第一章"、"第一节"等，前缀已经在标题中了
            if numeric_prefix:
                # 检查前缀是否已经在标题中（去除空格后比较）
                title_no_space = re.sub(r'\s+', '', title_clean)
                prefix_no_space = re.sub(r'\s+', '', str(numeric_prefix))
                if prefix_no_space in title_no_space or title_clean.startswith(numeric_prefix):
                    chunk_title = title_clean
                else:
                    chunk_title = f"{numeric_prefix} {title_clean}".strip()
            else:
                chunk_title = title_clean

            final_chunks.append({
                'chunk_id': chunk_id,
                'chunk_title': chunk_title,
                'text': section_content,
                'level': toc_header['level'],
                'parent_title': None,
                'numeric_prefix': numeric_prefix  # 保存前缀信息
            })
            global_counter += 1

        logger.info(f"严格按照目录提取到 {len(final_chunks)} 个章节")
        return final_chunks


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
    处理单个文件，返回章节统计信息

    Returns:
        [{'paper_id': '文件名', 'chapter_title': '章节标题', 'chapter_length': 长度}, ...]
    """
    file_name = os.path.basename(file_path)
    paper_id = os.path.splitext(file_name)[0]  # 去掉扩展名

    try:
        # 读取文件内容
        with open(file_path, 'r', encoding='utf-8') as f:
            text = f.read()

        # 使用BookProcessor拆分章节
        processor = BookProcessor()
        chapters = processor.split_by_chapters(text)

        # 构建结果列表
        results = []
        for chapter in chapters:
            chapter_title = chapter.get('chunk_title', '未知章节')
            chapter_text = chapter.get('text', '')
            chapter_length = len(chapter_text)
            # 获取前缀信息（如果有）
            numeric_prefix = chapter.get('numeric_prefix', '')

            results.append({
                'paper_id': paper_id,
                'chapter_title': chapter_title,
                'chapter_length': chapter_length,
                'chapter_prefix': numeric_prefix if numeric_prefix else ''  # 添加前缀列
            })

        logger.info(f"处理文件 {file_name}: 找到 {len(results)} 个章节")
        return results

    except Exception as e:
        logger.error(f"处理文件 {file_path} 时出错: {e}")
        # 即使出错，也返回一个记录
        return [{
            'paper_id': paper_id,
            'chapter_title': f'错误: {str(e)[:50]}',
            'chapter_length': 0,
            'chapter_prefix': ''
        }]


# 默认输入文件路径（模块级变量，可供其他脚本导入使用）
DEFAULT_INPUT_FILE = os.getenv("BOOKS_INPUT_FILE", "examples/9787040070293_sample.jsonl")


def main():
    """主函数"""
    # 输入文件路径（使用模块级变量）
    input_file = DEFAULT_INPUT_FILE

    # 根据输入文件名生成输出路径
    input_file_name = os.path.basename(input_file)
    input_file_name_without_ext = os.path.splitext(input_file_name)[0]
    output_dir = os.getenv("BOOKS_OUTPUT_DIR", "output/chapter_list")
    output_excel = os.path.join(output_dir, f"{input_file_name_without_ext}.xlsx")

    logger.info("=" * 60)
    logger.info("开始章节统计")
    logger.info("=" * 60)
    logger.info(f"输入文件: {input_file}")
    logger.info(f"输出Excel: {output_excel}")

    # 检查输入文件是否存在
    if not os.path.exists(input_file):
        logger.error(f"输入文件不存在: {input_file}")
        return

    # 处理文件
    logger.info("处理文件...")
    try:
        results = process_file(input_file)
        logger.info(f"处理完成: 共统计 {len(results)} 个章节")

        # 保存结果到Excel
        if results:
            df = pd.DataFrame(results)
            # 确保列顺序正确（如果有chapter_prefix列，包含它；否则不包含）
            if 'chapter_prefix' in df.columns:
                df = df[['paper_id', 'chapter_title', 'chapter_prefix', 'chapter_length']]
            else:
                df = df[['paper_id', 'chapter_title', 'chapter_length']]

            # 保存到Excel
            os.makedirs(os.path.dirname(output_excel), exist_ok=True)
            df.to_excel(output_excel, index=False, engine='openpyxl')
            logger.info(f"结果已保存到: {output_excel}")
        else:
            logger.warning("没有结果可保存")
    except Exception as e:
        logger.error(f"处理失败: {e}")
        raise

    logger.info("=" * 60)
    logger.info("章节统计完成")
    logger.info("=" * 60)


if __name__ == "__main__":
    main()
