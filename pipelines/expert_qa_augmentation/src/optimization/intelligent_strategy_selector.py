#!/usr/bin/env python3
"""
智能策略选择器 - 增强版实现（优化重构版）

核心优化点：
1) 分类：模式加权 + 互斥优先级 + 反例抑制，降低误判
2) 领域检测：关键词加权 + 物种先验 + 类别先验
3) 评分：严格权重 40/25/15/10/10 + 归一化 + 可解释 breakdown
4) 可复现：random seed + 小 jitter
5) 组合优化：覆盖面 + 协同 + 去冗余
6) 枚举映射：容错映射，避免 getattr 失败
"""
from __future__ import annotations

from typing import List, Dict, Any, Optional, Tuple
import logging
import random
import re
from dataclasses import dataclass
from collections import Counter, defaultdict

logger = logging.getLogger(__name__)


# ---------------------------
# 数据结构
# ---------------------------
@dataclass
class SeedQuestion:
    """种子问题数据结构"""
    question: str
    answer: str
    category: str
    species: str
    difficulty: str
    tags: List[str]


# ---------------------------
# 文本工具
# ---------------------------
_CN_PUNCT = "，。；：、（）()【】[]《》“”\"\'？！?.,;:"

def _norm_text(s: str) -> str:
    if not s:
        return ""
    s = s.strip()
    # 统一空白
    s = re.sub(r"\s+", " ", s)
    return s

def _lower(s: str) -> str:
    return (s or "").lower()

def _contains_cn_phrase(text: str, phrase: str) -> bool:
    return phrase in text

def _regex_count(pattern: str, text: str, flags: int = 0) -> int:
    try:
        return len(re.findall(pattern, text, flags))
    except re.error:
        return 0

def _word_boundary(pattern: str) -> str:
    # 给英文关键词加边界，避免 "how" 命中 "show"
    return rf"\b{pattern}\b"

def _clamp(x: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, x))


# ---------------------------
# 问题类型分类器（优化）
# ---------------------------
class QuestionTypeClassifier:
    """
    问题类型分类器：加权匹配 + 优先级 + 反例抑制
    """

    # 优先级：当多个类型得分接近时，用优先级决策（越靠前优先）
    PRIORITY = [
        "hypothetical",
        "prediction",
        "comparison",
        "evaluation",
        "causal",
        "method",
        "definition",
        "application",
        "general",
    ]

    # 每类 (pattern, weight)
    PATTERNS: Dict[str, List[Tuple[str, float, str]]] = {
        "definition": [
            (r"什么是", 2.5, "cn"),
            (r"定义", 2.0, "cn"),
            (r"含义", 1.6, "cn"),
            (r"概念", 1.3, "cn"),
            (r"指的是", 1.8, "cn"),
            # “包括/组成/构成”在正文里很常见，降低权重，且需结合问句特征才加分
            (r"包括", 0.5, "cn"),
            (r"组成", 0.5, "cn"),
            (r"构成", 0.5, "cn"),
            (_word_boundary("definition"), 2.0, "en"),
            (_word_boundary("means"), 1.2, "en"),
            (_word_boundary("refers to"), 1.2, "en"),
            (_word_boundary("consists of"), 0.8, "en"),
        ],
        "method": [
            (r"如何", 2.3, "cn"),
            (r"怎么", 1.8, "cn"),
            (r"怎样", 1.8, "cn"),
            (r"步骤", 1.8, "cn"),
            (r"流程", 1.5, "cn"),
            (r"过程", 1.2, "cn"),
            (r"方法", 1.2, "cn"),
            (r"技术", 1.0, "cn"),
            (_word_boundary("how to"), 2.2, "en"),
            (_word_boundary("method"), 1.8, "en"),
            (_word_boundary("steps"), 1.6, "en"),
            (_word_boundary("process"), 1.2, "en"),
        ],
        "causal": [
            (r"为什么", 2.6, "cn"),
            (r"原因", 1.8, "cn"),
            (r"导致", 1.3, "cn"),
            (r"引起", 1.2, "cn"),
            (r"由于", 0.9, "cn"),
            (r"机理", 1.6, "cn"),
            (r"机制", 1.6, "cn"),
            (r"原理", 1.2, "cn"),
            (_word_boundary("why"), 2.2, "en"),
            (_word_boundary("because"), 1.0, "en"),
            (_word_boundary("due to"), 1.0, "en"),
            (_word_boundary("cause"), 1.2, "en"),
            (_word_boundary("reason"), 1.2, "en"),
        ],
        "comparison": [
            (r"比较", 2.2, "cn"),
            (r"对比", 2.0, "cn"),
            (r"区别", 1.8, "cn"),
            (r"差异", 1.6, "cn"),
            (r"不同", 1.0, "cn"),
            (r"优缺点", 2.0, "cn"),
            (_word_boundary("compare"), 2.0, "en"),
            (_word_boundary("vs"), 1.6, "en"),
            (_word_boundary("difference"), 1.6, "en"),
            (_word_boundary("advantage"), 1.2, "en"),
            (_word_boundary("disadvantage"), 1.2, "en"),
        ],
        "application": [
            (r"应用", 1.8, "cn"),
            (r"使用", 1.2, "cn"),
            (r"实施", 1.2, "cn"),
            (r"实践", 1.2, "cn"),
            (r"案例", 1.2, "cn"),
            (r"实例", 1.2, "cn"),
            (r"例子", 1.0, "cn"),
            (_word_boundary("application"), 1.8, "en"),
            (_word_boundary("use"), 1.2, "en"),
            (_word_boundary("practice"), 1.2, "en"),
            (_word_boundary("case"), 1.0, "en"),
            (_word_boundary("example"), 1.0, "en"),
        ],
        "prediction": [
            (r"预测", 2.2, "cn"),
            (r"趋势", 1.8, "cn"),
            (r"发展", 1.2, "cn"),
            (r"前景", 1.6, "cn"),
            (r"展望", 1.6, "cn"),
            (_word_boundary("future"), 1.2, "en"),
            (_word_boundary("prediction"), 2.0, "en"),
            (_word_boundary("trend"), 1.6, "en"),
            (_word_boundary("prospect"), 1.6, "en"),
        ],
        "hypothetical": [
            (r"如果", 2.0, "cn"),
            (r"假设", 2.0, "cn"),
            (r"假如", 2.0, "cn"),
            (r"假定", 2.0, "cn"),
            (r"设想", 1.6, "cn"),
            (_word_boundary("if"), 1.2, "en"),
            (_word_boundary("assume"), 1.6, "en"),
            (_word_boundary("hypothetical"), 2.0, "en"),
            (_word_boundary("what if"), 2.0, "en"),
            (_word_boundary("suppose"), 1.6, "en"),
        ],
        "evaluation": [
            (r"评价", 2.0, "cn"),
            (r"评估", 2.0, "cn"),
            (r"判断", 1.6, "cn"),
            (r"选择", 1.2, "cn"),
            (r"推荐", 1.6, "cn"),
            (r"性能", 1.2, "cn"),
            (r"效率", 1.2, "cn"),
            (_word_boundary("evaluate"), 2.0, "en"),
            (_word_boundary("assess"), 2.0, "en"),
            (_word_boundary("judge"), 1.6, "en"),
            (_word_boundary("performance"), 1.2, "en"),
            (_word_boundary("effectiveness"), 1.2, "en"),
        ],
    }

    @staticmethod
    def classify(question: str, answer: str) -> str:
        """
        返回问题类型
        """
        q = _lower(_norm_text(question))
        a = _lower(_norm_text(answer))
        combined = f"{q} {a}".strip()

        if not combined:
            return "general"

        # 问号加成：若存在问号，对 definition/method/causal/comparison/evaluation 加少量加成
        has_qmark = ("?" in combined) or ("？" in combined)
        qmark_boost = 0.4 if has_qmark else 0.0

        # 反例抑制：纯陈述、无问号、且 question 很短（如标题）时，整体降权
        short_title_like = (not has_qmark) and (len(q) <= 12)

        scores: Dict[str, float] = {}
        for qtype, plist in QuestionTypeClassifier.PATTERNS.items():
            s = 0.0
            for pat, w, lang in plist:
                if lang == "cn":
                    cnt = 1 if _contains_cn_phrase(combined, pat) else 0
                else:
                    cnt = _regex_count(pat, combined, flags=re.IGNORECASE)
                if cnt:
                    s += w * cnt

            # 轻微问号加成（避免无问号的“说明性段落”被误判为 definition）
            if qtype in {"definition", "method", "causal", "comparison", "evaluation"}:
                s += qmark_boost

            # 对 definition 中的“包括/组成/构成”在无问号短标题场景强抑制
            if qtype == "definition" and short_title_like:
                s *= 0.6

            scores[qtype] = s

        if not scores or all(v <= 0.0 for v in scores.values()):
            return "general"

        # 取最大分；若分数接近，按 PRIORITY 决策
        best_score = max(scores.values())
        candidates = [k for k, v in scores.items() if abs(v - best_score) <= 0.35]

        if len(candidates) == 1:
            return candidates[0]

        for p in QuestionTypeClassifier.PRIORITY:
            if p in candidates:
                return p

        return candidates[0]


# ---------------------------
# 领域检测器（优化）
# ---------------------------
class DomainDetector:
    """
    领域检测：关键词加权 + 物种先验 + 类别先验
    """

    DOMAIN_KEYWORDS: Dict[str, List[Tuple[str, float]]] = {
        "breeding": [
            ("育种", 2.0), ("选育", 1.6), ("杂交", 1.2), ("转基因", 1.8),
            ("基因编辑", 2.0), ("分子标记", 1.8), ("基因组", 1.4), ("亲本", 1.2),
            ("杂交种", 1.2), ("自交系", 1.2),
            ("breeding", 1.6), ("hybrid", 1.2), ("selection", 1.2), ("genome", 1.0), ("marker", 1.0),
        ],
        "pathology": [
            ("病害", 1.8), ("病虫害", 2.0), ("真菌", 1.2), ("细菌", 1.2), ("病毒", 1.2),
            ("防治", 1.6), ("抗性", 1.4), ("杀菌剂", 1.2), ("农药", 1.0), ("病原", 1.2),
            ("disease", 1.6), ("pathogen", 1.4), ("fungus", 1.0), ("bacteria", 1.0), ("virus", 1.0), ("resistance", 1.0),
        ],
        "physiology": [
            ("生理", 1.8), ("生长", 1.2), ("发育", 1.2), ("光合", 1.2), ("呼吸", 1.0),
            ("代谢", 1.2), ("营养", 1.0), ("水分", 1.0), ("温度", 0.8), ("激素", 1.2),
            ("physiology", 1.6), ("growth", 1.0), ("development", 1.0), ("photosynthesis", 1.0), ("metabolism", 1.0),
        ],
        "cultivation": [
            ("栽培", 2.0), ("种植", 1.6), ("管理", 1.0), ("施肥", 1.4), ("灌溉", 1.4),
            ("密度", 1.0), ("收获", 1.0), ("产量", 1.2), ("品质", 1.0),
            ("cultivation", 1.6), ("planting", 1.2), ("management", 1.0), ("fertilizer", 1.0), ("irrigation", 1.0),
        ],
        "biotechnology": [
            ("生物技术", 2.0), ("分子", 1.0), ("蛋白", 1.0), ("基因", 0.8), ("细胞", 1.0),
            ("发酵", 1.2), ("酶", 1.0), ("代谢工程", 1.6),
            ("biotechnology", 1.8), ("molecular", 1.0), ("protein", 1.0), ("gene", 0.8), ("enzyme", 1.0),
        ],
        "genetics": [
            ("遗传", 2.0), ("染色体", 1.4), ("突变", 1.2), ("表达", 1.2),
            ("调控", 1.2), ("表观遗传", 1.8),
            ("genetics", 1.8), ("chromosome", 1.2), ("mutation", 1.2), ("expression", 1.2), ("regulation", 1.0),
        ],
        "environment": [
            ("环境", 1.8), ("气候", 1.6), ("土壤", 1.2), ("生态", 1.2), ("可持续", 1.6),
            ("适应性", 1.2), ("胁迫", 1.2),
            ("environment", 1.6), ("climate", 1.4), ("soil", 1.0), ("ecology", 1.0), ("adaptation", 1.0),
        ],
        "economics": [
            ("经济", 1.8), ("成本", 1.6), ("效益", 1.6), ("市场", 1.2), ("贸易", 1.0),
            ("价格", 1.2), ("收益", 1.2),
            ("economics", 1.6), ("cost", 1.2), ("benefit", 1.2), ("market", 1.0), ("price", 1.0),
        ],
        # 可选扩展：nutrition/health 等（如果你的枚举或下游支持）
    }

    SPECIES_PRIOR: Dict[str, Dict[str, float]] = {
        "玉米": {"breeding": 1.5, "cultivation": 1.2, "physiology": 0.8},
        "大豆": {"breeding": 1.2, "cultivation": 1.0, "genetics": 1.2},
        "水稻": {"breeding": 1.2, "cultivation": 1.0, "physiology": 1.0},
        "小麦": {"breeding": 1.2, "cultivation": 1.0, "pathology": 1.0},
        "油菜": {"breeding": 1.0, "cultivation": 1.0, "biotechnology": 1.0},
        "畜禽": {"breeding": 1.0},  # 若你扩展 nutrition/health，可在此加
        "合成生物技术": {"biotechnology": 1.6, "genetics": 1.0},
    }

    CATEGORY_PRIOR: Dict[str, Dict[str, float]] = {
        # category 字段如果是你的 taxonomy，可按需加强
        "育种": {"breeding": 1.5},
        "病虫害": {"pathology": 1.5},
        "生理": {"physiology": 1.2},
        "栽培": {"cultivation": 1.2},
        "分子生物学": {"biotechnology": 1.2, "genetics": 1.0},
    }

    @staticmethod
    def detect(question: str, answer: str, category: str, species: str) -> str:
        q = _lower(_norm_text(question))
        a = _lower(_norm_text(answer))
        c = _lower(_norm_text(category))
        combined = f"{q} {a} {c}".strip()

        if not combined:
            return "general"

        scores: Dict[str, float] = {}
        for domain, kws in DomainDetector.DOMAIN_KEYWORDS.items():
            s = 0.0
            for kw, w in kws:
                if kw.lower() in combined:
                    s += w
            scores[domain] = s

        # 物种先验
        sp = (species or "").strip()
        if sp in DomainDetector.SPECIES_PRIOR:
            for d, boost in DomainDetector.SPECIES_PRIOR[sp].items():
                if d in scores:
                    scores[d] += boost

        # 类别先验
        cat = (category or "").strip()
        if cat in DomainDetector.CATEGORY_PRIOR:
            for d, boost in DomainDetector.CATEGORY_PRIOR[cat].items():
                if d in scores:
                    scores[d] += boost

        if not scores or all(v <= 0.0 for v in scores.values()):
            return "general"

        best = max(scores.items(), key=lambda x: x[1])
        # 若最高分过低（例如只命中一个弱词），回退 general，避免乱贴领域
        if best[1] < 1.2:
            return "general"
        return best[0]


# ---------------------------
# 智能策略选择器（优化）
# ---------------------------
class IntelligentStrategySelector:
    """增强版智能策略选择器（优化版）"""

    def __init__(self, rng_seed: Optional[int] = None):
        """
        rng_seed: 传入固定值可复现策略选择
        """
        self.rng = random.Random(rng_seed)
        self._generation_method_enum = None

    def _get_generation_method_enum(self):
        """延迟导入GenerationMethod以避免循环导入"""
        if self._generation_method_enum is None:
            try:
                from ..core.qa_generator_v2 import GenerationMethod
                self._generation_method_enum = GenerationMethod
            except ImportError:
                self._generation_method_enum = None
        return self._generation_method_enum

        # 策略特征映射（你原始版本 + 可维护小修）
        self.strategy_features: Dict[str, Dict[str, Any]] = {
            "paraphrase": {
                "description": "同义改写/Paraphrase",
                "question_types": ["definition", "general"],
                "domains": ["general", "breeding", "cultivation"],
                "difficulties": ["easy", "medium"],
                "complexity": 1,
                "weight": 1.0,
                "synergy": ["elaboration"],
                "keywords": ["什么是", "定义", "含义", "概念", "解释"],
            },
            "elaboration": {
                "description": "详细阐述/Elaboration",
                "question_types": ["definition", "method", "general"],
                "domains": ["general", "breeding", "cultivation"],
                "difficulties": ["easy", "medium"],
                "complexity": 1,
                "weight": 1.0,
                "synergy": ["paraphrase"],
                "keywords": ["详细", "具体", "深入", "展开", "说明"],
            },
            "perspective_shift": {
                "description": "视角转换/Perspective shift",
                "question_types": ["evaluation", "comparison", "general"],
                "domains": ["general", "economics", "environment"],
                "difficulties": ["easy", "medium", "hard"],
                "complexity": 2,
                "weight": 1.2,
                "synergy": ["comparative_analysis"],
                "keywords": ["角度", "视角", "看法", "观点", "从", "从...看"],
            },
            "multi_turn": {
                "description": "多轮起始/Multi-turn seed",
                "question_types": ["method", "application", "causal"],
                "domains": ["general", "cultivation", "pathology"],
                "difficulties": ["medium", "hard"],
                "complexity": 2,
                "weight": 1.2,
                "synergy": ["method"],
                "keywords": ["步骤", "流程", "顺序", "过程", "如何进行"],
            },
            "cross_species": {
                "description": "跨物种迁移/Cross-species migration",
                "question_types": ["comparison", "application"],
                "domains": ["breeding", "genetics", "biotechnology"],
                "difficulties": ["medium", "hard"],
                "complexity": 2,
                "weight": 1.3,
                "synergy": ["comparative_analysis"],
                "keywords": ["其他作物", "跨物种", "对比", "比较", "不同物种"],
            },
            "reverse_reasoning": {
                "description": "反向推理/Reverse reasoning",
                "question_types": ["causal", "method"],
                "domains": ["general", "physiology", "genetics"],
                "difficulties": ["medium", "hard"],
                "complexity": 2,
                "weight": 1.2,
                "synergy": ["causal_chain"],
                "keywords": ["原因", "为什么", "导致", "引起", "结果"],
            },
            "innovative_application": {
                "description": "创新应用/Innovative application",
                "question_types": ["application", "method"],
                "domains": ["biotechnology", "genetics", "cultivation"],
                "difficulties": ["medium", "hard"],
                "complexity": 2,
                "weight": 1.3,
                "synergy": ["discipline_cross"],
                "keywords": ["应用", "使用", "实施", "创新", "新方法"],
            },
            "comparative_analysis": {
                "description": "比较分析/Comparative analysis",
                "question_types": ["comparison", "evaluation"],
                "domains": ["general", "breeding", "economics"],
                "difficulties": ["medium", "hard"],
                "complexity": 2,
                "weight": 1.2,
                "synergy": ["perspective_shift", "cross_species"],
                "keywords": ["比较", "对比", "区别", "差异", "优缺点"],
            },
            "future_scenario": {
                "description": "未来场景/Future scenario",
                "question_types": ["prediction", "hypothetical"],
                "domains": ["general", "environment", "economics"],
                "difficulties": ["medium", "hard"],
                "complexity": 2,
                "weight": 1.2,
                "synergy": ["hypothetical", "temporal_shift"],
                "keywords": ["未来", "预测", "趋势", "发展", "前景", "展望"],
            },
            "hypothetical": {
                "description": "假设分析/Hypothetical",
                "question_types": ["hypothetical", "prediction"],
                "domains": ["general", "environment", "biotechnology"],
                "difficulties": ["medium", "hard"],
                "complexity": 2,
                "weight": 1.2,
                "synergy": ["future_scenario", "counterfactual"],
                "keywords": ["如果", "假设", "设想", "假如", "假定"],
            },
            "counterfactual": {
                "description": "反事实分析/Counterfactual",
                "question_types": ["hypothetical", "causal"],
                "domains": ["general", "genetics", "pathology"],
                "difficulties": ["hard"],
                "complexity": 3,
                "weight": 1.5,
                "synergy": ["hypothetical"],
                "keywords": ["如果不是", "假如没有", "反过来", "相反情况"],
            },
            "meta_question": {
                "description": "元认知问题/Meta-question",
                "question_types": ["general", "method"],
                "domains": ["general"],
                "difficulties": ["hard"],
                "complexity": 3,
                "weight": 1.5,
                "synergy": ["method"],
                "keywords": ["如何学习", "如何理解", "方法论", "研究方法"],
            },
            "temporal_shift": {
                "description": "时间维度转换/Temporal shift",
                "question_types": ["prediction", "comparison"],
                "domains": ["general", "environment", "economics"],
                "difficulties": ["medium", "hard"],
                "complexity": 2,
                "weight": 1.2,
                "synergy": ["future_scenario", "comparative_analysis"],
                "keywords": ["历史", "过去", "现在", "未来", "演变", "发展"],
            },
            "spatial_shift": {
                "description": "空间维度转换/Spatial shift",
                "question_types": ["comparison", "application"],
                "domains": ["general", "environment"],
                "difficulties": ["medium", "hard"],
                "complexity": 2,
                "weight": 1.2,
                "synergy": ["cross_species", "comparative_analysis"],
                "keywords": ["地区", "区域", "不同地方", "地理", "环境"],
            },
            "discipline_cross": {
                "description": "学科交叉/Discipline crossing",
                "question_types": ["application", "method"],
                "domains": ["biotechnology", "genetics"],
                "difficulties": ["hard"],
                "complexity": 3,
                "weight": 1.4,
                "synergy": ["innovative_application"],
                "keywords": ["跨学科", "交叉", "融合", "结合"],
            },
            "scale_change": {
                "description": "尺度变换/Scale change",
                "question_types": ["comparison", "application"],
                "domains": ["general", "economics"],
                "difficulties": ["medium", "hard"],
                "complexity": 2,
                "weight": 1.2,
                "synergy": ["comparative_analysis"],
                "keywords": ["规模", "大小", "尺度", "层次", "层面"],
            },
            "time_series": {
                "description": "时间序列/Time series",
                "question_types": ["prediction", "method"],
                "domains": ["general", "economics"],
                "difficulties": ["medium", "hard"],
                "complexity": 2,
                "weight": 1.2,
                "synergy": ["future_scenario"],
                "keywords": ["时间序列", "动态", "变化", "趋势", "演变"],
            },
            "causal_chain": {
                "description": "因果链条/Causal chain",
                "question_types": ["causal", "method"],
                "domains": ["general", "physiology", "pathology"],
                "difficulties": ["hard"],
                "complexity": 3,
                "weight": 1.4,
                "synergy": ["reverse_reasoning", "multi_turn"],
                "keywords": ["因果", "链条", "连锁", "影响", "传导"],
            },
        }

        # 难度优先级
        self.difficulty_priority = {"easy": 1, "medium": 2, "hard": 3}

        self.type_classifier = QuestionTypeClassifier()
        self.domain_detector = DomainDetector()

        # 历史使用统计
        self.usage_history: Counter = Counter()
        self.strategy_success_rate: Dict[str, float] = defaultdict(lambda: 0.5)  # 默认 0.5

        # 容错映射：策略名 -> 枚举名（如果你的枚举命名不一致，可在这里补）
        self.enum_map: Dict[str, str] = {
            # "paraphrase": "PARAPHRASE",
            # "future_scenario": "FUTURE_SCENARIO",
        }

        logger.info(f"初始化智能策略选择器：{len(self.strategy_features)} strategies, rng_seed={rng_seed}")

    # ---------------------------
    # 外部接口
    # ---------------------------
    def select_strategies_for_seed(self, seed: SeedQuestion, target_variants: int = 5, available_strategies: List = None):
        """
        为种子问题选择最优策略

        Args:
            seed: 种子问题
            target_variants: 目标变体数量
            available_strategies: 可用策略列表，如果为None则使用所有策略

        返回：List[GenerationMethod]
        """
        logger.debug(f"选择策略: {seed.question[:60]}... target={target_variants}")
        if available_strategies:
            logger.debug(f"用户指定策略: {[s.value for s in available_strategies]}")

        # 1) 识别类型/领域
        qtype = self.type_classifier.classify(seed.question, seed.answer)
        domain = self.domain_detector.detect(seed.question, seed.answer, seed.category, seed.species)
        logger.debug(f"classify => type={qtype}, domain={domain}")

        # 2) 评分（带 breakdown，便于你排查误选）
        scores, breakdown = self._calculate_strategy_scores(seed, qtype, domain)

        # 3) 排序
        ranked = sorted(scores.items(), key=lambda x: x[1], reverse=True)

        # 4) 过滤可用策略（如果用户指定了策略）
        if available_strategies:
            # 将用户指定的策略转换为名称集合
            available_strategy_names = {s.value for s in available_strategies}
            # 只保留用户指定的策略
            ranked = [(name, score) for name, score in ranked if name in available_strategy_names]
            logger.debug(f"过滤后候选策略: {[name for name, _ in ranked]}")

        # 5) 动态候选池（保证组合优化有空间）
        pool = self._dynamic_pool_size(target_variants, total=len(ranked))
        candidates = [name for name, _ in ranked[:pool]]

        # 6) 映射枚举 + 去掉不可用
        enum_candidates = []
        for name in candidates:
            enum_obj = self._to_enum(None, name)
            if enum_obj is not None:
                enum_candidates.append(enum_obj)

        # 7) 若不足，补齐可用枚举（仅从用户指定的策略中补齐）
        if len(enum_candidates) < target_variants and available_strategies:
            remaining = [s for s in available_strategies if s not in enum_candidates]
            need = target_variants - len(enum_candidates)
            if remaining and need > 0:
                self.rng.shuffle(remaining)
                enum_candidates.extend(remaining[:need])
        elif len(enum_candidates) < target_variants:
            # 用户未指定策略，使用所有策略补齐
            all_enums = []
            for name in self.strategy_features.keys():
                e = self._to_enum(None, name)
                if e is not None:
                    all_enums.append(e)
            remaining = [e for e in all_enums if e not in enum_candidates]
            need = target_variants - len(enum_candidates)
            if remaining and need > 0:
                self.rng.shuffle(remaining)
                enum_candidates.extend(remaining[:need])

        # 8) 组合优化（覆盖 + 协同 + 去冗余）
        final = self._optimize_strategy_combination(
            selected=enum_candidates,
            target_count=target_variants,
            qtype=qtype,
            domain=domain,
        )

        # 8) 记录使用（只记录最终选择）
        for e in final:
            self.usage_history[e.value] += 1

        logger.debug("final strategies: %s", [e.value for e in final])
        return final

    # ---------------------------
    # 评分：严格权重 + 可解释
    # ---------------------------
    def _calculate_strategy_scores(
        self, seed: SeedQuestion, question_type: str, domain: str
    ) -> Tuple[Dict[str, float], Dict[str, Dict[str, float]]]:
        """
        返回：
          scores[strategy] = final_score
          breakdown[strategy] = {keyword/type/domain/difficulty/complexity/usage/success/weight/jitter}
        """
        W_KEYWORD = 0.40
        W_TYPE = 0.25
        W_DOMAIN = 0.15
        W_DIFFICULTY = 0.10
        W_COMPLEXITY = 0.10

        q = _lower(_norm_text(seed.question))
        a = _lower(_norm_text(seed.answer))
        combined = f"{q} {a}".strip()

        # 题/答为空时防御
        combined = combined or q or a or ""

        difficulty_level = self.difficulty_priority.get(seed.difficulty, 2)

        total_usage = max(sum(self.usage_history.values()), 1)

        scores: Dict[str, float] = {}
        breakdown: Dict[str, Dict[str, float]] = {}

        for strategy, feat in self.strategy_features.items():
            # 1) keyword：按命中数上限归一化
            kws = feat.get("keywords", [])
            # 允许关键词是简单短语；若你未来要支持 regex，可扩展为 (pattern, is_regex)
            hit = 0
            for kw in kws:
                if not kw:
                    continue
                if kw.startswith("re:"):
                    hit += _regex_count(kw[3:], combined, flags=re.IGNORECASE)
                else:
                    hit += 1 if kw.lower() in combined else 0

            # 上限：避免关键词很长列表导致分爆炸
            hit_cap = 6
            hit = min(hit, hit_cap)
            keyword_norm = hit / hit_cap  # 0~1
            keyword_score = keyword_norm * 5.0  # 映射到 0~5

            # 2) type match（0或1）
            type_score = 5.0 if question_type in feat.get("question_types", []) else 0.0

            # 3) domain match（0或1）
            domain_score = 4.0 if domain in feat.get("domains", []) else 0.0

            # 4) difficulty match（0或1）
            diff_score = 3.0 if seed.difficulty in feat.get("difficulties", []) else 0.0

            # 5) complexity fit：按差距给分
            complexity = int(feat.get("complexity", 1))
            # difficulty <= complexity 更适合
            if difficulty_level <= complexity:
                comp_score = 2.0
            elif difficulty_level == complexity + 1:
                comp_score = 1.0
            else:
                comp_score = 0.0

            # 加权合成（严格按你指定权重）
            base = (
                keyword_score * W_KEYWORD
                + type_score * W_TYPE
                + domain_score * W_DOMAIN
                + diff_score * W_DIFFICULTY
                + comp_score * W_COMPLEXITY
            )

            # usage 降权：用得越多越降（最多降 20%）
            usage_rate = self.usage_history[strategy] / total_usage
            usage_adjust = 1.0 - _clamp(usage_rate * 0.2, 0.0, 0.2)

            # success 提权：默认 0.5，不会过分影响；上限 +15%
            success = _clamp(self.strategy_success_rate[strategy], 0.0, 1.0)
            success_adjust = 0.85 + 0.30 * success  # 0.85~1.15

            # 策略本身权重
            w = float(feat.get("weight", 1.0))

            # 可控 jitter：0~0.25（小一些，避免随机压过规则）
            jitter = self.rng.uniform(0.0, 0.25)

            final = base * usage_adjust * success_adjust * w + jitter

            scores[strategy] = final
            breakdown[strategy] = {
                "keyword_score": keyword_score,
                "type_score": type_score,
                "domain_score": domain_score,
                "difficulty_score": diff_score,
                "complexity_score": comp_score,
                "base": base,
                "usage_adjust": usage_adjust,
                "success_adjust": success_adjust,
                "weight": w,
                "jitter": jitter,
                "final": final,
            }

        return scores, breakdown

    def _dynamic_pool_size(self, target_variants: int, total: int) -> int:
        # 给组合优化留空间，但别过大
        if target_variants <= 2:
            pool = target_variants * 3
        elif target_variants <= 5:
            pool = target_variants + 5
        else:
            pool = target_variants + 8
        return max(min(pool, total), min(total, target_variants))

    def _to_enum(self, _, strategy_name: str):
        # 延迟获取GenerationMethod枚举
        GenerationMethod = self._get_generation_method_enum()
        if GenerationMethod is None:
            logger.warning(f"无法导入GenerationMethod，返回None for {strategy_name}")
            return None
        # 先走 enum_map，再走默认 upper
        enum_name = self.enum_map.get(strategy_name, strategy_name.upper())
        if hasattr(GenerationMethod, enum_name):
            return getattr(GenerationMethod, enum_name)
        # 有些枚举可能用驼峰/别名，最后尝试 value 匹配
        for e in GenerationMethod:
            if getattr(e, "value", "") == strategy_name:
                return e
        logger.warning(f"未找到策略枚举映射: {strategy_name} -> {enum_name}")
        return None

    # ---------------------------
    # 组合优化：覆盖 + 协同 + 去冗余
    # ---------------------------
    def _optimize_strategy_combination(
        self,
        selected: List,
        target_count: int,
        qtype: str,
        domain: str,
    ) -> List:
        """
        从候选 selected 中选 target_count 个。
        目标：覆盖面（不同复杂度/类型倾向）+ 协同 + 避免同质化。
        """
        if len(selected) <= target_count:
            return selected

        # 预先拿到候选的元信息
        def meta(e) -> Dict[str, Any]:
            name = e.value
            feat = self.strategy_features.get(name, {})
            return {
                "name": name,
                "complexity": int(feat.get("complexity", 1)),
                "synergy": set(feat.get("synergy", [])),
                "qtypes": set(feat.get("question_types", [])),
                "domains": set(feat.get("domains", [])),
                "weight": float(feat.get("weight", 1.0)),
            }

        metas = {e: meta(e) for e in selected}

        # Step 1: 先挑一个“锚点策略”：最贴近 qtype+domain 且权重大
        def anchor_score(e) -> float:
            m = metas[e]
            s = 0.0
            if qtype in m["qtypes"]:
                s += 2.0
            if domain in m["domains"]:
                s += 1.5
            s += 0.5 * m["weight"]
            # 偏好与难度相匹配的复杂度：hard 倾向 3，medium 倾向 2，easy 倾向 1
            return s

        remaining = selected[:]
        remaining.sort(key=anchor_score, reverse=True)
        final = [remaining.pop(0)]

        # Step 2: 迭代选择，综合：
        # - synergy（与已选策略互补）
        # - 覆盖 complexity（避免全是 complexity=2
        # - 覆盖策略类别（qtype/domain 覆盖）
        while len(final) < target_count and remaining:
            def pick_score(e) -> float:
                m = metas[e]
                s = 0.0

                # 协同：若与任一已选互为 synergy，加分
                for f in final:
                    if metas[f]["name"] in m["synergy"] or m["name"] in metas[f]["synergy"]:
                        s += 1.2

                # 覆盖 complexity：与已选不同则加分
                comp_set = {metas[f]["complexity"] for f in final}
                if m["complexity"] not in comp_set:
                    s += 0.8

                # 覆盖 qtype/domain：增加多样性
                qtype_set = set().union(*[metas[f]["qtypes"] for f in final]) if final else set()
                dom_set = set().union(*[metas[f]["domains"] for f in final]) if final else set()
                if qtype not in qtype_set and qtype in m["qtypes"]:
                    s += 0.6
                if domain not in dom_set and domain in m["domains"]:
                    s += 0.4

                # 轻微偏好权重
                s += 0.2 * m["weight"]
                return s

            remaining.sort(key=pick_score, reverse=True)
            final.append(remaining.pop(0))

        return final[:target_count]

    # ---------------------------
    # 统计与工具
    # ---------------------------
    def record_usage(self, strategy_name: str, success: bool = True):
        """
        记录策略使用情况
        """
        self.usage_history[strategy_name] += 1
        # success rate 用滑动平均；失败也应更新
        cur = self.strategy_success_rate[strategy_name]
        target = 1.0 if success else 0.0
        self.strategy_success_rate[strategy_name] = cur * 0.9 + target * 0.1

    def get_strategy_info(self, strategy: str) -> Optional[Dict[str, Any]]:
        return self.strategy_features.get(strategy)

    def list_available_strategies(self) -> List[str]:
        return list(self.strategy_features.keys())

    def get_strategy_stats(self) -> Dict[str, Any]:
        return {
            "usage_history": dict(self.usage_history),
            "success_rate": dict(self.strategy_success_rate),
            "total_strategies": len(self.strategy_features),
            "available_strategies": self.list_available_strategies(),
        }

    def reset_stats(self):
        self.usage_history.clear()
        self.strategy_success_rate.clear()
        logger.info("重置策略统计信息")
