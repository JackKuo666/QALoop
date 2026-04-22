#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
植物知识图谱构建脚本 - 完整版
从PlantConnectome2025version_KG.csv（481万行）构建知识图谱
优化版本，用于处理大型数据集
"""

import pandas as pd
import json
import os
import csv
from collections import defaultdict, Counter
from typing import Dict, List, Set, Tuple
import re
import time
from datetime import datetime

class FullPlantKnowledgeGraphBuilder:
    def __init__(self, csv_file_path: str):
        """
        初始化知识图谱构建器

        Args:
            csv_file_path: CSV文件路径
        """
        self.csv_file_path = csv_file_path
        self.df = None
        self.nodes = set()
        self.edges = []
        self.node_properties = defaultdict(dict)
        self.edge_properties = defaultdict(dict)
        self.node_types = Counter()
        self.relationship_types = Counter()
        self.species = Counter()

        # 进度跟踪
        self.processed_rows = 0
        self.start_time = None

    def log_progress(self, message: str):
        """记录进度"""
        if self.start_time is None:
            self.start_time = time.time()
        elapsed = time.time() - self.start_time
        print(f"[{elapsed:6.1f}s] {message}")

    def clean_text(self, text):
        """清理文本"""
        if pd.isna(text) or text == '':
            return None
        # 移除多余的空格和特殊字符
        text = str(text).strip()
        # 移除换行符和制表符
        text = re.sub(r'[\n\t]+', ' ', text)
        # 移除多余空格
        text = re.sub(r'\s+', ' ', text)
        return text

    def load_data_sample(self, sample_size: int = 10000):
        """加载数据样本（用于快速测试）"""
        print(f"正在加载数据样本: {sample_size} 行")
        self.df = pd.read_csv(self.csv_file_path, nrows=sample_size, encoding='utf-8')
        print(f"成功加载 {len(self.df)} 行数据")
        return self.df

    def load_data_in_chunks(self, chunk_size: int = 50000):
        """分块加载数据"""
        print(f"开始分块加载数据（每块 {chunk_size} 行）")

        node_id_counter = 0
        total_nodes = set()
        total_edges = []
        chunk_count = 0

        try:
            for chunk_df in pd.read_csv(self.csv_file_path, chunksize=chunk_size, encoding='utf-8'):
                chunk_count += 1
                self.log_progress(f"处理第 {chunk_count} 块数据...")

                # 处理当前块
                for _, row in chunk_df.iterrows():
                    source = self.clean_text(row['source'])
                    source_type = self.clean_text(row['source type'])
                    target = self.clean_text(row['target'])
                    target_type = self.clean_text(row['target type'])
                    relationship = self.clean_text(row['relationship'])

                    # 记录节点
                    if source and source_type:
                        node_key = (source, source_type)
                        if node_key not in total_nodes:
                            total_nodes.add(node_key)
                            self.node_types[source_type] += 1

                    if target and target_type:
                        node_key = (target, target_type)
                        if node_key not in total_nodes:
                            total_nodes.add(node_key)
                            self.node_types[target_type] += 1

                    # 记录边
                    if source and relationship and target:
                        total_edges.append((source, relationship, target))
                        self.relationship_types[relationship] += 1

                        # 记录物种
                        if 'species' in row and pd.notna(row['species']):
                            self.species[row['species']] += 1

                self.log_progress(f"已处理 {len(total_nodes)} 个节点, {len(total_edges)} 条边")

        except Exception as e:
            print(f"处理过程中出错: {e}")
            raise

        self.nodes = total_nodes
        self.edges = total_edges

        self.log_progress(f"数据加载完成！")
        self.log_progress(f"总节点数: {len(self.nodes)}")
        self.log_progress(f"总边数: {len(self.edges)}")

        return len(self.nodes), len(self.edges)

    def load_data_streaming(self):
        """流式加载数据（使用csv模块）"""
        print(f"开始流式加载数据...")

        total_nodes = set()
        total_edges = []

        with open(self.csv_file_path, 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            chunk_count = 0
            chunk_size = 50000

            for row in reader:
                chunk_count += 1

                if chunk_count % chunk_size == 0:
                    self.log_progress(f"已处理 {chunk_count} 行...")

                source = self.clean_text(row['source'])
                source_type = self.clean_text(row['source type'])
                target = self.clean_text(row['target'])
                target_type = self.clean_text(row['target type'])
                relationship = self.clean_text(row['relationship'])

                # 记录节点
                if source and source_type:
                    total_nodes.add((source, source_type))
                    self.node_types[source_type] += 1

                if target and target_type:
                    total_nodes.add((target, target_type))
                    self.node_types[target_type] += 1

                # 记录边
                if source and relationship and target:
                    total_edges.append((source, relationship, target))
                    self.relationship_types[relationship] += 1

                    # 记录物种
                    if row.get('species') and row['species'].strip():
                        self.species[row['species']] += 1

        self.nodes = total_nodes
        self.edges = total_edges

        self.log_progress(f"数据加载完成！")
        self.log_progress(f"总节点数: {len(self.nodes)}")
        self.log_progress(f"总边数: {len(self.edges)}")

        return len(self.nodes), len(self.edges)

    def generate_json_graph(self, output_file: str):
        """生成JSON格式的图数据（优化版）"""
        self.log_progress(f"生成JSON图数据: {output_file}")

        # 分批写入以节省内存
        batch_size = 1000
        node_batches = []
        edge_batches = []

        # 节点批次
        nodes_list = []
        for i, (node_name, node_type) in enumerate(self.nodes):
            node_data = {
                'id': node_name,
                'label': node_type
            }
            nodes_list.append(node_data)

            if len(nodes_list) >= batch_size:
                node_batches.append(nodes_list)
                nodes_list = []

        if nodes_list:
            node_batches.append(nodes_list)

        # 边批次
        edges_list = []
        for source, relationship, target in self.edges:
            edge_data = {
                'source': source,
                'target': target,
                'type': relationship
            }
            edges_list.append(edge_data)

            if len(edges_list) >= batch_size:
                edge_batches.append(edges_list)
                edges_list = []

        if edges_list:
            edge_batches.append(edges_list)

        # 写入文件
        with open(output_file, 'w', encoding='utf-8') as f:
            f.write('{\n  "nodes": [\n')
            for i, batch in enumerate(node_batches):
                for j, node in enumerate(batch):
                    comma = ',' if not (i == len(node_batches) - 1 and j == len(batch) - 1) else ''
                    f.write(f'    {json.dumps(node, ensure_ascii=False)}{comma}\n')
            f.write('  ],\n  "edges": [\n')
            for i, batch in enumerate(edge_batches):
                for j, edge in enumerate(batch):
                    comma = ',' if not (i == len(edge_batches) - 1 and j == len(batch) - 1) else ''
                    f.write(f'    {json.dumps(edge, ensure_ascii=False)}{comma}\n')
            f.write('  ],\n  "metadata": {\n')
            f.write(f'    "total_nodes": {len(self.nodes)},\n')
            f.write(f'    "total_edges": {len(self.edges)},\n')
            f.write(f'    "node_types": {dict(self.node_types)},\n')
            f.write(f'    "relationship_types": {dict(self.relationship_types)},\n')
            f.write(f'    "species": {dict(self.species)}\n')
            f.write('  }\n}')

        self.log_progress(f"JSON图数据已保存到: {output_file}")

    def generate_statistics_report(self, output_file: str):
        """生成统计报告"""
        self.log_progress(f"生成统计报告: {output_file}")

        with open(output_file, 'w', encoding='utf-8') as f:
            f.write("# 植物知识图谱构建统计报告\n\n")
            f.write(f"生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n")

            f.write("## 基本统计\n\n")
            f.write(f"- 节点总数: {len(self.nodes):,}\n")
            f.write(f"- 边总数: {len(self.edges):,}\n")
            f.write(f"- 节点类型数: {len(self.node_types)}\n")
            f.write(f"- 关系类型数: {len(self.relationship_types)}\n")
            f.write(f"- 物种数: {len(self.species)}\n\n")

            f.write("## 节点类型分布（前20）\n\n")
            for node_type, count in self.node_types.most_common(20):
                f.write(f"- {node_type}: {count:,}\n")

            f.write("\n## 关系类型分布（前30）\n\n")
            for rel_type, count in self.relationship_types.most_common(30):
                f.write(f"- {rel_type}: {count:,}\n")

            f.write("\n## 物种分布（前20）\n\n")
            for species, count in self.species.most_common(20):
                f.write(f"- {species}: {count:,}\n")

        self.log_progress(f"统计报告已保存到: {output_file}")

    def generate_sample_cypher(self, sample_size: int = 5000, output_file: str = None):
        """生成Cypher查询样本（避免生成过大的文件）"""
        if output_file is None:
            output_file = "output/plant_kg_full_sample.cypher"

        self.log_progress(f"生成Cypher查询样本（前 {sample_size} 个节点）: {output_file}")

        with open(output_file, 'w', encoding='utf-8') as f:
            # 写入清理数据库的语句
            f.write("// 植物知识图谱Cypher查询（样本）\n")
            f.write("// 清理数据库\n")
            f.write("MATCH (n) DETACH DELETE n;\n\n")

            # 创建约束和索引
            f.write("// 创建约束和索引\n")
            f.write("CREATE CONSTRAINT node_id IF NOT EXISTS FOR (n) REQUIRE n.id IS UNIQUE;\n\n")

            # 写入节点创建语句（前sample_size个）
            f.write("// 创建节点（样本）\n")
            count = 0
            for node_name, node_type in self.nodes:
                if count >= sample_size:
                    break

                # 转义单引号
                name_escaped = node_name.replace("'", "\\'")
                type_escaped = node_type.replace("'", "\\'")

                f.write(f"CREATE (n:{type_escaped} {{id: '{name_escaped}', name: '{name_escaped}'}});\n")
                count += 1

            # 写入关系创建语句（前sample_size条）
            f.write("\n// 创建关系（样本）\n")
            count = 0
            for source, relationship, target in self.edges:
                if count >= sample_size:
                    break

                # 转义单引号
                source_escaped = source.replace("'", "\\'")
                relationship_escaped = relationship.replace("'", "\\'")
                target_escaped = target.replace("'", "\\'")

                f.write(f"MATCH (a {{id: '{source_escaped}'}}), (b {{id: '{target_escaped}'}}) ")
                f.write(f"CREATE (a)-[:{relationship_escaped}]->(b);\n")
                count += 1

        self.log_progress(f"Cypher查询样本已保存到: {output_file}")

    def build_graph(self, use_streaming: bool = True):
        """构建完整的知识图谱"""
        print("=" * 60)
        print("开始构建植物知识图谱（完整版）...")
        print("=" * 60)
        self.start_time = time.time()

        try:
            # 加载数据
            if use_streaming:
                node_count, edge_count = self.load_data_streaming()
            else:
                node_count, edge_count = self.load_data_in_chunks()

            # 生成统计报告
            report_file = "output/plant_kg_statistics.md"
            self.generate_statistics_report(report_file)

            # 生成JSON图数据
            json_file = "output/plant_kg_full.json"
            self.generate_json_graph(json_file)

            # 生成Cypher查询样本
            cypher_file = "output/plant_kg_full_sample.cypher"
            self.generate_sample_cypher(sample_size=5000, output_file=cypher_file)

            # 打印统计信息
            print("\n" + "=" * 60)
            print("✅ 知识图谱构建完成!")
            print("=" * 60)
            print(f"节点总数: {len(self.nodes):,}")
            print(f"边总数: {len(self.edges):,}")
            print(f"\n输出文件:")
            print(f"  - 统计报告: {report_file}")
            print(f"  - JSON图数据: {json_file}")
            print(f"  - Cypher查询样本: {cypher_file}")
            print("=" * 60)

            return {
                'nodes': self.nodes,
                'edges': self.edges,
                'statistics': {
                    'total_nodes': len(self.nodes),
                    'total_edges': len(self.edges),
                    'node_types': len(self.node_types),
                    'relationship_types': len(self.relationship_types),
                    'species': len(self.species)
                }
            }

        except Exception as e:
            print(f"❌ 构建知识图谱时出错: {e}")
            import traceback
            traceback.print_exc()
            return None

def main():
    """主函数"""
    import argparse
    parser = argparse.ArgumentParser(description="植物知识图谱构建（完整版）")
    parser.add_argument("--csv", default=None, help="CSV知识图谱文件路径")
    args = parser.parse_args()

    csv_file = args.csv or os.getenv("KG_CSV_FILE", "examples/sample_kg.csv")

    try:
        # 创建知识图谱构建器
        builder = FullPlantKnowledgeGraphBuilder(csv_file)

        # 构建图谱（使用流式加载）
        graph = builder.build_graph(use_streaming=True)

        return graph

    except Exception as e:
        print(f"❌ 脚本执行出错: {e}")
        import traceback
        traceback.print_exc()
        return None

if __name__ == "__main__":
    main()
