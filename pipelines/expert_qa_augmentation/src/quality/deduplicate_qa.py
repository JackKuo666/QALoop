#!/usr/bin/env python3
"""
问答对去重脚本
对 output_全部物种_expanded/ 目录下的所有 jsonl 文件进行去重处理
"""

import os
import json
from pathlib import Path
from collections import defaultdict
import hashlib
from datetime import datetime

def get_text_hash(text):
    """获取文本的MD5哈希值"""
    return hashlib.md5(text.strip().encode('utf-8')).hexdigest()

def get_qa_pair_hash(question, answer):
    """获取问答对的组合哈希"""
    combined = f"{question.strip()}|||{answer.strip()}"
    return hashlib.md5(combined.encode('utf-8')).hexdigest()

def normalize_text(text):
    """标准化文本（去除多余空白）"""
    return ' '.join(text.split())

def deduplicate_qa_files(input_dir, output_dir):
    """
    对目录下的所有jsonl文件进行去重
    """
    input_path = Path(input_dir)
    output_path = Path(output_dir)
    output_path.mkdir(exist_ok=True)

    # 存储所有QA对
    # key: QA对哈希, value: (物种, 问题, 答案, 元数据)
    all_qa_pairs = defaultdict(list)

    # 按物种分组统计
    species_stats = defaultdict(int)
    total_files = 0
    total_pairs = 0

    print("=" * 70)
    print("🔄 问答对去重处理")
    print("=" * 70)
    print(f"\n📂 输入目录: {input_dir}")
    print(f"📂 输出目录: {output_dir}")
    print()

    # 扫描所有jsonl文件
    jsonl_files = sorted(input_path.glob("*.jsonl"))

    if not jsonl_files:
        print("❌ 未找到任何jsonl文件")
        return

    print(f"📊 发现 {len(jsonl_files)} 个jsonl文件\n")

    # 读取所有文件
    for file_path in jsonl_files:
        total_files += 1
        filename_species = file_path.stem.split('_QA_集合_')[0]

        print(f"📖 处理文件: {file_path.name}")
        file_pairs = 0

        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue

                    try:
                        data = json.loads(line)
                        question = normalize_text(data.get('question', ''))
                        answer = normalize_text(data.get('answer', ''))

                        if not question or not answer:
                            continue

                        # 【关键修复】优先从QA数据中读取species字段，其次使用seed_species，最后才使用文件名
                        species_name = data.get('species')
                        if not species_name:
                            # 尝试从seed_species获取
                            seed_species = data.get('seed_species')
                            if seed_species:
                                species_name = seed_species
                        if not species_name:
                            # 最后使用文件名中的物种
                            species_name = filename_species

                        # 获取QA对哈希
                        qa_hash = get_qa_pair_hash(question, answer)

                        # 存储QA对，保留第一个遇到的出现
                        if qa_hash not in all_qa_pairs:
                            all_qa_pairs[qa_hash] = {
                                'species': species_name,
                                'question': question,
                                'answer': answer,
                                'metadata': data.get('metadata', {}),
                                'source_files': [file_path.name]
                            }
                            species_stats[species_name] += 1
                            file_pairs += 1
                            total_pairs += 1
                        else:
                            # 如果已存在，添加源文件信息（避免重复记录）
                            if file_path.name not in all_qa_pairs[qa_hash]['source_files']:
                                all_qa_pairs[qa_hash]['source_files'].append(file_path.name)

                    except json.JSONDecodeError as e:
                        print(f"   ⚠️  JSON解析错误: {e}")
                        continue

        except Exception as e:
            print(f"   ❌ 文件读取错误: {e}")
            continue

        print(f"   ✅ 读取 {file_pairs} 个独特QA对\n")

    print("=" * 70)
    print("📈 去重统计")
    print("=" * 70)
    print(f"\n原始文件数: {total_files}")
    print(f"原始总对数: {total_pairs}")
    print(f"去重后对数: {len(all_qa_pairs)}")

    duplicates = total_pairs - len(all_qa_pairs)
    if duplicates > 0:
        duplicate_rate = (duplicates / total_pairs) * 100
        print(f"发现重复: {duplicates} 对 ({duplicate_rate:.2f}%)")
    else:
        print("✅ 未发现重复")

    print(f"\n各物种去重后数量:")
    for species in sorted(species_stats.keys()):
        count = sum(1 for qa in all_qa_pairs.values() if qa['species'] == species)
        print(f"  {species}: {count} 对")

    # 按物种保存去重后的文件
    print("\n" + "=" * 70)
    print("💾 保存去重结果")
    print("=" * 70)

    # 按物种分组
    species_qa_pairs = defaultdict(list)
    for qa_data in all_qa_pairs.values():
        species_qa_pairs[qa_data['species']].append(qa_data)

    # 生成时间戳
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

    # 为每个物种保存一个文件
    saved_files = []
    for species, qa_list in sorted(species_qa_pairs.items()):
        output_file = output_path / f"{species}_QA_去重_{timestamp}.jsonl"
        saved_count = 0

        with open(output_file, 'w', encoding='utf-8') as f:
            for qa in qa_list:
                # 构建输出数据
                output_data = {
                    'question': qa['question'],
                    'answer': qa['answer'],
                    'species': qa['species'],
                    'metadata': qa['metadata'],
                    'source_files': qa['source_files']
                }
                f.write(json.dumps(output_data, ensure_ascii=False) + '\n')
                saved_count += 1

        print(f"✅ {species}: {saved_count} 对 → {output_file.name}")
        saved_files.append(output_file)

    # 保存汇总报告
    report_file = output_path / f"去重报告_{timestamp}.json"
    report_data = {
        'timestamp': timestamp,
        'input_dir': str(input_dir),
        'output_dir': str(output_dir),
        'statistics': {
            'original_files': total_files,
            'original_pairs': total_pairs,
            'deduplicated_pairs': len(all_qa_pairs),
            'duplicates_removed': duplicates,
            'duplicate_rate_percent': round((duplicates / total_pairs * 100), 2) if total_pairs > 0 else 0
        },
        'species_counts': {
            species: sum(1 for qa in all_qa_pairs.values() if qa['species'] == species)
            for species in sorted(species_stats.keys())
        },
        'output_files': [str(f) for f in saved_files]
    }

    with open(report_file, 'w', encoding='utf-8') as f:
        json.dump(report_data, f, ensure_ascii=False, indent=2)

    print(f"\n📊 汇总报告: {report_file.name}")

    print("\n" + "=" * 70)
    print("✅ 去重完成！")
    print("=" * 70)
    print(f"\n📂 输出目录: {output_dir}")
    print(f"📄 去重文件: {len(saved_files)} 个")
    print(f"📊 去重后总计: {len(all_qa_pairs)} 对问答对")
    print("=" * 70)

if __name__ == "__main__":
    import sys

    # 默认路径
    input_directory = "output_全部物种_expanded"
    output_directory = "output_全部物种_deduplicated"

    # 如果提供了参数，使用参数
    if len(sys.argv) > 1:
        input_directory = sys.argv[1]
    if len(sys.argv) > 2:
        output_directory = sys.argv[2]

    deduplicate_qa_files(input_directory, output_directory)
