#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
llm_answer_validator.py

升级版：基于知识图谱的 LLM 答案验证器（aspects + claim + evidence 引用 + 证据校验）
重点：
1) “可疑 token”误伤修复：对 GTP/ATP/ADP/ARF 前缀碎片/菌株号碎片等做白名单与上下文豁免。
2) 否定语义关系处理：识别否定关系，内部计算 effective_polarity（不要求改 LLM 输出字段）。
3) 新增 info_factor：信息充足度因子（evidence 覆盖、关系多样性、邻居重合、非META占比）。
4) aspect_count < 3 => 直接 fail（hard fail，不看分数）。

依赖：
- 仅依赖你项目的 kg_system.PlantKnowledgeGraph（不依赖额外第三方库）
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Set, Tuple

from kg_system import PlantKnowledgeGraph


# -----------------------------
# Utilities
# -----------------------------
def _safe_lower(s: str) -> str:
    return (s or "").strip().lower()


def _norm_space(s: str) -> str:
    s = (s or "").strip()
    s = re.sub(r"\s+", " ", s)
    return s


def _as_list(x: Any) -> List[Any]:
    if x is None:
        return []
    if isinstance(x, list):
        return x
    return [x]


def _is_empty_str(x: Any) -> bool:
    return isinstance(x, str) and x.strip() == ""


@dataclass
class Triple:
    head: str
    relation: str
    tail: str
    direction: str = "out"  # for display; matching uses head/relation/tail primarily


# -----------------------------
# Validator
# -----------------------------
class LLMAnswerValidator:
    """
    证据引用 + claim 校验 + aspects hard constraint + info_factor
    """

    # --------- Point (1)：可疑 token 白名单（避免误伤） ---------
    _CHEM_STOPWORDS = {
        "gtp", "atp", "adp", "gdp", "nad", "fadh2", "fad", "coa", "amp",
        "co2", "h2o", "h+", "na+", "k+", "ca2+", "mg2+",
        "dna", "rna", "mrna", "trna", "rrna",
    }
    _COMMON_GENE_PREFIXES = {"arf", "rve", "npr", "toc", "phr", "ubc"}

    # --------- Point (2)：否定语义关系识别 ---------
    _NEGATIVE_RELATION_PHRASES = {
        "was not identified as",
        "is not identified as",
        "was not detected as",
        "is not detected as",
        "does not affect",
        "do not affect",
        "not associated with",
        "is not associated with",
        "was not associated with",
        "no association with",
        "not correlated with",
        "is not correlated with",
        "was not correlated with",
        "not required for",
        "is not required for",
        "was not required for",
        "not involved in",
        "is not involved in",
        "was not involved in",
        "not expressed in",
        "is not expressed in",
        "was not expressed in",
        # 你示例里这种也应该是“否定语义”
        "not overlapping with de in",
    }

    # meta/免责声明类关系（允许没有 evidence_ids）
    _META_RELATIONS = {
        "needs_more_context_for",
        "insufficient_information_for",
        "cannot_determine_from_available_information",
        "cannot_be_inferred_from_available_information",
        "unknown_from_available_information",
        "no_supported_claims_for",
    }

    # aspects 允许集合
    _ASPECTS_ALLOWED = {"gene_function", "regulation", "phenotype", "species", "pathway"}

    def __init__(self, kg: PlantKnowledgeGraph, validation_threshold: float = 0.6, min_aspects_required: int = 3):
        self.kg = kg
        self.validation_threshold = validation_threshold
        self.min_aspects_required = int(min_aspects_required)

        self.validation_stats = {
            "total_validated": 0,
            "passed": 0,
            "failed": 0,
            "avg_confidence": 0.0,
        }

    # -----------------------------
    # Public API
    # -----------------------------
    def validate_answer(self, qa_pair: Dict[str, Any]) -> Dict[str, Any]:
        self.validation_stats["total_validated"] += 1

        center_entity = _norm_space(str(qa_pair.get("entity", "") or ""))
        allowed_entities = _as_list(qa_pair.get("allowed_entities"))
        allowed_entities = [_norm_space(str(x)) for x in allowed_entities if str(x).strip()]
        allowed_set = set(allowed_entities) if allowed_entities else set()

        evidence_bank_raw = qa_pair.get("evidence_bank") or {}
        evidence_bank = self._parse_evidence_bank(evidence_bank_raw)

        answer_raw = qa_pair.get("answer")
        answer_json, parse_note = self._parse_answer_json(answer_raw)

        claims = _as_list(answer_json.get("claims"))
        used_evidence_raw = answer_json.get("used_evidence") or {}
        used_evidence = self._parse_evidence_bank(used_evidence_raw)

        merged_evidence = dict(evidence_bank)
        for eid, tri in used_evidence.items():
            if eid not in merged_evidence:
                merged_evidence[eid] = tri

        # 0) aspects validation (hard constraint)
        aspect_validation = self._validate_aspects(answer_json)

        # 1) entity validation
        entity_validation = self._validate_entities(
            center_entity=center_entity,
            allowed_set=allowed_set,
            claims=claims,
            answer_text=str(answer_json.get("answer_text", "") or ""),
        )

        # 2) evidence references validation
        evidence_validation = self._validate_evidence_references(
            claims=claims,
            evidence=merged_evidence,
        )

        # 3) kg consistency
        kg_consistency = self._validate_kg_neighbor_overlap(
            qa_pair=qa_pair,
            center_entity=center_entity,
            claims=claims,
        )

        # 4) claim support validation
        claim_validation = self._validate_claims_supported_by_evidence(
            claims=claims,
            allowed_set=allowed_set,
            evidence=merged_evidence,
        )

        # 5) info_factor (new)
        info_factor = self._compute_info_factor(
            aspects=aspect_validation.get("aspects", []),
            evidence=merged_evidence,
            evidence_validation=evidence_validation,
            claim_validation=claim_validation,
            kg_consistency=kg_consistency,
        )

        # 6) aggregate confidence score
        confidence = self._aggregate_confidence(
            entity_validation=entity_validation,
            evidence_validation=evidence_validation,
            kg_consistency=kg_consistency,
            claim_validation=claim_validation,
            info_factor=info_factor,
        )

        # hard fail: aspect_count < min_aspects_required
        hard_fail = not bool(aspect_validation.get("passed"))
        validation_passed = (not hard_fail) and (confidence >= self.validation_threshold)

        details = self._make_details(
            aspect_validation=aspect_validation,
            info_factor=info_factor,
            entity_validation=entity_validation,
            evidence_validation=evidence_validation,
            kg_consistency=kg_consistency,
            claim_validation=claim_validation,
            hard_fail=hard_fail,
        )

        out = {
            "validation": {
                "parse_note": parse_note,
                "aspect_validation": aspect_validation,
                "info_factor": info_factor,
                "entity_validation": entity_validation,
                "evidence_validation": evidence_validation,
                "kg_consistency": kg_consistency,
                "claim_validation": claim_validation,
                "confidence_score": float(confidence),
                "confidence_level": self._confidence_level(confidence),
                "validation_passed": bool(validation_passed),
                "hard_fail": bool(hard_fail),
                "validation_details": details,
            }
        }

        # stats
        if validation_passed:
            self.validation_stats["passed"] += 1
        else:
            self.validation_stats["failed"] += 1
        n = self.validation_stats["total_validated"]
        prev = self.validation_stats["avg_confidence"]
        self.validation_stats["avg_confidence"] = prev + (confidence - prev) / max(1, n)

        return out

    # -----------------------------
    # Parsing
    # -----------------------------
    def _parse_answer_json(self, answer_raw: Any) -> Tuple[Dict[str, Any], str]:
        if isinstance(answer_raw, dict):
            return answer_raw, "answer(dict)"
        if isinstance(answer_raw, str):
            s = answer_raw.strip()
            if not s:
                return {"aspects": [], "answer_text": "", "claims": [], "used_evidence": {}}, "answer(empty_str)"
            try:
                j = json.loads(s)
                if isinstance(j, dict):
                    # ensure fields exist
                    if "aspects" not in j:
                        j["aspects"] = []
                    if "claims" not in j:
                        j["claims"] = []
                    if "used_evidence" not in j:
                        j["used_evidence"] = {}
                    if "answer_text" not in j:
                        j["answer_text"] = ""
                    return j, "answer(str->json)"
                return {"aspects": [], "answer_text": s, "claims": [], "used_evidence": {}}, "answer(str->json_non_dict)"
            except Exception:
                return {"aspects": [], "answer_text": s, "claims": [], "used_evidence": {}}, "answer(str_plain)"
        return {"aspects": [], "answer_text": "", "claims": [], "used_evidence": {}}, "answer(unknown_type)"

    def _parse_evidence_bank(self, evidence_raw: Any) -> Dict[str, Triple]:
        out: Dict[str, Triple] = {}
        if not isinstance(evidence_raw, dict):
            return out
        for eid, v in evidence_raw.items():
            try:
                if not isinstance(v, dict):
                    continue
                h = _norm_space(str(v.get("head", "") or ""))
                r = _norm_space(str(v.get("relation", "") or ""))
                t = _norm_space(str(v.get("tail", "") or ""))
                d = _norm_space(str(v.get("direction", "") or "out")) or "out"
                if h and r and t:
                    out[str(eid)] = Triple(head=h, relation=r, tail=t, direction=d)
            except Exception:
                continue
        return out

    # -----------------------------
    # New: aspect validation (hard constraint)
    # -----------------------------
    def _validate_aspects(self, answer_json: Dict[str, Any]) -> Dict[str, Any]:
        aspects_raw = answer_json.get("aspects", [])
        aspects = []
        for a in _as_list(aspects_raw):
            a = _safe_lower(str(a))
            if a in self._ASPECTS_ALLOWED and a not in aspects:
                aspects.append(a)

        aspect_count = len(aspects)
        passed = aspect_count >= self.min_aspects_required

        invalid = []
        for a in _as_list(aspects_raw):
            a0 = _safe_lower(str(a))
            if a0 and a0 not in self._ASPECTS_ALLOWED:
                invalid.append(a0)

        return {
            "aspects": aspects,
            "aspect_count": int(aspect_count),
            "min_required": int(self.min_aspects_required),
            "invalid_aspects": sorted(set(invalid)),
            "passed": bool(passed),
        }

    # -----------------------------
    # Validation blocks
    # -----------------------------
    def _validate_entities(
        self,
        center_entity: str,
        allowed_set: Set[str],
        claims: List[Dict[str, Any]],
        answer_text: str,
    ) -> Dict[str, Any]:
        declared_entities: Set[str] = set()
        invalid_claim_entities: List[str] = []

        for c in claims:
            if not isinstance(c, dict):
                continue
            h = _norm_space(str(c.get("head", "") or ""))
            t = _norm_space(str(c.get("tail", "") or ""))
            if h:
                declared_entities.add(h)
            if t:
                declared_entities.add(t)

            if allowed_set:
                if h and h not in allowed_set:
                    invalid_claim_entities.append(h)
                if t and t not in allowed_set:
                    invalid_claim_entities.append(t)

        invalid_claim_entities = sorted(set(invalid_claim_entities))

        suspicious = self._extract_entity_like_tokens(answer_text)
        suspicious = self._filter_suspicious_tokens(
            suspicious_tokens=suspicious,
            allowed_set=allowed_set,
            declared_entities=declared_entities,
        )

        if allowed_set:
            if not claims:
                coverage_score = 0.5
            else:
                total_entities = 0
                bad_entities = 0
                for c in claims:
                    if not isinstance(c, dict):
                        continue
                    h = _norm_space(str(c.get("head", "") or ""))
                    t = _norm_space(str(c.get("tail", "") or ""))
                    if h:
                        total_entities += 1
                        if h not in allowed_set:
                            bad_entities += 1
                    if t:
                        total_entities += 1
                        if t not in allowed_set:
                            bad_entities += 1
                if total_entities == 0:
                    coverage_score = 0.5
                else:
                    coverage_score = max(0.0, 1.0 - (bad_entities / total_entities))
        else:
            coverage_score = 0.8

        passed = (coverage_score >= 0.6) and (len(invalid_claim_entities) == 0)

        return {
            "center_entity": center_entity,
            "allowed_entities_count": len(allowed_set),
            "declared_entities_in_claims": sorted(declared_entities),
            "invalid_claim_entities": invalid_claim_entities,
            "suspicious_tokens_outside_allowed": sorted(suspicious),
            "coverage_score": float(coverage_score),
            "passed": bool(passed),
        }

    def _validate_evidence_references(
        self,
        claims: List[Dict[str, Any]],
        evidence: Dict[str, Triple],
    ) -> Dict[str, Any]:
        referenced: List[str] = []
        missing: List[str] = []
        bad_evidence_format: List[str] = []
        empty_evidence_for_nonmeta = 0

        for c in claims:
            if not isinstance(c, dict):
                continue
            rel = _norm_space(str(c.get("relation", "") or ""))
            evidence_ids = _as_list(c.get("evidence_ids"))
            evidence_ids = [str(x) for x in evidence_ids if str(x).strip()]

            is_meta = self._is_meta_claim(rel, c)

            if not is_meta:
                if not evidence_ids:
                    empty_evidence_for_nonmeta += 1
                else:
                    referenced.extend(evidence_ids)

        for eid in referenced:
            if eid not in evidence:
                missing.append(eid)
            else:
                tri = evidence[eid]
                if not (tri.head and tri.relation and tri.tail):
                    bad_evidence_format.append(eid)

        referenced_uniq = sorted(set(referenced))
        missing_uniq = sorted(set(missing))
        bad_format_uniq = sorted(set(bad_evidence_format))

        denom = max(1, len(referenced_uniq) + empty_evidence_for_nonmeta)
        ok = len(missing_uniq) == 0 and len(bad_format_uniq) == 0 and empty_evidence_for_nonmeta == 0
        support_score = 1.0 if ok else max(
            0.0,
            1.0 - (len(missing_uniq) + len(bad_format_uniq) + empty_evidence_for_nonmeta) / denom
        )

        return {
            "referenced_evidence_ids": referenced_uniq,
            "missing_evidence_ids": missing_uniq,
            "bad_evidence_format": bad_format_uniq,
            "empty_evidence_for_nonmeta": int(empty_evidence_for_nonmeta),
            "support_score": float(support_score),
            "passed": bool(support_score >= 0.8),
        }

    def _validate_kg_neighbor_overlap(
        self,
        qa_pair: Dict[str, Any],
        center_entity: str,
        claims: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        neighbors = qa_pair.get("neighbors")
        neighbor_ids: Set[str] = set()

        if isinstance(neighbors, list):
            for n in neighbors:
                if isinstance(n, dict):
                    nid = _norm_space(str(n.get("id", "") or ""))
                    if nid:
                        neighbor_ids.add(nid)
        else:
            try:
                ns = self.kg.get_neighbors(center_entity) or []
                for n in ns:
                    if isinstance(n, dict):
                        nid = _norm_space(str(n.get("id", "") or ""))
                        if nid:
                            neighbor_ids.add(nid)
            except Exception:
                pass

        mentioned_entities: Set[str] = set()
        for c in claims:
            if not isinstance(c, dict):
                continue
            h = _norm_space(str(c.get("head", "") or ""))
            t = _norm_space(str(c.get("tail", "") or ""))
            if h:
                mentioned_entities.add(h)
            if t:
                mentioned_entities.add(t)

        overlap = len(mentioned_entities & neighbor_ids)

        if not neighbor_ids:
            avg = 0.7
        else:
            avg = overlap / max(1, len(neighbor_ids))
            avg = min(1.0, max(0.0, avg * 2.0))

        return {
            "neighbors_count": int(len(neighbor_ids)),
            "mentioned_entities_in_claims": sorted(mentioned_entities),
            "overlap_count": int(overlap),
            "average_score": float(avg),
            "passed": bool(avg >= 0.3),
        }

    def _validate_claims_supported_by_evidence(
        self,
        claims: List[Dict[str, Any]],
        allowed_set: Set[str],
        evidence: Dict[str, Triple],
    ) -> Dict[str, Any]:
        validated: List[Dict[str, Any]] = []
        supported = 0
        unsupported = 0
        unknown = 0

        for c in claims:
            if not isinstance(c, dict):
                continue
            head = _norm_space(str(c.get("head", "") or ""))
            rel = _norm_space(str(c.get("relation", "") or ""))
            tail = _norm_space(str(c.get("tail", "") or ""))
            polarity = _norm_space(str(c.get("polarity", "positive") or "positive"))
            evidence_ids = _as_list(c.get("evidence_ids"))
            evidence_ids = [str(x) for x in evidence_ids if str(x).strip()]
            conf = c.get("confidence", None)

            if self._is_meta_claim(rel, c):
                unknown += 1
                validated.append({
                    "head": head,
                    "relation": rel,
                    "tail": tail,
                    "polarity": polarity or "positive",
                    "effective_polarity": self._effective_polarity(rel, polarity),
                    "evidence_ids": evidence_ids,
                    "confidence": conf,
                    "status": "meta",
                    "support_score": 0.5,
                    "evidence": [],
                })
                continue

            if allowed_set:
                if (head and head not in allowed_set) or (tail and tail not in allowed_set):
                    unsupported += 1
                    validated.append({
                        "head": head,
                        "relation": rel,
                        "tail": tail,
                        "polarity": polarity or "positive",
                        "effective_polarity": self._effective_polarity(rel, polarity),
                        "evidence_ids": evidence_ids,
                        "confidence": conf,
                        "status": "invalid_entity",
                        "support_score": 0.0,
                        "evidence": [],
                        "note": "claim 中实体不在 allowed_entities",
                    })
                    continue

            if not (head and rel and tail):
                unsupported += 1
                validated.append({
                    "head": head,
                    "relation": rel,
                    "tail": tail,
                    "polarity": polarity or "positive",
                    "effective_polarity": self._effective_polarity(rel, polarity),
                    "evidence_ids": evidence_ids,
                    "confidence": conf,
                    "status": "bad_claim_format",
                    "support_score": 0.0,
                    "evidence": [],
                    "note": "claim 缺少 head/relation/tail",
                })
                continue

            if not evidence_ids:
                unsupported += 1
                validated.append({
                    "head": head,
                    "relation": rel,
                    "tail": tail,
                    "polarity": polarity or "positive",
                    "effective_polarity": self._effective_polarity(rel, polarity),
                    "evidence_ids": evidence_ids,
                    "confidence": conf,
                    "status": "missing_evidence",
                    "support_score": 0.0,
                    "evidence": [],
                    "note": "非 meta claim 必须提供 evidence_ids",
                })
                continue

            ev_hits: List[Dict[str, Any]] = []
            hit = False
            for eid in evidence_ids:
                tri = evidence.get(eid)
                if not tri:
                    continue
                if self._triple_matches_claim(tri, head, rel, tail):
                    hit = True
                    ev_hits.append({
                        "eid": eid,
                        "triple": {
                            "head": tri.head,
                            "relation": tri.relation,
                            "tail": tri.tail,
                            "direction": tri.direction,
                        }
                    })

            if hit:
                supported += 1
                validated.append({
                    "head": head,
                    "relation": rel,
                    "tail": tail,
                    "polarity": polarity or "positive",
                    "effective_polarity": self._effective_polarity(rel, polarity),
                    "evidence_ids": evidence_ids,
                    "confidence": conf,
                    "status": "supported",
                    "support_score": 1.0,
                    "evidence": ev_hits,
                })
            else:
                unsupported += 1
                validated.append({
                    "head": head,
                    "relation": rel,
                    "tail": tail,
                    "polarity": polarity or "positive",
                    "effective_polarity": self._effective_polarity(rel, polarity),
                    "evidence_ids": evidence_ids,
                    "confidence": conf,
                    "status": "unsupported",
                    "support_score": 0.0,
                    "evidence": [],
                    "note": "evidence_ids 中未找到与 claim 三元组严格一致的证据",
                })

        claim_count = len([c for c in claims if isinstance(c, dict)])
        support_rate = supported / max(1, supported + unsupported) if (supported + unsupported) > 0 else 0.5
        avg_support = (
            sum(float(x.get("support_score", 0.0)) for x in validated) / max(1, len(validated))
            if validated else 0.5
        )

        passed = (supported >= max(1, int(0.4 * max(1, claim_count)))) and (support_rate >= 0.5)
        if claim_count > 0 and (supported == 0) and (unsupported == 0) and (unknown == claim_count):
            passed = True

        return {
            "claims_validated": validated,
            "claim_count": int(claim_count),
            "supported_count": int(supported),
            "unsupported_count": int(unsupported),
            "unknown_count": int(unknown),
            "support_rate": float(support_rate),
            "average_support_score": float(avg_support),
            "passed": bool(passed),
        }

    # -----------------------------
    # New: info_factor
    # -----------------------------
    def _compute_info_factor(
        self,
        aspects: List[str],
        evidence: Dict[str, Triple],
        evidence_validation: Dict[str, Any],
        claim_validation: Dict[str, Any],
        kg_consistency: Dict[str, Any],
    ) -> Dict[str, Any]:
        """
        info_factor：衡量“信息是否足够支撑一个多维（>=3 aspects）回答”
        建议信号：
        - evidence_count（unique）
        - relation_diversity（unique relation count / evidence_count）
        - supported_nonmeta_count（supported claims）
        - meta_ratio（meta / total）
        - neighbor_overlap（kg_consistency）
        """
        ev_count = len(evidence or {})
        rels = set()
        for tri in (evidence or {}).values():
            if tri and tri.relation:
                rels.add(_norm_space(tri.relation))
        rel_div = (len(rels) / max(1, ev_count))

        claim_total = int(claim_validation.get("claim_count", 0))
        supported = int(claim_validation.get("supported_count", 0))
        unknown = int(claim_validation.get("unknown_count", 0))
        meta_ratio = (unknown / max(1, claim_total))

        overlap_score = float(kg_consistency.get("average_score", 0.7))
        ev_ref_score = float(evidence_validation.get("support_score", 0.5))
        avg_support = float(claim_validation.get("average_support_score", 0.5))

        # 归一化“证据数量得分”：>=6 视为较好
        ev_count_score = min(1.0, ev_count / 6.0)

        # 信息因子综合（你可以按数据分布继续调权）
        # - 证据数量/多样性、claim 支撑、邻居重合、证据引用结构
        raw = (
            0.30 * ev_count_score +
            0.15 * min(1.0, rel_div * 1.5) +
            0.25 * avg_support +
            0.15 * overlap_score +
            0.15 * ev_ref_score
        )
        # meta_ratio 越高越说明信息不足，做惩罚
        raw = raw * (1.0 - 0.35 * min(1.0, meta_ratio))

        raw = float(min(1.0, max(0.0, raw)))

        return {
            "evidence_count": int(ev_count),
            "unique_relations": int(len(rels)),
            "relation_diversity": float(rel_div),
            "supported_claims": int(supported),
            "claim_total": int(claim_total),
            "meta_ratio": float(meta_ratio),
            "neighbor_overlap_score": float(overlap_score),
            "score": float(raw),
        }

    # -----------------------------
    # Scoring & details
    # -----------------------------
    def _aggregate_confidence(
        self,
        entity_validation: Dict[str, Any],
        evidence_validation: Dict[str, Any],
        kg_consistency: Dict[str, Any],
        claim_validation: Dict[str, Any],
        info_factor: Dict[str, Any],
    ) -> float:
        """
        加权融合：
        - claim support 最重要
        - evidence reference 次之
        - entity constraint 次之
        - kg overlap 弱信号
        - info_factor：额外“信息充足度”修正（乘法/加法都可；这里用加权加法）
        """
        w_claim = 0.40
        w_evidence = 0.22
        w_entity = 0.16
        w_kg = 0.08
        w_info = 0.14

        s_claim = float(claim_validation.get("average_support_score", 0.5))
        s_evidence = float(evidence_validation.get("support_score", 0.5))
        s_entity = float(entity_validation.get("coverage_score", 0.5))
        s_kg = float(kg_consistency.get("average_score", 0.7))
        s_info = float(info_factor.get("score", 0.5))

        score = w_claim * s_claim + w_evidence * s_evidence + w_entity * s_entity + w_kg * s_kg + w_info * s_info
        return float(min(1.0, max(0.0, score)))

    def _confidence_level(self, score: float) -> str:
        if score >= 0.85:
            return "high"
        if score >= 0.6:
            return "medium"
        return "low"

    def _make_details(
        self,
        aspect_validation: Dict[str, Any],
        info_factor: Dict[str, Any],
        entity_validation: Dict[str, Any],
        evidence_validation: Dict[str, Any],
        kg_consistency: Dict[str, Any],
        claim_validation: Dict[str, Any],
        hard_fail: bool,
    ) -> List[str]:
        details: List[str] = []

        if hard_fail:
            details.append(f"❌ aspect_count 不足：要求 ≥ {aspect_validation.get('min_required')}，当前为 {aspect_validation.get('aspect_count')}（直接 fail）。")
        else:
            details.append(f"✅ aspects 满足要求：{aspect_validation.get('aspects', [])}。")

        # info_factor
        details.append(
            f"ℹ️ info_factor={info_factor.get('score', 0.0):.2f} "
            f"(evidence={info_factor.get('evidence_count')}, rels={info_factor.get('unique_relations')}, meta_ratio={info_factor.get('meta_ratio'):.2f})"
        )

        if claim_validation.get("passed"):
            if claim_validation.get("support_rate", 0.0) >= 0.8:
                details.append("✅ Claim 支撑度高：多数断言可被结构化关系支持。")
            else:
                details.append("⚠️ Claim 支撑度中等：部分断言支持不足或 evidence 未对齐。")
        else:
            details.append("❌ Claim证据不足：多数断言无法找到支持证据或实体不合规。")

        if evidence_validation.get("passed"):
            details.append("✅ Evidence 引用结构良好：evidence_id 可解释且格式规范。")
        else:
            details.append("❌ Evidence 引用存在问题：缺失/格式错误/非meta断言缺少证据。")

        if entity_validation.get("passed"):
            details.append("✅ 实体约束基本满足：claims 实体与允许集合对齐良好。")
        else:
            details.append("❌ 实体约束较差：claims 中出现不允许实体或格式问题。")

        if kg_consistency.get("passed"):
            details.append("✅ 围绕中心实体：与其已知关联存在一定重合。")
        else:
            details.append("⚠️ 与中心实体关联较弱：可考虑多用邻居实体构建可检验断言。")

        sus = entity_validation.get("suspicious_tokens_outside_allowed") or []
        if sus:
            details.append(f"ℹ️ 检测到少量实体样 token 但未在允许集：{sus[:8]}{'...' if len(sus)>8 else ''}")

        return details

    # -----------------------------
    # Token extraction & filtering (Point 1)
    # -----------------------------
    def _extract_entity_like_tokens(self, text: str) -> Set[str]:
        text = text or ""
        tokens: Set[str] = set()

        patterns = [
            r"\b[A-Z]{2,}[A-Z0-9\-\+\/]*\b",
            r"\b[A-Z][a-z]{1,5}\d+\b",
            r"\b[A-Za-z]{2,8}\d{1,4}\b",
            r"\b[A-Z0-9]{2,}\-[A-Z0-9\-]{2,}\b",
        ]
        for p in patterns:
            for m in re.findall(p, text):
                tokens.add(_norm_space(m))

        for m in re.findall(r"“([^”]{1,40})”", text):
            tokens.add(_norm_space(m))
        for m in re.findall(r"\"([^\"]{1,40})\"", text):
            tokens.add(_norm_space(m))

        tokens = {t for t in tokens if len(t) >= 2}
        return tokens

    def _filter_suspicious_tokens(
        self,
        suspicious_tokens: Set[str],
        allowed_set: Set[str],
        declared_entities: Set[str],
    ) -> Set[str]:
        out: Set[str] = set()
        allowed_lowers = {_safe_lower(x) for x in allowed_set} if allowed_set else set()
        declared_lowers = {_safe_lower(x) for x in declared_entities} if declared_entities else set()

        for tok in suspicious_tokens:
            tl = _safe_lower(tok)
            if not tl:
                continue

            if tl in self._CHEM_STOPWORDS:
                continue

            if tl in allowed_lowers or tl in declared_lowers:
                continue

            if tl in self._COMMON_GENE_PREFIXES:
                if any(x.startswith(tl) for x in allowed_lowers) or any(x.startswith(tl) for x in declared_lowers):
                    continue

            if allowed_lowers and any(tl in x for x in allowed_lowers):
                continue
            if declared_lowers and any(tl in x for x in declared_lowers):
                continue

            if tl.replace("-", "") in self._CHEM_STOPWORDS:
                continue

            out.add(tok)

        return out

    # -----------------------------
    # Negative relation handling (Point 2)
    # -----------------------------
    def _effective_polarity(self, relation: str, polarity: str) -> str:
        rl = _safe_lower(relation)
        pl = _safe_lower(polarity) or "positive"

        if rl in self._NEGATIVE_RELATION_PHRASES:
            return "negative"

        if "not" in rl and (
            "identified" in rl
            or "associated" in rl
            or "affect" in rl
            or "required" in rl
            or "involved" in rl
            or "expressed" in rl
            or "detected" in rl
            or "overlapping" in rl
        ):
            return "negative"

        if pl in {"negative", "pos", "positive", "unknown"}:
            return "negative" if pl == "negative" else ("positive" if pl in {"pos", "positive"} else "unknown")
        return "positive"

    def _is_meta_claim(self, relation: str, claim: Dict[str, Any]) -> bool:
        rl = _safe_lower(relation)
        if rl in self._META_RELATIONS:
            return True

        tail = _norm_space(str(claim.get("tail", "") or ""))
        ev = _as_list(claim.get("evidence_ids"))
        ev = [str(x).strip() for x in ev if str(x).strip()]
        if (not tail) and (not ev) and (("context" in rl) or ("insufficient" in rl) or ("cannot" in rl) or ("unknown" in rl)):
            return True
        return False

    # -----------------------------
    # Evidence matching
    # -----------------------------
    def _triple_matches_claim(self, tri: Triple, head: str, relation: str, tail: str) -> bool:
        """
        strict match：head/relation/tail 全一致（大小写与空格已归一）
        注意：生成器端已统一把证据存成 head -rel-> tail 的“正向”形式，
             所以这里不再用 direction 做翻转匹配（避免 in/out 双重语义混乱）。
        """
        h = _norm_space(head)
        r = _norm_space(relation)
        t = _norm_space(tail)
        if not (h and r and t):
            return False
        if _norm_space(tri.relation) != r:
            return False
        return (_norm_space(tri.head) == h) and (_norm_space(tri.tail) == t)


if __name__ == "__main__":
    pass
