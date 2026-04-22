#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
植物知识图谱Web API
"""

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Dict, List, Optional
import uvicorn
import json
from pathlib import Path

from .database import PlantKnowledgeGraph, GraphAnalyzer, MultiHopReasoningEngine
from .analyzer import ComprehensiveAnalyzer, VisualizationHelper
from .config import API_CONFIG


# Pydantic模型
class NodeQuery(BaseModel):
    node_id: str


class PathQuery(BaseModel):
    start_entity: str
    end_entity: str
    max_hops: int = 5


class AnalysisQuery(BaseModel):
    center_node: str
    radius: int = 2


# 创建FastAPI应用
app = FastAPI(
    title="植物知识图谱API",
    description="可持续使用的植物知识图谱系统，支持多跳推理和图算法分析",
    version="1.0.0"
)

# 添加CORS中间件
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 全局变量
kg = None
analyzer = None
reasoner = None
visualizer = None


@app.on_event("startup")
async def startup_event():
    """应用启动事件"""
    global kg, analyzer, reasoner, visualizer

    print("\n🚀 植物知识图谱系统启动中...")
    print("=" * 80)

    # 初始化图谱（使用NetworkX作为后端）
    kg = PlantKnowledgeGraph(backend='networkx')

    # 加载示例数据或从文件加载
    csv_file = os.getenv("KG_CSV_FILE", "examples/sample_kg.csv")
    if Path(csv_file).exists():
        print(f"📥 加载数据: {csv_file}")
        kg.load_from_csv(csv_file, sample_size=50000)  # 加载5万条边作为示例
    else:
        print("⚠️  未找到数据文件，使用示例数据")
        _load_sample_data()

    # 初始化分析器
    analyzer = ComprehensiveAnalyzer(kg)
    reasoner = MultiHopReasoningEngine(kg)
    visualizer = VisualizationHelper(kg)

    # 运行基础分析
    print("\n🔬 运行基础图分析...")
    basic_analysis = analyzer.run_full_analysis()

    # 保存分析结果
    output_dir = Path("output")
    output_dir.mkdir(exist_ok=True)
    analyzer.save_analysis(basic_analysis, output_dir / "api_analysis_results.json")

    print("\n✅ 系统启动完成!")
    print("=" * 80)
    print(f"🌐 API文档: http://localhost:{API_CONFIG['port']}/docs")
    print("=" * 80)


def _load_sample_data():
    """加载示例数据"""
    sample_nodes = [
        ('Arabidopsis thaliana', 'organism'),
        ('Oryza sativa', 'organism'),
        ('DREB2A', 'gene'),
        ('OsNAC6', 'gene'),
        ('drought resistance', 'phenotype'),
        ('salt tolerance', 'phenotype'),
        ('root development', 'process'),
        ('protein1', 'protein'),
    ]

    for node_id, node_type in sample_nodes:
        kg.add_node(node_id, node_type)

    sample_edges = [
        ('Arabidopsis thaliana', 'DREB2A', 'contain'),
        ('Oryza sativa', 'OsNAC6', 'contain'),
        ('DREB2A', 'drought resistance', 'regulate'),
        ('OsNAC6', 'drought resistance', 'regulate'),
        ('OsNAC6', 'root development', 'affect'),
        ('DREB2A', 'salt tolerance', 'regulate'),
        ('root development', 'drought resistance', 'influence'),
    ]

    for source, target, relation in sample_edges:
        kg.add_edge(source, target, relation)


# API路由

@app.get("/", response_class=HTMLResponse)
async def root():
    """主页"""
    return """
    <!DOCTYPE html>
    <html>
    <head>
        <title>植物知识图谱系统</title>
        <meta charset="UTF-8">
        <style>
            body { font-family: Arial, sans-serif; margin: 40px; }
            h1 { color: #2c3e50; }
            .api-link { background: #3498db; color: white; padding: 10px 20px;
                       text-decoration: none; border-radius: 5px; }
            .info { background: #ecf0f1; padding: 20px; border-radius: 5px; margin: 20px 0; }
        </style>
    </head>
    <body>
        <h1>🌱 植物知识图谱系统</h1>
        <div class="info">
            <h2>系统特性</h2>
            <ul>
                <li>✅ 支持多跳推理</li>
                <li>✅ 图算法分析</li>
                <li>✅ 中心性分析</li>
                <li>✅ 社区检测</li>
                <li>✅ 可视化导出</li>
            </ul>
        </div>
        <p>
            <a class="api-link" href="/docs">📚 查看API文档</a>
            <a class="api-link" href="/stats" style="margin-left: 10px;">📊 查看统计信息</a>
        </p>
    </body>
    </html>
    """


@app.get("/stats")
async def get_stats():
    """获取图统计信息"""
    if not kg:
        raise HTTPException(status_code=503, detail="系统未初始化")

    stats = kg.get_statistics()
    return JSONResponse(stats)


@app.get("/nodes/{node_id}")
async def get_node(node_id: str):
    """获取节点信息"""
    if not kg:
        raise HTTPException(status_code=503, detail="系统未初始化")

    node = kg.get_node(node_id)
    if not node:
        raise HTTPException(status_code=404, detail=f"节点 {node_id} 不存在")

    return JSONResponse(node)


@app.get("/nodes/{node_id}/neighbors")
async def get_neighbors(node_id: str):
    """获取邻居节点"""
    if not kg:
        raise HTTPException(status_code=503, detail="系统未初始化")

    neighbors = kg.get_neighbors(node_id)
    return JSONResponse({
        'node_id': node_id,
        'neighbors': neighbors,
        'count': len(neighbors)
    })


@app.post("/path")
async def find_path(query: PathQuery):
    """查找路径"""
    if not kg:
        raise HTTPException(status_code=503, detail="系统未初始化")

    paths = kg.find_path(
        query.start_entity,
        query.end_entity,
        query.max_hops
    )

    return JSONResponse({
        'start_entity': query.start_entity,
        'end_entity': query.end_entity,
        'paths': paths,
        'count': len(paths)
    })


@app.post("/reason")
async def reason_path(query: PathQuery):
    """推理路径"""
    if not reasoner:
        raise HTTPException(status_code=503, detail="推理引擎未初始化")

    result = reasoner.reason_path(
        query.start_entity,
        query.end_entity,
        query.max_hops
    )

    return JSONResponse(result)


@app.post("/analyze/full")
async def run_full_analysis():
    """运行完整分析"""
    if not analyzer:
        raise HTTPException(status_code=503, detail="分析器未初始化")

    results = analyzer.run_full_analysis()
    return JSONResponse(results)


@app.post("/analyze/centrality")
async def analyze_centrality(methods: List[str] = Query(None)):
    """分析中心性"""
    if not analyzer:
        raise HTTPException(status_code=503, detail="分析器未初始化")

    if not methods:
        methods = ['degree', 'betweenness', 'closeness']

    results = analyzer.graph_analyzer.calculate_centrality(methods)
    return JSONResponse(results)


@app.post("/analyze/communities")
async def detect_communities():
    """检测社区"""
    if not analyzer:
        raise HTTPException(status_code=503, detail="分析器未初始化")

    results = analyzer.graph_analyzer.detect_communities()
    return JSONResponse(results)


@app.post("/analyze/important-nodes")
async def find_important_nodes(top_k: int = Query(20, ge=1, le=100)):
    """查找重要节点"""
    if not analyzer:
        raise HTTPException(status_code=503, detail="分析器未初始化")

    results = analyzer.graph_analyzer.find_important_nodes(k=top_k)
    return JSONResponse(results)


@app.post("/analyze/hub-genes")
async def find_hub_genes(top_k: int = Query(20, ge=1, le=100)):
    """查找中心基因"""
    if not analyzer:
        raise HTTPException(status_code=503, detail="分析器未初始化")

    results = analyzer.identify_hub_genes(top_k=top_k)
    return JSONResponse(results)


@app.post("/analyze/phenotype")
async def analyze_phenotype(phenotype: str = Query(...)):
    """分析表型关联"""
    if not analyzer:
        raise HTTPException(status_code=503, detail="分析器未初始化")

    results = analyzer.analyze_phenotype_associations(phenotype)
    return JSONResponse(results)


@app.post("/visualize/subgraph")
async def visualize_subgraph(center_node: str = Query(...), radius: int = Query(2, ge=1, le=5)):
    """生成子图"""
    if not visualizer:
        raise HTTPException(status_code=503, detail="可视化器未初始化")

    subgraph = visualizer.generate_subgraph(center_node, radius)

    # 转换为JSON
    nodes = [{'id': n, **subgraph.nodes[n]} for n in subgraph.nodes()]
    edges = [{'source': u, 'target': v, **subgraph.edges[u, v]}
             for u, v in subgraph.edges()]

    return JSONResponse({
        'center_node': center_node,
        'radius': radius,
        'nodes': nodes,
        'edges': edges
    })


@app.post("/visualize/export-cytoscape")
async def export_cytoscape(center_node: str = Query(...),
                          radius: int = Query(2, ge=1, le=5)):
    """导出为Cytoscape格式"""
    if not visualizer:
        raise HTTPException(status_code=503, detail="可视化器未初始化")

    subgraph = visualizer.generate_subgraph(center_node, radius)

    output_file = f"output/subgraph_{center_node.replace(' ', '_')}.json"
    visualizer.export_for_cytoscape(subgraph, output_file)

    return JSONResponse({
        'message': '导出成功',
        'file': output_file
    })


@app.get("/search")
async def search_nodes(q: str = Query(..., min_length=2)):
    """搜索节点"""
    if not kg:
        raise HTTPException(status_code=503, detail="系统未初始化")

    # 简单的名称搜索
    results = []
    for node_id in kg.graph.nodes():
        if q.lower() in node_id.lower():
            node_data = kg.get_node(node_id)
            results.append({
                'id': node_id,
                'type': node_data.get('type', 'unknown')
            })

            if len(results) >= 20:  # 限制返回数量
                break

    return JSONResponse({
        'query': q,
        'results': results,
        'count': len(results)
    })


# CLI入口点
def run_server():
    """运行API服务器"""
    uvicorn.run(
        "kg_system.api:app",
        host=API_CONFIG['host'],
        port=API_CONFIG['port'],
        reload=API_CONFIG['debug']
    )


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description='植物知识图谱API服务器')
    parser.add_argument('--host', default=API_CONFIG['host'], help='服务器主机')
    parser.add_argument('--port', type=int, default=API_CONFIG['port'], help='服务器端口')
    parser.add_argument('--reload', action='store_true', help='自动重载')

    args = parser.parse_args()

    print("=" * 80)
    print("🌱 植物知识图谱系统 API")
    print("=" * 80)
    print(f"地址: http://{args.host}:{args.port}")
    print(f"文档: http://{args.host}:{args.port}/docs")
    print("=" * 80)

    uvicorn.run(
        "kg_system.api:app",
        host=args.host,
        port=args.port,
        reload=args.reload
    )
