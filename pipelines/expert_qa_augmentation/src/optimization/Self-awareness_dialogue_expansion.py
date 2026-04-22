#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
对话扩增模块（优化版）
- 基于 OpenAI messages JSONL（每行一个 {"messages":[...]}）
- 每条 seed 扩增 N 倍（默认 10）
- 增加"自然度"：规则/模板扰动 + 可选 LLM rewrite hook
- 保留 gate：结构校验、注入/越界过滤、长度约束
- 去重：exact 去重 + 预训练语言模型 embedding 语义去重（可选 FAISS 加速）
- 集成 LLMEnhancedDialogueExpander（智能扩增）

依赖：
  必需：
    pip install -U sentence-transformers numpy
  可选（大规模建议）：
    pip install -U faiss-cpu

环境变量配置：
  支持从 .env 文件读取 OPENAI_API_KEY 或 DEEPSEEK_API_KEY
  在当前目录创建 .env 文件，内容示例：
    OPENAI_API_KEY=${OPENAI_API_KEY}
    DEEPSEEK_API_KEY=${DEEPSEEK_API_KEY}

运行示例：
  python dialogue_expansion_optimized.py \
    --input seed.jsonl \
    --output out.expanded.jsonl \
    --expand_factor 10 \
    --emb_model sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2 \
    --dup_threshold 0.972 \
    --use_faiss

启用 LLM 智能扩增：
  python dialogue_expansion_optimized.py ... --enable_llm_rewrite
"""

import argparse
import json
import logging
import os
import random
import re
import time
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import numpy as np

logger = logging.getLogger(__name__)

# =============================================================================
# 基础清洗与注入检测
# =============================================================================

_WS_RE = re.compile(r"\s+")
_CONTROL_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")

INJECTION_PATTERNS = [
    r"forget\s+the\s+identity",
    r"ignore\s+previous\s+instructions",
    r"disregard\s+system",
    r"bypass\s+safety",
    r"developer\s+message",
    r"system\s+prompt",
    r"please\s+forget\s+",
    r"请忽略.*指令",
    r"忘记.*(开发者|系统|规则|指令)",
]
INJECTION_RE = re.compile("|".join(INJECTION_PATTERNS), re.IGNORECASE)


def normalize_text(t: str) -> str:
    """轻量 normalize：去控制字符、压缩空白、strip。"""
    if t is None:
        return ""
    t = _CONTROL_RE.sub("", t)
    t = t.replace("\r\n", "\n").replace("\r", "\n")
    t = _WS_RE.sub(" ", t).strip()
    return t


def signature_exact(user: str, assistant: str) -> str:
    """exact 去重 key（normalize 后）。"""
    u = normalize_text(user).lower()
    a = normalize_text(assistant).lower()
    return f"u:{u}||a:{a}"


# =============================================================================
# 数据结构
# =============================================================================

@dataclass
class DialogueSample:
    """对话样本数据结构"""
    messages: List[Dict[str, str]]  # OpenAI messages格式
    category: str = "一般对话"
    domain: str = "通用"
    tags: List[str] = None

    def __post_init__(self):
        if self.tags is None:
            self.tags = []

    def get_user_message(self) -> str:
        for msg in self.messages:
            if msg.get("role") == "user":
                return msg.get("content", "")
        return ""

    def get_assistant_message(self) -> str:
        for msg in self.messages:
            if msg.get("role") == "assistant":
                return msg.get("content", "")
        return ""

    def get_system_message(self) -> str:
        for msg in self.messages:
            if msg.get("role") == "system":
                return msg.get("content", "")
        return ""


@dataclass
class ExpandedDialogue:
    """扩增后的对话"""
    messages: List[Dict[str, str]]
    generation_method: str
    seed_sample: DialogueSample
    quality_score: float = 0.0
    meta: Optional[Dict[str, Any]] = None

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


# =============================================================================
# Gate（结构校验 + 注入过滤 + 长度约束）
# =============================================================================

class DialogueGate:
    def __init__(
        self,
        min_user_len: int = 2,
        min_assistant_len: int = 2,
        max_user_len: int = 4000,
        max_assistant_len: int = 12000,
        require_system: bool = False,
    ):
        self.min_user_len = min_user_len
        self.min_assistant_len = min_assistant_len
        self.max_user_len = max_user_len
        self.max_assistant_len = max_assistant_len
        self.require_system = require_system

    def _check_schema(self, messages: List[Dict[str, str]]) -> Tuple[bool, str]:
        if not isinstance(messages, list) or not messages:
            return False, "schema:messages_not_list"
        roles = [m.get("role") for m in messages if isinstance(m, dict)]
        if "user" not in roles or "assistant" not in roles:
            return False, "schema:missing_user_or_assistant"
        if self.require_system and "system" not in roles:
            return False, "schema:missing_system"
        return True, "ok"

    def _check_injection(self, user_text: str) -> Tuple[bool, str]:
        if INJECTION_RE.search(user_text or ""):
            return False, "safety:prompt_injection"
        return True, "ok"

    def _check_len(self, user_text: str, assistant_text: str) -> Tuple[bool, str]:
        u = normalize_text(user_text)
        a = normalize_text(assistant_text)
        if len(u) < self.min_user_len:
            return False, "len:user_too_short"
        if len(a) < self.min_assistant_len:
            return False, "len:assistant_too_short"
        if len(u) > self.max_user_len:
            return False, "len:user_too_long"
        if len(a) > self.max_assistant_len:
            return False, "len:assistant_too_long"
        return True, "ok"

    def gate(self, messages: List[Dict[str, str]]) -> Tuple[bool, str]:
        ok, reason = self._check_schema(messages)
        if not ok:
            return False, reason

        user_text = ""
        assistant_text = ""
        for m in messages:
            if m.get("role") == "user" and not user_text:
                user_text = m.get("content", "") or ""
            if m.get("role") == "assistant" and not assistant_text:
                assistant_text = m.get("content", "") or ""

        ok, reason = self._check_injection(user_text)
        if not ok:
            return False, reason

        ok, reason = self._check_len(user_text, assistant_text)
        if not ok:
            return False, reason

        return True, "ok"


# =============================================================================
# 预训练 embedding 去重（pair 去重 + 可选 assistant-only 去重）
# =============================================================================

class EmbeddingDeduper:
    """
    - 维护已接受样本向量（L2 normalize）
    - cosine sim >= threshold -> duplicate
    - 可选 FAISS 加速
    """

    def __init__(
        self,
        model_name: str,
        device: Optional[str] = None,
        use_faiss: bool = False,
    ):
        from sentence_transformers import SentenceTransformer

        self.model_name = model_name
        self.model = SentenceTransformer(model_name, device=device)

        self.use_faiss = use_faiss
        self._vecs: List[np.ndarray] = []
        self._faiss = None
        self._index = None

        if use_faiss:
            try:
                import faiss  # type: ignore
                self._faiss = faiss
            except Exception as e:
                logger.warning(f"FAISS 不可用，自动回退到 numpy 计算。err={e}")
                self._faiss = None
                self.use_faiss = False

    @staticmethod
    def _l2_normalize(v: np.ndarray) -> np.ndarray:
        n = np.linalg.norm(v)
        if n == 0:
            return v
        return v / n

    def encode(self, text: str) -> np.ndarray:
        v = self.model.encode([text], convert_to_numpy=True, show_progress_bar=False)[0].astype("float32")
        return self._l2_normalize(v)

    def _faiss_rebuild(self):
        if not (self.use_faiss and self._faiss is not None):
            return
        if not self._vecs:
            self._index = None
            return
        d = int(self._vecs[0].shape[0])
        idx = self._faiss.IndexFlatIP(d)  # normalized vec => inner product == cosine
        mat = np.stack(self._vecs, axis=0)
        idx.add(mat)
        self._index = idx

    def add(self, text: str, vec: Optional[np.ndarray] = None):
        if vec is None:
            vec = self.encode(text)
        self._vecs.append(vec)
        if self.use_faiss and self._faiss is not None:
            if self._index is None:
                self._faiss_rebuild()
            else:
                self._index.add(vec.reshape(1, -1))

    def is_duplicate(self, text: str, threshold: float, top_k: int = 16) -> Tuple[bool, float]:
        if not self._vecs:
            return False, 0.0
        vec = self.encode(text)

        # FAISS
        if self.use_faiss and self._faiss is not None and self._index is not None:
            k = min(top_k, len(self._vecs))
            sims, _ = self._index.search(vec.reshape(1, -1), k)
            max_sim = float(sims[0][0]) if k > 0 else 0.0
            return (max_sim >= threshold), max_sim

        # Numpy
        mat = np.stack(self._vecs, axis=0)
        sims = mat @ vec
        max_sim = float(np.max(sims))
        return (max_sim >= threshold), max_sim


# =============================================================================
# 受保护的名称列表（在扩增过程中保持不变）
# =============================================================================

PROTECTED_NAMES = [
    "之江实验室",
    "崖州湾国家实验室",
    "Zhejiang Lab",
    "Yazhouwan National Laboratory",
]


def protect_names(text: str) -> Tuple[str, Dict[str, str]]:
    """
    将受保护的名称替换为占位符，返回替换后的文本和映射字典。
    """
    placeholders = {}
    for i, name in enumerate(PROTECTED_NAMES):
        placeholder = f"__PROTECTED_NAME_{i}__"
        if name in text:
            placeholders[placeholder] = name
            text = text.replace(name, placeholder)
    return text, placeholders


def restore_names(text: str, placeholders: Dict[str, str]) -> str:
    """
    将占位符还原为原始的受保护名称。
    """
    for placeholder, name in placeholders.items():
        text = text.replace(placeholder, name)
    return text


# =============================================================================
# 变体模板（支持 EN + ZH + 意图识别 + 表面自然度改写）
# =============================================================================

class DialogueVariationTemplates:
    """对话变体模板（扩展版本，支持更多 intent）"""

    EN_Q_VARIANTS = {
        "identity": [
            "Who are you?",
            "Can you tell me who you are?",
            "Could you introduce yourself?",
            "May I know your identity?",
            "What is your identity?",
            "Would you mind introducing yourself briefly?",
        ],
        "name": [
            "What's your name?",
            "What do I call you?",
            "Could you tell me your name?",
            "May I know your name?",
        ],
        "capability": [
            "What can you do?",
            "What are your main capabilities?",
            "What can you help with?",
            "What are you good at?",
        ],
        "coverage": [
            "What species do you cover?",
            "Which species are within your scope?",
            "What organisms do you support?",
        ],
        "difference": [
            "What makes you different from general AI assistants?",
            "How are you different from a general assistant?",
            "Why should I use you instead of a generic AI assistant?",
        ],
        "training": [
            "What are you trained on?",
            "Where does your training data come from?",
            "What data sources were used to train you?",
        ],
        "limits": [
            "What are your limitations?",
            "What can't you do?",
            "Where should I be cautious when using you?",
        ],
        "metacog": [
            "Do you know when you don't know something?",
            "How do you handle uncertainty?",
            "How do you respond if you're not sure?",
        ],
    }

    ZH_Q_VARIANTS = {
        "identity": ["你是谁？", "可以介绍一下你自己吗？", "能否告诉我你是谁？", "我可以知道你的身份吗？"],
        "name": ["你叫什么？", "你叫什么名字？", "我该怎么称呼你？", "你可以告诉我你的名字吗？"],
        "capability": ["你有哪些能力？", "你的主要能力领域有哪些？", "你能帮我做什么？", "你擅长什么？"],
        "coverage": ["你覆盖哪些物种？", "你的物种范围是什么？", "你支持哪些作物/畜种？"],
        "difference": ["你和通用AI助手有什么不同？", "你相比通用助手有什么优势？", "为什么你更适合农业科研？"],
        "training": ["你是基于什么训练的？", "你的训练数据来自哪里？", "你学习过哪些公开资料？"],
        "limits": ["你有什么局限性？", "你有哪些做不到的事情？", "使用你时有哪些边界需要注意？"],
        "metacog": ["你知道自己不知道什么吗？", "你怎么处理不确定性？", "当你不确定时会怎么回答？"],
    }

    # 助手回答段落可组合块
    EN_ASSIST_STARTERS = ["Sure.", "Certainly.", "In short,", "Briefly,", "To summarize,"]
    ZH_ASSIST_STARTERS = ["当然。", "可以的。", "好的。", "简要来说，", "总体而言，"]

    @staticmethod
    def detect_lang(text: str) -> str:
        return "zh" if re.search(r"[\u4e00-\u9fff]", text or "") else "en"

    @staticmethod
    def detect_intent(user: str) -> str:
        u = (user or "").lower()
        uz = user or ""

        if re.search(r"\bwho are you\b|\bidentity\b|introduce yourself", u):
            return "identity"
        if re.search(r"\bwhat('?s| is) your name\b|\bcall you\b", u):
            return "name"
        if re.search(r"\bwhat can you do\b|\bcapabilit", u):
            return "capability"
        if re.search(r"\bspecies\b|\bcover\b|\bscope\b", u):
            return "coverage"
        if re.search(r"\bdifferent\b|\bgeneral ai\b|\bgeneric\b", u):
            return "difference"
        if re.search(r"\btrained\b|\btraining data\b|\bdata sources\b", u):
            return "training"
        if re.search(r"\blimitations?\b|\bcan't\b|\bcannot\b", u):
            return "limits"
        if re.search(r"\buncertain\b|\bnot sure\b|\bdon't know\b", u):
            return "metacog"

        if "你是谁" in uz or "身份" in uz or "自我介绍" in uz or "介绍一下你" in uz:
            return "identity"
        if "你叫" in uz or "称呼" in uz or "名字" in uz:
            return "name"
        if "能力" in uz or "能做" in uz or "帮我" in uz:
            return "capability"
        if "物种" in uz or "覆盖" in uz or "支持哪些" in uz:
            return "coverage"
        if "不同" in uz or "优势" in uz or "通用AI" in uz:
            return "difference"
        if "训练" in uz or "数据" in uz or "来源" in uz:
            return "training"
        if "局限" in uz or "做不到" in uz or "边界" in uz:
            return "limits"
        if "不知道" in uz or "不确定" in uz:
            return "metacog"

        return "general"

    @classmethod
    def sample_user_variation(cls, original_user: str) -> str:
        lang = cls.detect_lang(original_user)
        intent = cls.detect_intent(original_user)

        # 如果是一般意图，直接返回原文保持语言一致
        if intent == "general":
            return original_user.strip()

        if lang == "zh":
            pool = cls.ZH_Q_VARIANTS.get(intent) or []
        else:
            pool = cls.EN_Q_VARIANTS.get(intent) or []

        # 如果没有对应语言的变体池，返回原文
        if not pool:
            return original_user.strip()

        picked = random.choice(pool)

        # 自然度：轻微礼貌/语气处理
        if lang == "en":
            if random.random() < 0.20 and not picked.lower().startswith(("could", "would", "may")):
                picked = "Could you " + picked[0].lower() + picked[1:]
            if random.random() < 0.15:
                picked = picked.rstrip("?") + "?"
        else:
            if random.random() < 0.25 and not picked.endswith("？"):
                picked = picked.rstrip("。") + "？"

        return picked.strip()

    @classmethod
    def mutate_assistant_surface(cls, original_assistant: str) -> str:
        # 先保护特定名称
        a, placeholders = protect_names(original_assistant)
        a = normalize_text(a)
        lang = cls.detect_lang(a)

        starters = cls.ZH_ASSIST_STARTERS if lang == "zh" else cls.EN_ASSIST_STARTERS
        if random.random() < 0.35 and not a.startswith(tuple(starters)):
            a = random.choice(starters) + " " + a

        # 轻微断句：提升可读性
        if random.random() < 0.25:
            if lang == "zh":
                a = a.replace("，", "。")
            else:
                a = a.replace(" and ", ". ")

        # 少量结尾引导（不引入新事实）
        if random.random() < 0.20:
            if lang == "zh":
                a += " 如果你提供更具体的需求，我可以更有针对性地说明。"
            else:
                a += " If you share your specific need, I can tailor the answer."

        # 还原受保护的名称
        a = restore_names(a, placeholders)
        return a.strip()


# =============================================================================
# LLM rewrite hook（已实现版本）
# =============================================================================

class LLMRewriteHook:
    """
    LLM rewrite hook - 增强自然度和多样性
    """

    def __init__(self, enabled: bool = False, api_key: str = None, api_base: str = None, model_name: str = "gpt-5.1"):
        self.enabled = enabled
        self.api_key = api_key
        self.api_base = api_base or os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1")
        self.model_name = model_name
        self.client = None
        self._setup_client()

    def _setup_client(self):
        """设置API客户端"""
        if not self.enabled:
            return
        try:
            from openai import OpenAI
            self.client = OpenAI(
                base_url=self.api_base,
                api_key=self.api_key
            )
            logger.info(f"LLM rewrite hook 客户端初始化成功")
        except Exception as e:
            logger.warning(f"LLM rewrite hook 客户端初始化失败: {e}")
            self.enabled = False

    def call_llm(self, system: str, user: str, assistant: str) -> Tuple[str, str]:
        """调用LLM进行智能改写"""
        if not self.enabled or not self.client:
            return user, assistant

        # 保护特定名称
        user_protected, user_placeholders = protect_names(user)
        assistant_protected, assistant_placeholders = protect_names(assistant)
        system_protected, system_placeholders = protect_names(system)

        # 合并所有占位符映射
        all_placeholders = {**user_placeholders, **assistant_placeholders, **system_placeholders}

        # 构建受保护名称的提示信息
        protected_names_hint = "、".join(PROTECTED_NAMES)

        # 检测原始语言
        original_lang = DialogueVariationTemplates.detect_lang(user + assistant)
        lang_hint = "中文" if original_lang == "zh" else "英文"

        try:
            prompt = f"""
请将以下对话改写成更自然、更多样化的版本：

System: {system_protected}
User: {user_protected}
Assistant: {assistant_protected}

要求：
1. 保持核心语义和信息不变
2. 改变表达方式、语气、措辞
3. 保持对话的自然流畅
4. 可以从不同角度提问或回答
5. 重要：以下名称必须保持原样不变：{protected_names_hint}
6. 重要：必须使用{lang_hint}进行改写，保持与原文语言一致，不要切换语言

请以JSON格式返回：
{{
  "user": "改写后的用户问题",
  "assistant": "改写后的助手回答"
}}
"""

            response = self.client.chat.completions.create(
                model=self.model_name,
                messages=[
                    {"role": "system", "content": "You are a professional dialogue enhancement assistant."},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.7,
                max_tokens=2000
            )

            content = response.choices[0].message.content
            # 解析JSON
            import re
            json_match = re.search(r'\{.*\}', content, re.DOTALL)
            if json_match:
                parsed = json.loads(json_match.group(0))
                new_user = parsed.get("user", user_protected)
                new_assistant = parsed.get("assistant", assistant_protected)

                # 验证语言一致性，如果语言不一致则返回原文
                new_lang = DialogueVariationTemplates.detect_lang(new_user + new_assistant)
                if new_lang != original_lang:
                    logger.warning(f"LLM rewrite 语言不一致，原语言={original_lang}，新语言={new_lang}，返回原文")
                    return user, assistant

                # 还原受保护的名称
                new_user = restore_names(new_user, all_placeholders)
                new_assistant = restore_names(new_assistant, all_placeholders)
                return new_user, new_assistant

        except Exception as e:
            logger.warning(f"LLM rewrite 失败: {e}")

        return user, assistant

    def rewrite(self, system: str, user: str, assistant: str) -> Tuple[str, str]:
        if not self.enabled:
            return user, assistant
        return self.call_llm(system, user, assistant)


# =============================================================================
# Expander（整合：模板 + 自然度 + gate + embedding 去重 + N 倍扩增）
# =============================================================================

class DialogueExpander:
    def __init__(
        self,
        gate: DialogueGate,
        emb_model: str,
        dup_threshold: float,
        use_faiss: bool = False,
        device: Optional[str] = None,
        enable_llm_rewrite: bool = False,
        assistant_only_dedup: bool = False,
        assistant_dup_threshold: float = 0.985,
        api_key: str = None,
        api_base: str = None,
        model_name: str = "gpt-5.1",
    ):
        self.templates = DialogueVariationTemplates()
        self.gate = gate
        self.rewriter = LLMRewriteHook(
            enabled=enable_llm_rewrite,
            api_key=api_key,
            api_base=api_base,
            model_name=model_name
        )

        self.dup_threshold = dup_threshold
        self.exact_seen_global: set[str] = set()

        self.pair_deduper_global = EmbeddingDeduper(
            model_name=emb_model,
            device=device,
            use_faiss=use_faiss,
        )

        self.assistant_only_dedup = assistant_only_dedup
        self.assistant_dup_threshold = assistant_dup_threshold
        self.assistant_deduper_global = None
        if assistant_only_dedup:
            self.assistant_deduper_global = EmbeddingDeduper(
                model_name=emb_model,
                device=device,
                use_faiss=use_faiss,
            )

    def expand_dialogue(
        self,
        seed_sample: DialogueSample,
        num_variations: int = 10,
        variation_types: Optional[List[str]] = None,
        max_trials: int = 200,
    ) -> List[ExpandedDialogue]:
        """
        扩增对话样本（每条 seed 扩增 num_variations 条）
        """
        system_msg = seed_sample.get_system_message()
        user_msg = seed_sample.get_user_message()
        assistant_msg = seed_sample.get_assistant_message()

        expanded_dialogues: List[ExpandedDialogue] = []

        # local dedup
        exact_seen_local: set[str] = set()
        pair_deduper_local = EmbeddingDeduper(
            model_name=self.pair_deduper_global.model_name,
            device=None,
            use_faiss=False,
        )

        trials = 0
        while len(expanded_dialogues) < num_variations and trials < max_trials:
            trials += 1

            # 1) 用户问题变体（多语言/多意图）
            varied_user_msg = self.templates.sample_user_variation(user_msg)

            # 2) 助手表面自然度增强（不引入新事实）
            varied_assistant_msg = self.templates.mutate_assistant_surface(assistant_msg)

            # 3) 可选 LLM rewrite hook（更强自然度）
            varied_user_msg, varied_assistant_msg = self.rewriter.rewrite(
                system=system_msg,
                user=varied_user_msg,
                assistant=varied_assistant_msg,
            )

            # 4) normalize
            varied_user_msg = normalize_text(varied_user_msg)
            varied_assistant_msg = normalize_text(varied_assistant_msg)

            # 5) 组装 messages
            new_messages: List[Dict[str, str]] = []
            if system_msg:
                new_messages.append({"role": "system", "content": system_msg})
            new_messages.append({"role": "user", "content": varied_user_msg})
            new_messages.append({"role": "assistant", "content": varied_assistant_msg})

            # 6) gate
            ok, reason = self.gate.gate(new_messages)
            if not ok:
                continue

            # 7) exact 去重
            ek = signature_exact(varied_user_msg, varied_assistant_msg)
            if ek in exact_seen_local or ek in self.exact_seen_global:
                continue

            # 8) embedding 去重（pair）
            pair_text = f"USER: {varied_user_msg}\nASSISTANT: {varied_assistant_msg}"
            dup_l, _ = pair_deduper_local.is_duplicate(pair_text, threshold=self.dup_threshold, top_k=8)
            if dup_l:
                continue

            dup_g, _ = self.pair_deduper_global.is_duplicate(pair_text, threshold=self.dup_threshold, top_k=16)
            if dup_g:
                continue

            # 9) 可选：assistant-only 去重
            if self.assistant_only_dedup and self.assistant_deduper_global is not None:
                dup_a, _ = self.assistant_deduper_global.is_duplicate(
                    varied_assistant_msg, threshold=self.assistant_dup_threshold, top_k=16
                )
                if dup_a:
                    continue

            # accept
            exact_seen_local.add(ek)
            self.exact_seen_global.add(ek)
            pair_deduper_local.add(pair_text)
            self.pair_deduper_global.add(pair_text)
            if self.assistant_only_dedup and self.assistant_deduper_global is not None:
                self.assistant_deduper_global.add(varied_assistant_msg)

            method = "template+naturalize+gate+emb_dedup"
            if self.rewriter.enabled:
                method += "+llm_rewrite"

            expanded_dialogues.append(
                ExpandedDialogue(
                    messages=new_messages,
                    generation_method=method,
                    seed_sample=seed_sample,
                    quality_score=0.9,
                    meta={
                        "dup_threshold": self.dup_threshold,
                        "assistant_only_dedup": self.assistant_only_dedup,
                    },
                )
            )

        logger.info(
            f"seed expanded={len(expanded_dialogues)}/{num_variations}, trials={trials}, category={seed_sample.category}"
        )
        return expanded_dialogues


# =============================================================================
# JSONL IO
# =============================================================================

def load_dialogues_from_jsonl(file_path: str) -> List[DialogueSample]:
    dialogues: List[DialogueSample] = []
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            for ln, line in enumerate(f, 1):
                line = line.strip()
                if not line:
                    continue
                try:
                    data = json.loads(line)
                except Exception as e:
                    logger.warning(f"跳过第{ln}行（JSON解析失败）: {e}")
                    continue

                if "messages" in data and isinstance(data["messages"], list):
                    dialogue = DialogueSample(
                        messages=data["messages"],
                        category=data.get("category", "一般对话"),
                        domain=data.get("domain", "通用"),
                        tags=data.get("tags", []),
                    )
                    dialogues.append(dialogue)
                else:
                    logger.warning(f"跳过第{ln}行（缺少messages）")
    except Exception as e:
        logger.error(f"加载对话数据失败: {e}")

    return dialogues


def save_expanded_dialogues(
    expanded_dialogues: List[ExpandedDialogue],
    output_file: str,
    format: str = "jsonl",
):
    output_path = Path(output_file)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    if format == "jsonl":
        with open(output_path, "w", encoding="utf-8") as f:
            for dialogue in expanded_dialogues:
                f.write(json.dumps(dialogue.to_dict(), ensure_ascii=False) + "\n")
    else:
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump([d.to_dict() for d in expanded_dialogues], f, ensure_ascii=False, indent=2)

    logger.info(f"扩增对话已保存到: {output_path}")


# =============================================================================
# .env 文件读取
# =============================================================================

def load_dotenv(env_file: str = ".env", override: bool = True) -> None:
    """
    简单读取 .env 文件并设置环境变量
    支持格式: KEY=value 或 KEY="value"
    忽略以 # 开头的注释行和空行

    Args:
        env_file: .env 文件路径
        override: 是否覆盖已存在的环境变量（默认 True）
    """
    env_path = Path(env_file)
    if not env_path.exists():
        logger.debug(f".env file not found: {env_path}")
        return

    logger.info(f"Loading environment variables from: {env_path}")
    try:
        with open(env_path, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                # 跳过空行和注释
                if not line or line.startswith('#'):
                    continue

                # 查找第一个 = 号
                if '=' not in line:
                    continue

                key, value = line.split('=', 1)
                key = key.strip()
                value = value.strip()

                # 去除引号
                if value.startswith('"') and value.endswith('"'):
                    value = value[1:-1]
                elif value.startswith("'") and value.endswith("'"):
                    value = value[1:-1]

                # 设置环境变量
                if key:
                    # 检查是否应该覆盖
                    existing_value = os.getenv(key)
                    if existing_value is None or override:
                        os.environ[key] = value
                        logger.debug(f"Set env var: {key}=***")

        logger.info(f"Successfully loaded environment variables from {env_path}")
    except Exception as e:
        logger.warning(f"Failed to load .env file: {e}")


# =============================================================================
# CLI
# =============================================================================

def build_argparser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser()
    p.add_argument("--input", required=True, help="输入 seed.jsonl（每行一个 {messages:[...]}）")
    p.add_argument("--output", required=True, help="输出 expanded.jsonl")
    p.add_argument("--expand_factor", type=int, default=10, help="每条 seed 扩增倍数")
    p.add_argument("--max_trials", type=int, default=250, help="每条 seed 最大尝试次数（用于满足去重与 gate）")

    # gate
    p.add_argument("--min_user_len", type=int, default=2)
    p.add_argument("--min_assistant_len", type=int, default=2)
    p.add_argument("--max_user_len", type=int, default=4000)
    p.add_argument("--max_assistant_len", type=int, default=12000)
    p.add_argument("--require_system", action="store_true", help="强制必须包含 system 角色")

    # embedding dedup
    p.add_argument(
        "--emb_model",
        default="sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2",
        help="sentence-transformers 模型名",
    )
    p.add_argument("--dup_threshold", type=float, default=0.972, help="pair embedding 去重阈值（cosine）")
    p.add_argument("--use_faiss", action="store_true", help="使用 faiss 加速语义去重（大规模建议）")
    p.add_argument("--device", default=None, help="embedding 设备：cpu / cuda（如可用）")

    # llm rewrite hook
    p.add_argument("--enable_llm_rewrite", action="store_true", help="启用 LLM rewrite hook（增强自然度）")
    p.add_argument("--api_key", default=None, help="API密钥（OPENAI_API_KEY 或 DEEPSEEK_API_KEY）")
    p.add_argument("--api_base", default=os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1"), help="API基础地址")
    p.add_argument("--model_name", default="gpt-5.1", help="模型名称")

    # optional: assistant-only dedup
    p.add_argument("--assistant_only_dedup", action="store_true", help="额外对 assistant 做语义去重（抑制模板化）")
    p.add_argument("--assistant_dup_threshold", type=float, default=0.985, help="assistant-only 去重阈值（cosine）")

    # misc
    p.add_argument("--seed", type=int, default=13, help="随机种子")
    p.add_argument("--log_level", default="INFO")
    return p


def main():
    args = build_argparser().parse_args()
    logging.basicConfig(level=getattr(logging, args.log_level.upper(), logging.INFO))
    random.seed(args.seed)
    np.random.seed(args.seed)

    # 加载 .env 文件中的环境变量
    load_dotenv()

    # 获取API密钥（优先级：命令行参数 > .env文件 > 系统环境变量）
    api_key = args.api_key or os.getenv("OPENAI_API_KEY") or os.getenv("DEEPSEEK_API_KEY")

    if args.enable_llm_rewrite and not api_key:
        logger.warning(
            "LLM rewrite is enabled but no API key found. "
            "Please set OPENAI_API_KEY or DEEPSEEK_API_KEY in .env file or environment."
        )

    seeds = load_dialogues_from_jsonl(args.input)
    logger.info(f"Loaded {len(seeds)} seed dialogues from {args.input}")

    gate = DialogueGate(
        min_user_len=args.min_user_len,
        min_assistant_len=args.min_assistant_len,
        max_user_len=args.max_user_len,
        max_assistant_len=args.max_assistant_len,
        require_system=args.require_system,
    )

    expander = DialogueExpander(
        gate=gate,
        emb_model=args.emb_model,
        dup_threshold=args.dup_threshold,
        use_faiss=args.use_faiss,
        device=args.device,
        enable_llm_rewrite=args.enable_llm_rewrite,
        assistant_only_dedup=args.assistant_only_dedup,
        assistant_dup_threshold=args.assistant_dup_threshold,
        api_key=api_key,
        api_base=args.api_base,
        model_name=args.model_name,
    )

    all_expanded: List[ExpandedDialogue] = []
    start_time = time.time()

    for i, seed in enumerate(seeds):
        expanded = expander.expand_dialogue(
            seed_sample=seed,
            num_variations=args.expand_factor,
            variation_types=None,
            max_trials=args.max_trials,
        )
        all_expanded.extend(expanded)
        logger.info(f"Seed[{i}] expanded {len(expanded)}/{args.expand_factor}")

    elapsed = time.time() - start_time
    save_expanded_dialogues(all_expanded, args.output, format="jsonl")
    logger.info(f"Done. Total expanded dialogues: {len(all_expanded)} (耗时: {elapsed:.2f}秒)")


if __name__ == "__main__":
    main()
