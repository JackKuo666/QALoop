#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Prompt Enhancer Module

将扩展分类信息添加到 QA 生成提示词中，让模型根据分类视角进行精准扩增。
- 保持 seed 结构不变，仅增强 prompt 上下文。
- 支持 deterministic 类别选择，保证同一 seed 多次运行结果一致（利于数据可复现）。
"""

from __future__ import annotations

import hashlib
import random
import re
import sys
from dataclasses import dataclass
from typing import Dict, List, Optional, Sequence, Tuple

# Add parent directory to Python path to allow imports
sys.path.insert(0, __file__.replace('optimization/prompt_enhancer.py', ''))

from core.qa_generator_v2 import SeedQuestion


EXP_CAT_PREFIX = "EXP_CAT:"


@dataclass(frozen=True)
class EnhancerConfig:
    """
    Enhancer configuration.

    selection_mode:
        - "deterministic": same seed -> same chosen category (stable)
        - "random": random choice each time
    deterministic_salt:
        Changes the deterministic mapping if you want another stable permutation.
    """
    selection_mode: str = "deterministic"  # "deterministic" | "random"
    deterministic_salt: str = "PromptEnhancer.v1"
    max_category_len_in_prompt: int = 60
    header_width: int = 70


def _norm(s: str) -> str:
    s = (s or "").strip().lower()
    s = re.sub(r"\s+", " ", s)
    return s


def _stable_choice(items: Sequence[str], key: str) -> str:
    """
    Deterministically choose an element from items based on key.
    """
    if not items:
        raise ValueError("items must be non-empty")
    h = hashlib.sha256(key.encode("utf-8")).hexdigest()
    idx = int(h[:8], 16) % len(items)
    return items[idx]


class PromptEnhancer:
    """提示词增强器（优化版）"""

    def __init__(self, config: Optional[EnhancerConfig] = None):
        self.config = config or EnhancerConfig()

        # ---- category -> strategy description (keyword-driven fallback) ----
        self.category_to_strategy: Dict[str, str] = {
            # 分子生物学相关
            "分子生物学": "重点关注分子机制、基因调控、蛋白质功能等微观层面的科学问题",
            "分子遗传学": "从基因表达、遗传变异、基因组编辑等角度深入分析",
            "功能基因组学": "关注基因功能注释、通路分析、系统生物学方法",
            "转录调控": "聚焦转录因子、表观遗传、基因调控网络",
            "基因编辑": "从CRISPR、基因编辑技术、遗传转化等技术创新角度",
            "载体工程": "涉及基因克隆、表达载体构建、转化体系优化",

            # 生理学相关
            "生理学": "从植物生理过程、功能机制等宏观角度分析",
            "生理生态": "关注植物与环境互作、生理适应机制",
            "光合作用": "重点讨论光合生理、光能转化效率、碳固定机制",
            "代谢": "从物质代谢、能量代谢、代谢途径调控等角度",
            "信号转导": "聚焦激素信号、环境信号感知与响应机制",
            "发育生物学": "关注植物生长发育、形态建成、发育调控",
            "繁殖生物学": "从开花、授粉、结实等繁殖过程角度",

            # 育种学相关
            "育种": "从品种改良、选择育种、杂交优势等应用角度",
            "分子育种": "结合分子标记、基因组选择等现代育种技术",
            "经典育种": "关注传统育种方法、选择策略、杂交改良",
            "种质资源": "从种质评价、创新利用、基因资源保护角度",
            "回交导入": "聚焦特定性状导入、背景选择、育种流程",

            # 生物统计学相关
            "统计": "从实验设计、数据分析、统计推断等方法学角度",
            "生物统计": "关注统计模型、假设检验、方差分析等方法",
            "实验设计": "聚焦实验方案设计、对照设置、变量控制",
            "数据分析": "强调数据挖掘、模式识别、预测建模",
            "统计遗传": "从数量遗传、遗传参数估计、选择指数等角度",

            # 生态学相关
            "生态": "从生态系统、群落结构、生态功能等宏观角度",
            "群体生态": "关注群体动态、种间关系、竞争与共存",
            "冠层": "聚焦冠层结构、光分布、田间微环境",
            "环境": "从环境因子、环境胁迫、环境适应性角度",
            "适应": "关注植物适应性进化、胁迫响应机制",

            # 遗传学相关
            "遗传": "从遗传规律、遗传变异、遗传机制角度",
            "群体遗传": "聚焦基因频率、遗传漂变、选择作用",
            "基因组": "从基因组结构、基因组变异、比较基因组角度",
            "遗传变异": "关注SNP、InDel、CNV等变异类型及效应",
            "关联分析": "聚焦GWAS、连锁分析、精细定位方法",
            "基因组选择": "从基因组预测、遗传评估、选择效率角度",

            # 表型学相关
            "表型": "从表型测量、表型变异、表型与基因型关联角度",
            "表型组": "关注高通量表型、多维表型数据、表型组学",
            "高通量表型": "聚焦自动化表型采集、图像分析、表型平台",
            "时序表型": "从动态表型、发育轨迹、时间序列分析角度",
            "性状": "关注目标性状、复杂性状、候选基因验证",
            "成像": "从显微成像、荧光成像、高光谱成像等角度",
            "显微成像": "聚焦细胞形态、亚细胞结构、超微结构观察",

            # 生物信息学相关
            "生物信息": "从生物信息学方法、数据库、数据挖掘角度",
            "组学": "关注基因组学、转录组学、蛋白质组学、代谢组学",
            "系统生物学": "聚焦系统建模、网络分析、整合分析方法",
            "网络生物学": "从生物网络、网络拓扑、模块分析角度",
            "机器学习": "关注机器学习算法、模式识别、预测模型",
            "深度学习": "聚焦深度神经网络、图像识别、自然语言处理",
            "图模型": "从图论方法、网络分析、图数据库角度",

            # 生物化学相关
            "生物化学": "从生化反应、酶学机制、代谢途径角度",
            "酶学": "关注酶催化机制、酶活性调控、酶工程",
            "代谢工程": "聚焦代谢途径设计、途径优化、代谢调控",

            # 作物学相关
            "作物学": "从作物生产、栽培技术、管理措施等应用角度",
            "栽培": "关注种植技术、密度调控、田间管理",
            "耕作": "聚焦土壤耕作、轮作制度、保护性耕作",
            "田间": "从田间试验、实际生产、应用推广角度",
            "管理": "关注生产管理、技术集成、效益评估",

            # 逆境生物学相关
            "逆境": "从环境胁迫、逆境生理、抗逆机制角度",
            "胁迫": "聚焦盐胁迫、干旱胁迫、温度胁迫等非生物胁迫",
            "抗性": "关注抗性鉴定、抗性机制、抗性遗传",
            "耐盐": "从盐碱地利用、耐盐机制、盐胁迫响应角度",
            "耐旱": "聚焦水分利用、耐旱性评价、节水农业",
            "耐高温": "关注热胁迫、高温适应性、抗热机制",
            "耐低温": "从冷害机理、抗寒性、抗冻机制角度",
        }

        # ---- base category templates (ZH/EN) ----
        self.category_templates_zh: Dict[str, str] = {
            "分子生物学": self._tpl_zh(
                title="分子生物学",
                bullets=[
                    "重点关注分子机制、基因调控、蛋白质功能等微观层面的科学问题",
                    "可涉及：基因表达调控、蛋白互作、信号通路、分子标记等",
                    "答案建议覆盖：机制要点、关键分子（基因/蛋白）、实验验证路线与判据",
                ],
            ),
            "生理学": self._tpl_zh(
                title="植物生理学",
                bullets=[
                    "关注植物生理过程、功能机制、生长发育调控",
                    "可涉及：光合作用、呼吸作用、物质运输、激素调控等",
                    "答案建议覆盖：生理机理、调控因子、测定方法与生理意义",
                ],
            ),
            "育种学": self._tpl_zh(
                title="作物育种学",
                bullets=[
                    "关注品种改良、选择育种、杂交优势等应用价值",
                    "可涉及：育种目标、选择方法、杂交策略、品质改良等",
                    "答案建议覆盖：育种方案、技术路线、预期效果与应用前景",
                ],
            ),
            "生物统计学": self._tpl_zh(
                title="生物统计学",
                bullets=[
                    "关注实验设计、数据分析、统计推断等方法学",
                    "可涉及：方差分析、回归分析、多变量统计、贝叶斯方法等",
                    "答案建议覆盖：统计模型/检验、实验设计要点、结果解释与统计意义",
                ],
            ),
            "生态学": self._tpl_zh(
                title="生态学",
                bullets=[
                    "关注植物与环境互作、适应性、生态功能",
                    "可涉及：群体生态、生理生态、进化生态等",
                    "答案建议覆盖：生态机制、关键环境因子、适应策略与生态意义",
                ],
            ),
            "遗传学": self._tpl_zh(
                title="遗传学",
                bullets=[
                    "关注遗传规律、遗传变异、遗传机制",
                    "可涉及：数量遗传、群体遗传、分子遗传、遗传参数估计等",
                    "答案建议覆盖：遗传效应、变异来源、遗传模型与可验证推断",
                ],
            ),
            "表型学": self._tpl_zh(
                title="表型组学",
                bullets=[
                    "关注表型测量、表型变异、表型与基因型关联",
                    "可涉及：高通量表型、图像分析、动态监测、关联建模等",
                    "答案建议覆盖：表型定义与指标、测量/采集方法、分析流程与关联解释",
                ],
            ),
            "生物信息学": self._tpl_zh(
                title="生物信息学",
                bullets=[
                    "关注生物数据处理、信息提取、知识发现",
                    "可涉及：数据库/工具、算法流程、整合分析、预测建模等",
                    "答案建议覆盖：数据来源、方法步骤、工具选择与结果解读",
                ],
            ),
            "生物化学": self._tpl_zh(
                title="生物化学",
                bullets=[
                    "关注生化反应、酶学机制、代谢途径",
                    "可涉及：酶催化、代谢通路、调控节点、能量代谢等",
                    "答案建议覆盖：反应机理、关键酶/底物、调控方式与生化意义",
                ],
            ),
            "作物学": self._tpl_zh(
                title="作物学",
                bullets=[
                    "关注作物生产、栽培技术、管理措施",
                    "可涉及：种植制度、栽培参数、田间管理、产量形成等",
                    "答案建议覆盖：技术要点、关键参数、适用条件与效果评估",
                ],
            ),
            "逆境生物学": self._tpl_zh(
                title="逆境生物学",
                bullets=[
                    "关注环境胁迫、逆境生理、抗逆机制",
                    "可涉及：盐/旱/高温/低温等胁迫类型与响应通路",
                    "答案建议覆盖：胁迫机理、抗逆策略、调控通路与应用建议",
                ],
            ),
        }

        # 英文模板（可进一步扩充；目前覆盖“基础类别”）
        self.category_templates_en: Dict[str, str] = {
            "分子生物学": self._tpl_en(
                title="Molecular Biology",
                bullets=[
                    "Emphasize molecular mechanisms, gene regulation, and protein function",
                    "May include: expression regulation, protein interactions, signaling pathways",
                    "Answer should cover: key molecules, mechanism, and validation approaches",
                ],
            ),
            "生理学": self._tpl_en(
                title="Plant Physiology",
                bullets=[
                    "Focus on physiological processes and functional regulation",
                    "May include: photosynthesis, transport, hormone regulation",
                    "Answer should cover: mechanism, factors, measurements, significance",
                ],
            ),
            "育种学": self._tpl_en(
                title="Crop Breeding",
                bullets=[
                    "Focus on breeding objectives and practical value",
                    "May include: selection strategies, crossing schemes, trait improvement",
                    "Answer should cover: pipeline, expected gains, and deployment considerations",
                ],
            ),
            "生物统计学": self._tpl_en(
                title="Biostatistics",
                bullets=[
                    "Focus on experimental design, analysis, and inference",
                    "May include: ANOVA, regression, multivariate models, Bayesian inference",
                    "Answer should cover: model choice, design, interpretation, significance",
                ],
            ),
            "生态学": self._tpl_en(
                title="Ecology",
                bullets=[
                    "Focus on plant–environment interactions and adaptation",
                    "May include: population dynamics, stress ecology, eco-evolutionary aspects",
                    "Answer should cover: drivers, mechanisms, strategies, ecological meaning",
                ],
            ),
            "遗传学": self._tpl_en(
                title="Genetics",
                bullets=[
                    "Focus on genetic variation, inheritance, and mechanisms",
                    "May include: quantitative genetics, population genetics, genetic models",
                    "Answer should cover: effects, sources of variation, and testable predictions",
                ],
            ),
            "表型学": self._tpl_en(
                title="Phenotyping / Phenomics",
                bullets=[
                    "Focus on phenotype definition, measurement, and genotype–phenotype links",
                    "May include: high-throughput phenotyping, imaging, time-series traits",
                    "Answer should cover: metrics, measurement, analysis workflow, associations",
                ],
            ),
            "生物信息学": self._tpl_en(
                title="Bioinformatics",
                bullets=[
                    "Focus on data processing and computational interpretation",
                    "May include: databases, pipelines, integration, prediction models",
                    "Answer should cover: data sources, methods, tools, interpretation",
                ],
            ),
            "生物化学": self._tpl_en(
                title="Biochemistry",
                bullets=[
                    "Focus on enzymatic mechanisms and metabolic pathways",
                    "May include: catalysis, pathway regulation, key nodes",
                    "Answer should cover: mechanism, enzymes/substrates, regulation, meaning",
                ],
            ),
            "作物学": self._tpl_en(
                title="Agronomy / Crop Science",
                bullets=[
                    "Focus on production, cultivation practices, and management",
                    "May include: field management, parameter optimization, yield formation",
                    "Answer should cover: practices, parameters, conditions, and evaluation",
                ],
            ),
            "逆境生物学": self._tpl_en(
                title="Stress Biology",
                bullets=[
                    "Focus on stress types, responses, and tolerance mechanisms",
                    "May include: drought/salt/heat/cold stress pathways",
                    "Answer should cover: mechanisms, regulation, and applications",
                ],
            ),
        }

        # 缓存：category string -> rendered template
        self._template_cache: Dict[Tuple[str, str], str] = {}

        # 为模糊匹配准备一个“归一化索引”
        self._strategy_keys_norm: List[Tuple[str, str]] = [
            (_norm(k), k) for k in self.category_to_strategy.keys()
        ]

    # --------------------------
    # Template builders
    # --------------------------
    def _tpl_zh(self, title: str, bullets: List[str]) -> str:
        lines = [f"【扩展分类视角：{title}】", "请从以下角度进行扩增："]
        lines += [f"- {b}" for b in bullets]
        return "\n".join(lines)

    def _tpl_en(self, title: str, bullets: List[str]) -> str:
        lines = [f"[Expansion Perspective: {title}]", "Expand using the following guidance:"]
        lines += [f"- {b}" for b in bullets]
        return "\n".join(lines)

    # --------------------------
    # Category extraction & selection
    # --------------------------
    def extract_expanded_categories(self, seed: SeedQuestion) -> List[str]:
        """从 seed.tags 中提取扩展分类信息（EXP_CAT:xxx）"""
        tags = getattr(seed, "tags", None) or []
        out: List[str] = []
        for tag in tags:
            if isinstance(tag, str) and tag.startswith(EXP_CAT_PREFIX):
                cat = tag[len(EXP_CAT_PREFIX):].strip()
                if cat:
                    out.append(cat)
        # 去重但保序
        seen = set()
        uniq = []
        for c in out:
            if c not in seen:
                uniq.append(c)
                seen.add(c)
        return uniq

    def _choose_category(self, seed: SeedQuestion, categories: List[str]) -> str:
        """
        Choose one category from extracted categories.
        - deterministic: stable per (seed.question + salt)
        - random: random choice
        """
        if len(categories) == 1:
            return categories[0]

        mode = (self.config.selection_mode or "").strip().lower()
        if mode == "random":
            return random.choice(categories)

        # deterministic default
        key = f"{self.config.deterministic_salt}||{getattr(seed, 'question', '')}||{getattr(seed, 'species', '')}"
        return _stable_choice(categories, key)

    # --------------------------
    # Category template resolution (exact -> fuzzy -> fallback)
    # --------------------------
    def _resolve_template(self, category: str, lang: str) -> str:
        cache_key = (category, lang)
        if cache_key in self._template_cache:
            return self._template_cache[cache_key]

        lang = "zh" if lang != "en" else "en"
        cat = (category or "").strip()
        cat_norm = _norm(cat)

        # 1) exact match: base category templates
        if lang == "zh":
            if cat in self.category_templates_zh:
                tpl = self.category_templates_zh[cat]
                self._template_cache[cache_key] = tpl
                return tpl
        else:
            # EN uses the same key set (中文分类名作为键)，也允许直接命中
            if cat in self.category_templates_en:
                tpl = self.category_templates_en[cat]
                self._template_cache[cache_key] = tpl
                return tpl

        # 2) fuzzy match by keyword inclusion in the selected category string
        matched_keyword = None
        matched_desc = None

        # 优先：直接包含策略 key（中文常见）
        for key_norm, key_raw in self._strategy_keys_norm:
            if key_norm and key_norm in cat_norm:
                matched_keyword = key_raw
                matched_desc = self.category_to_strategy[key_raw]
                break

        # 3) fallback: try reverse containment (category is short, keyword is long)
        if matched_keyword is None:
            for key_norm, key_raw in self._strategy_keys_norm:
                if cat_norm and cat_norm in key_norm:
                    matched_keyword = key_raw
                    matched_desc = self.category_to_strategy[key_raw]
                    break

        # 4) render fuzzy template
        if matched_keyword and matched_desc:
            if lang == "zh":
                tpl = "\n".join([
                    f"【扩展分类视角：{matched_keyword}】",
                    "请从以下角度进行扩增：",
                    f"- {matched_desc}",
                    f"- 重点关注：{cat[:self.config.max_category_len_in_prompt]}",
                    "- 答案建议覆盖：专业术语、科学机理、实验验证思路、潜在应用价值",
                ])
            else:
                tpl = "\n".join([
                    f"[Expansion Perspective: {matched_keyword}]",
                    "Expand using the following guidance:",
                    f"- {matched_desc}",
                    f"- Focus: {cat[:self.config.max_category_len_in_prompt]}",
                    "- Answer should include: terminology, mechanism, validation ideas, potential applications",
                ])
            self._template_cache[cache_key] = tpl
            return tpl

        # 5) final fallback: generic template
        if lang == "zh":
            tpl = "\n".join([
                f"【扩展分类视角：{cat[:self.config.max_category_len_in_prompt]}】",
                f"请从 {cat[:self.config.max_category_len_in_prompt]} 的专业角度进行扩增，关注该领域的核心科学问题、技术方法与研究范式。",
                "答案建议体现该领域的专业深度、可验证性与潜在应用价值。",
            ])
        else:
            tpl = "\n".join([
                f"[Expansion Perspective: {cat[:self.config.max_category_len_in_prompt]}]",
                "Expand from the field-specific perspective, emphasizing core scientific questions, methods, and research conventions.",
                "Answer should demonstrate depth, testability, and potential applications.",
            ])

        self._template_cache[cache_key] = tpl
        return tpl

    # --------------------------
    # Public: build category context
    # --------------------------
    def build_category_context(self, seed: SeedQuestion, lang: str = "zh") -> str:
        """
        Build expansion context block based on ONE selected EXP_CAT category in seed.tags.
        If no EXP_CAT tags exist, return empty string.
        """
        cats = self.extract_expanded_categories(seed)
        if not cats:
            return ""

        selected = self._choose_category(seed, cats)
        template = self._resolve_template(selected, lang=lang)

        w = max(30, int(self.config.header_width))
        line = "=" * w

        if lang == "zh":
            block = "\n".join([
                "",
                line,
                "【扩展分类指导信息】",
                line,
                template,
                "",
                line,
                "【生成要求】",
                line,
                "请基于上述扩展分类视角生成符合专业标准的问答对。",
                "要求：概念边界清晰、机制表述可验证、结论自洽，避免泛泛而谈。",
                line,
                "",
            ])
            return block

        # English
        block = "\n".join([
            "",
            line,
            "[Expansion Guidance]",
            line,
            template,
            "",
            line,
            "[Generation Requirements]",
            line,
            "Generate a professional-grade QA pair following the guidance above.",
            "Requirements: clear concept boundaries, testable mechanisms, coherent conclusions, avoid vague statements.",
            line,
            "",
        ])
        return block

    # --------------------------
    # Public: build seed deepening context (NEW FEATURE)
    # --------------------------
    def build_seed_deepening_context(self, seed: SeedQuestion, category: str, base_question: str, lang: str = "zh") -> str:
        """
        Build a context for deepening the seed question from a specific EXP_CAT perspective.
        This keeps the seed question's core theme but approaches it from a different angle.
        """
        # Get the template for this specific category
        template = self._resolve_template(category, lang=lang)

        w = max(30, int(self.config.header_width))
        line = "=" * w

        if lang == "zh":
            block = "\n".join([
                "",
                line,
                "【种子问题深化指导】",
                line,
                f"基于种子问题：{base_question}",
                "",
                f"【深化视角：{category}】",
                template,
                "",
                line,
                "【深化要求】",
                line,
                "请保持种子问题的核心主题和科学问题，但从上述视角进行深化：",
                "1. 保持与种子问题的主题一致性和科学逻辑",
                "2. 从指定扩展分类的专业角度重新阐述问题",
                "3. 深入探讨该视角下的科学机制、技术方法或应用价值",
                "4. 确保生成的是对种子问题的专业化深化，而非全新问题",
                "",
                "5. **答案必须包含CoT推理链**",
                "   - 在答案中生成4-7步推理过程（cot字段）",
                "   - cot数组中的每个元素使用'Step X:'格式，但不要在内容中重复'Step X:'",
                "   - 例如：cot = ['Step 1:分析光温信号', 'Step 2:评估协同作用']",
                "   - 抽象为可复用的科学推理逻辑，避免具体数值或细节",
                line,
                "",
            ])
            return block

        # English
        block = "\n".join([
            "",
            line,
            "[Seed Deepening Guidance]",
            line,
            f"Based on seed question: {base_question}",
            "",
            f"[Deepening Perspective: {category}]",
            template,
            "",
            line,
            "[Deepening Requirements]",
            line,
            "Maintain the core theme and scientific logic of the seed question, deepen it from the specified perspective:",
            "1. Keep theme consistency and scientific logic with the seed question",
            "2. Reframe the question from the professional angle of the specified EXP_CAT",
            "3. Explore scientific mechanisms, technical methods, or application values in depth",
            "4. Ensure this is a professional deepening of the seed question, not a completely new question",
            "",
            "5. **Answer MUST include CoT reasoning chain**",
            "   - Generate 4-7 reasoning steps in the answer (cot field)",
            "   - Each element in cot array uses 'Step X:' format, but do NOT repeat 'Step X:' in the content itself",
            "   - Example: cot = ['Step 1:Analyze light signals', 'Step 2:Evaluate synergistic effects']",
            "   - Abstract as reusable scientific reasoning logic, avoiding specific numbers or details",
            line,
            "",
        ])
        return block

    def enhance_seed_question_with_category(self, seed: SeedQuestion, category: str, base_question: str, lang: str = "zh") -> SeedQuestion:
        """
        Enhance a SeedQuestion by deepening it from a specific EXP_CAT perspective.
        This creates a deepened version that maintains the seed's core theme.
        """
        ctx = self.build_seed_deepening_context(seed, category, base_question, lang=lang)

        if not ctx:
            return seed

        deepened_question = f"{base_question}\n{ctx}"

        # 保存原始问题（用于RAG查询）
        original_question = getattr(seed, 'original_question', None) or seed.question

        return SeedQuestion(
            question=deepened_question,
            answer=seed.answer,
            category=seed.category,
            species=seed.species,
            difficulty=seed.difficulty,
            tags=list(seed.tags) if getattr(seed, "tags", None) else [],
            original_question=original_question,  # 保留原始问题
        )

    def create_deepened_variants(self, seed: SeedQuestion, base_question: str, lang: str = "zh") -> List[SeedQuestion]:
        """
        Create deepened variants of the seed question from all available EXP_CAT perspectives.
        Returns one deepened variant for each EXP_CAT category.
        """
        categories = self.extract_expanded_categories(seed)
        if not categories:
            # If no EXP_CAT tags, return the original seed
            return [seed]

        variants = []
        for category in categories:
            variant = self.enhance_seed_question_with_category(seed, category, base_question, lang=lang)
            variants.append(variant)

        return variants

    # --------------------------
    # Public: enhance seed question
    # --------------------------
    def enhance_seed_question(self, seed: SeedQuestion, base_question: str, lang: str = "zh") -> SeedQuestion:
        """
        Enhance a SeedQuestion by appending category context to the question prompt.
        If no EXP_CAT tags exist, return the original seed unchanged.
        """
        ctx = self.build_category_context(seed, lang=lang)
        if not ctx:
            return seed

        enhanced_question = f"{base_question}\n{ctx}"

        return SeedQuestion(
            question=enhanced_question,
            answer=seed.answer,
            category=seed.category,
            species=seed.species,
            difficulty=seed.difficulty,
            tags=list(seed.tags) if getattr(seed, "tags", None) else [],
        )

    def enhance_multiple_seeds(self, seeds: List[SeedQuestion], lang: str = "zh") -> List[SeedQuestion]:
        """Batch enhance seeds using this enhancer instance."""
        out: List[SeedQuestion] = []
        for s in seeds:
            out.append(self.enhance_seed_question(s, s.question, lang=lang))
        return out

    # --------------------------
    # Reporting utilities (consistent with selection policy)
    # --------------------------
    def summarize_categories(self, seeds: List[SeedQuestion]) -> Dict[str, int]:
        """Count how many times each EXP_CAT appears across seeds (availability, not chosen)."""
        stats: Dict[str, int] = {}
        for s in seeds:
            for c in self.extract_expanded_categories(s):
                stats[c] = stats.get(c, 0) + 1
        return stats

    def chosen_category_for_seed(self, seed: SeedQuestion) -> Optional[str]:
        cats = self.extract_expanded_categories(seed)
        if not cats:
            return None
        return self._choose_category(seed, cats)

    def print_enhancement_report(self, seeds: List[SeedQuestion], lang: str = "zh", show_examples: int = 3) -> None:
        """
        Print a deterministic and consistent report:
        - availability distribution (all possible EXP_CAT)
        - chosen category distribution (what enhancer would actually use)
        """
        total = len(seeds)
        avail_stats = self.summarize_categories(seeds)

        chosen_stats: Dict[str, int] = {}
        enhanced = 0
        for s in seeds:
            chosen = self.chosen_category_for_seed(s)
            if chosen:
                enhanced += 1
                chosen_stats[chosen] = chosen_stats.get(chosen, 0) + 1

        print("\n" + "=" * 70)
        print("Prompt Enhancement Report")
        print("=" * 70)
        print(f"Total seeds: {total}")
        print(f"Enhanced seeds (has EXP_CAT): {enhanced}")
        print(f"Enhancement rate: {(enhanced / total * 100.0) if total else 0:.1f}%")
        print(f"Selection mode: {self.config.selection_mode}")

        if avail_stats:
            print("\nAvailable EXP_CAT distribution (count of availability):")
            for i, (cat, cnt) in enumerate(sorted(avail_stats.items(), key=lambda x: x[1], reverse=True), 1):
                print(f"  {i:2d}. {cat:40s}: {cnt:4d}")

        if chosen_stats:
            print("\nChosen category distribution (based on selection policy):")
            for i, (cat, cnt) in enumerate(sorted(chosen_stats.items(), key=lambda x: x[1], reverse=True), 1):
                print(f"  {i:2d}. {cat:40s}: {cnt:4d}")

        if show_examples > 0:
            print("\nExamples:")
            for i, s in enumerate(seeds[:show_examples], 1):
                chosen = self.chosen_category_for_seed(s) or "None"
                q_preview = (s.question or "").replace("\n", " ")
                q_preview = q_preview[:80] + ("..." if len(q_preview) > 80 else "")
                print(f"  [{i}] Question: {q_preview}")
                print(f"      Chosen EXP_CAT: {chosen}")

        print("=" * 70)


# -----------------------------
# Example usage
# -----------------------------
if __name__ == "__main__":
    from run_expansion_from_dir_expert import parse_expert_questions, map_categories_to_expert

    expert_questions_data = parse_expert_questions("专家问题_扩增CoT.xlsx")

    enhancer = PromptEnhancer(
        config=EnhancerConfig(
            selection_mode="deterministic",   # 推荐：保证可复现
            deterministic_salt="expansion-v1",
        )
    )

    seed_questions: List[SeedQuestion] = []
    for eq in expert_questions_data:
        mapped_categories = map_categories_to_expert(eq.get("extended_categories", []), {})

        tags = ["expert_question", eq.get("direction", "未知")]
        for extended_category in eq.get("extended_categories", []):
            tags.append(f"{EXP_CAT_PREFIX}{extended_category}")

        seed_questions.append(
            SeedQuestion(
                question=eq.get("question", ""),
                answer="",
                category=mapped_categories[0] if mapped_categories else "未知",
                species=eq.get("direction", "未知"),
                difficulty="hard",
                tags=tags,
            )
        )

    enhancer.print_enhancement_report(seed_questions, lang="zh", show_examples=3)
