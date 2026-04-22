#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
植物知识图谱数据库接口
支持NetworkX和Neo4j两种后端
"""

import networkx as nx
from typing import Dict, List, Tuple, Optional, Any
import json
from pathlib import Path
from collections import defaultdict, Counter
import time

class PlantKnowledgeGraph:
    """植物知识图谱主类"""

    def __init__(self, backend='networkx'):
        """
        初始化知识图谱

        Args:
            backend: 'networkx' 或 'neo4j'
        """
        self.backend = backend
        self.graph = None

        if backend == 'networkx':
            self._init_networkx()
        elif backend == 'neo4j':
            self._init_neo4j()
        else:
            raise ValueError(f"Unsupported backend: {backend}")

    def _init_networkx(self):
        """初始化NetworkX图"""
        self.graph = nx.MultiDiGraph()
        print("✅ NetworkX图初始化完成")

    def _init_neo4j(self):
        """初始化Neo4j连接"""
        try:
            from neo4j import GraphDatabase
            from .config import NEO4J_CONFIG

            self.driver = GraphDatabase.driver(
                NEO4J_CONFIG['uri'],
                auth=(NEO4J_CONFIG['username'], NEO4J_CONFIG['password'])
            )
            print("✅ Neo4j连接已建立")
        except ImportError:
            print("❌ Neo4j驱动未安装，使用NetworkX替代")
            self.backend = 'networkx'
            self._init_networkx()

    def add_node(self, node_id: str, node_type: str, properties: Dict = None):
        """添加节点"""
        if self.backend == 'networkx':
            self.graph.add_node(
                node_id,
                type=node_type,
                **(properties or {})
            )
        elif self.backend == 'neo4j':
            with self.driver.session() as session:
                session.run(
                    "MERGE (n:Entity {id: $id, type: $type})",
                    id=node_id, type=node_type
                )

    def add_edge(self, source: str, target: str, relation: str, properties: Dict = None):
        """添加边"""
        if self.backend == 'networkx':
            self.graph.add_edge(
                source, target,
                relation=relation,
                **(properties or {})
            )
        elif self.backend == 'neo4j':
            with self.driver.session() as session:
                session.run(
                    """
                    MATCH (a:Entity {id: $source})
                    MATCH (b:Entity {id: $target})
                    MERGE (a)-[r:RELATES {relation: $relation}]->(b)
                    """,
                    source=source, target=target, relation=relation
                )

    def get_node(self, node_id: str) -> Optional[Dict]:
        """获取节点信息"""
        if self.backend == 'networkx':
            if node_id in self.graph.nodes:
                data = self.graph.nodes[node_id].copy()
                data['id'] = node_id
                return data
            return None

        elif self.backend == 'neo4j':
            with self.driver.session() as session:
                result = session.run(
                    "MATCH (n:Entity {id: $id}) RETURN n",
                    id=node_id
                )
                record = result.single()
                if record:
                    node = record['n']
                    return dict(node)
                return None

    def get_neighbors(self, node_id: str) -> List[Dict]:
        """获取邻居节点"""
        if self.backend == 'networkx':
            neighbors = []
            for neighbor in self.graph.neighbors(node_id):
                edge_data = self.graph.get_edge_data(node_id, neighbor)
                neighbors.append({
                    'id': neighbor,
                    'data': self.graph.nodes[neighbor],
                    'relations': [edge_data.get('relation', '')]
                })
            return neighbors

        elif self.backend == 'neo4j':
            with self.driver.session() as session:
                result = session.run(
                    """
                    MATCH (n:Entity {id: $id})-[r]->(m:Entity)
                    RETURN m, r.relation as relation
                    """,
                    id=node_id
                )
                return [
                    {
                        'id': record['m']['id'],
                        'data': dict(record['m']),
                        'relations': [record['relation']]
                    }
                    for record in result
                ]

    def find_path(self, start: str, end: str, max_hops: int = 5) -> List[Dict]:
        """查找两点间的所有路径"""
        if self.backend == 'networkx':
            try:
                paths = list(nx.all_simple_paths(
                    self.graph, start, end, cutoff=max_hops
                ))

                result = []
                for path in paths:
                    path_info = {
                        'entities': path,
                        'edges': [],
                        'hops': len(path) - 1
                    }

                    for i in range(len(path) - 1):
                        edge_data = self.graph.get_edge_data(path[i], path[i+1])
                        path_info['edges'].append({
                            'from': path[i],
                            'to': path[i+1],
                            'relation': edge_data.get('relation', '')
                        })

                    result.append(path_info)

                return result
            except (nx.NetworkXNoPath, nx.NodeNotFound):
                return []

        elif self.backend == 'neo4j':
            with self.driver.session() as session:
                query = f"""
                MATCH path = (a:Entity {{id: $start}})-[:RELATES*1..{max_hops}]->(b:Entity {{id: $end}})
                RETURN path
                LIMIT 100
                """
                result = session.run(query, start=start, end=end)

                paths = []
                for record in result:
                    path = record['path']
                    nodes = list(path.nodes)
                    edges = list(path.relationships)

                    path_info = {
                        'entities': [node['id'] for node in nodes],
                        'edges': [
                            {
                                'from': edges[i]['start']['id'],
                                'to': edges[i]['end']['id'],
                                'relation': edges[i]['relation']
                            }
                            for i in range(len(edges))
                        ],
                        'hops': len(edges)
                    }
                    paths.append(path_info)

                return paths

    def find_random_causal_path(self, max_hops: int = 3) -> Optional[Dict]:
        """查找随机的因果路径"""
        import random

        if self.backend == 'networkx':
            # 从NetworkX图中查找随机路径
            nodes = list(self.graph.nodes())
            if len(nodes) < 2:
                return None

            # 随机选择起点
            start = random.choice(nodes)

            # 尝试找到一条路径
            for _ in range(100):  # 最多尝试100次
                # 随机选择终点（不是起点）
                end_candidates = [n for n in nodes if n != start]
                if not end_candidates:
                    break
                end = random.choice(end_candidates)

                try:
                    # 查找路径
                    paths = list(nx.all_simple_paths(self.graph, start, end, cutoff=max_hops))
                    if paths:
                        path = random.choice(paths)
                        edges = []
                        for i in range(len(path) - 1):
                            edge_data = self.graph.get_edge_data(path[i], path[i+1])
                            if edge_data:
                                edges.append({
                                    'from': path[i],
                                    'to': path[i+1],
                                    'relation': edge_data.get('relation', '')
                                })
                        return {
                            'nodes': [{'name': n} for n in path],
                            'edges': edges
                        }
                except (nx.NetworkXNoPath, KeyError):
                    continue

            return None

        elif self.backend == 'neo4j':
            # 从Neo4j中查找随机路径
            try:
                with self.driver.session() as session:
                    result = session.run(
                        """
                        MATCH path = (n:Entity)-[*..%d]->(m:Entity)
                        WHERE n <> m
                        RETURN path
                        LIMIT 1
                        """ % max_hops
                    )
                    records = list(result)
                    if records:
                        path = records[0]['path']
                        nodes = [node['id'] for node in path.nodes]
                        edges = []
                        for rel in path.relationships:
                            edges.append({
                                'from': rel.start['id'],
                                'to': rel.end['id'],
                                'relation': rel.get('relation', '')
                            })
                        return {
                            'nodes': [{'name': n} for n in nodes],
                            'edges': edges
                        }
            except Exception:
                pass

            return None

        return None

    def get_statistics(self) -> Dict:
        """获取图统计信息"""
        if self.backend == 'networkx':
            stats = {
                'nodes': self.graph.number_of_nodes(),
                'edges': self.graph.number_of_edges(),
                'is_directed': self.graph.is_directed(),
                'node_types': Counter(
                    data.get('type', 'unknown')
                    for data in self.graph.nodes.values()
                ),
                'relation_types': Counter(
                    data.get('relation', 'unknown')
                    for _, _, data in self.graph.edges(data=True)
                )
            }
            return stats

        elif self.backend == 'neo4j':
            try:
                with self.driver.session() as session:
                    # 查询节点数量
                    node_count = session.run("MATCH (n) RETURN count(n) as count").single()['count']
                    # 查询边数量
                    edge_count = session.run("MATCH ()-[r]->() RETURN count(r) as count").single()['count']
                    # 查询节点类型
                    type_result = session.run("MATCH (n) RETURN n.type as type, count(n) as count")
                    node_types = Counter(record['type'] for record in type_result)
                    # 查询关系类型
                    relation_result = session.run("MATCH ()-[r]->() RETURN r.relation as relation, count(r) as count")
                    relation_types = Counter(record['relation'] for record in relation_result)

                    return {
                        'nodes': node_count,
                        'edges': edge_count,
                        'is_directed': True,
                        'node_types': node_types,
                        'relation_types': relation_types
                    }
            except Exception as e:
                print(f"⚠️  Neo4j查询失败: {e}")
                return {
                    'nodes': 0,
                    'edges': 0,
                    'is_directed': True,
                    'node_types': Counter(),
                    'relation_types': Counter()
                }

    def save_to_file(self, filepath: str):
        """保存图到文件"""
        if self.backend == 'networkx':
            nx.write_gml(self.graph, filepath)
            print(f"✅ 图已保存到: {filepath}")

        elif self.backend == 'neo4j':
            print("⚠️  Neo4j数据应通过数据库导出")

    def load_from_csv(self, csv_file: str, sample_size: int = None):
        """从CSV导入数据，支持两种列名格式"""
        print(f"📥 从CSV导入数据: {csv_file}")

        import csv

        edge_count = 0
        with open(csv_file, 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            fieldnames = reader.fieldnames or []

            # 自动检测列名格式
            # 优先检测 subject/relation/object 格式（更常见）
            if 'subject' in fieldnames and 'object' in fieldnames:
                col_src = 'subject'
                col_src_type = 'subject_type'
                col_rel = 'relation'
                col_tgt = 'object'
                col_tgt_type = 'object_type'
            elif 'source type' in fieldnames or 'source_type' in fieldnames:
                col_src = 'source'
                col_src_type = 'source type' if 'source type' in fieldnames else 'source_type'
                col_rel = 'relationship'
                col_tgt = 'target'
                col_tgt_type = 'target type' if 'target type' in fieldnames else 'target_type'
            else:
                print(f"⚠️ 无法识别CSV列名格式: {fieldnames}")
                return

            for row in reader:
                if sample_size and edge_count >= sample_size:
                    break

                source = row.get(col_src, '').strip()
                source_type = row.get(col_src_type, '').strip()
                relationship = row.get(col_rel, '').strip()
                target = row.get(col_tgt, '').strip()
                target_type = row.get(col_tgt_type, '').strip()

                if not all([source, source_type, relationship, target, target_type]):
                    continue

                # 添加节点
                self.add_node(source, source_type)
                self.add_node(target, target_type)

                # 添加边
                self.add_edge(source, target, relationship)

                edge_count += 1

                if edge_count % 10000 == 0:
                    print(f"  已处理 {edge_count} 条边...")

        print(f"✅ 导入完成: {edge_count} 条边")

    def close(self):
        """关闭连接"""
        if self.backend == 'neo4j' and hasattr(self, 'driver'):
            self.driver.close()
            print("✅ Neo4j连接已关闭")


# 图算法分析类
class GraphAnalyzer:
    """图算法分析器"""

    def __init__(self, kg: PlantKnowledgeGraph):
        self.kg = kg

    def calculate_centrality(self, methods: List[str] = None) -> Dict:
        """计算中心性指标"""
        if methods is None:
            methods = ['degree', 'betweenness', 'closeness']

        results = {}

        for method in methods:
            print(f"📊 计算中心性: {method}")

            if method == 'degree':
                centrality = nx.degree_centrality(self.kg.graph)
            elif method == 'betweenness':
                centrality = nx.betweenness_centrality(self.kg.graph)
            elif method == 'closeness':
                centrality = nx.closeness_centrality(self.kg.graph)
            elif method == 'eigenvector':
                try:
                    centrality = nx.eigenvector_centrality(self.kg.graph)
                except:
                    print(f"⚠️  {method}计算失败，跳过")
                    continue
            else:
                print(f"⚠️  未知的中心性方法: {method}")
                continue

            # 排序并取top 20
            top_nodes = sorted(
                centrality.items(),
                key=lambda x: x[1],
                reverse=True
            )[:20]

            results[method] = top_nodes

        return results

    def detect_communities(self) -> Dict:
        """检测社区"""
        print("🔍 检测社区...")

        # 使用Louvain算法
        try:
            import community as community_louvain
            partition = community_louvain.best_partition(self.kg.graph.to_undirected())
        except ImportError:
            print("⚠️  python-louvain未安装，使用Label Propagation")
            partition = nx.community.label_propagation_communities(self.kg.graph.to_undirected())
            partition = {node: i for i, community in enumerate(partition) for node in community}

        # 统计社区
        community_counts = Counter(partition.values())

        return {
            'partition': partition,
            'community_count': len(community_counts),
            'community_sizes': dict(community_counts.most_common()),
            'largest_community': community_counts.most_common(1)[0] if community_counts else None
        }

    def find_important_nodes(self, k: int = 20) -> Dict:
        """找出重要节点"""
        print(f"🎯 寻找Top {k}重要节点...")

        # 综合多个指标
        degree = nx.degree_centrality(self.kg.graph)
        betweenness = nx.betweenness_centrality(self.kg.graph)

        # 计算综合得分
        combined_score = {}
        for node in self.kg.graph.nodes():
            combined_score[node] = (
                degree.get(node, 0) * 0.4 +
                betweenness.get(node, 0) * 0.6
            )

        # 排序
        top_nodes = sorted(
            combined_score.items(),
            key=lambda x: x[1],
            reverse=True
        )[:k]

        return {
            'top_nodes': top_nodes,
            'criteria': '综合中心性 (度中心性40% + 介数中心性60%)'
        }

    def analyze_shortest_paths(self, sample_size: int = 100) -> Dict:
        """分析最短路径"""
        print(f"📏 分析最短路径 (采样{sample_size}个节点)...")

        nodes = list(self.kg.graph.nodes())[:sample_size]
        path_lengths = []

        for i, start in enumerate(nodes[:20]):  # 进一步采样
            try:
                lengths = nx.single_source_shortest_path_length(
                    self.kg.graph, start, cutoff=5
                )
                path_lengths.extend(lengths.values())
            except:
                continue

        if not path_lengths:
            return {'error': '无法计算路径长度'}

        return {
            'avg_path_length': sum(path_lengths) / len(path_lengths),
            'min_path_length': min(path_lengths),
            'max_path_length': max(path_lengths),
            'sample_count': len(path_lengths)
        }


# 多跳推理引擎
class MultiHopReasoningEngine:
    """多跳推理引擎"""

    def __init__(self, kg: PlantKnowledgeGraph):
        self.kg = kg

    def reason_path(self, start_entity: str, end_entity: str, max_hops: int = 5) -> Dict:
        """推理两个实体间的路径"""
        print(f"🔍 推理路径: {start_entity} -> {end_entity}")

        start_time = time.time()
        paths = self.kg.find_path(start_entity, end_entity, max_hops)

        if not paths:
            elapsed = time.time() - start_time
            return {
                'paths': [],
                'count': 0,
                'time': elapsed,
                'message': f'未找到 {start_entity} 到 {end_entity} 的路径'
            }

        # 分析路径
        analyzed_paths = []
        for path in paths:
            hops = path['hops']
            relations = [edge['relation'] for edge in path['edges']]

            analyzed_paths.append({
                'entities': path['entities'],
                'relations': relations,
                'hops': hops,
                'reasoning': self._explain_path(path)
            })

        elapsed = time.time() - start_time

        return {
            'paths': analyzed_paths,
            'count': len(analyzed_paths),
            'time': elapsed,
            'start_entity': start_entity,
            'end_entity': end_entity
        }

    def _explain_path(self, path: Dict) -> str:
        """解释推理路径"""
        entities = path['entities']
        relations = [edge['relation'] for edge in path['edges']]

        explanation = f"通过{len(relations)}步推理: "
        steps = []

        for i, (entity, relation) in enumerate(zip(entities[:-1], relations)):
            steps.append(f"{entity} {relation} {entities[i+1]}")

        explanation += "，然后".join(steps)

        return explanation

    def find_all_paths_from(self, entity: str, max_hops: int = 3, limit: int = 100) -> List[Dict]:
        """从某个实体出发找到所有可达实体"""
        print(f"🌐 从 {entity} 探索所有可达实体...")

        paths = []
        nodes = list(self.kg.graph.nodes())

        for target in nodes:
            if target == entity:
                continue

            entity_paths = self.kg.find_path(entity, target, max_hops)
            if entity_paths:
                paths.extend(entity_paths[:1])  # 只取最短路径

            if len(paths) >= limit:
                break

        return {
            'paths': paths,
            'count': len(paths),
            'source': entity,
            'max_hops': max_hops
        }


if __name__ == "__main__":
    # 测试代码
    print("🧪 植物知识图谱系统测试")

    # 创建图谱
    kg = PlantKnowledgeGraph(backend='networkx')

    # 添加测试数据
    kg.add_node('Arabidopsis thaliana', 'organism')
    kg.add_node('gene1', 'gene')
    kg.add_node('drought resistance', 'phenotype')

    kg.add_edge('Arabidopsis thaliana', 'gene1', 'contain')
    kg.add_edge('gene1', 'drought resistance', 'regulate')

    # 统计信息
    stats = kg.get_statistics()
    print(f"\n📊 图统计: {stats}")

    # 多跳推理
    reasoner = MultiHopReasoningEngine(kg)
    result = reasoner.reason_path('Arabidopsis thaliana', 'drought resistance')
    print(f"\n🔍 推理结果: {result}")

    print("\n✅ 测试完成!")
