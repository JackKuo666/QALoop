#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
处理种子问题数据：
1. 读取 questions_20251125 文件夹下的所有 xlsx 文件
2. 提取问题并与两个已存在问题文件中的问题去重
   - merged_17101.jsonl
   - merged_seed_questions.jsonl
3. 按物种分类保存为 json 文件
"""

import pandas as pd
import json
import os
from collections import defaultdict

def read_existing_questions(file_paths):
    """
    读取已存在的问题（支持多个文件）

    Args:
        file_paths: 文件路径列表或单个文件路径

    Returns:
        set: 已存在问题的集合
    """
    existing_questions = set()

    # 如果是单个字符串，转换为列表
    if isinstance(file_paths, str):
        file_paths = [file_paths]

    print(f"开始读取 {len(file_paths)} 个已存在问题文件:")

    for file_path in file_paths:
        if not os.path.exists(file_path):
            print(f"⚠️  警告: 文件不存在，跳过: {file_path}")
            continue

        print(f"\n  正在读取: {os.path.basename(file_path)}")
        file_count = 0
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                for line_num, line in enumerate(f, 1):
                    try:
                        data = json.loads(line.strip())
                        if 'question' in data:
                            question = data['question'].strip()
                            if question:
                                existing_questions.add(question)
                                file_count += 1
                    except json.JSONDecodeError as e:
                        print(f"    警告: 第 {line_num} 行 JSON 解析失败: {e}")
            print(f"    → 从 {os.path.basename(file_path)} 读取了 {file_count} 个问题")
        except Exception as e:
            print(f"    ❌ 错误: 读取文件失败: {e}")

    print(f"\n✅ 总共读取了 {len(existing_questions)} 个不重复的已存在问题")
    return existing_questions

def extract_questions_from_xlsx(file_path):
    """从 xlsx 文件中提取问题及其分类信息"""
    questions = []
    try:
        # 读取所有工作表
        excel_file = pd.ExcelFile(file_path)
        print(f"  读取文件: {os.path.basename(file_path)}")
        print(f"  工作表: {excel_file.sheet_names}")

        for sheet_name in excel_file.sheet_names:
            try:
                df = pd.read_excel(file_path, sheet_name=sheet_name)
                print(f"    工作表 '{sheet_name}': {len(df)} 行, 列: {list(df.columns)}")

                # 查找包含问题的列
                question_col = None
                category_col = None
                sub_category_col = None

                for col in df.columns:
                    col_str = str(col).lower()
                    if '问题' in col_str or 'question' in col_str:
                        question_col = col
                    elif 'sub_category' in col_str or 'sub-category' in col_str or '子类别' in col_str or '子分类' in col_str or '亚类' in col_str:
                        sub_category_col = col
                    elif 'category' in col_str or '类别' in col_str or '分类' in col_str or '类型' in col_str:
                        category_col = col

                if question_col is None:
                    print(f"    警告: 未找到问题列，跳过工作表 '{sheet_name}'")
                    continue

                print(f"    找到列: 问题={question_col}, category={category_col}, sub_category={sub_category_col}")

                # 提取问题和分类信息
                for idx in range(len(df)):
                    value = df[question_col].iloc[idx]
                    if pd.notna(value) and str(value).strip():
                        question = str(value).strip()
                        if question and len(question) > 3:  # 过滤太短的问题
                            # 读取category
                            category = ''
                            if category_col is not None and pd.notna(df[category_col].iloc[idx]):
                                category = str(df[category_col].iloc[idx]).strip()

                            # 读取sub_category
                            sub_category = ''
                            if sub_category_col is not None and pd.notna(df[sub_category_col].iloc[idx]):
                                sub_category = str(df[sub_category_col].iloc[idx]).strip()

                            questions.append({
                                'question': question,
                                'category': category,
                                'sub_category': sub_category,
                                'sheet': sheet_name,
                                'row': idx + 1
                            })

            except Exception as e:
                print(f"    错误: 读取工作表 '{sheet_name}' 失败: {e}")

        print(f"  提取到 {len(questions)} 个问题")
    except Exception as e:
        print(f"错误: 读取 xlsx 文件失败: {e}")

    return questions

def determine_species(file_name):
    """根据文件名确定物种"""
    file_name_lower = file_name.lower()
    file_name_orig = file_name
    if '大豆' in file_name_orig or 'soybean' in file_name_lower:
        return '大豆'
    elif '水稻' in file_name_orig or 'rice' in file_name_lower:
        return '水稻'
    elif '小麦' in file_name_orig or 'wheat' in file_name_lower:
        return '小麦'
    elif '玉米' in file_name_orig or 'corn' in file_name_lower or 'maize' in file_name_lower:
        return '玉米'
    elif '油菜' in file_name_orig or 'rapeseed' in file_name_lower or 'canola' in file_name_lower:
        return '油菜'
    elif '畜禽' in file_name_orig or 'livestock' in file_name_lower or 'animal' in file_name_lower:
        return '畜禽'
    elif '合成' in file_name_orig or '生物技术' in file_name_orig or 'synthetic' in file_name_lower:
        return '合成生物技术'
    else:
        return '未知'

def categorize_question(question):
    """根据问题内容进行详细分类，返回 (category, sub_category)"""

    # 自我认知类 - 身份与角色定位
    identity_keywords = ['我究竟是', '我的身份', '我的角色', '我是谁', '我应该是', '我的定位',
                        '作为.*专家', '作为.*助手', '我的职责', '我的使命']
    for kw in identity_keywords:
        if kw in question:
            return '自我认知', '身份与角色定位'

    # 自我认知类 - 元认知与过程解释
    metacog_keywords = ['我之所以', '我的思考', '我认为', '我选择', '我判断', '我理解',
                       '我的推理', '我的分析', '元认知', '过程解释', '我的方法']
    for kw in metacog_keywords:
        if kw in question:
            return '自我认知类语料', '元认知与过程解释'

    # 场景化任务与指令遵循类 - 数据分析与解读
    data_analysis_keywords = ['分析', '检测', '测序', '解读', '评估', '鉴定', '预测',
                             '重测序', '转录组', '基因组', 'GWAS', 'QTL', 'SNP',
                             '表达量', '差异表达', '富集分析', '结构变异', 'SV']
    for kw in data_analysis_keywords:
        if kw in question:
            return '场景化任务与指令遵循类语料', '数据分析与解读'

    # 核心知识问答 - 物种特异性知识问答
    return '核心知识问答', '物种特异性知识问答'

def main():
    # 文件路径 - 使用环境变量或命令行参数配置
    questions_dir = os.environ.get('QUESTIONS_DIR', './data/')
    existing_questions_files_str = os.environ.get('EXISTING_QUESTIONS_FILES', '')
    existing_questions_files = [
        f.strip() for f in existing_questions_files_str.split(',') if f.strip()
    ] if existing_questions_files_str else []
    output_dir = os.environ.get('OUTPUT_DIR', './output/')

    # 创建输出目录
    os.makedirs(output_dir, exist_ok=True)
    print(f"创建输出目录: {output_dir}")

    # 读取已存在的问题（支持多个文件）
    existing_questions = read_existing_questions(existing_questions_files)
    print(f"\n已存在问题总数: {len(existing_questions)}")

    # 读取所有 xlsx 文件
    xlsx_files = [f for f in os.listdir(questions_dir) if f.endswith('.xlsx')]
    print(f"\n找到 {len(xlsx_files)} 个 xlsx 文件")

    all_new_questions = []
    species_questions = defaultdict(list)

    for xlsx_file in xlsx_files:
        file_path = os.path.join(questions_dir, xlsx_file)
        species = determine_species(xlsx_file)
        print(f"\n{'='*60}")
        print(f"处理文件: {xlsx_file} (物种: {species})")
        print('='*60)

        questions = extract_questions_from_xlsx(file_path)

        # 去重并过滤已存在的问题
        new_questions = []
        for q in questions:
            if q['question'] not in existing_questions:
                new_questions.append(q)
            else:
                print(f"    跳过已存在的问题: {q['question'][:50]}...")

        print(f"  新问题数量: {len(new_questions)} / {len(questions)}")

        # 分类并添加到总列表
        for q in new_questions:
            # 优先使用xlsx中的分类，如果为空则使用自动分类
            if q['category'] and q['sub_category']:
                category = q['category']
                sub_category = q['sub_category']
            else:
                category, sub_category = categorize_question(q['question'])

            formatted_q = {
                'question': q['question'],
                'category': category,
                'sub_category': sub_category,
                'species': species
            }

            all_new_questions.append(formatted_q)
            species_questions[species].append(formatted_q)

    # 按物种保存
    print(f"\n{'='*60}")
    print("保存结果")
    print('='*60)

    total_saved = 0
    for species, questions in species_questions.items():
        if not questions:
            continue

        output_file = os.path.join(output_dir, f'{species}_questions.json')
        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(questions, f, ensure_ascii=False, indent=2)

        print(f"保存 {species}: {len(questions)} 个问题 -> {output_file}")
        total_saved += len(questions)

    # 保存汇总统计
    summary = {
        'total_files_processed': len(xlsx_files),
        'existing_questions_count': len(existing_questions),
        'new_questions_count': total_saved,
        'species_breakdown': {species: len(questions) for species, questions in species_questions.items()},
        'output_directory': output_dir
    }

    summary_file = os.path.join(output_dir, 'summary.json')
    with open(summary_file, 'w', encoding='utf-8') as f:
        json.dump(summary, f, ensure_ascii=False, indent=2)

    print(f"\n{'='*60}")
    print("处理完成")
    print('='*60)
    print(f"总文件数: {summary['total_files_processed']}")
    print(f"已存在问题: {summary['existing_questions_count']}")
    print(f"新增问题: {summary['new_questions_count']}")
    print(f"输出目录: {output_dir}")
    print("\n各物种问题数:")
    for species, count in summary['species_breakdown'].items():
        print(f"  {species}: {count}")
    print(f"\n汇总统计已保存到: {summary_file}")

if __name__ == '__main__':
    main()
