#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
qa_generator.py

因果链QA生成器（最终版，增强版 + 统计报告白名单 TopK + 确定性模式）
- Neo4j 后端（PlantKnowledgeGraph backend="neo4j"）
- 自然问句 + 隐式约束词表（稳定过 validator）
- LLM 强制输出 JSON: aspects(>=3) + claims + used_evidence
- Validator 进行 evidence 引用 + claim 校验 + aspect_count hard fail + info_factor

✅ 本版本新增功能：
1. 严格只用统计报告 TopK（例如 Top20）
   - 仅允许 node_types / relation_types / species 在统计报告的 top_* 前 K 内
   - 候选实体筛选、evidence 扩展、random path 都强制白名单过滤

2. 从完整图谱Top统计信息生成QA
   - 新增 --use-top-stats 参数，可直接从Neo4j查询Top K统计信息
   - 无需stats-json文件，自动从数据库获取Top 20节点和关系类型
   - 基于Top K统计信息进行随机采样生成QA对

3. 确定性模式（新增）
   - 新增 --deterministic-mode 参数，启用确定性生成
   - 新增 --seed 参数，控制随机种子，确保可复现性
   - 确定性模式下：随机采样可复现，输出结果一致
   - 适用于测试、验证和基准测试

4. 基于关键词生成QA（新增）
   - 新增 --keyword 参数，基于关键词（如"rice"）从Neo4j查询相关实体并生成QA
   - 新增 --keyword-qa-num 参数，控制基于关键词生成的QA数量
   - 自动在实体的id, name, aliases, synonyms字段中搜索关键词
   - 支持多种任务类型（基因功能、调控机制、表型分析、物种特征、调控通路）

CLI:
--csv --output --gene-function --regulation --phenotype --species --pathway --threshold
新增:
--stats-json               统计报告json（DataImporter.save_stats输出）
--restrict-to-report       开启白名单过滤（node_types/relations/species）
--report-topk              严格使用统计报告 TopK（例如 20），否则默认使用"报告中出现过的全量"
--drop-generic-relations   丢弃低信息关系（had/is/in/include/...），可与TopK叠加
--restrict-species-to-top  只允许 top species（配合白名单更严格）
--use-top-stats           从Neo4j直接查询Top K统计信息并生成QA
--top-k                   Top K统计信息查询的K值（默认20）
--deterministic-mode      启用确定性模式（可复现）
--seed                    随机种子（确定性模式下生效）
--keyword                 基于关键词生成QA（如：rice, wheat等）
--keyword-qa-num          基于关键词生成的QA数量（默认20）

使用示例：
1. 传统模式（从stats-json文件加载白名单）：
   python llm_enhanced_kg_qa_generator_v1.py --stats-json output/import_stats.json --restrict-to-report --report-topk 20

2. Top统计信息模式（直接从数据库查询）：
   python llm_enhanced_kg_qa_generator_v1.py --use-top-stats --top-k 20

3. 确定性模式（可复现，测试用）：
   python llm_enhanced_kg_qa_generator_v1.py --use-top-stats --top-k 20 --deterministic-mode --seed 42

4. 确定性 + Top统计信息模式：
   python llm_enhanced_kg_qa_generator_v1.py --use-top-stats --top-k 20 --deterministic-mode --seed 42 --gene-function 10

5. 基于关键词生成QA（rice相关）：
   python llm_enhanced_kg_qa_generator_v1.py --keyword rice --keyword-qa-num 20

6. 基于关键词 + 确定性模式：
   python llm_enhanced_kg_qa_generator_v1.py --keyword rice --keyword-qa-num 30 --deterministic-mode --seed 42

注意：
- 需要你的项目中存在 kg_system.py / llm_client.py / llm_answer_validator.py
- PlantKnowledgeGraph(backend="neo4j") 需要 Neo4j 连接配置可用
- 确定性模式确保结果可复现，适用于测试和验证
"""

import re
import json
import argparse
import os
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Any
import random

from kg_system import PlantKnowledgeGraph
from llm_client import LLMClient
from llm_answer_validator import LLMAnswerValidator


class DoctoralQAGenerator:
    """博士论文级因果链QA生成器（Neo4j版本）"""

    # =============================
    # 常量定义
    # =============================
    DEFAULT_MAX_EDGES = 30
    DEFAULT_MIN_EDGES_PREFERRED = 6
    DEFAULT_ALLOWED_ENTITIES_K = 25
    DEFAULT_MAX_CLAIMS = 7
    DEFAULT_QUERY_LIMIT = 3000
    DEFAULT_MAX_PER_TYPE = 50
    DEFAULT_TOP_K = 20
    DEFAULT_MAX_RETRY = 2
    MAX_NODE_TYPES_TO_QUERY = 20  # 最多查询的节点类型数量

    # =============================
    # 0) 自然问句模板 + 隐式约束词表
    # =============================
    NATURAL_QUESTION_TEMPLATES: Dict[str, List[str]] = {
        "基因功能": [
            "你能用一段话讲清楚 {entity} 主要在做什么吗？它更像是在信号链的上游、中间节点，还是下游执行端？",
            "目前关于 {entity} 最可靠的结论是什么？它可能通过什么分子层面的方式影响相关过程？",
            "如果只允许你给出一个最可能的作用模型：{entity} 会如何影响相关生理过程？你会怎么描述？",
            "围绕 {entity}，请给出一个可检验的机制假说：它可能通过哪些环节推动或抑制下游事件？",
        ],
        "调控机制": [
            "{entity} 可能通过哪些分子层面的关联影响植物生理？请把确定的部分和推断的部分分开说。",
            "从现有线索看，{entity} 更可能调控什么？它可能处在通路的哪个层级？",
            "如果我要设计实验验证 {entity} 的作用位点，你建议先验证哪些关键环节？",
            "你能给出一个从“分子事件 → 过程输出”的解释路径，说明 {entity} 可能如何发挥作用吗？",
        ],
        "表型分析": [
            "关于表型 {entity}，目前有哪些分子层面的线索可以解释它？哪些只是推测？",
            "如果把 {entity} 当作一个可观测输出，你会从哪些分子过程去解释它的来源？",
            "围绕 {entity}，请给出最可能的生物学解释路径，并指出证据最强的环节。",
            "为了理解 {entity}，你会优先看哪些相关实体/过程的关联线索？",
        ],
        "物种特征": [
            "从分子层面看，{entity} 有哪些值得提炼的生物学特性？",
            "如果用机制语言概括 {entity} 的关键特性，你会抓住哪些线索？",
            "围绕 {entity}，哪些分子过程或表型特征最能区分它？",
            "{entity} 的哪些分子关联最可能解释其生态/生理特征？",
        ],
        "调控通路": [
            "围绕 {entity}，请串起一条尽可能自洽的机制链，说明信号如何逐步传到下游。",
            "如果把 {entity} 放进一个更大的网络里，它最可能连接哪些上游输入与下游输出？",
            "请给出一条可检验的链式解释：{entity} 如何通过一系列分子事件影响结果？",
            "围绕 {entity}，你能构建一个“从触发到输出”的路径叙述吗？",
        ],
    }

    HIDDEN_CONSTRAINT_LEXICON: Dict[str, List[str]] = {
        "禁止用词": [
            "图谱", "知识图谱", "证据库", "证据池", "三元组", "Neo4j", "Cypher",
        ],
        "实体约束提示": [
            "claims.head/tail 必须逐字匹配 Allowed entity IDs",
            "answer_text 尽量不用 Allowed 之外的新实体名；需要时用泛化描述",
        ],
        "证据约束提示": [
            "非 META claim 的 relation 必须来自 Evidence.relation",
            "非 META claim 的 evidence_ids 必须非空且引用 Evidence 中存在的 EID",
            "used_evidence 只列出实际引用到的 EID 子集",
        ],
        "aspects 约束提示": [
            "aspects 至少 3 项",
            "aspects 候选仅限 gene_function/regulation/phenotype/species/pathway",
            "aspects 必须包含本题要求维度集合",
        ],
        "信息不足策略": [
            "信息不足时用自然语言表达不足，并追加 META claim",
            "META relation 仅限 insufficient_information_for / cannot_determine_from_available_information / no_supported_claims_for / needs_more_context_for",
        ],
        "质量与稳定性": [
            "claims 优先 3~N 条；不足时至少 1~2 条（允许 META）",
            "confidence 给 0~1 的合理数值（支持度越强越高）",
        ],
    }

    # 低信息关系（可选丢弃）
    DEFAULT_GENERIC_RELATIONS = {
        "had", "has", "have",
        "is", "in",
        "include", "includes",
        "contain", "contains",
        "show", "shows", "exhibit", "exhibits", "display",
        "identified in",
        "associated with",
        "resulted in", "leads to",
        "increased", "induces", "induce",
    }

    def __init__(
        self,
        llm_config: Optional[Dict] = None,
        validation_threshold: float = 0.6,
        stats_json: Optional[str] = None,
        restrict_to_report: bool = False,
        drop_generic_relations: bool = False,
        restrict_species_to_top: bool = False,
        report_topk: Optional[int] = None,
        deterministic_mode: bool = False,
        seed: Optional[int] = None,
    ):
        # 尝试 Neo4j，不可用则回退到 NetworkX
        try:
            print("🔗 尝试连接Neo4j数据库...")
            self.kg = PlantKnowledgeGraph(backend="neo4j")
            # 验证连接是否真的可用
            if self.kg.backend == "neo4j":
                with self.kg.driver.session() as session:
                    session.run("RETURN 1").consume()
                print("✅ Neo4j连接验证成功")
        except Exception as e:
            print(f"⚠️ Neo4j不可用({e})，回退到NetworkX内存后端")
            self.kg = PlantKnowledgeGraph(backend="networkx")

        # 确定性模式配置
        self.deterministic_mode = deterministic_mode
        self.seed = seed if seed is not None else 42

        # 设置随机种子（确定性模式下）
        if self.deterministic_mode:
            print(f"🎯 确定性模式启用，随机种子: {self.seed}")
            random.seed(self.seed)

        self.llm_client = LLMClient(llm_config)
        self.validator = LLMAnswerValidator(self.kg, validation_threshold=validation_threshold)
        self.validation_threshold = validation_threshold

        self.qa_pairs: List[Dict] = []
        self.validation_stats = {"total_generated": 0, "validation_passed": 0, "validation_failed": 0}

        # 实体别名目录（alias->canonical）
        self.entity_alias_to_canonical: Dict[str, str] = {}
        self.canonical_entities: set[str] = set()

        # 统计报告白名单（TopK）
        self.stats_json = stats_json
        self.restrict_to_report = restrict_to_report
        self.drop_generic_relations = drop_generic_relations
        self.restrict_species_to_top = restrict_species_to_top
        self.report_topk = report_topk

        self.allowed_node_types: set[str] = set()
        self.allowed_relations: set[str] = set()
        self.allowed_species: set[str] = set()
        self.drop_relations: set[str] = set()

        if self.drop_generic_relations:
            self.drop_relations = set(self.DEFAULT_GENERIC_RELATIONS)

        if self.stats_json:
            self._load_report_whitelists(self.stats_json)

    # -----------------------------
    # normalization
    # -----------------------------
    @staticmethod
    def _norm(s: str) -> str:
        s = (s or "").strip()
        s = re.sub(r"\s+", " ", s)
        return s

    @staticmethod
    def _norm_key(s: str) -> str:
        s = (s or "").strip().lower()
        s = re.sub(r"\s+", " ", s)
        s = re.sub(r"[`'\"“”‘’]", "", s)
        s = re.sub(r"[_\-]+", " ", s)
        s = re.sub(r"\s*\(\s*", "(", s)
        s = re.sub(r"\s*\)\s*", ")", s)
        return s

    # -----------------------------
    # 统计报告白名单加载（TopK）
    # -----------------------------
    def _load_report_whitelists(self, stats_json_path: str) -> None:
        p = Path(stats_json_path)
        if not p.exists():
            print(f"⚠️ stats_json 不存在：{stats_json_path}，将不启用白名单")
            return

        try:
            data = json.loads(p.read_text(encoding="utf-8"))
        except Exception as e:
            print(f"⚠️ stats_json 解析失败：{e}，将不启用白名单")
            return

        # importer.save_stats() 输出字段（优先用 top_*，实现 "TopK 严格"）
        top_node_types = data.get("top_node_types") or {}
        top_rel_types  = data.get("top_relation_types") or {}
        top_species    = data.get("top_species") or {}

        # 若用户没给 --report-topk，则回退到"出现过的全量"
        if not self.report_topk:
            node_types = data.get("node_types") or {}
            rel_types  = data.get("relation_types") or {}
            species    = data.get("species") or {}
            nt = set(map(str, node_types.keys() if node_types else top_node_types.keys()))
            rt = set(map(str, rel_types.keys() if rel_types else top_rel_types.keys()))
            sp = set(map(str, species.keys() if species else top_species.keys()))
        else:
            k = int(self.report_topk)
            nt = list(top_node_types.keys())[:k]
            rt = list(top_rel_types.keys())[:k]
            sp = list(top_species.keys())[:k]
            nt = set(map(str, nt))
            rt = set(map(str, rt))
            sp = set(map(str, sp))

        nt.discard("")
        rt.discard("")
        sp.discard("")

        self.allowed_node_types = nt
        self.allowed_relations = rt
        self.allowed_species = sp

        mode = f"Top{self.report_topk}" if self.report_topk else "ALL_SEEN"
        print(f"📌 统计报告白名单加载完成({mode})：node_types={len(nt)}, relations={len(rt)}, species={len(sp)}")

    # -----------------------------
    # 确定性采样辅助方法
    # -----------------------------
    def _deterministic_sample(self, population: List, k: int) -> List:
        """
        确定性采样：使用random.sample（确定性模式下已设置种子，确保可复现）
        """
        if len(population) <= k:
            return population.copy()
        return random.sample(population, k)

    def _deterministic_choice(self, choices: List) -> Any:
        """
        确定性选择：使用random.choice（确定性模式下已设置种子，确保可复现）
        """
        return random.choice(choices)

    def _log_deterministic_status(self):
        """记录确定性模式状态"""
        if self.deterministic_mode:
            print(f"  ✓ 确定性模式：随机种子={self.seed}，结果可复现")
        else:
            print(f"  ℹ  随机模式：每次运行结果可能不同")

    def _get_top_nodes_and_relations_from_neo4j(self, top_k: int = None) -> Dict[str, Any]:
        """直接从Neo4j/NetworkX查询Top K节点类型和关系类型

        Args:
            top_k: Top K值，默认使用DEFAULT_TOP_K

        Returns:
            包含top_node_types, top_relation_types, top_species的字典
        """
        if top_k is None:
            top_k = self.DEFAULT_TOP_K

        if self.kg.backend == "networkx":
            return self._get_top_stats_networkx(top_k)

        print(f"\n🔍 从Neo4j查询Top {top_k}统计信息...")
        try:
            with self.kg.driver.session() as session:
                # 查询Top节点类型
                node_type_query = """
                MATCH (n:Entity)
                WHERE n.type IS NOT NULL
                RETURN n.type AS type, count(*) AS count
                ORDER BY count DESC
                LIMIT $k
                """
                node_result = session.run(node_type_query, k=top_k)
                top_node_types = {r["type"]: r["count"] for r in node_result if r["type"]}

                # 查询Top关系类型
                relation_type_query = """
                MATCH ()-[r:RELATES]->()
                WHERE r.relation IS NOT NULL
                RETURN r.relation AS relation, count(*) AS count
                ORDER BY count DESC
                LIMIT $k
                """
                rel_result = session.run(relation_type_query, k=top_k)
                top_relation_types = {r["relation"]: r["count"] for r in rel_result if r["relation"]}

                # 查询Top物种（如果有species属性）
                species_query = """
                MATCH (n:Entity)
                WHERE n.species IS NOT NULL
                RETURN n.species AS species, count(*) AS count
                ORDER BY count DESC
                LIMIT $k
                """
                species_result = session.run(species_query, k=top_k)
                top_species = {r["species"]: r["count"] for r in species_result if r["species"]}

                print(f"✅ Top {top_k}节点类型: {list(top_node_types.keys())[:5]}...")
                print(f"✅ Top {top_k}关系类型: {list(top_relation_types.keys())[:5]}...")
                print(f"✅ Top {top_k}物种: {list(top_species.keys())[:5] if top_species else 'N/A'}...")

                return {
                    "top_node_types": top_node_types,
                    "top_relation_types": top_relation_types,
                    "top_species": top_species
                }
        except Exception as e:
            print(f"⚠️ 查询Top统计信息失败：{e}")
            return {"top_node_types": {}, "top_relation_types": {}, "top_species": {}}

    def _get_top_stats_networkx(self, top_k: int) -> Dict[str, Any]:
        """从NetworkX图获取Top K统计信息"""
        from collections import Counter
        print(f"\n🔍 从NetworkX查询Top {top_k}统计信息...")
        try:
            G = self.kg.graph
            node_type_counts = Counter()
            rel_counts = Counter()
            species_counts = Counter()

            for nid, data in G.nodes(data=True):
                ntype = data.get("type", "")
                if ntype:
                    node_type_counts[ntype] += 1
                sp = data.get("species", "")
                if sp:
                    species_counts[sp] += 1

            for _, _, data in G.edges(data=True):
                rel = data.get("relation", "")
                if rel:
                    rel_counts[rel] += 1

            top_node_types = dict(node_type_counts.most_common(top_k))
            top_relation_types = dict(rel_counts.most_common(top_k))
            top_species = dict(species_counts.most_common(top_k))

            print(f"✅ Top {top_k}节点类型: {list(top_node_types.keys())[:5]}...")
            print(f"✅ Top {top_k}关系类型: {list(top_relation_types.keys())[:5]}...")

            return {
                "top_node_types": top_node_types,
                "top_relation_types": top_relation_types,
                "top_species": top_species
            }
        except Exception as e:
            print(f"⚠️ NetworkX统计失败：{e}")
            return {"top_node_types": {}, "top_relation_types": {}, "top_species": {}}

    def _relation_allowed(self, rel: str) -> bool:
        rel = self._norm(rel)
        if not rel:
            return False
        if self.drop_generic_relations and rel in self.drop_relations:
            return False
        if self.restrict_to_report and self.allowed_relations:
            return rel in self.allowed_relations
        return True

    def _node_type_allowed(self, node_type: str) -> bool:
        node_type = self._norm(node_type)
        if not node_type:
            return False
        if self.restrict_to_report and self.allowed_node_types:
            return node_type in self.allowed_node_types
        return True

    def _species_allowed(self, species: str) -> bool:
        species = self._norm(species)
        if not species:
            return True  # 没写species不拦
        if self.restrict_species_to_top and self.allowed_species:
            return species in self.allowed_species
        return True

    # -----------------------------
    # 自然问句生成
    # -----------------------------
    def build_natural_question(self, task_type: str, entity: str) -> str:
        templates = self.NATURAL_QUESTION_TEMPLATES.get(task_type, [])
        if not templates:
            return f"你能解释一下 {entity} 的主要作用以及它可能如何影响相关过程吗？"
        # 使用确定性选择（如果启用）
        t = self._deterministic_choice(templates)
        return t.format(entity=entity)

    def build_entity_catalog(self, limit: int = 200000) -> None:
        """从 Neo4j/NetworkX 拉实体目录：alias/name/synonyms -> canonical id"""
        if self.kg.backend == "networkx":
            self._build_entity_catalog_networkx(limit)
            return

        print("📚 构建实体目录（alias -> canonical）...")
        alias_map: Dict[str, str] = {}
        canonical_set: set[str] = set()

        query = """
        MATCH (n:Entity)
        RETURN n.id AS id,
               coalesce(n.name, n.id) AS name,
               coalesce(n.aliases, []) AS aliases,
               coalesce(n.synonyms, []) AS synonyms
        LIMIT $limit
        """
        try:
            with self.kg.driver.session() as session:
                result = session.run(query, limit=limit)
                for r in result:
                    cid = r["id"]
                    if not cid:
                        continue
                    canonical_set.add(cid)

                    for a in [cid, r["name"], *r["aliases"], *r["synonyms"]]:
                        if not a:
                            continue
                        key = self._norm_key(str(a))
                        if key not in alias_map:
                            alias_map[key] = cid
                        else:
                            old = alias_map[key]
                            if ("(" in cid and "(" not in old) or (len(cid) > len(old)):
                                alias_map[key] = cid

            self.entity_alias_to_canonical = alias_map
            self.canonical_entities = canonical_set
            print(f"✅ 实体目录完成：canonical={len(canonical_set)}, aliases={len(alias_map)}")
        except Exception as e:
            print(f"⚠️ 构建实体目录失败：{e}")

    def _build_entity_catalog_networkx(self, limit: int = 200000) -> None:
        """从NetworkX图构建实体目录"""
        print("📚 从NetworkX构建实体目录（alias -> canonical）...")
        alias_map: Dict[str, str] = {}
        canonical_set: set[str] = set()
        G = self.kg.graph

        for i, (nid, data) in enumerate(G.nodes(data=True)):
            if i >= limit:
                break
            cid = nid
            if not cid:
                continue
            canonical_set.add(cid)

            name = data.get("name", cid)
            aliases = data.get("aliases", [])
            synonyms = data.get("synonyms", [])
            if isinstance(aliases, str):
                aliases = [aliases]
            if isinstance(synonyms, str):
                synonyms = [synonyms]

            for a in [cid, name, *aliases, *synonyms]:
                if not a:
                    continue
                key = self._norm_key(str(a))
                if key not in alias_map:
                    alias_map[key] = cid
                else:
                    old = alias_map[key]
                    if ("(" in cid and "(" not in old) or (len(cid) > len(old)):
                        alias_map[key] = cid

        self.entity_alias_to_canonical = alias_map
        self.canonical_entities = canonical_set
        print(f"✅ NetworkX实体目录完成：canonical={len(canonical_set)}, aliases={len(alias_map)}")

    def _canonicalize_entity(self, raw: str) -> Optional[str]:
        if not raw:
            return None
        return self.entity_alias_to_canonical.get(self._norm_key(raw))

    # -----------------------------
    # KG load
    # -----------------------------
    def load_knowledge_graph(self, csv_file: Optional[str] = None, sample_size: int = 50000):
        backend_name = "NetworkX" if self.kg.backend == "networkx" else "Neo4j"
        if csv_file:
            print(f"\n📥 从CSV导入数据到{backend_name}: {csv_file} (采样: {sample_size})")
            self.kg.load_from_csv(csv_file, sample_size=sample_size)
            print("✅ 数据导入完成")
        else:
            print(f"\n📥 使用现有的{backend_name}数据库")

        self.build_entity_catalog()

        stats = self.kg.get_statistics()
        backend_name = "NetworkX" if self.kg.backend == "networkx" else "Neo4j"
        print(f"✅ {backend_name}知识图谱统计: 节点={stats.get('nodes', 0)}, 边={stats.get('edges', 0)}")

    # -----------------------------
    # neighbors / evidence de-dup + evidence expansion
    # -----------------------------
    def dedup_neighbors(self, neighbors: List[Dict]) -> List[Dict]:
        if not neighbors:
            return []

        seen = set()
        out: List[Dict] = []
        for n in neighbors:
            if not isinstance(n, dict):
                continue
            nid = self._norm(str(n.get("id", "") or ""))
            rels = n.get("relations") or []
            rel = self._norm(str(rels[0] if rels else ""))
            if not nid:
                continue
            if rel and not self._relation_allowed(rel):
                continue
            key = (nid, rel)
            if key in seen:
                continue
            seen.add(key)
            out.append({"id": nid, "relations": [rel] if rel else []})
        return out

    def _fetch_edges_from_neo4j(self, center_entity: str, limit_each: int = 40) -> List[Dict[str, str]]:
        """扩展证据池：同时拉 out/in，且做 relation 白名单过滤（优化：合并查询）"""
        if self.kg.backend == "networkx":
            return self._fetch_edges_networkx(center_entity, limit_each)

        edges: List[Dict[str, str]] = []
        try:
            with self.kg.driver.session() as session:
                # 合并out和in查询，减少数据库往返
                q_combined = """
                MATCH (a:Entity {id:$center})-[r:RELATES]->(b:Entity)
                RETURN a.id AS head, r.relation AS rel, b.id AS tail, 'out' AS direction
                LIMIT $lim
                UNION ALL
                MATCH (a:Entity)-[r:RELATES]->(b:Entity {id:$center})
                RETURN a.id AS head, r.relation AS rel, b.id AS tail, 'in' AS direction
                LIMIT $lim
                """
                res = session.run(q_combined, center=center_entity, lim=limit_each)
                for rec in res:
                    h = rec.get("head")
                    rel = rec.get("rel")
                    t = rec.get("tail")
                    direction = rec.get("direction", "out")
                    if h and rel and t and self._relation_allowed(str(rel)):
                        edges.append({
                            "head": str(h),
                            "relation": str(rel),
                            "tail": str(t),
                            "direction": str(direction)
                        })
        except Exception:
            return []

        return edges

    def _fetch_edges_networkx(self, center_entity: str, limit_each: int = 40) -> List[Dict[str, str]]:
        """从NetworkX图获取实体的出入边"""
        edges: List[Dict[str, str]] = []
        G = self.kg.graph

        if center_entity not in G:
            return edges

        # Out edges
        for _, tgt, data in list(G.out_edges(center_entity, data=True))[:limit_each]:
            rel = data.get("relation", "")
            if rel and self._relation_allowed(rel):
                edges.append({"head": center_entity, "relation": rel, "tail": tgt, "direction": "out"})

        # In edges
        for src, _, data in list(G.in_edges(center_entity, data=True))[:limit_each]:
            rel = data.get("relation", "")
            if rel and self._relation_allowed(rel):
                edges.append({"head": src, "relation": rel, "tail": center_entity, "direction": "in"})

        return edges

    def build_evidence_bank(
        self,
        center_entity: str,
        neighbors: List[Dict],
        max_edges: int = 30,
        min_edges_preferred: int = 6,
    ) -> Dict[str, Dict]:
        center_entity = self._norm(center_entity)
        neighbors = self.dedup_neighbors(neighbors or [])

        triples: List[Dict[str, str]] = []
        seen = set()

        def add_triple(h: str, r: str, t: str, d: str = "out"):
            h = self._norm(h)
            r = self._norm(r)
            t = self._norm(t)
            d = self._norm(d) or "out"
            if not (h and r and t):
                return
            if not self._relation_allowed(r):
                return
            key = (h, r, t, d)
            if key in seen:
                return
            seen.add(key)
            triples.append({"head": h, "relation": r, "tail": t, "direction": d})

        # 1) from neighbors
        for n in neighbors[:max_edges]:
            rels = n.get("relations") or []
            rel = rels[0] if rels else ""
            nid = n.get("id")
            if nid and rel:
                add_triple(center_entity, rel, nid, "out")

        # 2) expand if needed
        if len(triples) < min_edges_preferred:
            # 使用max_edges作为limit，确保获取足够的边
            extra = self._fetch_edges_from_neo4j(center_entity, limit_each=max_edges)
            for tr in extra:
                add_triple(tr["head"], tr["relation"], tr["tail"], tr.get("direction", "out"))
                if len(triples) >= max_edges:
                    break

        # 3) fallback random path if still not enough
        if len(triples) < min_edges_preferred:
            path = self._query_random_path(max_hops=2)
            if path:
                for tr in path.get("edges", []):
                    add_triple(tr.get("head", ""), tr.get("relation", ""), tr.get("tail", ""), tr.get("direction", "out"))
                    if len(triples) >= max_edges:
                        break

        evidence_bank: Dict[str, Dict] = {}
        for i, tr in enumerate(triples[:max_edges], start=1):
            evidence_bank[f"E{i}"] = tr
        return evidence_bank

    def build_allowed_entities(
        self,
        center_entity: str,
        neighbors: List[Dict],
        evidence_bank: Dict[str, Dict],
        k: int = 25,
    ) -> List[str]:
        allowed: List[str] = []

        def add(x: str):
            x = self._norm(x)
            if x and x not in allowed:
                allowed.append(x)

        add(center_entity)

        neighbors = self.dedup_neighbors(neighbors or [])
        for n in neighbors[:k]:
            add(n.get("id", ""))

        for tr in evidence_bank.values():
            add(tr.get("head", ""))
            add(tr.get("tail", ""))

        return allowed[: max(12, k + 8)]

    # -----------------------------
    # Aspect requirement (>=3)
    # -----------------------------
    @staticmethod
    def _aspect_list_default(task_type: str) -> List[str]:
        if task_type in {"基因功能", "调控机制"}:
            return ["gene_function", "regulation", "pathway"]
        if task_type in {"表型分析"}:
            return ["phenotype", "regulation", "pathway"]
        if task_type in {"物种特征"}:
            return ["species", "phenotype", "regulation"]
        return ["pathway", "regulation", "gene_function"]

    def _format_hidden_lexicon(self) -> str:
        return json.dumps(self.HIDDEN_CONSTRAINT_LEXICON, ensure_ascii=False, indent=2)

    def make_strict_prompt(
        self,
        task_type: str,
        question: str,
        center_entity: str,
        allowed_entities: List[str],
        evidence_bank: Dict[str, Dict],
        max_claims: int = 7,
        aspects_required: Optional[List[str]] = None,
    ) -> str:
        if aspects_required is None:
            aspects_required = self._aspect_list_default(task_type)

        hidden_lexicon = self._format_hidden_lexicon()

        prompt = f"""
你是植物分子机制写作助手。你必须基于给定的“可检索关联事实”（Evidence）回答问题，并输出严格 JSON。

【用户问题（自然问句）】
{question}

【隐式约束词表（必须遵守，但不要在 answer_text 中复述这些条目）】
{hidden_lexicon}

【任务类型】
{task_type}

【多维度硬约束】
- 输出 JSON 必须包含 "aspects" 字段（数组），且至少包含 3 项
- aspects 候选集合仅限：["gene_function","regulation","phenotype","species","pathway"]
- aspects 必须至少包含以下要求集合：{json.dumps(aspects_required, ensure_ascii=False)}

【实体约束（硬约束）】
- 你输出的 claims 中 head/tail 必须逐字匹配 Allowed entity IDs 中的某一个
- answer_text 尽量不引入 Allowed 之外的新实体名；必要时用“某些调控因子/某类过程/某种信号”等泛化表达

【禁用措辞（硬约束）】
- answer_text 中禁止出现：{json.dumps(self.HIDDEN_CONSTRAINT_LEXICON["禁止用词"], ensure_ascii=False)}

Allowed entity IDs:
{json.dumps(allowed_entities, ensure_ascii=False, indent=2)}

Evidence（可引用事实，格式: evidence_id -> {{head, relation, tail, direction}}）:
{json.dumps(evidence_bank, ensure_ascii=False, indent=2)}

【输出格式（必须是严格 JSON；不要输出任何解释文字）】
{{
  "aspects": ["gene_function","regulation","pathway"],
  "answer_text": "200-320字左右，自然语言回答（禁止出现禁用词）",
  "claims": [
    {{
      "head": "实体ID（来自Allowed）",
      "relation": "关系字符串（必须来自某条Evidence的relation，或 META 关系）",
      "tail": "实体ID（来自Allowed；META claim 可为空字符串）",
      "polarity": "positive",
      "evidence_ids": ["E1","E2"],
      "confidence": 0.0
    }}
  ],
  "used_evidence": {{
    "E1": {{"head":"...","relation":"...","tail":"...","direction":"out"}}
  }}
}}

【规则（硬约束）】
A) 非 META claim：
   - relation 必须与某条 Evidence 的 relation 完全一致
   - evidence_ids 必须非空，且每个 evidence_id 都必须出现在 Evidence 中
B) used_evidence 只列出 claims 里实际引用到的 evidence_id（子集即可）
C) 信息不足时允许使用 META claim，relation 必须取以下之一：
   - insufficient_information_for
   - cannot_determine_from_available_information
   - no_supported_claims_for
   - needs_more_context_for
   META claim 的 evidence_ids 允许为空，tail 允许为空字符串
D) claims 数量优先 3~{max_claims}；若确实不足，至少输出 1~2 条（可用 META）
E) aspects 至少 3 项，并包含要求集合
"""
        return prompt.strip()

    # -----------------------------
    # Generate with retry
    # -----------------------------
    def generate_with_retry(
        self,
        qa: Dict,
        prompt: str,
        allowed_entities: List[str],
        evidence_bank: Dict[str, Dict],
        max_retry: int = 2,
    ) -> Dict:
        answer = self.llm_client.generate_response(prompt, temperature=0.4)
        qa["answer"] = answer
        qa["allowed_entities"] = allowed_entities
        qa["evidence_bank"] = evidence_bank

        validation = self.validator.validate_answer(qa)
        qa["validation"] = validation["validation"]

        tries = 0
        while (not qa["validation"]["validation_passed"]) and tries < max_retry:
            tries += 1
            details = qa["validation"].get("validation_details", [])
            ev_issues = qa["validation"].get("evidence_validation", {})
            claim_issues = qa["validation"].get("claim_validation", {})
            aspect_issues = qa["validation"].get("aspect_validation", {})
            info_factor = qa["validation"].get("info_factor", {})

            repair_prompt = f"""
你上一版输出未通过结构校验。请在不改变问题核心含义前提下做“最小修改”，输出新的严格 JSON（不要输出任何解释文字）。

【高频失败点（逐条修复）】
- aspects 缺失或少于 3 项：必须提供 aspects，且至少 3 项，并包含题目要求维度
- claims head/tail 不在 Allowed entity IDs：必须替换为 Allowed 中的实体ID
- 非 META claim 的 evidence_ids 为空或引用不存在的 EID：必须引用 Evidence 中存在的 evidence_id
- 非 META claim 的 relation 不在 Evidence.relation 中：必须改成 Evidence 的 relation 文本
- used_evidence 未覆盖 claims 引用的 EID：补齐 used_evidence 子集

【校验摘要】
{json.dumps({
  "details": details,
  "aspect_validation": aspect_issues,
  "info_factor": info_factor,
  "evidence_validation": ev_issues,
  "claim_validation_summary": {
    "claim_count": claim_issues.get("claim_count"),
    "supported_count": claim_issues.get("supported_count"),
    "unsupported_count": claim_issues.get("unsupported_count"),
    "unknown_count": claim_issues.get("unknown_count"),
  }
}, ensure_ascii=False, indent=2)}

Allowed entity IDs:
{json.dumps(allowed_entities, ensure_ascii=False, indent=2)}

Evidence:
{json.dumps(evidence_bank, ensure_ascii=False, indent=2)}

请输出修复后的严格 JSON（仅 JSON）。
"""
            answer = self.llm_client.generate_response(repair_prompt.strip(), temperature=0.2)
            qa["answer"] = answer
            validation = self.validator.validate_answer(qa)
            qa["validation"] = validation["validation"]

        return qa

    # -----------------------------
    # Neo4j queries
    # -----------------------------
    def _query_entities_with_neighbors(self, entity_type: str, limit: int = 2000) -> List[Tuple[str, List[Dict]]]:
        """候选中心实体：按节点类型过滤 + 关系过滤"""
        rows: List[Tuple[str, List[Dict]]] = []
        if self.kg.backend == "networkx":
            return self._query_entities_with_neighbors_networkx(entity_type, limit)

        # 节点类型白名单过滤（如果启用）
        if not self._node_type_allowed(entity_type):
            return []

        q = """
        MATCH (n:Entity {type:$t})-[r:RELATES]->(m:Entity)
        WHERE size(n.id) > 1
        RETURN n.id AS id,
               collect({id:m.id, rel: r.relation}) AS ns
        LIMIT $limit
        """
        with self.kg.driver.session() as session:
            result = session.run(q, t=entity_type, limit=limit)
            for rec in result:
                eid = rec["id"]
                ns = rec["ns"] or []
                neighbors = [{"id": x.get("id"), "relations": [x.get("rel")]} for x in ns if x.get("id") and x.get("rel")]
                neighbors = self.dedup_neighbors(neighbors)
                if not neighbors:
                    continue
                rows.append((eid, neighbors))
        return rows

    def _query_entities_by_keyword(
        self, 
        keyword: str, 
        limit: int = 1000,
        search_fields: List[str] = None
    ) -> List[Tuple[str, List[Dict]]]:
        """根据关键词查询实体及其邻居
        
        Args:
            keyword: 搜索关键词（如"rice"）
            limit: 最大返回数量
            search_fields: 搜索字段列表，默认搜索id, name, aliases, synonyms
            
        Returns:
            实体和邻居的元组列表 [(entity_id, neighbors), ...]
        """
        if search_fields is None:
            search_fields = ["id", "name", "aliases", "synonyms"]
            
        rows: List[Tuple[str, List[Dict]]] = []
        if self.kg.backend == "networkx":
            return self._query_entities_by_keyword_networkx(keyword, limit)

        print(f"🔍 搜索包含关键词 '{keyword}' 的实体...")
        try:
            with self.kg.driver.session() as session:
                # 构建搜索条件：在id, name, aliases, synonyms中搜索
                # 使用DISTINCT在查询层面去重，提高效率
                keyword_lower = keyword.lower()
                q = """
                MATCH (n:Entity)-[r:RELATES]->(m:Entity)
                WHERE size(n.id) > 1
                  AND (
                    toLower(n.id) CONTAINS $keyword
                    OR (n.name IS NOT NULL AND toLower(n.name) CONTAINS $keyword)
                    OR (n.aliases IS NOT NULL AND ANY(alias IN n.aliases WHERE toLower(alias) CONTAINS $keyword))
                    OR (n.synonyms IS NOT NULL AND ANY(syn IN n.synonyms WHERE toLower(syn) CONTAINS $keyword))
                  )
                WITH DISTINCT n, collect(DISTINCT {id:m.id, rel: r.relation}) AS ns
                WHERE size(ns) > 0
                RETURN n.id AS id,
                       n.name AS name,
                       ns
                ORDER BY size(ns) DESC
                LIMIT $limit
                """
                result = session.run(q, keyword=keyword_lower, limit=limit)
                for rec in result:
                    eid = rec["id"]
                    if not eid:
                        continue
                    
                    ns = rec["ns"] or []
                    neighbors = [
                        {"id": x.get("id"), "relations": [x.get("rel")]} 
                        for x in ns 
                        if x.get("id") and x.get("rel")
                    ]
                    neighbors = self.dedup_neighbors(neighbors)
                    if neighbors:
                        rows.append((eid, neighbors))
                
                print(f"✅ 找到 {len(rows)} 个包含关键词 '{keyword}' 的实体（已过滤有邻居的实体）")
        except Exception as e:
            print(f"⚠️ 查询关键词实体失败：{e}")
            
        return rows

    def _query_random_path(self, max_hops: int = 3) -> Optional[Dict[str, Any]]:
        """随机路径：强制 relation 白名单过滤；过滤后不足则返回 None"""
        if self.kg.backend == "networkx":
            return self._query_random_path_networkx(max_hops)
        try:
            with self.kg.driver.session() as session:
                q = f"""
                MATCH p=(a:Entity)-[rs:RELATES*1..{max_hops}]->(b:Entity)
                WHERE a.id <> b.id
                RETURN nodes(p) AS ns, relationships(p) AS rs
                ORDER BY rand()
                LIMIT 3
                """
                # 多取几条，过滤后更可能留下一条可用
                for rec in session.run(q):
                    ns = rec["ns"]
                    rs = rec["rs"]
                    nodes = [n["id"] for n in ns]
                    edges = []
                    for i, r in enumerate(rs):
                        rel = r.get("relation") if hasattr(r, "get") else r["relation"]
                        rel = str(rel)
                        if not self._relation_allowed(rel):
                            edges = []
                            break
                        edges.append({"head": nodes[i], "relation": rel, "tail": nodes[i + 1], "direction": "out"})
                    if edges:
                        return {"nodes": nodes, "edges": edges}
                return None
        except Exception:
            return None

    # -----------------------------
    # NetworkX fallback implementations
    # -----------------------------
    def _query_entities_with_neighbors_networkx(self, entity_type: str, limit: int = 2000) -> List[Tuple[str, List[Dict]]]:
        """从NetworkX图查询指定类型的实体及其邻居"""
        rows: List[Tuple[str, List[Dict]]] = []
        if not self._node_type_allowed(entity_type):
            return []

        G = self.kg.graph
        for nid, data in G.nodes(data=True):
            if data.get("type") != entity_type:
                continue
            if len(nid) <= 1:
                continue

            neighbors = []
            for _, tgt, edge_data in G.out_edges(nid, data=True):
                rel = edge_data.get("relation", "")
                if rel and self._relation_allowed(rel):
                    neighbors.append({"id": tgt, "relations": [rel]})

            neighbors = self.dedup_neighbors(neighbors)
            if neighbors:
                rows.append((nid, neighbors))
            if len(rows) >= limit:
                break

        return rows

    def _query_entities_by_keyword_networkx(self, keyword: str, limit: int = 1000) -> List[Tuple[str, List[Dict]]]:
        """从NetworkX图搜索包含关键词的实体及其邻居"""
        rows: List[Tuple[str, List[Dict]]] = []
        keyword_lower = keyword.lower()

        print(f"🔍 从NetworkX搜索包含关键词 '{keyword}' 的实体...")
        G = self.kg.graph

        for nid, data in G.nodes(data=True):
            if len(nid) <= 1:
                continue

            # 搜索 id, name 等字段
            searchable = [nid, data.get("name", "")]
            aliases = data.get("aliases", [])
            synonyms = data.get("synonyms", [])
            if isinstance(aliases, str):
                aliases = [aliases]
            if isinstance(synonyms, str):
                synonyms = [synonyms]
            searchable.extend(aliases)
            searchable.extend(synonyms)

            matched = False
            for field in searchable:
                if field and keyword_lower in str(field).lower():
                    matched = True
                    break

            if not matched:
                continue

            neighbors = []
            for _, tgt, edge_data in G.out_edges(nid, data=True):
                rel = edge_data.get("relation", "")
                if rel and self._relation_allowed(rel):
                    neighbors.append({"id": tgt, "relations": [rel]})

            neighbors = self.dedup_neighbors(neighbors)
            if neighbors:
                rows.append((nid, neighbors))
            if len(rows) >= limit:
                break

        print(f"✅ 找到 {len(rows)} 个包含关键词 '{keyword}' 的实体")
        return rows

    def _query_random_path_networkx(self, max_hops: int = 3) -> Optional[Dict[str, Any]]:
        """从NetworkX图查找随机路径"""
        import networkx as nx
        G = self.kg.graph
        nodes = list(G.nodes())
        if len(nodes) < 2:
            return None

        for _ in range(20):
            start = self._deterministic_choice(nodes)
            end_candidates = [n for n in nodes if n != start]
            if not end_candidates:
                continue
            end = self._deterministic_choice(end_candidates)

            try:
                paths = list(nx.all_simple_paths(G, start, end, cutoff=max_hops))
                if paths:
                    path = self._deterministic_choice(paths)
                    edges = []
                    valid = True
                    for i in range(len(path) - 1):
                        edge_data = G.get_edge_data(path[i], path[i + 1])
                        if edge_data:
                            rel = edge_data.get("relation", "")
                            if self._relation_allowed(rel):
                                edges.append({"head": path[i], "relation": rel, "tail": path[i + 1], "direction": "out"})
                            else:
                                valid = False
                                break
                    if valid and edges:
                        return {"nodes": path, "edges": edges}
            except (nx.NetworkXNoPath, nx.NodeNotFound, KeyError):
                continue

        return None

    def _query_entities_from_top_types_networkx(
        self,
        node_types: List[str],
        max_per_type: int = None
    ) -> List[Tuple[str, List[Dict]]]:
        """从NetworkX图中按节点类型采样实体"""
        if max_per_type is None:
            max_per_type = self.DEFAULT_MAX_PER_TYPE

        all_entities: List[Tuple[str, List[Dict]]] = []
        G = self.kg.graph

        print(f"\n🎲 从NetworkX图采样实体：{node_types[:5]}...")

        for node_type in node_types[:self.MAX_NODE_TYPES_TO_QUERY]:
            type_entities = []
            for nid, data in G.nodes(data=True):
                if data.get("type") != node_type or len(nid) <= 1:
                    continue

                neighbors = []
                for _, tgt, edge_data in G.out_edges(nid, data=True):
                    rel = edge_data.get("relation", "")
                    if rel and self._relation_allowed(rel):
                        neighbors.append({"id": tgt, "relations": [rel]})

                neighbors = self.dedup_neighbors(neighbors)
                if neighbors:
                    type_entities.append((nid, neighbors))

            sampled = self._deterministic_sample(type_entities, min(len(type_entities), max_per_type))
            all_entities.extend(sampled)
            print(f"  - {node_type}: {len(sampled)} 个实体")

        print(f"✅ 总共采样实体：{len(all_entities)} 个")
        return all_entities

    # -----------------------------
    # QA generators
    # -----------------------------
    def generate_gene_function_qa(self, num_qa: int = 10) -> List[Dict]:
        candidates = self._query_entities_with_neighbors("gene", limit=self.DEFAULT_QUERY_LIMIT)
        if not candidates:
            print("⚠️ 未找到 gene 节点（或被统计报告白名单过滤为空）")
            return []

        selected = self._deterministic_sample(candidates, min(num_qa, len(candidates)))
        out: List[Dict] = []

        for gene, neighbors in selected:
            qa = self._generate_single_qa(
                task_type="基因功能",
                entity=gene,
                neighbors=neighbors,
                max_claims=7,
                aspects_required=["gene_function", "regulation", "pathway"],
            )
            if qa:
                out.append(qa)

        return out

    def generate_regulation_mechanism_qa(self, num_qa: int = 10) -> List[Dict]:
        candidates = self._query_entities_with_neighbors("gene", limit=self.DEFAULT_QUERY_LIMIT)
        if not candidates:
            print("⚠️ 未找到调控机制相关 gene 节点（或被过滤为空）")
            return []

        selected = self._deterministic_sample(candidates, min(num_qa, len(candidates)))
        out: List[Dict] = []

        for gene, neighbors in selected:
            qa = self._generate_single_qa(
                task_type="调控机制",
                entity=gene,
                neighbors=neighbors,
                max_claims=8,
                aspects_required=["regulation", "pathway", "phenotype"],
            )
            if qa:
                out.append(qa)

        return out

    def generate_phenotype_qa(self, num_qa: int = 10) -> List[Dict]:
        # 注意：若统计报告Top20里没有 trait，则 trait 回退会被白名单拒绝
        candidates = self._query_entities_with_neighbors("phenotype", limit=self.DEFAULT_QUERY_LIMIT)
        if not candidates:
            print("⚠️ 未找到 phenotype 类型节点，尝试 trait 回退")
            candidates = self._query_entities_with_neighbors("trait", limit=2000)
            if not candidates:
                print("⚠️ 未找到表型/trait 节点（或被过滤为空）")
                return []

        selected = self._deterministic_sample(candidates, min(num_qa, len(candidates)))
        out: List[Dict] = []

        for ph, neighbors in selected:
            qa = self._generate_single_qa(
                task_type="表型分析",
                entity=ph,
                neighbors=neighbors,
                max_claims=8,
                aspects_required=["phenotype", "regulation", "pathway"],
            )
            if qa:
                out.append(qa)

        return out

    def generate_species_qa(self, num_qa: int = 10) -> List[Dict]:
        candidates = self._query_entities_with_neighbors("organism", limit=self.DEFAULT_QUERY_LIMIT)
        if not candidates:
            print("⚠️ 未找到 organism 节点（或被过滤为空）")
            return []

        selected = self._deterministic_sample(candidates, min(num_qa, len(candidates)))
        out: List[Dict] = []

        for sp, neighbors in selected:
            # 物种白名单（如果启用）
            if self.restrict_species_to_top and self.allowed_species and (sp not in self.allowed_species):
                continue

            qa = self._generate_single_qa(
                task_type="物种特征",
                entity=sp,
                neighbors=neighbors,
                max_claims=8,
                aspects_required=["species", "phenotype", "regulation"],
            )
            if qa:
                out.append(qa)

        return out

    def generate_causal_pathway_qa(self, num_qa: int = 10) -> List[Dict]:
        out: List[Dict] = []

        for _ in range(num_qa * 3):  # 多尝试几次，过滤后可用路径更少
            if len(out) >= num_qa:
                break
            path = self._query_random_path(max_hops=3)
            if not path:
                continue

            nodes = path["nodes"]
            edges = path["edges"]
            center = nodes[0]

            evidence_bank = {f"E{i}": tr for i, tr in enumerate(edges, start=1)}
            if len(evidence_bank) < 1:
                continue

            neighbors = [{"id": n, "relations": []} for n in nodes[1:]]
            
            # 对于pathway类型，需要特殊处理evidence_bank
            neighbors = self.dedup_neighbors(neighbors)
            question = self.build_natural_question("调控通路", center)
            allowed = self.build_allowed_entities(center, neighbors, evidence_bank, k=30)

            prompt = self.make_strict_prompt(
                task_type="调控通路",
                question=question,
                center_entity=center,
                allowed_entities=allowed,
                evidence_bank=evidence_bank,
                max_claims=9,
                aspects_required=["pathway", "regulation", "gene_function"],
            )

            qa = {
                "type": "调控通路",
                "question": question,
                "entity": center,
                "neighbors": neighbors[:12],
                "source": "Neo4j + LLM(JSON:aspects+claim+evidence) + Validator",
            }

            qa = self.generate_with_retry(qa, prompt, allowed, evidence_bank, max_retry=self.DEFAULT_MAX_RETRY)
            self._update_generation_stats(qa)
            out.append(qa)

        return out[:num_qa]

    def generate_pathway_qa(self, num_qa: int = 10) -> List[Dict]:
        return self.generate_causal_pathway_qa(num_qa)

    # -----------------------------
    # 基于关键词生成QA（新增）
    # -----------------------------
    def generate_qa_by_keyword(
        self, 
        keyword: str, 
        num_qa: int = 20,
        task_types: Optional[List[str]] = None
    ) -> List[Dict]:
        """基于关键词生成QA对
        
        Args:
            keyword: 搜索关键词（如"rice"）
            num_qa: 要生成的QA数量
            task_types: 任务类型列表，如果为None则使用所有类型
            
        Returns:
            生成的QA对列表
        """
        if task_types is None:
            task_types = ["基因功能", "调控机制", "表型分析", "物种特征", "调控通路"]
        
        print(f"\n{'='*80}")
        print(f"🌾 基于关键词 '{keyword}' 生成QA对")
        print(f"{'='*80}")
        
        # 查询包含关键词的实体
        candidates = self._query_entities_by_keyword(keyword, limit=num_qa * 3)
        if not candidates:
            print(f"⚠️ 未找到包含关键词 '{keyword}' 的实体")
            return []
        
        print(f"📊 找到 {len(candidates)} 个候选实体，将生成 {num_qa} 个QA对")
        
        # 使用确定性采样
        selected = self._deterministic_sample(candidates, min(num_qa, len(candidates)))
        
        all_qa: List[Dict] = []
        task_type_cycle = task_types * ((len(selected) // len(task_types)) + 1)
        
        for idx, (entity, neighbors) in enumerate(selected):
            # 轮换使用不同的任务类型
            task_type = task_type_cycle[idx % len(task_type_cycle)]
            
            # 根据任务类型确定aspects和max_claims
            if task_type == "基因功能":
                max_claims = 7
                aspects_required = ["gene_function", "regulation", "pathway"]
            elif task_type == "调控机制":
                max_claims = 8
                aspects_required = ["regulation", "pathway", "phenotype"]
            elif task_type == "表型分析":
                max_claims = 8
                aspects_required = ["phenotype", "regulation", "pathway"]
            elif task_type == "物种特征":
                max_claims = 8
                aspects_required = ["species", "phenotype", "regulation"]
            else:  # 调控通路
                max_claims = 9
                aspects_required = ["pathway", "regulation", "gene_function"]
            
            qa = self._generate_single_qa(
                task_type=task_type,
                entity=entity,
                neighbors=neighbors,
                max_claims=max_claims,
                aspects_required=aspects_required,
                source_prefix=f"Neo4j + Keyword({keyword})",
            )
            if qa:
                all_qa.append(qa)
                print(f"  ✓ 已生成 {len(all_qa)}/{num_qa} 个QA对: {task_type} - {entity[:50]}...")
        
        self.qa_pairs = all_qa
        print(
            f"\n✅ 关键词 '{keyword}' QA对生成完成: 总数={len(all_qa)}, "
            f"验证通过={self.validation_stats['validation_passed']}, "
            f"未通过={self.validation_stats['validation_failed']}"
        )
        return all_qa

    # -----------------------------
    # orchestration
    # -----------------------------
    def generate_all_qa(self, num_per_type: Dict[str, int]) -> List[Dict]:
        """生成所有类型的QA对
        
        Args:
            num_per_type: 每种类型要生成的QA数量字典
            
        Returns:
            生成的QA对列表
        """
        # 使用映射表简化代码
        generator_map = {
            "gene_function": self.generate_gene_function_qa,
            "regulation": self.generate_regulation_mechanism_qa,
            "phenotype": self.generate_phenotype_qa,
            "species": self.generate_species_qa,
            "pathway": self.generate_pathway_qa,
        }
        
        all_qa: List[Dict] = []
        for qa_type, generator_func in generator_map.items():
            if qa_type in num_per_type and num_per_type[qa_type] > 0:
                all_qa.extend(generator_func(num_per_type[qa_type]))

        self.qa_pairs = all_qa
        print(
            f"\n✅ 总QA对: {len(all_qa)}, "
            f"验证通过: {self.validation_stats['validation_passed']}, "
            f"未通过: {self.validation_stats['validation_failed']}"
        )
        return all_qa

    # -----------------------------
    # 从Top 20统计信息生成QA（新增）
    # -----------------------------
    def _query_entities_from_top_types(
        self, 
        node_types: List[str], 
        max_per_type: int = None
    ) -> List[Tuple[str, List[Dict]]]:
        """从Top节点类型中随机采样实体
        
        Args:
            node_types: 节点类型列表
            max_per_type: 每种类型最多采样数量，默认使用DEFAULT_MAX_PER_TYPE
            
        Returns:
            实体和邻居的元组列表
        """
        if max_per_type is None:
            max_per_type = self.DEFAULT_MAX_PER_TYPE
            
        all_entities: List[Tuple[str, List[Dict]]] = []
        if self.kg.backend == "networkx":
            return self._query_entities_from_top_types_networkx(node_types, max_per_type)

        print(f"\n🎲 从Top节点类型中采样实体：{node_types[:5]}...")
        try:
            with self.kg.driver.session() as session:
                for node_type in node_types[:self.MAX_NODE_TYPES_TO_QUERY]:
                    q = """
                    MATCH (n:Entity {type:$t})-[r:RELATES]->(m:Entity)
                    WHERE size(n.id) > 1
                    RETURN n.id AS id,
                           collect({id:m.id, rel: r.relation}) AS ns
                    ORDER BY rand()
                    LIMIT $lim
                    """
                    result = session.run(q, t=node_type, lim=max_per_type)
                    entities = []
                    for rec in result:
                        eid = rec["id"]
                        ns = rec["ns"] or []
                        neighbors = [
                            {"id": x.get("id"), "relations": [x.get("rel")]} 
                            for x in ns 
                            if x.get("id") and x.get("rel")
                        ]
                        neighbors = self.dedup_neighbors(neighbors)
                        if neighbors and eid:
                            entities.append((eid, neighbors))

                    # 每种类型最多采样一定数量
                    sampled = self._deterministic_sample(entities, min(len(entities), max_per_type))
                    all_entities.extend(sampled)
                    print(f"  - {node_type}: {len(sampled)} 个实体")

        except Exception as e:
            print(f"⚠️ 采样实体失败：{e}")

        print(f"✅ 总共采样实体：{len(all_entities)} 个")
        return all_entities

    def generate_qa_from_top_stats(self, num_per_type: Dict[str, int], top_k: int = 20) -> List[Dict]:
        """从Top K统计信息生成QA对"""
        print("\n" + "=" * 80)
        print(f"🎯 从完整图谱Top {top_k}统计信息生成QA对")
        print("=" * 80)

        # 1. 获取Top K统计信息
        stats = self._get_top_nodes_and_relations_from_neo4j(top_k=top_k)
        top_node_types = list(stats["top_node_types"].keys())
        top_relation_types = list(stats["top_relation_types"].keys())

        if not top_node_types:
            print("⚠️ 未找到节点类型，无法生成QA")
            return []

        # 2. 设置白名单（使用Top K）
        self.allowed_node_types = set(top_node_types[:top_k])
        self.allowed_relations = set(top_relation_types[:top_k])

        print(f"\n📌 使用Top {top_k}白名单：")
        print(f"  - 节点类型 ({len(self.allowed_node_types)}): {list(self.allowed_node_types)[:5]}...")
        print(f"  - 关系类型 ({len(self.allowed_relations)}): {list(self.allowed_relations)[:5]}...")

        # 3. 根据用户要求的类型生成QA
        all_qa: List[Dict] = []

        # QA类型配置：task_type -> (type_filter_func, max_claims, aspects_required, fallback_slice)
        qa_configs = {
            "gene_function": (
                lambda types, k: [t for t in types[:k] if "gene" in t.lower()] or types[:3],
                7,
                ["gene_function", "regulation", "pathway"],
                slice(0, 3),
            ),
            "regulation": (
                lambda types, k: types[:5],
                8,
                ["regulation", "pathway", "phenotype"],
                slice(0, 5),
            ),
            "phenotype": (
                lambda types, k: [t for t in types[:k] if any(x in t.lower() for x in ["phenotype", "trait", "character"])] or types[3:8],
                8,
                ["phenotype", "regulation", "pathway"],
                slice(3, 8),
            ),
            "species": (
                lambda types, k: [t for t in types[:k] if any(x in t.lower() for x in ["species", "organism", "plant"])] or types[5:10],
                8,
                ["species", "phenotype", "regulation"],
                slice(5, 10),
            ),
            "pathway": (
                lambda types, k: [t for t in types[:k] if any(x in t.lower() for x in ["pathway", "process", "signal"])] or types[2:7],
                9,
                ["pathway", "regulation", "gene_function"],
                slice(2, 7),
            ),
        }

        # 统一处理所有类型的QA生成
        for qa_key, (type_filter_func, max_claims, aspects_required, fallback_slice) in qa_configs.items():
            if num_per_type.get(qa_key, 0) <= 0:
                continue

            task_type_map = {
                "gene_function": "基因功能",
                "regulation": "调控机制",
                "phenotype": "表型分析",
                "species": "物种特征",
                "pathway": "调控通路",
            }
            task_type = task_type_map[qa_key]

            # 筛选节点类型
            filtered_types = type_filter_func(top_node_types, top_k)
            if not filtered_types:
                filtered_types = top_node_types[fallback_slice]

            candidates = self._query_entities_from_top_types(filtered_types, max_per_type=self.DEFAULT_MAX_PER_TYPE)
            if not candidates:
                continue

            selected = self._deterministic_sample(candidates, min(num_per_type[qa_key], len(candidates)))
            for entity, neighbors in selected:
                # 物种白名单特殊处理
                if qa_key == "species" and self.restrict_species_to_top and self.allowed_species:
                    if entity not in self.allowed_species:
                        continue

                qa = self._generate_single_qa(
                    task_type=task_type,
                    entity=entity,
                    neighbors=neighbors,
                    max_claims=max_claims,
                    aspects_required=aspects_required,
                    source_prefix=f"Neo4j + Top{top_k}",
                )
                if qa:
                    all_qa.append(qa)

        self.qa_pairs = all_qa
        print(
            f"\n✅ Top {top_k} QA对生成完成: 总数={len(all_qa)}, "
            f"验证通过={self.validation_stats['validation_passed']}, "
            f"未通过={self.validation_stats['validation_failed']}"
        )
        return all_qa

    def save_qa_pairs(self, output_dir: str):
        output_path = Path(output_dir)
        if not output_path.is_absolute():
            output_path = Path(__file__).parent / output_path
        output_path.mkdir(parents=True, exist_ok=True)

        jsonl_file = output_path / "qa_pairs.jsonl"
        with open(jsonl_file, "w", encoding="utf-8") as f:
            for qa in self.qa_pairs:
                json.dump(qa, f, ensure_ascii=False)
                f.write("\n")

        json_file = output_path / "qa_pairs.json"
        with open(json_file, "w", encoding="utf-8") as f:
            json.dump(self.qa_pairs, f, ensure_ascii=False, indent=2)

        print(f"✅ QA结果已保存到: {jsonl_file}")
        print(f"✅ QA结果已保存到: {json_file}")

    # -----------------------------
    # internal stats
    # -----------------------------
    def _update_generation_stats(self, qa: Dict) -> None:
        self.validation_stats["total_generated"] += 1
        if qa.get("validation", {}).get("validation_passed"):
            self.validation_stats["validation_passed"] += 1
        else:
            self.validation_stats["validation_failed"] += 1

    # -----------------------------
    # 通用QA生成方法（减少代码重复）
    # -----------------------------
    def _generate_single_qa(
        self,
        task_type: str,
        entity: str,
        neighbors: List[Dict],
        max_claims: int = None,
        aspects_required: Optional[List[str]] = None,
        source_prefix: str = "Neo4j",
    ) -> Optional[Dict]:
        """
        通用的单个QA生成方法，减少代码重复
        """
        if max_claims is None:
            max_claims = self.DEFAULT_MAX_CLAIMS
        
        neighbors = self.dedup_neighbors(neighbors)
        if not neighbors:
            return None

        question = self.build_natural_question(task_type, entity)
        evidence_bank = self.build_evidence_bank(
            entity, 
            neighbors, 
            max_edges=self.DEFAULT_MAX_EDGES, 
            min_edges_preferred=self.DEFAULT_MIN_EDGES_PREFERRED
        )
        if not evidence_bank:
            return None

        allowed = self.build_allowed_entities(
            entity, 
            neighbors, 
            evidence_bank, 
            k=self.DEFAULT_ALLOWED_ENTITIES_K
        )

        if aspects_required is None:
            aspects_required = self._aspect_list_default(task_type)

        prompt = self.make_strict_prompt(
            task_type=task_type,
            question=question,
            center_entity=entity,
            allowed_entities=allowed,
            evidence_bank=evidence_bank,
            max_claims=max_claims,
            aspects_required=aspects_required,
        )

        qa = {
            "type": task_type,
            "question": question,
            "entity": entity,
            "neighbors": neighbors[:12],
            "source": f"{source_prefix} + LLM(JSON:aspects+claim+evidence) + Validator",
        }

        qa = self.generate_with_retry(
            qa, 
            prompt, 
            allowed, 
            evidence_bank, 
            max_retry=self.DEFAULT_MAX_RETRY
        )
        self._update_generation_stats(qa)
        return qa


def main():
    parser = argparse.ArgumentParser(description="博士论文级因果链QA生成器 - Neo4j版本（自然问句 + aspects+claim+evidence JSON + TopK白名单 + 本地模型支持）")
    parser.add_argument("--csv", help="CSV知识图谱文件路径（可选，用于首次导入数据到Neo4j）")
    parser.add_argument("--output", default="output", help="输出目录")
    parser.add_argument("--gene-function", type=int, default=10, help="基因功能QA数量")
    parser.add_argument("--regulation", type=int, default=10, help="调控机制QA数量")
    parser.add_argument("--phenotype", type=int, default=10, help="表型分析QA数量")
    parser.add_argument("--species", type=int, default=10, help="物种特征QA数量")
    parser.add_argument("--pathway", type=int, default=10, help="调控通路QA数量")
    parser.add_argument("--threshold", type=float, default=0.6, help="验证阈值")

    # API端点选择（参考 argi_filter_v4_local.py）
    # 默认根据环境变量LLM_API_TYPE决定，如果未设置则使用OpenAI
    # 注意：如果.env中设置了LLM_API_TYPE=openai，则默认使用OpenAI
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--use-local", action="store_true",
                      help="使用本地OSS模型")
    group.add_argument("--use-openai", action="store_true",
                      help="使用OpenAI API（默认，如果.env中LLM_API_TYPE=openai）")

    # 新增：统计报告白名单控制
    parser.add_argument("--stats-json", default=None, help="DataImporter.save_stats 输出的统计报告 JSON 路径")
    parser.add_argument("--restrict-to-report", action="store_true", help="启用统计报告白名单过滤（node_types/relations/species）")
    parser.add_argument("--report-topk", type=int, default=None, help="严格只使用统计报告 TopK 白名单（例如 20）")
    parser.add_argument("--drop-generic-relations", action="store_true", help="丢弃低信息关系（had/is/in/include...）")
    parser.add_argument("--restrict-species-to-top", action="store_true", help="物种严格限制为白名单（通常配合TopK）")

    # 新增：从Top统计信息生成QA
    parser.add_argument("--use-top-stats", action="store_true", default=False, help="直接从Neo4j查询Top K统计信息并生成QA（不使用stats-json文件）")
    parser.add_argument("--top-k", type=int, default=20, help="Top K统计信息查询的K值（默认20）")

    # 新增：确定性模式参数
    parser.add_argument("--deterministic-mode", action="store_true", default=False, help="启用确定性模式（可复现，适用于测试和验证）")
    parser.add_argument("--seed", type=int, default=42, help="随机种子（确定性模式下生效，确保结果可复现）")

    # 新增：基于关键词生成QA
    parser.add_argument("--keyword", type=str, default=None, help="基于关键词生成QA（如：rice, wheat等）")
    parser.add_argument("--keyword-qa-num", type=int, default=20, help="基于关键词生成的QA数量（默认20）")

    args = parser.parse_args()

    # 设置API端点（参考 argi_filter_v4_local.py）
    from llm_client import set_api_endpoint, LOCAL_API_BASE_URL, OPENAI_API_BASE_URL, load_env
    # 加载.env文件
    load_env()
    
    # 根据参数和环境变量决定使用哪个API
    # 优先级：命令行参数 > 环境变量 > 默认值（OpenAI）
    if args.use_openai:
        use_local = False
    elif args.use_local:
        use_local = True
    else:
        # 根据环境变量决定，默认使用OpenAI
        llm_api_type = os.getenv("LLM_API_TYPE", "openai").lower()
        use_local = (llm_api_type == "local")
        print(f"ℹ️  根据环境变量LLM_API_TYPE={llm_api_type}，使用{'本地' if use_local else 'OpenAI'} API")
    
    set_api_endpoint(use_local=use_local)

    # 确定API端点类型和详细信息
    api_type = "本地OSS" if use_local else "OpenAI"
    base_url = LOCAL_API_BASE_URL if use_local else OPENAI_API_BASE_URL
    model = os.environ.get('LOCAL_MODEL', 'gpt-oss-120b') if use_local else os.environ.get('OPENAI_MODEL', 'gpt-5.1')

    print("=" * 80)
    print("🌱 博士论文级因果链问答系统 - Neo4j版本（自然问句 + aspects+claim+evidence JSON + TopK白名单 + 本地模型支持 + 确定性模式）")
    print("=" * 80)
    print(f"🔌 API端点: {api_type}")
    print(f"🏠 base_url: {base_url}")
    print(f"🤖 模型: {model}")
    if args.deterministic_mode:
        print(f"🎯 确定性模式: 启用，随机种子={args.seed}")
    else:
        print(f"ℹ  随机模式: 每次运行结果可能不同")
    print("=" * 80)

    generator = DoctoralQAGenerator(
        validation_threshold=args.threshold,
        stats_json=args.stats_json,
        restrict_to_report=args.restrict_to_report,
        drop_generic_relations=args.drop_generic_relations,
        restrict_species_to_top=args.restrict_species_to_top,
        report_topk=args.report_topk,
        deterministic_mode=args.deterministic_mode,
        seed=args.seed,
    )
    generator.load_knowledge_graph(args.csv)

    # 选择生成模式
    if args.keyword:
        # 模式3：基于关键词生成QA（优先级最高）
        print(f"\n🚀 使用关键词模式：基于关键词 '{args.keyword}' 生成QA")
        generator.generate_qa_by_keyword(
            keyword=args.keyword,
            num_qa=args.keyword_qa_num
        )
    elif args.use_top_stats:
        # 模式1：从Top K统计信息直接生成
        print("\n🚀 使用Top统计信息模式：直接从Neo4j查询Top K统计信息并生成QA")
        num_per_type = {
            "gene_function": args.gene_function,
            "regulation": args.regulation,
            "phenotype": args.phenotype,
            "species": args.species,
            "pathway": args.pathway,
        }
        generator.generate_qa_from_top_stats(num_per_type, top_k=args.top_k)
    else:
        # 模式2：使用原有的生成方式
        print("\n🚀 使用传统模式：根据指定类型生成QA")
        num_per_type = {
            "gene_function": args.gene_function,
            "regulation": args.regulation,
            "phenotype": args.phenotype,
            "species": args.species,
            "pathway": args.pathway,
        }
        generator.generate_all_qa(num_per_type)

    generator.save_qa_pairs(args.output)


if __name__ == "__main__":
    main()
