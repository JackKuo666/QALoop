#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
植物知识图谱系统配置文件
"""

import os

# Neo4j配置
NEO4J_CONFIG = {
    'uri': os.getenv('NEO4J_URI', 'bolt://localhost:7687'),
    'username': os.getenv('NEO4J_USER', 'neo4j'),
    'password': os.getenv('NEO4J_PASSWORD', ''),
    'database': 'plant_kg'
}

# NetworkX配置 (备用方案)
NETWORKX_CONFIG = {
    'directed': True,  # 知识图谱是有向图
    'multi': False    # 单一关系边
}

# 图算法配置
GRAPH_ALGORITHMS = {
    'community_detection': {
        'method': 'louvain',  # louvain, leiden, label_propagation
        'threshold': 0.5
    },
    'centrality': {
        'methods': ['betweenness', 'closeness', 'degree', 'eigenvector'],
        'top_k': 20
    },
    'path_analysis': {
        'max_path_length': 5,
        'path_limit': 100
    }
}

# 多跳推理配置
MULTIHOP_CONFIG = {
    'max_hops': 5,  # 最大跳数
    'timeout': 30,   # 查询超时(秒)
    'max_paths': 1000  # 最大路径数
}

# 数据导入配置
IMPORT_CONFIG = {
    'batch_size': 10000,
    'create_constraints': True,
    'create_indexes': True,
    'sample_size': None  # None表示导入全部数据
}

# API配置
API_CONFIG = {
    'host': '0.0.0.0',
    'port': 8000,
    'debug': True,
    'workers': 4
}

# 缓存配置
CACHE_CONFIG = {
    'enabled': True,
    'ttl': 3600,  # 1小时
    'max_size': 1000
}
