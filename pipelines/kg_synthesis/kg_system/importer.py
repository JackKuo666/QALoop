#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
植物知识图谱数据导入器（增强版）
- 支持按“统计报告 Top 类别白名单”过滤导入
- 支持导入时同步导出 QA 候选 triples.jsonl（只包含白名单内样本）
- 修复原实现中的参数/依赖/后处理问题
"""

import csv
import json
import time
from pathlib import Path
from typing import Dict, Optional, Set, Tuple
from collections import Counter

try:
    import networkx as nx
except Exception:
    nx = None

from .database import PlantKnowledgeGraph
from .config import IMPORT_CONFIG


# -----------------------------
# 1) Default whitelists from your report
#    （你也可以用 --report-json 自动从统计报告 json 加载）
# -----------------------------

DEFAULT_TOP_NODE_TYPES: Set[str] = {
    "gene", "phenotype", "organism", "metabolite", "protein", "mutant", "treatment",
    "process", "organ", "subcellular compartment", "tissue", "cell type",
    "protein complex", "enzyme", "protein domain", "method", "genetic element",
    "technique", "gene family", "tool",
}

DEFAULT_TOP_RELATIONS: Set[str] = {
    "had", "show", "regulate", "contain", "involved in", "include", "exhibit",
    "interact with", "affect", "is", "expressed in", "induce", "resulted in",
    "cause", "increased", "leads to", "binds", "associated with", "encode",
    "is involved in", "in", "promote", "inhibit", "produce", "control",
    "induces", "display", "identified in", "enhance", "activates",
}

DEFAULT_TOP_SPECIES: Set[str] = {
    "Arabidopsis thaliana", "Oryza sativa", "Zea mays", "Solanum lycopersicum",
    "Glycine max", "Triticum aestivum", "Nicotiana tabacum", "Brassica napus",
    "Nicotiana benthamiana", "Saccharomyces cerevisiae", "Gossypium hirsutum",
    "Hordeum vulgare", "Brassica rapa", "Vitis vinifera", "Medicago truncatula",
    "Solanum tuberosum", "Homo sapiens", "Populus trichocarpa",
    "Escherichia coli", "Chlamydomonas reinhardtii",
}

# 过泛关系（可选剔除）
DEFAULT_DROP_GENERIC: Set[str] = {"had", "show", "include", "contain", "exhibit", "display", "in", "is"}


def _load_whitelists_from_report(report_json_path: Optional[str]) -> Tuple[Set[str], Set[str], Set[str]]:
    """
    从 save_stats() 写出的 stats json 里加载白名单（top_*）。
    要求字段存在：
      - top_node_types
      - top_relation_types
      - top_species
    """
    if not report_json_path:
        return DEFAULT_TOP_NODE_TYPES, DEFAULT_TOP_RELATIONS, DEFAULT_TOP_SPECIES

    p = Path(report_json_path)
    if not p.exists():
        raise FileNotFoundError(f"report_json not found: {report_json_path}")

    data = json.loads(p.read_text(encoding="utf-8"))

    node_types = set(data.get("top_node_types", {}).keys()) or DEFAULT_TOP_NODE_TYPES
    rel_types = set(data.get("top_relation_types", {}).keys()) or DEFAULT_TOP_RELATIONS
    species = set(data.get("top_species", {}).keys()) or DEFAULT_TOP_SPECIES

    return node_types, rel_types, species


class DataImporter:
    """数据导入器（增强版：白名单过滤 + QA候选导出）"""

    def __init__(
        self,
        kg_backend: str = "networkx",
        *,
        restrict_node_types: bool = False,
        restrict_relations: bool = False,
        restrict_species: bool = False,
        drop_generic_relations: bool = False,
        report_json: Optional[str] = None,
        qa_candidates_jsonl: Optional[str] = None,
    ):
        """
        Args:
            kg_backend: 'networkx' or 'neo4j' etc.
            restrict_node_types: 只保留白名单 node types（source type/target type）
            restrict_relations: 只保留白名单 relation types（relationship）
            restrict_species: 只保留白名单 species
            drop_generic_relations: 丢弃过泛关系（即使在白名单内）
            report_json: 从你的统计报告 json 加载 top 白名单；None 则用默认内置白名单
            qa_candidates_jsonl: 导入过程中把通过过滤的边写出 jsonl（用于后续 QA 生成）
        """
        self.kg = PlantKnowledgeGraph(backend=kg_backend)

        node_types, rels, species = _load_whitelists_from_report(report_json)
        self.allow_node_types = node_types
        self.allow_relations = rels
        self.allow_species = species

        self.restrict_node_types = restrict_node_types
        self.restrict_relations = restrict_relations
        self.restrict_species = restrict_species
        self.drop_generic_relations = drop_generic_relations
        self.drop_generic_set = DEFAULT_DROP_GENERIC

        self.qa_candidates_jsonl = qa_candidates_jsonl
        self._qa_fp = None

        self.stats = {
            "nodes": 0,
            "edges": 0,
            "node_types": Counter(),
            "relation_types": Counter(),
            "species": Counter(),
            "import_time": 0.0,
            # extra
            "skipped_rows": 0,
            "skipped_by_node_type": 0,
            "skipped_by_relation": 0,
            "skipped_by_species": 0,
            "qa_candidates_written": 0,
        }

    def import_csv(self, csv_file: str, sample_size: Optional[int] = None, create_constraints: bool = True) -> Dict:
        """从CSV导入数据（支持白名单过滤）"""
        print("=" * 80)
        print(f"📥 开始导入CSV数据: {csv_file}")
        print("=" * 80)

        start_time = time.time()

        if create_constraints and getattr(self.kg, "backend", None) == "neo4j":
            self._create_constraints()

        if self.qa_candidates_jsonl:
            outp = Path(self.qa_candidates_jsonl)
            outp.parent.mkdir(parents=True, exist_ok=True)
            self._qa_fp = outp.open("w", encoding="utf-8")

        try:
            self._import_csv_data(csv_file, sample_size)
            self._post_import_processing()
        finally:
            if self._qa_fp:
                self._qa_fp.close()
                self._qa_fp = None

        elapsed_time = time.time() - start_time
        self.stats["import_time"] = elapsed_time

        print("\n" + "=" * 80)
        print("✅ 导入完成")
        print("=" * 80)
        print(f"⏱️  总耗时: {elapsed_time:.2f} 秒")
        print("📊 导入统计:")
        print(f"   节点数: {self.stats['nodes']:,}")
        print(f"   边数: {self.stats['edges']:,}")
        print(f"   节点类型: {len(self.stats['node_types'])}")
        print(f"   关系类型: {len(self.stats['relation_types'])}")
        print(f"   物种数: {len(self.stats['species'])}")
        print(f"   跳过行: {self.stats['skipped_rows']:,}")
        if self.qa_candidates_jsonl:
            print(f"   QA候选写出: {self.stats['qa_candidates_written']:,} -> {self.qa_candidates_jsonl}")
        print("=" * 80)

        return self.stats

    def _create_constraints(self):
        """创建约束和索引（Neo4j）"""
        print("\n🔧 创建约束和索引...")

        if getattr(self.kg, "backend", None) == "neo4j":
            with self.kg.driver.session() as session:
                session.run("""
                    CREATE CONSTRAINT entity_id IF NOT EXISTS
                    FOR (n:Entity) REQUIRE n.id IS UNIQUE
                """)
                session.run("""
                    CREATE INDEX entity_type IF NOT EXISTS
                    FOR (n:Entity) ON (n.type)
                """)
                session.run("""
                    CREATE INDEX relation_type IF NOT EXISTS
                    FOR ()-[r:RELATES]-() ON (r.relation)
                """)
            print("  ✅ 约束和索引创建完成")

    def _row_passes_filters(self, source_type: str, relationship: str, target_type: str, species: str) -> bool:
        # 关系过滤
        if self.restrict_relations and relationship not in self.allow_relations:
            self.stats["skipped_by_relation"] += 1
            return False
        if self.drop_generic_relations and relationship in self.drop_generic_set:
            self.stats["skipped_by_relation"] += 1
            return False

        # 节点类型过滤（两端都要在白名单内）
        if self.restrict_node_types:
            if source_type not in self.allow_node_types or target_type not in self.allow_node_types:
                self.stats["skipped_by_node_type"] += 1
                return False

        # 物种过滤（可选）
        if self.restrict_species:
            if not species or species not in self.allow_species:
                self.stats["skipped_by_species"] += 1
                return False

        return True

    def _write_qa_candidate(self, source: str, source_type: str, relationship: str, target: str, target_type: str, species: str):
        if not self._qa_fp:
            return
        obj = {
            "head": source,
            "head_type": source_type,
            "relation": relationship,
            "tail": target,
            "tail_type": target_type,
            "species": species,
        }
        self._qa_fp.write(json.dumps(obj, ensure_ascii=False) + "\n")
        self.stats["qa_candidates_written"] += 1

    def _import_csv_data(self, csv_file: str, sample_size: Optional[int]):
        """导入CSV数据（带过滤）"""
        node_seen = set()
        edge_count = 0

        with open(csv_file, "r", encoding="utf-8") as f:
            reader = csv.DictReader(f)

            for row in reader:
                if sample_size and edge_count >= sample_size:
                    break

                source = (row.get("source") or "").strip()
                source_type = (row.get("source type") or "").strip()
                relationship = (row.get("relationship") or "").strip()
                target = (row.get("target") or "").strip()
                target_type = (row.get("target type") or "").strip()
                species = (row.get("species") or "").strip()

                # 跳过不完整的行
                if not all([source, source_type, relationship, target, target_type]):
                    self.stats["skipped_rows"] += 1
                    continue

                # 过滤（只允许统计报告中的类别）
                if not self._row_passes_filters(source_type, relationship, target_type, species):
                    self.stats["skipped_rows"] += 1
                    continue

                # 添加节点（去重）
                if source not in node_seen:
                    self.kg.add_node(source, source_type)
                    node_seen.add(source)
                    self.stats["nodes"] += 1
                    self.stats["node_types"][source_type] += 1

                if target not in node_seen:
                    self.kg.add_node(target, target_type)
                    node_seen.add(target)
                    self.stats["nodes"] += 1
                    self.stats["node_types"][target_type] += 1

                # 添加边（你可根据 PlantKnowledgeGraph.add_edge 支持情况，传更多属性）
                self.kg.add_edge(source, target, relationship)
                self.stats["edges"] += 1
                self.stats["relation_types"][relationship] += 1

                if species:
                    self.stats["species"][species] += 1

                # 同步写出 QA 候选
                self._write_qa_candidate(source, source_type, relationship, target, target_type, species)

                edge_count += 1
                if edge_count % 10000 == 0:
                    print(f"  📥 已处理 {edge_count:,} 条边...")

        print("\n✅ CSV数据导入完成")

    def _post_import_processing(self):
        """导入后处理"""
        print("\n🔧 执行导入后处理...")

        validation_result = self._validate_data()
        if validation_result["errors"] > 0:
            print(f"  ⚠️  发现 {validation_result['errors']} 个验证错误")
        if validation_result["warnings"]:
            for w in validation_result["warnings"][:5]:
                print(f"  ⚠️  {w}")

        self._generate_stats_report()
        print("  ✅ 导入后处理完成")

    def _validate_data(self) -> Dict:
        """验证数据质量（仅 networkx backend 且 nx 可用时执行）"""
        print("  🔍 验证数据质量...")

        errors = 0
        warnings = []

        if nx is None:
            warnings.append("networkx 未安装，跳过 isolate/self-loop 检查")
            return {"errors": errors, "warnings": warnings}

        # 仅当 backend 的图结构存在且为 networkx 兼容
        g = getattr(self.kg, "graph", None)
        if g is None:
            warnings.append("当前 backend 不暴露 graph，跳过 isolate/self-loop 检查")
            return {"errors": errors, "warnings": warnings}

        try:
            isolated_nodes = list(nx.isolates(g))
            if isolated_nodes:
                warnings.append(f"发现 {len(isolated_nodes)} 个孤立节点")
            self_loops = list(nx.selfloop_edges(g))
            if self_loops:
                warnings.append(f"发现 {len(self_loops)} 个自环边")
        except Exception as e:
            warnings.append(f"networkx 校验失败: {e}")

        return {"errors": errors, "warnings": warnings}

    def _generate_stats_report(self):
        """生成统计报告（控制台）"""
        top_node_types = self.stats["node_types"].most_common(10)
        print("\n  📊 Top 10 节点类型:")
        for node_type, count in top_node_types:
            print(f"    {node_type}: {count:,}")

        top_relation_types = self.stats["relation_types"].most_common(10)
        print("\n  📊 Top 10 关系类型:")
        for rel_type, count in top_relation_types:
            print(f"    {rel_type}: {count:,}")

        top_species = self.stats["species"].most_common(10)
        print("\n  📊 Top 10 物种:")
        for sp, count in top_species:
            print(f"    {sp}: {count:,}")

        print("\n  🧹 过滤跳过统计:")
        print(f"    skipped_rows: {self.stats['skipped_rows']:,}")
        print(f"    skipped_by_relation: {self.stats['skipped_by_relation']:,}")
        print(f"    skipped_by_node_type: {self.stats['skipped_by_node_type']:,}")
        print(f"    skipped_by_species: {self.stats['skipped_by_species']:,}")

    def save_stats(self, output_file: str):
        """保存统计信息"""
        stats_data = {
            "import_time": self.stats["import_time"],
            "nodes": self.stats["nodes"],
            "edges": self.stats["edges"],
            "node_types": dict(self.stats["node_types"]),
            "relation_types": dict(self.stats["relation_types"]),
            "species": dict(self.stats["species"]),
            "top_node_types": dict(self.stats["node_types"].most_common(20)),
            "top_relation_types": dict(self.stats["relation_types"].most_common(20)),
            "top_species": dict(self.stats["species"].most_common(20)),
            "filtering": {
                "restrict_node_types": self.restrict_node_types,
                "restrict_relations": self.restrict_relations,
                "restrict_species": self.restrict_species,
                "drop_generic_relations": self.drop_generic_relations,
                "allow_node_types_size": len(self.allow_node_types),
                "allow_relations_size": len(self.allow_relations),
                "allow_species_size": len(self.allow_species),
                "drop_generic_set": sorted(list(self.drop_generic_set)),
            },
            "skips": {
                "skipped_rows": self.stats["skipped_rows"],
                "skipped_by_node_type": self.stats["skipped_by_node_type"],
                "skipped_by_relation": self.stats["skipped_by_relation"],
                "skipped_by_species": self.stats["skipped_by_species"],
            },
            "qa_candidates_written": self.stats["qa_candidates_written"],
        }

        outp = Path(output_file)
        outp.parent.mkdir(parents=True, exist_ok=True)
        outp.write_text(json.dumps(stats_data, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"✅ 统计信息已保存到: {output_file}")


# -----------------------------
# CLI
# -----------------------------
if __name__ == "__main__":
    import argparse

    ap = argparse.ArgumentParser()
    ap.add_argument("csv_file", help="path/to/data.csv")
    ap.add_argument("--sample-size", type=int, default=None)
    ap.add_argument("--backend", default="neo4j", help="networkx|neo4j|...")
    ap.add_argument("--report-json", default=None, help="stats json to load top_* whitelists (optional)")
    ap.add_argument("--restrict-node-types", action="store_true")
    ap.add_argument("--restrict-relations", action="store_true")
    ap.add_argument("--restrict-species", action="store_true")
    ap.add_argument("--drop-generic-relations", action="store_true")
    ap.add_argument("--qa-candidates-jsonl", default=None, help="write filtered triples for QA generation")
    ap.add_argument("--stats-out", default="output/import_stats.json")

    args = ap.parse_args()

    if not Path(args.csv_file).exists():
        raise SystemExit(f"错误: 文件不存在 {args.csv_file}")

    importer = DataImporter(
        kg_backend=args.backend,
        restrict_node_types=args.restrict_node_types,
        restrict_relations=args.restrict_relations,
        restrict_species=args.restrict_species,
        drop_generic_relations=args.drop_generic_relations,
        report_json=args.report_json,
        qa_candidates_jsonl=args.qa_candidates_jsonl,
    )

    stats = importer.import_csv(args.csv_file, sample_size=args.sample_size)
    importer.save_stats(args.stats_out)

    print("\n✅ 导入任务完成!")
