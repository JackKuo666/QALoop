#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
植物知识图谱构建脚本
从PlantConnectome2025_KG_sampled_10k.csv构建知识图谱
"""

import pandas as pd
import json
import csv
import os
from collections import defaultdict, Counter
from typing import Dict, List, Set, Tuple
import re

class PlantKnowledgeGraphBuilder:
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

    def load_data(self):
        """加载CSV数据"""
        print(f"正在加载数据: {self.csv_file_path}")
        try:
            # 尝试不同的分隔符和编码
            self.df = pd.read_csv(self.csv_file_path, encoding='utf-8')
            print(f"成功加载 {len(self.df)} 行数据")
            print(f"列名: {list(self.df.columns)}")
        except UnicodeDecodeError:
            print("UTF-8编码失败，尝试其他编码...")
            self.df = pd.read_csv(self.csv_file_path, encoding='latin-1')
            print(f"成功加载 {len(self.df)} 行数据")
        except Exception as e:
            print(f"加载数据时出错: {e}")
            raise

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

    def process_nodes(self):
        """处理节点信息"""
        print("\n处理节点信息...")

        # 处理source节点
        for _, row in self.df.iterrows():
            source = self.clean_text(row['source'])
            source_type = self.clean_text(row['source type'])
            target = self.clean_text(row['target'])
            target_type = self.clean_text(row['target type'])

            if source:
                self.nodes.add((source, source_type))
                self.node_types[source_type] += 1

                # 添加节点属性
                node_key = f"{source}|{source_type}"
                self.node_properties[node_key]['name'] = source
                self.node_properties[node_key]['type'] = source_type

                # 添加其他属性
                if 'species' in row and pd.notna(row['species']):
                    self.node_properties[node_key]['species'] = row['species']
                if 'source_extracted_definition' in row and pd.notna(row['source_extracted_definition']):
                    self.node_properties[node_key]['definition'] = row['source_extracted_definition']
                if 'source resolved' in row and pd.notna(row['source resolved']):
                    self.node_properties[node_key]['resolved_name'] = row['source resolved']

            if target:
                self.nodes.add((target, target_type))
                self.node_types[target_type] += 1

                # 添加节点属性
                node_key = f"{target}|{target_type}"
                self.node_properties[node_key]['name'] = target
                self.node_properties[node_key]['type'] = target_type

                # 添加其他属性
                if 'species' in row and pd.notna(row['species']):
                    self.node_properties[node_key]['species'] = row['species']
                if 'target_extracted_definition' in row and pd.notna(row['target_extracted_definition']):
                    self.node_properties[node_key]['definition'] = row['target_extracted_definition']
                if 'target resolved' in row and pd.notna(row['target resolved']):
                    self.node_properties[node_key]['resolved_name'] = row['target resolved']

        print(f"处理了 {len(self.nodes)} 个唯一节点")
        print(f"节点类型分布: {dict(self.node_types.most_common())}")

    def process_edges(self):
        """处理边（关系）信息"""
        print("\n处理关系信息...")

        for _, row in self.df.iterrows():
            source = self.clean_text(row['source'])
            relationship = self.clean_text(row['relationship'])
            target = self.clean_text(row['target'])

            if source and relationship and target:
                edge = (source, relationship, target)
                self.edges.append(edge)
                self.relationship_types[relationship] += 1

                # 添加边属性
                edge_key = f"{source}|{relationship}|{target}"
                self.edge_properties[edge_key]['source'] = source
                self.edge_properties[edge_key]['relationship'] = relationship
                self.edge_properties[edge_key]['target'] = target

                # 添加其他属性
                if 'gene' in row and pd.notna(row['gene']):
                    self.edge_properties[edge_key]['gene'] = row['gene']
                if 'pubmedID' in row and pd.notna(row['pubmedID']):
                    self.edge_properties[edge_key]['pubmed_id'] = row['pubmedID']
                if 'species' in row and pd.notna(row['species']):
                    self.edge_properties[edge_key]['species'] = row['species']
                    self.species[row['species']] += 1

        print(f"处理了 {len(self.edges)} 条关系")
        print(f"关系类型分布: {dict(self.relationship_types.most_common(10))}")

    def generate_neo4j_cypher(self, output_file: str):
        """生成Neo4j Cypher查询"""
        print(f"\n生成Neo4j Cypher查询: {output_file}")

        with open(output_file, 'w', encoding='utf-8') as f:
            # 写入清理数据库的语句
            f.write("// 清理数据库\n")
            f.write("MATCH (n) DETACH DELETE n;\n\n")

            # 创建约束和索引
            f.write("// 创建约束和索引\n")
            f.write("CREATE CONSTRAINT node_id IF NOT EXISTS FOR (n) REQUIRE n.id IS UNIQUE;\n\n")

            # 写入节点创建语句
            f.write("// 创建节点\n")
            for node_name, node_type in self.nodes:
                node_key = f"{node_name}|{node_type}"
                properties = self.node_properties[node_key]

                # 转义单引号
                name_escaped = node_name.replace("'", "\\'")
                type_escaped = node_type.replace("'", "\\'")

                f.write(f"CREATE (n:{type_escaped} {{id: '{name_escaped}', name: '{name_escaped}'")

                # 添加其他属性
                for key, value in properties.items():
                    if key not in ['name', 'type']:
                        value_str = str(value).replace("'", "\\'")
                        f.write(f", {key}: '{value_str}'")

                f.write("});\n")

            f.write("\n// 创建关系\n")
            for source, relationship, target in self.edges:
                edge_key = f"{source}|{relationship}|{target}"
                properties = self.edge_properties[edge_key]

                # 转义单引号
                source_escaped = source.replace("'", "\\'")
                relationship_escaped = relationship.replace("'", "\\'")
                target_escaped = target.replace("'", "\\'")

                f.write(f"MATCH (a {{id: '{source_escaped}'}}), (b {{id: '{target_escaped}'}}) ")
                f.write(f"CREATE (a)-[:{relationship_escaped} ")

                # 添加关系属性
                if len(properties) > 3:  # 超过source, relationship, target
                    f.write("{")
                    prop_list = []
                    for key, value in properties.items():
                        if key not in ['source', 'relationship', 'target']:
                            value_str = str(value).replace("'", "\\'")
                            prop_list.append(f"{key}: '{value_str}'")
                    f.write(", ".join(prop_list))
                    f.write("}")
                f.write("]->(b);\n")

        print(f"Neo4j Cypher查询已保存到: {output_file}")

    def generate_json_graph(self, output_file: str):
        """生成JSON格式的图数据"""
        print(f"\n生成JSON图数据: {output_file}")

        # 转换为节点和边的列表
        nodes_list = []
        for node_name, node_type in self.nodes:
            node_key = f"{node_name}|{node_type}"
            properties = self.node_properties[node_key].copy()
            properties['id'] = node_name
            properties['label'] = node_type
            nodes_list.append(properties)

        edges_list = []
        for source, relationship, target in self.edges:
            edge_key = f"{source}|{relationship}|{target}"
            properties = self.edge_properties[edge_key].copy()
            properties['id'] = f"{source}-{relationship}-{target}"
            properties['source'] = source
            properties['target'] = target
            properties['type'] = relationship
            edges_list.append(properties)

        graph_data = {
            'nodes': nodes_list,
            'edges': edges_list,
            'metadata': {
                'total_nodes': len(self.nodes),
                'total_edges': len(self.edges),
                'node_types': dict(self.node_types),
                'relationship_types': dict(self.relationship_types),
                'species': dict(self.species)
            }
        }

        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(graph_data, f, ensure_ascii=False, indent=2)

        print(f"JSON图数据已保存到: {output_file}")

    def generate_statistics(self):
        """生成统计信息"""
        print("\n=== 知识图谱统计信息 ===")
        print(f"节点总数: {len(self.nodes)}")
        print(f"边总数: {len(self.edges)}")
        print(f"节点类型数: {len(self.node_types)}")
        print(f"关系类型数: {len(self.relationship_types)}")
        print(f"物种数: {len(self.species)}")

        print("\n节点类型分布:")
        for node_type, count in self.node_types.most_common():
            print(f"  {node_type}: {count}")

        print("\n关系类型分布:")
        for rel_type, count in self.relationship_types.most_common(15):
            print(f"  {rel_type}: {count}")

        print("\n物种分布:")
        for species, count in self.species.most_common(10):
            print(f"  {species}: {count}")

    def build_graph(self):
        """构建完整的知识图谱"""
        print("开始构建植物知识图谱...")
        print("=" * 50)

        # 加载数据
        self.load_data()

        # 处理节点和边
        self.process_nodes()
        self.process_edges()

        # 生成输出文件
        self.generate_statistics()

        # 生成Neo4j Cypher查询
        cypher_file = "output/plant_kg.cypher"
        self.generate_neo4j_cypher(cypher_file)

        # 生成JSON图数据
        json_file = "output/plant_kg.json"
        self.generate_json_graph(json_file)

        print("\n" + "=" * 50)
        print("知识图谱构建完成!")
        print(f"输出文件:")
        print(f"  - Neo4j Cypher: {cypher_file}")
        print(f"  - JSON图数据: {json_file}")

        return {
            'nodes': self.nodes,
            'edges': self.edges,
            'node_properties': dict(self.node_properties),
            'edge_properties': dict(self.edge_properties)
        }

def main():
    """主函数"""
    csv_file = os.getenv("KG_CSV_FILE", "examples/sample_kg.csv")

    try:
        # 创建知识图谱构建器
        builder = PlantKnowledgeGraphBuilder(csv_file)

        # 构建图谱
        graph = builder.build_graph()

        print("\n✅ 知识图谱构建成功!")
        return graph

    except Exception as e:
        print(f"❌ 构建知识图谱时出错: {e}")
        import traceback
        traceback.print_exc()
        return None

if __name__ == "__main__":
    main()
