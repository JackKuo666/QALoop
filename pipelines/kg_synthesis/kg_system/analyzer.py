#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
植物知识图谱图算法分析器
"""

import json
import time
from typing import Dict, List, Tuple, Any
from pathlib import Path
import networkx as nx
from collections import defaultdict, Counter

from .database import GraphAnalyzer, MultiHopReasoningEngine
from .config import GRAPH_ALGORITHMS


class ComprehensiveAnalyzer:
    """综合分析器"""

    def __init__(self, kg):
        """初始化"""
        self.kg = kg
        self.graph_analyzer = GraphAnalyzer(kg)
        self.reasoner = MultiHopReasoningEngine(kg)

    def run_full_analysis(self) -> Dict:
        """运行完整分析"""
        print("=" * 80)
        print("🔬 开始综合图分析")
        print("=" * 80)

        results = {
            'timestamp': time.strftime('%Y-%m-%d %H:%M:%S'),
            'basic_stats': {},
            'centrality': {},
            'communities': {},
            'important_nodes': {},
            'path_analysis': {},
            'network_properties': {}
        }

        # 1. 基础统计
        print("\n📊 1. 基础统计分析")
        results['basic_stats'] = self.kg.get_statistics()

        # 2. 中心性分析
        print("\n📊 2. 中心性分析")
        centrality_methods = GRAPH_ALGORITHMS['centrality']['methods']
        results['centrality'] = self.graph_analyzer.calculate_centrality(centrality_methods)

        # 3. 社区检测
        print("\n🔍 3. 社区检测")
        results['communities'] = self.graph_analyzer.detect_communities()

        # 4. 重要节点识别
        print("\n🎯 4. 重要节点识别")
        results['important_nodes'] = self.graph_analyzer.find_important_nodes(
            k=GRAPH_ALGORITHMS['centrality']['top_k']
        )

        # 5. 路径分析
        print("\n📏 5. 路径分析")
        results['path_analysis'] = self.graph_analyzer.analyze_shortest_paths()

        # 6. 网络属性
        print("\n🌐 6. 网络属性分析")
        results['network_properties'] = self._analyze_network_properties()

        print("\n" + "=" * 80)
        print("✅ 综合分析完成")
        print("=" * 80)

        return results

    def _analyze_network_properties(self) -> Dict:
        """分析网络属性"""
        if self.kg.backend != 'networkx':
            return {'note': 'NetworkX required for detailed analysis'}

        properties = {}

        # 密度
        density = nx.density(self.kg.graph)
        properties['density'] = density

        # 连通性
        is_connected = nx.is_weakly_connected(self.kg.graph)
        properties['is_connected'] = is_connected

        if is_connected:
            # 直径
            try:
                diameter = nx.diameter(self.kg.graph.to_undirected())
                properties['diameter'] = diameter
            except:
                properties['diameter'] = 'N/A'

            # 平均路径长度
            try:
                avg_path_length = nx.average_shortest_path_length(
                    self.kg.graph.to_undirected()
                )
                properties['avg_path_length'] = avg_path_length
            except:
                properties['avg_path_length'] = 'N/A'

        # 聚类系数
        try:
            clustering = nx.average_clustering(self.kg.graph.to_undirected())
            properties['clustering_coefficient'] = clustering
        except:
            properties['clustering_coefficient'] = 'N/A'

        return properties

    def find_key_regulatory_paths(self, gene: str, phenotype: str) -> Dict:
        """查找关键的调控路径"""
        print(f"\n🔍 查找调控路径: {gene} -> {phenotype}")

        # 查找所有路径
        paths = self.kg.find_path(gene, phenotype, max_hops=5)

        if not paths:
            return {
                'found': False,
                'message': f'未找到 {gene} 到 {phenotype} 的路径'
            }

        # 分析路径
        analyzed_paths = []
        for path in paths:
            score = self._calculate_path_score(path)
            analyzed_paths.append({
                'entities': path['entities'],
                'edges': path['edges'],
                'score': score,
                'hops': path['hops'],
                'explanation': self._explain_regulatory_path(path)
            })

        # 按得分排序
        analyzed_paths.sort(key=lambda x: x['score'], reverse=True)

        return {
            'found': True,
            'count': len(analyzed_paths),
            'top_paths': analyzed_paths[:10],
            'source': gene,
            'target': phenotype
        }

    def _calculate_path_score(self, path: Dict) -> float:
        """计算路径得分"""
        # 基于路径长度和关系类型计算得分
        hops = path['hops']
        relations = [edge['relation'] for edge in path['edges']]

        # 重要关系类型加权
        relation_weights = {
            'regulate': 1.0,
            'encode': 0.9,
            'interact with': 0.8,
            'affect': 0.7,
            'involved in': 0.6
        }

        weight_sum = sum(relation_weights.get(rel, 0.5) for rel in relations)
        avg_weight = weight_sum / len(relations)

        # 路径越短得分越高
        length_score = 1.0 / (1.0 + hops)

        # 综合得分
        score = avg_weight * 0.7 + length_score * 0.3

        return score

    def _explain_regulatory_path(self, path: Dict) -> str:
        """解释调控路径"""
        entities = path['entities']
        edges = path['edges']

        explanation = f"通过{len(edges)}步调控: "
        steps = []

        for edge in edges:
            from_node = edge['from']
            relation = edge['relation']
            to_node = edge['to']
            steps.append(f"{from_node} {relation} {to_node}")

        explanation += "，然后".join(steps)

        return explanation

    def identify_hub_genes(self, top_k: int = 20) -> Dict:
        """识别中心基因"""
        print(f"\n🧬 识别Top {top_k}中心基因")

        # 获取度中心性
        degree_centrality = nx.degree_centrality(self.kg.graph)

        # 获取介数中心性
        betweenness_centrality = nx.betweenness_centrality(self.kg.graph)

        # 只考虑基因节点
        gene_nodes = {}
        for node_id in self.kg.graph.nodes():
            node_data = self.kg.graph.nodes[node_id]
            if node_data.get('type') == 'gene':
                gene_nodes[node_id] = {
                    'degree': degree_centrality.get(node_id, 0),
                    'betweenness': betweenness_centrality.get(node_id, 0),
                    'combined_score': (
                        degree_centrality.get(node_id, 0) * 0.4 +
                        betweenness_centrality.get(node_id, 0) * 0.6
                    )
                }

        # 排序
        sorted_genes = sorted(
            gene_nodes.items(),
            key=lambda x: x[1]['combined_score'],
            reverse=True
        )[:top_k]

        return {
            'hub_genes': [
                {
                    'gene': gene,
                    'degree_centrality': data['degree'],
                    'betweenness_centrality': data['betweenness'],
                    'combined_score': data['combined_score']
                }
                for gene, data in sorted_genes
            ],
            'criteria': '综合中心性 (度中心性40% + 介数中心性60%)',
            'total_genes': len(gene_nodes)
        }

    def find_common_neighbors(self, node1: str, node2: str) -> Dict:
        """查找两个节点的共同邻居"""
        print(f"\n🔍 查找共同邻居: {node1} 与 {node2}")

        neighbors1 = set(self.kg.graph.neighbors(node1))
        neighbors2 = set(self.kg.graph.neighbors(node2))

        common = neighbors1 & neighbors2
        unique1 = neighbors1 - neighbors2
        unique2 = neighbors2 - neighbors1

        return {
            'common_neighbors': list(common),
            'count_common': len(common),
            'unique_to_node1': list(unique1),
            'unique_to_node2': list(unique2),
            'jaccard_similarity': len(common) / len(neighbors1 | neighbors2) if neighbors1 | neighbors2 else 0
        }

    def analyze_phenotype_associations(self, phenotype: str) -> Dict:
        """分析表型关联"""
        print(f"\n🧬 分析表型关联: {phenotype}")

        # 查找与表型相关的所有实体
        neighbors = self.kg.get_neighbors(phenotype)

        # 按类型分组
        type_groups = defaultdict(list)
        for neighbor in neighbors:
            node_type = neighbor['data'].get('type', 'unknown')
            type_groups[node_type].append(neighbor)

        # 分析每个类型
        analysis = {}
        for node_type, nodes in type_groups.items():
            relations = []
            for node in nodes:
                relations.extend(node['relations'])

            analysis[node_type] = {
                'count': len(nodes),
                'top_nodes': [n['id'] for n in nodes[:10]],
                'relation_distribution': dict(Counter(relations))
            }

        return {
            'phenotype': phenotype,
            'associated_types': analysis,
            'total_associations': len(neighbors)
        }

    def save_analysis(self, results: Dict, output_file: str):
        """保存分析结果"""
        Path(output_file).parent.mkdir(parents=True, exist_ok=True)

        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(results, f, ensure_ascii=False, indent=2)

        print(f"\n✅ 分析结果已保存到: {output_file}")


class VisualizationHelper:
    """可视化辅助类"""

    def __init__(self, kg):
        self.kg = kg

    def generate_subgraph(self, center_node: str, radius: int = 2) -> nx.Graph:
        """生成子图"""
        print(f"\n🎨 生成子图: {center_node} (半径: {radius})")

        # 使用BFS获取邻居
        if self.kg.backend == 'networkx':
            nodes = {center_node}
            current_level = {center_node}

            for _ in range(radius):
                next_level = set()
                for node in current_level:
                    next_level.update(self.kg.graph.neighbors(node))
                current_level = next_level
                nodes.update(current_level)

            subgraph = self.kg.graph.subgraph(nodes)
            return subgraph

        else:
            raise NotImplementedError("Only NetworkX supported for visualization")

    def export_for_cytoscape(self, subgraph: nx.Graph, output_file: str):
        """导出为Cytoscape格式"""
        print(f"\n💾 导出为Cytoscape格式: {output_file}")

        # 转换为节点和边列表
        nodes = []
        edges = []

        for node_id in subgraph.nodes():
            node_data = subgraph.nodes[node_id]
            nodes.append({
                'id': node_id,
                'label': node_id,
                'type': node_data.get('type', 'unknown')
            })

        for source, target in subgraph.edges():
            edge_data = subgraph.get_edge_data(source, target)
            edges.append({
                'source': source,
                'target': target,
                'relation': edge_data.get('relation', '')
            })

        cytoscape_data = {
            'nodes': nodes,
            'edges': edges
        }

        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(cytoscape_data, f, ensure_ascii=False, indent=2)

        print(f"✅ Cytoscape文件已导出: {output_file}")
        print(f"   节点数: {len(nodes)}")
        print(f"   边数: {len(edges)}")


# 使用示例
if __name__ == "__main__":
    # 测试代码
    from database import PlantKnowledgeGraph

    print("🧪 图算法分析器测试")

    # 创建测试图
    kg = PlantKnowledgeGraph(backend='networkx')

    # 添加测试数据
    test_data = [
        ('Arabidopsis', 'organism'),
        ('gene1', 'gene'),
        ('gene2', 'gene'),
        ('drought resistance', 'phenotype'),
        ('seed yield', 'phenotype'),
    ]

    for node, node_type in test_data:
        kg.add_node(node, node_type)

    kg.add_edge('Arabidopsis', 'gene1', 'contain')
    kg.add_edge('gene1', 'drought resistance', 'regulate')
    kg.add_edge('gene1', 'seed yield', 'regulate')
    kg.add_edge('gene2', 'drought resistance', 'regulate')

    # 运行分析
    analyzer = ComprehensiveAnalyzer(kg)
    results = analyzer.run_full_analysis()

    print("\n✅ 测试完成!")
