#!/usr/bin/env python3
"""
专家问题QA扩增脚本
专门处理专家问题_扩增CoT.xlsx文件，按照扩展种子问题分类进行QA扩增
支持基于domain_task_expert.xlsx的分类映射和权重配置
支持RAG（检索增强生成）功能
支持将扩展分类信息添加到提示词中，让模型根据分类进行精准扩增
"""
import asyncio
import json
import sys
import os
import logging

# Add parent directory to Python path to allow imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.main_batch import generate_rag_enhanced_prompt
import time
import pandas as pd
import yaml
import requests
from pathlib import Path
from typing import Dict, List, Any, Optional
from datetime import datetime
from core.qa_generator_v2 import DeepSeekGenerator, SeedQuestion, GenerationMethod, QualityConfig
from optimization.prompt_enhancer import PromptEnhancer

# 设置日志记录器
logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# 中英文对照字典（用于RAG检索优化）
CN_EN_DICT = {
    "光合作用": "photosynthesis",
    "叶绿体": "chloroplast",
    "叶绿素": "chlorophyll",
    "类胡萝卜素": "carotenoid",
    "卡尔文循环": "Calvin cycle",
    "C3植物": "C3 plants",
    "C4植物": "C4 plants",
    "CAM植物": "CAM plants",
    "气孔": "stomata",
    "叶肉细胞": "mesophyll cells",
    "维管束鞘细胞": "bundle sheath cells",
    "RuBisCO": "ribulose-1,5-bisphosphate carboxylase/oxygenase",
    "RuBP": "ribulose-1,5-bisphosphate",
    "PGA": "phosphoglycerate",
    "ATP": "adenosine triphosphate",
    "NADPH": "nicotinamide adenine dinucleotide phosphate",
    "光系统": "photosystem",
    "光系统II": "photosystem II",
    "光系统I": "photosystem I",
    "电子传递链": "electron transport chain",
    "质子梯度": "proton gradient",
    "ATP合酶": "ATP synthase",
    "水裂解": "water splitting",
    "氧气释放": "oxygen evolution",
    "二氧化碳固定": "carbon dioxide fixation",
    "三碳化合物": "three-carbon compounds",
    "四碳化合物": "four-carbon compounds",
    "PEP羧化酶": "phosphoenolpyruvate carboxylase",
    "苹果酸": "malate",
    "天冬氨酸": "aspartate",
    "景天酸代谢": "crassulacean acid metabolism",
    "气孔导度": "stomatal conductance",
    "蒸腾作用": "transpiration",
    "水分利用效率": "water use efficiency",
    "光抑制": "photoinhibition",
    "光保护": "photoprotection",
    "热耗散": "thermal dissipation",
    "叶黄素循环": "xanthophyll cycle",
    "玉米黄质": "zeaxanthin",
    "花药黄质": "antheraxanthin",
    "紫黄质": "violaxanthin",
    "光合磷酸化": "photophosphorylation",
    "氧化磷酸化": "oxidative phosphorylation",
    "底物水平磷酸化": "substrate-level phosphorylation",
    "呼吸作用": "respiration",
    "有氧呼吸": "aerobic respiration",
    "无氧呼吸": "anaerobic respiration",
    "糖酵解": "glycolysis",
    "柠檬酸循环": "citric acid cycle",
    "三羧酸循环": "tricarboxylic acid cycle",
    "电子传递": "electron transfer",
    "细胞色素": "cytochrome",
    "质体醌": "plastoquinone",
    "质体蓝素": "plastocyanin",
    "铁氧还蛋白": "ferredoxin",
    "FNR": "ferredoxin-NADP+ reductase",
    "光合电子传递": "photosynthetic electron transport",
    "环式电子传递": "cyclic electron transport",
    "非环式电子传递": "non-cyclic electron transport",
    "量子效率": "quantum efficiency",
    "光合速率": "photosynthetic rate",
    "净光合速率": "net photosynthetic rate",
    "表观光合速率": "apparent photosynthetic rate",
    "实际光合速率": "actual photosynthetic rate",
    "暗呼吸": "dark respiration",
    "光补偿点": "light compensation point",
    "光饱和点": "light saturation point",
    "表观量子效率": "apparent quantum yield",
    "羧化效率": "carboxylation efficiency",
    "Rubisco活化酶": "Rubisco activase",
    "Rubisco结合蛋白": "Rubisco binding protein",
    "分子伴侣": "molecular chaperone",
    "蛋白酶体": "proteasome",
    "泛素": "ubiquitin",
    "26S蛋白酶体": "26S proteasome",
    "叶绿素a": "chlorophyll a",
    "叶绿素b": "chlorophyll b",
    "叶绿素a/b结合蛋白": "chlorophyll a/b binding protein",
    "LHCI": "light-harvesting complex I",
    "LHCII": "light-harvesting complex II",
    "捕光复合体": "light-harvesting complex",
    "光保护蛋白": "photoprotective protein",
    "PsbS蛋白": "PsbS protein",
    "抗氧化剂": "antioxidant",
    "抗坏血酸": "ascorbic acid",
    "谷胱甘肽": "glutathione",
    "超氧化物歧化酶": "superoxide dismutase",
    "过氧化氢酶": "catalase",
    "过氧化物酶": "peroxidase",
    "活性氧": "reactive oxygen species",
    "单线态氧": "singlet oxygen",
    "超氧阴离子": "superoxide anion",
    "过氧化氢": "hydrogen peroxide",
    "羟基自由基": "hydroxyl radical",
    "膜脂过氧化": "membrane lipid peroxidation",
    "MDA": "malondialdehyde",
    "电导率": "electrolyte leakage",
    "相对含水量": "relative water content",
    "自由水": "free water",
    "束缚水": "bound water",
    "水势": "water potential",
    "渗透势": "osmotic potential",
    "压力势": "pressure potential",
    "基质势": "matric potential",
    "衬质势": "matrix potential",
    "渗透调节": "osmotic adjustment",
    "渗透保护剂": "osmoprotectant",
    "脯氨酸": "proline",
    "甜菜碱": "betaine",
    "可溶性糖": "soluble sugar",
    "可溶性蛋白": "soluble protein",
    "LEA蛋白": "late embryogenesis abundant protein",
    "热激蛋白": "heat shock protein",
    "HSP": "heat shock protein",
    "分子伴侣": "molecular chaperone",
    "钙调蛋白": "calmodulin",
    "钙调磷酸酶": "calcineurin",
    "钙依赖性蛋白激酶": "calcium-dependent protein kinase",
    "CDPK": "calcium-dependent protein kinase",
    "MAP激酶": "MAP kinase",
    "MAPK": "mitogen-activated protein kinase",
    "MAPKK": "MAP kinase kinase",
    "MAPKKK": "MAP kinase kinase kinase",
    "信号转导": "signal transduction",
    "第二信使": "second messenger",
    "cAMP": "cyclic adenosine monophosphate",
    "cGMP": "cyclic guanosine monophosphate",
    "IP3": "inositol 1,4,5-trisphosphate",
    "DAG": "diacylglycerol",
    "磷脂酶C": "phospholipase C",
    "磷脂酶D": "phospholipase D",
    "磷脂酶A2": "phospholipase A2",
    "花生四烯酸": "arachidonic acid",
    "茉莉酸": "jasmonic acid",
    "水杨酸": "salicylic acid",
    "脱落酸": "abscisic acid",
    "ABA": "abscisic acid",
    "乙烯": "ethylene",
    "赤霉素": "gibberellin",
    "GA": "gibberellin",
    "细胞分裂素": "cytokinin",
    "CTK": "cytokinin",
    "生长素": "auxin",
    "IAA": "indole-3-acetic acid",
    "油菜素内酯": "brassinosteroid",
    "BR": "brassinosteroid",
    "独脚金内酯": "strigolactone",
    "SL": "strigolactone",
    "植物激素": "plant hormone",
    "植物生长调节剂": "plant growth regulator",
    "向光性": "phototropism",
    "向地性": "geotropism",
    "向化性": "chemotropism",
    "向水性": "hydrotropism",
    "向触性": "thigmotropism",
    "昼夜节律": "circadian rhythm",
    "生物钟": "biological clock",
    "光周期": "photoperiod",
    "长日照植物": "long-day plant",
    "短日照植物": "short-day plant",
    "日中性植物": "day-neutral plant",
    "临界日照长度": "critical photoperiod",
    "光周期诱导": "photoperiodic induction",
    "春化作用": "vernalization",
    "低温春化": "low temperature vernalization",
    "种子休眠": "seed dormancy",
    "后熟": "after-ripening",
    "层积处理": "stratification",
    "赤霉素处理": "gibberellin treatment",
    "打破休眠": "breaking dormancy",
    "萌发": "germination",
    "胚根": "radicle",
    "胚芽": "plumule",
    "胚轴": "hypocotyl",
    "胚乳": "endosperm",
    "子叶": "cotyledon",
    "种皮": "seed coat",
    "种脐": "hilum",
    "种孔": "micropyle",
    "胚珠": "ovule",
    "子房": "ovary",
    "花柱": "style",
    "柱头": "stigma",
    "花药": "anther",
    "花丝": "filament",
    "雄蕊": "stamen",
    "雌蕊": "pistil",
    "花瓣": "petal",
    "花萼": "sepal",
    "花托": "receptacle",
    "花梗": "pedicel",
    "完全花": "complete flower",
    "不完全花": "incomplete flower",
    "两性花": "hermaphrodite flower",
    "单性花": "unisexual flower",
    "雌雄同株": "monoecious",
    "雌雄异株": "dioecious",
    "自花授粉": "self-pollination",
    "异花授粉": "cross-pollination",
    "风媒花": "anemophilous flower",
    "虫媒花": "entomophilous flower",
    "鸟媒花": "ornithophilous flower",
    "传粉": "pollination",
    "受精": "fertilization",
    "双受精": "double fertilization",
    "胚囊": "embryo sac",
    "助细胞": "synergid",
    "反足细胞": "antipodal cell",
    "极核": "polar nucleus",
    "卵细胞": "egg cell",
    "花粉管": "pollen tube",
    "精子": "sperm cell",
    "精细胞": "generative cell",
    "营养细胞": "vegetative cell",
    "花粉粒": "pollen grain",
    "小孢子": "microspore",
    "大孢子": "megaspore",
    "孢子": "spore",
    "配子": "gamete",
    "配子体": "gametophyte",
    "孢子体": "sporophyte",
    "世代交替": "alternation of generations",
    "无性生殖": "asexual reproduction",
    "有性生殖": "sexual reproduction",
    "营养繁殖": "vegetative propagation",
    "扦插": "cutting",
    "嫁接": "grafting",
    "压条": "layering",
    "分株": "division",
    "组织培养": "tissue culture",
    "细胞培养": "cell culture",
    "器官培养": "organ culture",
    "胚胎培养": "embryo culture",
    "花药培养": "anther culture",
    "花粉培养": "pollen culture",
    "原生质体培养": "protoplast culture",
    "体细胞胚发生": "somatic embryogenesis",
    "体细胞杂交": "somatic hybridization",
    "原生质体融合": "protoplast fusion",
    "细胞融合": "cell fusion",
    "融合剂": "fusogen",
    "PEG": "polyethylene glycol",
    "仙台病毒": "Sendai virus",
    "灭活病毒": "inactivated virus",
    "杂交瘤": "hybridoma",
    "单克隆抗体": "monoclonal antibody",
    "多克隆抗体": "polyclonal antibody",
    "抗原": "antigen",
    "抗体": "antibody",
    "免疫反应": "immune response",
    "细胞免疫": "cellular immunity",
    "体液免疫": "humoral immunity",
    "过敏反应": "allergic reaction",
    "超敏反应": "hypersensitivity",
    "自身免疫": "autoimmunity",
    "免疫耐受": "immune tolerance",
    "免疫记忆": "immune memory",
    "免疫细胞": "immune cell",
    "淋巴细胞": "lymphocyte",
    "T细胞": "T cell",
    "B细胞": "B cell",
    "巨噬细胞": "macrophage",
    "树突状细胞": "dendritic cell",
    "自然杀伤细胞": "natural killer cell",
    "细胞因子": "cytokine",
    "干扰素": "interferon",
    "白细胞介素": "interleukin",
    "肿瘤坏死因子": "tumor necrosis factor",
    "生长因子": "growth factor",
    "转化生长因子": "transforming growth factor",
    "TGF": "transforming growth factor",
    "表皮生长因子": "epidermal growth factor",
    "EGF": "epidermal growth factor",
    "成纤维细胞生长因子": "fibroblast growth factor",
    "FGF": "fibroblast growth factor",
    "胰岛素样生长因子": "insulin-like growth factor",
    "IGF": "insulin-like growth factor",
    "神经生长因子": "nerve growth factor",
    "NGF": "nerve growth factor",
    "血小板衍生生长因子": "platelet-derived growth factor",
    "PDGF": "platelet-derived growth factor",
    "血管内皮生长因子": "vascular endothelial growth factor",
    "VEGF": "vascular endothelial growth factor",
    "骨形态发生蛋白": "bone morphogenetic protein",
    "BMP": "bone morphogenetic protein",
    " Wnt信号": "Wnt signaling",
    "Hedgehog信号": "Hedgehog signaling",
    "Notch信号": "Notch signaling",
    "Hippo信号": "Hippo signaling",
    "mTOR信号": "mTOR signaling",
    "AMPK信号": "AMPK signaling",
    "PI3K/Akt信号": "PI3K/Akt signaling",
    "MAPK级联": "MAPK cascade",
    "JAK/STAT信号": "JAK/STAT signaling",
    "TGF-β信号": "TGF-β signaling",
    "BMP信号": "BMP signaling",
    "Wnt信号通路": "Wnt signaling pathway",
    "Hedgehog信号通路": "Hedgehog signaling pathway",
    "Notch信号通路": "Notch signaling pathway",
    "Hippo信号通路": "Hippo signaling pathway",
    "mTOR信号通路": "mTOR signaling pathway",
    "AMPK信号通路": "AMPK signaling pathway",
    "PI3K/Akt信号通路": "PI3K/Akt signaling pathway",
    "MAPK级联通路": "MAPK cascade pathway",
    "JAK/STAT信号通路": "JAK/STAT signaling pathway",
    "TGF-β信号通路": "TGF-β signaling pathway",
    "BMP信号通路": "BMP signaling pathway"
}

def translate_query_to_english(query: str) -> str:
    """
    将中文查询翻译为英文，提高RAG检索效果

    Args:
        query: 中文查询文本

    Returns:
        str: 英文查询文本
    """
    # 如果查询已经是英文，直接返回
    if all(ord(char) < 128 for char in query if char.strip()):
        return query

    # 使用开源翻译库 mtranslate
    try:
        from mtranslate import translate
        print(f"   🌐 翻译查询: {query[:50]}...")
        result = translate(query, 'en', 'zh')
        print(f"   ✅ 翻译完成: {result[:50]}...")
        return result
    except Exception as e:
        print(f"   ⚠️ mtranslate翻译失败，使用字典翻译: {e}")
        # 降级到字典翻译
        translated_query = query
        # 按长度排序，优先替换长词组
        for cn_term, en_term in sorted(CN_EN_DICT.items(), key=lambda x: len(x[0]), reverse=True):
            if cn_term in translated_query:
                translated_query = translated_query.replace(cn_term, en_term)
        return translated_query


def smart_retrieve(rag_client: 'RAGClient', query: str, top_k: int = 5, data_source: Optional[List[str]] = None) -> List[Dict[str, Any]]:
    """
    智能RAG检索：根据查询内容自动选择最佳检索语言和策略

    Args:
        rag_client: RAG客户端
        query: 查询文本
        top_k: 检索文档数量
        data_source: 数据源列表

    Returns:
        检索结果列表
    """
    # 自动检测查询语言
    is_chinese = any(ord(char) > 127 for char in query if char.strip())

    if is_chinese:
        # 中文查询：使用翻译优化检索
        print(f"   🔤 检测到中文查询，启动翻译优化...")
        english_query = translate_query_to_english(query)

        # 使用英文进行检索
        print(f"   🔍 使用英文检索: {english_query[:50]}...")
        documents = rag_client.retrieve(
            query=english_query,
            top_k=top_k,
            data_source=data_source,
            language="en"  # 强制使用英文检索
        )

        # 如果英文检索结果少，回退到中文检索
        if len(documents) < 2:
            print(f"   ⚠️ 英文检索结果较少，回退到中文检索...")
            documents = rag_client.retrieve(
                query=query,
                top_k=top_k,
                data_source=data_source,
                language="zh"
            )
    else:
        # 英文查询：直接检索
        print(f"   🔍 使用英文检索: {query[:50]}...")
        documents = rag_client.retrieve(
            query=query,
            top_k=top_k,
            data_source=data_source,
            language="en"
        )

    return documents


from src.core.batch_processor import BatchQAGenerator

# RAG配置（已优化）
RAG_CONFIG = {
    'url': 'http://localhost:9487/retrieve',
    'headers': {'Content-Type': 'application/json'},
    'timeout': 180,  # 增加到180秒（3分钟），处理复杂查询
    'max_retries': 2,  # 从3减少到2
}

# RAG缓存机制
PROJECT_ROOT = Path(__file__).parent.parent.parent
RAG_CACHE_DIR = PROJECT_ROOT / "data" / "processed" / "rag_cache"
RAG_CACHE_FILE = RAG_CACHE_DIR / "rag_cache.json"

def get_rag_cache_key(query: str, top_k: int, data_source: list) -> str:
    """生成RAG缓存键"""
    import hashlib
    content = f"{query}:{top_k}:{','.join(sorted(data_source))}"
    return hashlib.md5(content.encode('utf-8')).hexdigest()

def get_rag_cached_result(cache_key: str) -> Optional[List[Dict[str, Any]]]:
    """获取RAG缓存结果"""
    try:
        if not RAG_CACHE_FILE.exists():
            return None
        with open(RAG_CACHE_FILE, 'r', encoding='utf-8') as f:
            cache = json.load(f)
            return cache.get(cache_key)
    except Exception as e:
        print(f"   ⚠️ 读取RAG缓存失败: {e}")
        return None

def save_rag_cache_result(cache_key: str, result: List[Dict[str, Any]]):
    """保存RAG缓存结果"""
    try:
        RAG_CACHE_DIR.mkdir(exist_ok=True)
        cache = {}
        if RAG_CACHE_FILE.exists():
            with open(RAG_CACHE_FILE, 'r', encoding='utf-8') as f:
                cache = json.load(f)
        cache[cache_key] = result
        with open(RAG_CACHE_FILE, 'w', encoding='utf-8') as f:
            json.dump(cache, f, ensure_ascii=False, indent=2)
        print(f"   💾 RAG缓存已保存")
    except Exception as e:
        print(f"   ⚠️ 保存RAG缓存失败: {e}")

# 智能筛选功能
def should_use_rag(question: str, answer: str) -> bool:
    """
    判断是否需要使用RAG增强
    基于多维度分析的智能筛选

    Args:
        question: 问题文本
        answer: 答案文本

    Returns:
        bool: True表示需要使用RAG，False表示不需要
    """
    # 计算基础指标
    combined_text = question + answer
    question_len = len(question)
    answer_len = len(answer)
    combined_len = len(combined_text)

    # 1. 专业关键词检测（增强版）
    # 科学和技术类关键词
    science_keywords = [
        '研究', '实验', '分析', '理论', '模型', '假设',
        '论文', '文献', '期刊', '数据', '统计', '结果',
        '发现', '观察', '测量', '验证', '结论'
    ]

    # 技术和方法类关键词
    tech_keywords = [
        '技术', '方法', '手段', '工具', '设备', '仪器',
        '工艺', '流程', '步骤', '操作', '实施', '应用',
        '技术路线', '实施方案', '操作规程'
    ]

    # 机制和原理类关键词
    mechanism_keywords = [
        '机制', '原理', '机理', '原因', '为什么', '如何',
        '怎么', '怎样', '如何实现', '如何进行', '如何提高',
        '影响因子', '作用机制', '调控机制'
    ]

    # 比较和评估类关键词
    compare_keywords = [
        '比较', '对比', '区别', '差异', '不同', '优势', '劣势',
        '优缺点', '利弊', '效果', '效能', '性能', '效率',
        '评估', '评价', '判断', '选择', '推荐'
    ]

    # 发展趋势类关键词
    trend_keywords = [
        '最新', '前沿', '进展', '发展', '趋势', '未来',
        '预测', '展望', '方向', '创新', '突破', '革新',
        '新进展', '新方法', '新技术', '新成果'
    ]

    # 专业领域特定词汇（农业相关）
    agri_keywords = [
        '育种', '品种', '产量', '品质', '抗性', '适应性',
        '种植', '栽培', '管理', '施肥', '灌溉', '病虫害',
        '遗传', '基因组', '表型', '育种值', '选择指数',
        '转基因', '基因编辑', '分子标记', '辅助选择'
    ]

    # 统计和计算类关键词
    stats_keywords = [
        '显著性', 'p值', '方差', '标准差', '置信区间',
        '相关性', '回归', '预测模型', '机器学习',
        '深度学习', '人工智能', '算法', '模型'
    ]

    # 合并所有关键词
    all_keywords = (
        science_keywords + tech_keywords + mechanism_keywords +
        compare_keywords + trend_keywords + agri_keywords +
        stats_keywords
    )

    # 计算关键词匹配得分
    keyword_score = sum(1 for kw in all_keywords if kw in combined_text)

    # 2. 问题类型分析
    # 开放性问题（需要详细回答）
    open_questions = [
        '为什么', '如何', '怎么', '怎样', '什么', '哪些',
        '哪个', '如何实现', '如何进行', '如何提高',
        '为什么选择', '为什么采用', '怎么解决',
        '怎样优化', '如何改善', '如何处理'
    ]

    # 封闭性问题（简单回答是/否）
    closed_questions = [
        '是否', '能不能', '可不可以', '有没有', '是不是',
        '会不会', '能不能', '需不需要', '要不要'
    ]

    # 判断问题类型
    is_open_question = any(q in question for q in open_questions)
    is_closed_question = any(q in question for q in closed_questions)

    # 3. 答案长度分析
    # 根据长度判断问题复杂度
    is_long_answer = answer_len > 800
    is_medium_answer = 200 < answer_len <= 800
    is_short_answer = answer_len <= 200

    # 4. 复杂概念检测
    # 包含复杂概念或专业术语的问题更可能需要RAG
    complex_concepts = [
        '分子', '基因', '蛋白', '细胞', '代谢', '信号',
        '转录', '翻译', '表达', '调控', '网络', '通路',
        '系统', '模型', '框架', '体系', '机制'
    ]

    has_complex_concepts = any(c in combined_text for c in complex_concepts)

    # 5. 数量和统计信息检测
    has_numbers = any(char.isdigit() for char in combined_text)
    has_percent = '%' in combined_text or '百分' in combined_text
    has_units = any(unit in combined_text for unit in ['kg', 'g', '吨', '亩', '公顷', '米', 'cm', 'mm'])

    # 6. 计算综合得分
    score = 0

    # 关键词匹配 (最高30分)
    score += min(keyword_score * 3, 30)

    # 问题类型 (最高20分)
    if is_open_question:
        score += 15
    if is_closed_question:
        score -= 5  # 封闭性问题通常不需要RAG

    # 答案长度 (最高20分)
    if is_long_answer:
        score += 20
    elif is_medium_answer:
        score += 10

    # 复杂概念 (最高15分)
    if has_complex_concepts:
        score += 15

    # 数据和单位 (最高10分)
    if has_numbers:
        score += 5
    if has_percent:
        score += 3
    if has_units:
        score += 2

    # 问题长度 (最高5分)
    if question_len > 50:
        score += 5
    elif question_len > 30:
        score += 3

    # 7. 特殊规则
    # 极短问题直接跳过
    if question_len < 5:
        return False

    # 极长答案直接使用RAG
    if answer_len > 2000:
        return True

    # 非常短的回答通常不需要RAG（但专业问题和开放性问题除外）
    # 如果有多个关键词或开放性问题，即使答案短也使用RAG
    if answer_len < 50:
        # 专业问题开放性问题即使答案短也使用RAG
        if is_open_question or keyword_score >= 3 or has_complex_concepts:
            pass  # 不跳过，继续判断
        else:
            return False

    # 8. 决策阈值
    # 总分阈值：超过25分使用RAG（降低阈值以提高召回率）
    # 调整阈值以平衡准确性和覆盖率

    return score >= 25

class RAGClient:
    """RAG客户端，用于检索增强生成"""

    def __init__(self, config: Dict[str, Any] = None):
        self.config = config or RAG_CONFIG
        self.session = requests.Session()

        # 配置重试策略
        from requests.adapters import HTTPAdapter
        from urllib3.util.retry import Retry

        retry_strategy = Retry(
            total=self.config.get('max_retries', 3),
            backoff_factor=1,
            status_forcelist=[429, 500, 502, 503, 504],
        )
        adapter = HTTPAdapter(max_retries=retry_strategy)
        self.session.mount("http://", adapter)
        self.session.mount("https://", adapter)

    def retrieve(self, query: str, top_k: int = 5, data_source: Optional[List[str]] = None, language: str = "zh") -> List[Dict[str, Any]]:
        """
        从RAG服务检索相关文档（已集成缓存和优化）

        Args:
            query: 查询字符串
            top_k: 返回文档数量
            data_source: 数据源列表，如 ["pubmed"]
            language: 语言设置

        Returns:
            检索结果列表
        """
        if not data_source:
            data_source = ["pubmed"]

        # 生成缓存键并检查缓存
        cache_key = get_rag_cache_key(query, top_k, data_source)
        cached_result = get_rag_cached_result(cache_key)
        if cached_result is not None:
            print(f"   💾 RAG缓存命中: {query[:50]}...")
            return cached_result

        # 缓存未命中，执行检索
        payload = {
            "query": query,
            "top_k": top_k,
            "data_source": data_source,
            "language": language
        }

        try:
            print(f"   🔍 RAG检索中: {query[:50]}...")
            response = self.session.post(
                self.config['url'],
                headers=self.config['headers'],
                json=payload,
                timeout=self.config['timeout']
            )
            response.raise_for_status()
            result = response.json()

            # 标准化返回格式
            if isinstance(result, dict) and 'data' in result:
                final_result = result['data']
            elif isinstance(result, dict) and 'results' in result:
                final_result = result['results']
            elif isinstance(result, list):
                final_result = result
            else:
                final_result = []

            # 保存到缓存
            save_rag_cache_result(cache_key, final_result)
            print(f"   ✅ RAG检索完成: 找到 {len(final_result)} 篇文档")

            return final_result

        except requests.exceptions.Timeout:
            print(f"   ⏰ RAG检索超时 ({self.config['timeout']}秒)")
            return []
        except requests.exceptions.RequestException as e:
            print(f"❌ RAG检索失败: {e}")
            return []
        except Exception as e:
            print(f"❌ RAG处理错误: {e}")
            return []

    def close(self):
        """关闭客户端"""
        self.session.close()

def format_rag_context(documents: List[Dict[str, Any]]) -> str:
    """
    格式化RAG检索结果为上下文文本

    Args:
        documents: 检索文档列表

    Returns:
        格式化的上下文字符串
    """
    if not documents:
        return ""

    contexts = []
    for i, doc in enumerate(documents, 1):
        # 提取文档内容
        title = doc.get('title', f'文档{i}')
        content = doc.get('content', doc.get('text', ''))
        source = doc.get('source', doc.get('data_source', ''))

        context_entry = f"[{i}] {title}\n{source}\n{content}\n"
        contexts.append(context_entry)

    return "\n".join(contexts)

def mark_seeds_for_rag(seed_questions: List[SeedQuestion], rag_client: Optional[RAGClient], enable_ratio: float = 1.0) -> List[SeedQuestion]:
    """
    标记哪些种子需要RAG增强（不立即执行RAG检索）

    Args:
        seed_questions: 原始种子问题列表
        rag_client: RAG客户端
        enable_ratio: 启用RAG的种子比例（0.0-1.0，默认1.0启用全部）

    Returns:
        标记后的种子问题列表
    """
    if not rag_client:
        return seed_questions

    marked_seeds = []
    total_seeds = len(seed_questions)

    # 计算要启用RAG的种子数量
    import random
    random.seed(42)  # 确保可重复性
    rag_seed_count = int(total_seeds * enable_ratio)

    if rag_seed_count < total_seeds:
        print(f"\n⚡ 性能优化：仅对 {rag_seed_count}/{total_seeds} ({enable_ratio*100:.0f}%) 个种子启用RAG增强")
    else:
        print(f"\n🔍 标记RAG增强种子 ({total_seeds} 个种子)")

    # 随机选择要增强的种子索引
    rag_seed_indices = set(random.sample(range(total_seeds), rag_seed_count)) if rag_seed_count > 0 else set()

    # 统计信息
    marked_rag_count = 0
    smart_filter_count = 0

    for i, seed in enumerate(seed_questions, 1):
        # 检查是否应该为此种子启用RAG
        need_rag = False
        if i - 1 in rag_seed_indices:
            # 使用智能筛选判断是否真的需要RAG
            if should_use_rag(seed.question, seed.answer):
                need_rag = True
                smart_filter_count += 1

        # 为种子添加RAG标记
        tags = seed.tags.copy()
        if need_rag:
            tags.append('needs_rag')
            marked_rag_count += 1

        # 创建新的种子问题（包含RAG标记）
        marked_seed = SeedQuestion(
            question=seed.question,
            answer=seed.answer,
            category=seed.category,
            species=seed.species,
            difficulty=seed.difficulty,
            tags=tags
        )

        marked_seeds.append(marked_seed)

        # 进度显示
        if i % 10 == 0 or i == total_seeds:
            print(f"  ✓ 已标记 {i}/{total_seeds} ({i/total_seeds*100:.1f}%) - 标记RAG: {marked_rag_count}")

    print(f"\n✅ RAG标记完成！")
    print(f"   📊 统计信息:")
    print(f"      总种子数: {total_seeds}")
    print(f"      标记RAG: {marked_rag_count} 个")
    print(f"      智能筛选: {smart_filter_count} 个")
    print(f"      RAG标记率: {marked_rag_count/total_seeds*100:.1f}%\n")

    return marked_seeds


def parse_dual_version_response(response_text):
    """
    解析包含两个版本的回答
    返回: (cited_version, no_citation_version)
    """
    import re

    cited_version = ""
    no_citation_version = ""

    # 尝试匹配两个版本的格式
    cited_match = re.search(r'【带引用版本】\s*(.*?)\s*【无引用版本】', response_text, re.DOTALL)
    no_citation_match = re.search(r'【无引用版本】\s*(.*?)$', response_text, re.DOTALL)

    if cited_match and no_citation_match:
        cited_version = cited_match.group(1).strip()
        no_citation_version = no_citation_match.group(1).strip()
    else:
        # 如果格式不匹配，尝试其他可能的格式
        lines = response_text.split('\n')
        cited_section = False
        no_citation_section = False

        for line in lines:
            if '带引用版本' in line:
                cited_section = True
                no_citation_section = False
                continue
            elif '无引用版本' in line:
                cited_section = False
                no_citation_section = True
                continue
            elif cited_section:
                cited_version += line + '\n'
            elif no_citation_section:
                no_citation_version += line + '\n'

        cited_version = cited_version.strip()
        no_citation_version = no_citation_version.strip()

    # 如果仍然无法解析，将整个响应作为两个版本
    if not cited_version and not no_citation_version:
        cited_version = response_text
        no_citation_version = response_text
    elif not cited_version and no_citation_version:
        cited_version = no_citation_version
    elif cited_version and not no_citation_version:
        no_citation_version = re.sub(r'\[bdd-rag-citation:\d+\]', '', cited_version).strip()

    return cited_version, no_citation_version


def get_rag_enhanced_prompt(seed: SeedQuestion, rag_client: RAGClient, top_k: int = 5, data_source: Optional[List[str]] = None) -> str:
    """
    为单个种子动态获取RAG增强（已启用智能翻译优化）

    Args:
        seed: 种子问题
        rag_client: RAG客户端
        top_k: 检索文档数量
        data_source: 数据源列表

    Returns:
        增强后的提示词
    """
    # 构建查询内容
    query = seed.question

    # 使用智能检索（自动翻译优化）
    print(f"   🎯 开始智能检索: {query[:50]}...")
    documents = smart_retrieve(rag_client, query, top_k, data_source)

    if documents:
        # 格式化RAG上下文
        rag_context = format_rag_context(documents)

        # 生成增强的提示词
        enhanced_prompt = generate_rag_enhanced_prompt(
            seed.question,
            seed.answer,
            rag_context
        )
        return enhanced_prompt
    else:
        # 如果没有检索到相关文档，使用原始问题
        return seed.question


def enhance_seeds_with_rag(seed_questions: List[SeedQuestion], rag_client: RAGClient, top_k: int = 5, data_source: Optional[List[str]] = None, enable_ratio: float = 1.0, parallel: bool = True) -> List[SeedQuestion]:
    """
    使用RAG增强种子问题（已集成智能筛选和优化，支持并行处理）

    Args:
        seed_questions: 原始种子问题列表
        rag_client: RAG客户端
        top_k: 检索文档数量
        data_source: 数据源列表
        enable_ratio: 启用RAG的种子比例（0.0-1.0，默认1.0启用全部）
        parallel: 是否并行处理（默认True）

    Returns:
        增强后的种子问题列表
    """
    if not rag_client:
        return seed_questions

    if parallel:
        # 并行模式：先标记，然后动态增强
        print(f"\n🚀 并行模式：RAG增强和QA生成将同时进行")
        return mark_seeds_for_rag(seed_questions, rag_client, enable_ratio)
    else:
        # 串行模式：预先增强所有种子
        return _enhance_seeds_sync(seed_questions, rag_client, top_k, data_source, enable_ratio)


def _enhance_seeds_sync(seed_questions: List[SeedQuestion], rag_client: RAGClient, top_k: int = 5, data_source: Optional[List[str]] = None, enable_ratio: float = 1.0) -> List[SeedQuestion]:
    """
    预先增强所有种子（串行模式）
    """
    enhanced_seeds = []
    total_seeds = len(seed_questions)

    # 计算要启用RAG的种子数量
    import random
    random.seed(42)  # 确保可重复性
    rag_seed_count = int(total_seeds * enable_ratio)

    if rag_seed_count < total_seeds:
        print(f"\n⚡ 性能优化：仅对 {rag_seed_count}/{total_seeds} ({enable_ratio*100:.0f}%) 个种子启用RAG增强")
    else:
        print(f"\n🔍 开始RAG增强处理 ({total_seeds} 个种子)")

    # 随机选择要增强的种子索引
    rag_seed_indices = set(random.sample(range(total_seeds), rag_seed_count)) if rag_seed_count > 0 else set()

    # 统计信息
    use_rag_count = 0
    skip_rag_count = 0
    smart_filter_count = 0

    for i, seed in enumerate(seed_questions, 1):
        # 构建查询内容
        query = seed.question

        # 检查是否应该为此种子启用RAG
        should_rag = False
        if i - 1 in rag_seed_indices:
            # 使用智能筛选判断是否真的需要RAG
            if should_use_rag(seed.question, seed.answer):
                should_rag = True
                smart_filter_count += 1
            else:
                skip_rag_count += 1

        if should_rag:
            # 检索相关文档
            try:
                documents = rag_client.retrieve(
                    query=query,
                    top_k=top_k,
                    data_source=data_source
                )

                if documents:
                    # 格式化RAG上下文
                    rag_context = format_rag_context(documents)

                    # 生成增强的提示词
                    enhanced_prompt = generate_rag_enhanced_prompt(
                        seed.question,
                        seed.answer,
                        rag_context
                    )

                    # 创建新的种子问题（使用增强的提示词作为问题）
                    enhanced_seed = SeedQuestion(
                        question=enhanced_prompt,
                        answer=seed.answer,
                        category=seed.category,
                        species=seed.species,
                        difficulty=seed.difficulty,
                        tags=seed.tags + ['rag_enhanced'],
                        rag_query=query,
                        rag_documents=documents,
                        rag_context=rag_context,
                        rag_retrieval_status="success"  # 检索成功（有文献）
                    )

                    enhanced_seeds.append(enhanced_seed)
                    use_rag_count += 1
                else:
                    # 检索成功但未找到文献
                    enhanced_seed = SeedQuestion(
                        question=seed.question,
                        answer=seed.answer,
                        category=seed.category,
                        species=seed.species,
                        difficulty=seed.difficulty,
                        tags=seed.tags + ['rag_enhanced'],
                        rag_query=query,
                        rag_documents=None,
                        rag_context=None,
                        rag_retrieval_status="success_no_docs"  # 检索成功但无文献
                    )
                    enhanced_seeds.append(enhanced_seed)
                    use_rag_count += 1
            except Exception as e:
                print(f"  ⚠️ RAG检索失败: {e}")
                # 检索失败
                failed_seed = SeedQuestion(
                    question=seed.question,
                    answer=seed.answer,
                    category=seed.category,
                    species=seed.species,
                    difficulty=seed.difficulty,
                    tags=seed.tags + ['rag_enhanced'],
                    rag_query=None,
                    rag_documents=None,
                    rag_context=None,
                    rag_retrieval_status="failed"  # 检索失败
                )
                enhanced_seeds.append(failed_seed)
                use_rag_count += 1
        else:
            # 不使用RAG，直接使用原始种子
            enhanced_seeds.append(seed)

        # 进度显示
        if i % 5 == 0 or i == total_seeds:
            print(f"  ✓ 已处理 {i}/{total_seeds} ({i/total_seeds*100:.1f}%) - 使用RAG: {use_rag_count}, 跳过: {skip_rag_count}")

    enhanced_count = len([s for s in enhanced_seeds if 'rag_enhanced' in s.tags])
    print(f"\n✅ RAG增强完成！")
    print(f"   📊 统计信息:")
    print(f"      总种子数: {total_seeds}")
    print(f"      使用RAG: {use_rag_count} 个")
    print(f"      跳过RAG: {skip_rag_count} 个")
    print(f"      智能筛选: {smart_filter_count} 个")
    print(f"      实际增强: {enhanced_count} 个")
    print(f"      RAG利用率: {use_rag_count/total_seeds*100:.1f}%\n")

    return enhanced_seeds

# 全局变量存储专家问题映射
_EXPERT_TASK_MAPPING = None

def load_expert_task_mapping(excel_path=None):
    """
    加载domain_task_expert.xlsx文件，构建专家任务分类映射

    Args:
        excel_path: Excel文件路径，默认使用当前目录下的domain_task_expert.xlsx

    Returns:
        dict: 专家任务分类映射
    """
    if excel_path is None:
        # Try to load from data/raw/ directory (new structure) first, then fall back to old location
        excel_path = Path(__file__).parent.parent / 'data' / 'raw' / 'domain_task_expert.xlsx'
        if not excel_path.exists():
            excel_path = Path(__file__).parent / 'domain_task_expert.xlsx'

    if not Path(excel_path).exists():
        print(f"⚠️  domain_task_expert.xlsx 文件不存在: {excel_path}")
        print("将使用默认映射...")
        return {}

    try:
        df = pd.read_excel(excel_path)
        print(f"✅ 成功加载 domain_task_expert.xlsx: {len(df)} 条记录")

        # 构建分类映射
        mapping = {}

        for _, row in df.iterrows():
            category = row['分类']
            species_list = ['玉米', '大豆', '水稻', '油菜', '小麦', '畜禽', '合成生物']

            # 收集每个物种的权重信息
            species_weights = {}
            for species in species_list:
                if species in df.columns:
                    weight = row[species]
                    if pd.notna(weight):
                        species_weights[species] = weight

            mapping[category] = species_weights

        print(f"✅ 构建专家任务映射完成:")
        print(f"   - 分类数量: {len(mapping)}")

        return mapping

    except Exception as e:
        print(f"❌ 加载domain_task_expert.xlsx失败: {e}")
        import traceback
        traceback.print_exc()
        return {}

def parse_expert_questions(excel_path):
    """
    读取专家问题_扩增CoT.xlsx文件

    Args:
        excel_path: Excel文件路径

    Returns:
        list: 专家问题列表，每个元素包含问题、分类和扩展分类
    """
    if not Path(excel_path).exists():
        print(f"❌ 文件不存在: {excel_path}")
        return []

    try:
        df = pd.read_excel(excel_path)
        print(f"✅ 成功加载专家问题文件: {len(df)} 条记录")

        expert_questions = []
        current_direction = None

        for idx, row in df.iterrows():
            # 更新当前方向
            if pd.notna(row['Unnamed: 0']):
                direction = str(row['Unnamed: 0']).strip()
                if '方向' in direction:
                    current_direction = direction.replace('方向', '')
                else:
                    # 如果没有"方向"后缀，直接使用该值作为direction
                    current_direction = direction

            # 提取专家问题
            if pd.notna(row['专家问题']):
                question = str(row['专家问题']).strip()
                categories_str = str(row['扩展种子问题分类']).strip() if pd.notna(row['扩展种子问题分类']) else ""

                # 解析扩展分类（用"/"分隔）
                extended_categories = [c.strip() for c in categories_str.split('/') if c.strip()]

                expert_questions.append({
                    'direction': current_direction,
                    'question': question,
                    'extended_categories': extended_categories,
                    'original_categories': categories_str
                })

        print(f"✅ 解析专家问题完成: {len(expert_questions)} 个问题")
        return expert_questions

    except Exception as e:
        print(f"❌ 读取专家问题文件失败: {e}")
        import traceback
        traceback.print_exc()
        return []

def map_categories_to_expert(categories, expert_mapping):
    """
    将扩展种子问题分类映射到专家任务分类

    Args:
        categories: 扩展种子问题分类列表
        expert_mapping: 专家任务映射

    Returns:
        list: 映射后的分类列表
    """
    mapped_categories = []

    # 定义分类关键词映射
    category_keywords = {
        '基础理论问答': ['基础理论', '基础', '理论'],
        '物种特异性知识问答': ['物种特异性', '品种', '作物'],
        '生物技术与方法论': ['生物技术', '方法论', '技术', '实验'],
        '病虫草害与抗性机制': ['病虫', '抗性', '病害', '虫害'],
        '生理生化与代谢': ['生理', '生化', '代谢'],
        '育种方案设计与评估': ['育种方案', '设计', '评估'],
        '数据分析与解读': ['数据分析', '数据科学', '解读'],
        '操作规程与问题排查': ['操作规程', '排查', '规程'],
        '文献与信息总结': ['文献', '总结', '信息'],
        '生物信息学分析指令': ['生物信息学', '分析指令', '信息学']
    }

    # 对每个扩展分类进行匹配
    for category in categories:
        category_lower = category.lower()
        best_match = None
        best_score = 0

        # 遍历专家映射中的分类
        for expert_cat in expert_mapping.keys():
            score = 0
            # 计算匹配分数
            if expert_cat in category:
                score += 10

            # 关键词匹配
            if expert_cat in category_keywords:
                for keyword in category_keywords[expert_cat]:
                    if keyword in category:
                        score += 3

            if score > best_score:
                best_score = score
                best_match = expert_cat

        # 如果找到匹配，添加到结果中
        if best_match and best_match not in mapped_categories:
            mapped_categories.append(best_match)

    # 如果没有匹配到任何分类，使用第一个分类或默认分类
    if not mapped_categories and categories:
        mapped_categories.append(categories[0])

    return mapped_categories if mapped_categories else ['核心知识问答']

async def expand_expert_questions(
    excel_file,
    output_suffix="expert_expanded",
    variants_per_seed=1,
    use_rag=False,
    rag_url=None,
    rag_top_k=5,
    rag_data_source=None,
    rag_timeout=300,
    rag_enable_ratio=1.0,
    parallel_rag=True,
    difficulty_level=None,
    max_similarity=0.30,
    enable_prompt_enhancement=True,
    strategies=None,
    variants_per_expand_class=1,
    enforce_species_consistency=False,
    enable_seed_deepening=False
):
    """
    扩增专家问题的QA对

    Args:
        excel_file: 专家问题Excel文件路径
        output_suffix: 输出目录后缀
        variants_per_seed: 每个种子生成的变体数
        use_rag: 是否使用RAG增强
        rag_url: RAG服务URL
        rag_top_k: RAG检索文档数量
        rag_data_source: RAG数据源
        rag_timeout: RAG超时时间
        rag_enable_ratio: RAG启用比例
        parallel_rag: 是否并行处理RAG
        difficulty_level: 生成的QA对难度级别
        max_similarity: 最大相似度阈值（0.0-1.0），控制生成结果与种子问题的相似程度
        enable_prompt_enhancement: 是否启用提示词增强，将扩展分类信息添加到提示词中
        strategies: 指定的生成策略列表，如果为None则使用默认策略
        variants_per_expand_class: 每个扩展分类生成的QA对数量
        enforce_species_consistency: 是否强制扩增问题的物种与种子问题物种一致（可选，默认False）
        enable_seed_deepening: 是否启用种子问题深化模式，保持主题一致性，从不同扩展分类角度深化（可选，默认False）
    """
    print(f"\n{'='*70}")
    print(f"🔬 开始处理专家问题扩增")
    print(f"{'='*70}")

    # 【调试】输出use_rag参数值
    logger.info(f"🔍 调试: use_rag = {use_rag}")

    # 读取专家问题
    expert_questions = parse_expert_questions(excel_file)
    if not expert_questions:
        print(f"❌ 没有读取到专家问题")
        return {
            'status': 'failed',
            'error': '没有读取到专家问题',
            'seed_count': 0,
            'total_generated': 0
        }

    # 加载专家任务映射
    global _EXPERT_TASK_MAPPING
    _EXPERT_TASK_MAPPING = load_expert_task_mapping()

    # 转换为SeedQuestion对象
    seed_questions = []
    category_stats = {}

    # 【修改】先执行RAG检索，对每个专家问题只检索一次
    # 存储RAG检索结果：{问题: 检索结果}
    rag_results_cache = {}

    # 初始化RAG客户端（如果启用RAG）
    rag_client = None
    logger.info(f"🔍 检查use_rag条件: use_rag={use_rag}")
    if use_rag:
        logger.info(f"🔍 开始初始化RAG客户端...")
        print(f"\n🔍 初始化RAG客户端...")
        rag_config = RAG_CONFIG.copy()
        if rag_url:
            rag_config['url'] = rag_url
        if rag_timeout:
            rag_config['timeout'] = rag_timeout

        print(f"   正在连接到RAG服务: {rag_config['url']}")
        try:
            rag_client = RAGClient(config=rag_config)
            logger.info(f"✅ RAG客户端初始化成功")
            print(f"✅ RAG客户端已初始化")
            print(f"   URL: {rag_config['url']}")
            print(f"   数据源: {rag_data_source or ['pubmed']}")
            print(f"   Top-K: {rag_top_k}")
            print(f"   启用比例: {rag_enable_ratio*100:.0f}%")
            print(f"   处理模式: {'并行模式（立即加载RAG检索）' if parallel_rag else '串行模式（预先增强所有种子）'}")
        except Exception as e:
            logger.error(f"❌ RAG客户端初始化失败: {e}")
            print(f"❌ RAG客户端初始化失败: {e}")
            print(f"⚠️ 将继续运行但不使用RAG增强")
            use_rag = False
    else:
        logger.info(f"⚠️ use_rag为False，跳过RAG客户端初始化")

    logger.info(f"🔍 检查预检索条件: rag_client={rag_client is not None}, use_rag={use_rag}")
    if rag_client and use_rag:
        print(f"\n🔍 执行RAG预检索（每个专家问题只检索一次）...")
        rag_retrieved_count = 0
        for i, eq in enumerate(expert_questions, 1):
            # 构建查询内容
            query = eq['question']

            # 检查是否应该为此种子启用RAG
            should_rag = False
            if should_use_rag(eq['question'], ""):  # 专家问题没有答案，用空字符串
                should_rag = True

            if should_rag:
                try:
                    # 使用智能检索（自动翻译优化）
                    documents = smart_retrieve(rag_client, query, rag_top_k, rag_data_source)

                    # 检查documents不仅存在，还要有有效内容
                    if documents and len(documents) > 0 and any(doc for doc in documents if doc):
                        # 格式化RAG上下文
                        rag_context = format_rag_context(documents)
                        rag_results_cache[query] = {
                            'documents': documents,
                            'context': rag_context,
                            'status': 'success'
                        }
                        rag_retrieved_count += 1
                    else:
                        # 检索成功但未找到文献
                        rag_results_cache[query] = {
                            'documents': None,
                            'context': None,
                            'status': 'success_no_docs'
                        }
                        rag_retrieved_count += 1
                except Exception as e:
                    print(f"  ⚠️ RAG检索失败: {e}")
                    # 检索失败
                    rag_results_cache[query] = {
                        'documents': None,
                        'context': None,
                        'status': 'failed'
                    }
            else:
                # 不需要RAG
                rag_results_cache[query] = {
                    'documents': None,
                    'context': None,
                    'status': 'skipped'
                }

            # 进度显示
            if i % 5 == 0 or i == len(expert_questions):
                print(f"  ✓ 已检索 {i}/{len(expert_questions)} ({i/len(expert_questions)*100:.1f}%) - RAG检索: {rag_retrieved_count}")

        print(f"\n✅ RAG预检索完成！")
        print(f"   📊 统计信息:")
        print(f"      专家问题总数: {len(expert_questions)}")
        successful_rag = sum(1 for r in rag_results_cache.values() if r['status'] in ['success', 'success_no_docs'])
        print(f"      成功检索: {successful_rag} 个")
        print(f"      RAG检索率: {successful_rag/len(expert_questions)*100:.1f}%\n")

    for eq in expert_questions:
        # 映射分类
        mapped_categories = map_categories_to_expert(
            eq['extended_categories'],
            _EXPERT_TASK_MAPPING
        )

        # 获取方向（物种）
        direction = eq['direction'] if eq['direction'] else '通用'

        # 使用第一个映射的分类作为主分类
        primary_category = mapped_categories[0] if mapped_categories else '核心知识问答'

        # 更新统计信息
        if primary_category not in category_stats:
            category_stats[primary_category] = 0
        category_stats[primary_category] += 1

        # 【关键修改】为每个扩展分类单独创建一个SeedQuestion
        # 原因：PromptEnhancer会随机选择1个EXP_CAT生成提示词，
        #      导致其他分类被忽略。为每个分类单独创建SeedQuestion可以确保所有分类都被处理
        for extended_category in eq['extended_categories']:
            # 构建精简的tags，只包含当前扩展分类
            tags = ['expert_question', direction]
            # 只添加当前扩展分类的EXP_CAT标签
            tags.append(f"EXP_CAT:{extended_category}")

            # 【修改】从缓存中获取RAG结果
            rag_result = rag_results_cache.get(eq['question'], {
                'documents': None,
                'context': None,
                'status': 'skipped'
            })

            # 如果RAG成功且有上下文，添加到tags
            if rag_result['status'] in ['success', 'success_no_docs']:
                tags.append('rag_enhanced')

            # 【关键修改】设置rag_used标志，防止qa_generator_v2.py重复RAG检索
            # 验证RAG字段一致性
            if rag_result['status'] == 'success':
                # 检查documents是否真的有内容
                if not rag_result['documents'] or len(rag_result['documents']) == 0:
                    logger.warning(f"⚠️ RAG状态为success但documents为空或无效，强制修正为success_no_docs")
                    rag_result['status'] = 'success_no_docs'

            # 计算有效文档数量
            if rag_result['documents'] and len(rag_result['documents']) > 0:
                # 统计有有效内容的文档数量
                valid_docs = [doc for doc in rag_result['documents'] if doc and str(doc).strip()]
                rag_documents_count = len(valid_docs)
            else:
                rag_documents_count = 0

            seed = SeedQuestion(
                question=eq['question'],
                answer="",  # 专家问题没有标准答案
                category=primary_category,
                species=direction,
                difficulty='hard',  # 专家问题设置为困难级别
                tags=tags,
                # 【修改】传递RAG相关信息
                rag_used=rag_result['status'] in ['success', 'success_no_docs'],  # 设置rag_used标志
                rag_documents_count=rag_documents_count,  # 【关键修复】设置有效文档数量
                rag_query=eq['question'] if rag_result['status'] in ['success', 'success_no_docs'] else None,
                rag_documents=rag_result['documents'],
                rag_context=rag_result['context'],
                rag_retrieval_status=rag_result['status']
            )
            seed_questions.append(seed)

    print(f"🔄 转换为种子: {len(seed_questions)} 个")

    # 统计专家问题的分类分布
    print(f"📊 专家问题分类分布:")
    for cat, count in sorted(category_stats.items(), key=lambda x: x[1], reverse=True):
        print(f"   - {cat}: {count} 个")

    # 统计扩展分类的分布
    expanded_category_stats = {}
    for eq in expert_questions:
        for cat in eq['extended_categories']:
            expanded_category_stats[cat] = expanded_category_stats.get(cat, 0) + 1

    print(f"📊 扩展分类分布:")
    for cat, count in sorted(expanded_category_stats.items(), key=lambda x: x[1], reverse=True):
        print(f"   - {cat}: {count} 个")

    # 【修改】RAG增强处理（已在前面的预检索阶段完成，跳过此步骤）
    # 因为我们已经对每个专家问题只执行了一次RAG检索，并将结果传递给了所有扩展分类
    if rag_client and use_rag:
        print(f"\n✅ RAG增强已在预检索阶段完成")
        print(f"   种子数量: {len(seed_questions)}")
        print(f"   RAG标记: {len([s for s in seed_questions if 'rag_enhanced' in s.tags])} 个")
        print(f"   共享RAG结果: 是（每个专家问题只检索一次）")

    # Prompt增强处理（将扩展分类信息添加到提示词中）
    # 为每个扩展分类创建 variants_per_expand_class 个变体
    if enable_prompt_enhancement:
        print(f"\n✨ 启用提示词增强...")
        if enable_seed_deepening:
            print(f"   种子问题深化模式：保持主题一致性，从不同扩展分类角度深化")
        else:
            print(f"   将扩展分类信息添加到提示词中，让模型根据分类进行精准扩增")
        print(f"   为每个扩展分类生成 {variants_per_expand_class} 个变体")
        try:
            enhancer = PromptEnhancer()

            # 新建一个列表来存储所有变体
            expanded_seed_questions = []

            # 为每个种子问题创建多个变体，每个变体对应一个扩展分类
            for seed in seed_questions:
                # 提取该种子问题的所有扩展分类
                categories = enhancer.extract_expanded_categories(seed)

                if not categories:
                    # 如果没有扩展分类，只保留原始种子
                    expanded_seed_questions.append(seed)
                    continue

                # 为每个扩展分类创建指定数量的变体
                for category in categories:
                    for variant_idx in range(variants_per_expand_class):
                        if enable_seed_deepening:
                            # 使用种子问题深化模式
                            variant_seed = enhancer.enhance_seed_question_with_category(
                                seed, category, seed.question, lang="zh"
                            )
                        else:
                            # 使用原有的提示词增强模式
                            category_context = enhancer.build_category_context(
                                enhancer._choose_category(seed, [category]), lang="zh"
                            )
                            enhanced_question = f"{seed.question}\n{category_context}"

                            # 保存原始问题（用于RAG查询）
                            original_question = getattr(seed, 'original_question', None) or seed.question

                            variant_seed = SeedQuestion(
                                question=enhanced_question,
                                answer=seed.answer,
                                category=seed.category,
                                species=seed.species,
                                difficulty=seed.difficulty,
                                tags=seed.tags.copy(),
                                original_question=original_question  # 保留原始问题
                            )

                        # 添加变体标识到tags
                        variant_seed.tags.append(f"VARIANT_CATEGORY:{category}")
                        variant_seed.tags.append(f"VARIANT_INDEX:{variant_idx}")

                        expanded_seed_questions.append(variant_seed)

            # 替换原始种子问题列表
            seed_questions = expanded_seed_questions

            # 打印增强报告
            enhancer.print_enhancement_report(seed_questions, lang="zh")
            print(f"✅ 提示词增强完成！")
            print(f"📊 总计: {len(expanded_seed_questions)} 个变体 ({len([s for s in seed_questions if any(tag.startswith('VARIANT_') for tag in s.tags)])} 个扩展分类变体)")
        except Exception as e:
            print(f"❌ 提示词增强失败: {e}")
            print(f"⚠️ 将使用原始提示词继续执行")

    # 优化质量配置（针对专家问题）
    quality_cfg = QualityConfig(
        min_question_len=10,  # 专家问题通常较长
        min_answer_len=50,   # 专家问题需要详细回答
        max_answer_len=8000,
        base_quality_floor=0.0,
        enable_self_consistency=False,
        enable_model_judge=False,
        max_dup_similarity=max_similarity,  # 可控的相似度阈值
        banned_phrases=(),
        placeholder_patterns=()
    )

    # 确保 API Key 已加载
    import os
    if not os.getenv("OPENAI_API_KEY") and not os.getenv("DEEPSEEK_API_KEY"):
        # 尝试从 config/.env 加载
        env_path = Path(__file__).parent.parent / 'config' / '.env'
        if env_path.exists():
            from dotenv import load_dotenv
            load_dotenv(env_path)
            print(f"✅ 已加载 .env 文件: {env_path}")

    generator = DeepSeekGenerator(
        model_name='gpt-5.1',
        quality_cfg=quality_cfg,
        max_retries=5,
        max_concurrent=10,
        rag_client=rag_client
    )

    # 创建输出目录
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_dir = f'./output/output_expert_expanded_{timestamp}'
    Path(output_dir).mkdir(parents=True, exist_ok=True)

    batch_processor = BatchQAGenerator(
        generator,
        output_dir,
        target_species=None  # 让系统根据种子问题内容自动识别物种
    )

    # 设置生成策略
    if strategies is None:
        # 默认策略：专家问题适合的策略
        methods = [
            GenerationMethod.ELABORATION,
            GenerationMethod.PERSPECTIVE_SHIFT,
            GenerationMethod.MULTI_TURN,
            GenerationMethod.COMPARATIVE_ANALYSIS,
            GenerationMethod.FUTURE_SCENARIO,
            GenerationMethod.HYPOTHETICAL,
            GenerationMethod.META_QUESTION,
            GenerationMethod.TEMPORAL_SHIFT,
            GenerationMethod.SPATIAL_SHIFT,
            GenerationMethod.DISCIPLINE_CROSS,
            GenerationMethod.SCALE_CHANGE,
            GenerationMethod.CAUSAL_CHAIN
        ]
        print(f"🎯 使用默认策略 ({len(methods)} 个策略)")
    else:
        methods = strategies
        print(f"🎯 使用自定义策略 ({len(methods)} 个策略)")

    # 显示策略信息
    if methods:
        strategy_names = [m.value for m in methods]
        print(f"   策略列表: {', '.join(strategy_names[:5])}")
        if len(strategy_names) > 5:
            print(f"   ... (还有 {len(strategy_names) - 5} 个策略)")

    # 计算每个原始种子问题的平均变体数
    original_seed_count = len([s for s in seed_questions if not any(tag.startswith("VARIANT_") for tag in s.tags)])
    avg_variants = len(seed_questions) / original_seed_count if original_seed_count > 0 else 0

    print(f"🚀 开始生成 (每个种子平均{avg_variants:.1f}个变体)")
    start_time = time.time()

    try:
        # 使用变体数量作为 variants_per_seed
        effective_variants = max(1, int(avg_variants))
        result = await batch_processor.generate_from_seeds_async(
            seed_questions=seed_questions,
            variants_per_seed=effective_variants,
            batch_size=5,  # 专家问题处理较慢，减少批次大小
            concurrent_batches=2,  # 减少并发数
            methods=methods,
            difficulty_level=difficulty_level,
            enforce_species_consistency=enforce_species_consistency
        )

        elapsed = time.time() - start_time

        # 统计信息
        stats = result['generation_stats']
        total_generated = stats['total_generated']
        success_count = stats['successful_generations']
        failure_count = stats['failed_generations']

        print(f"\n{'='*70}")
        print(f"✅ 专家问题扩增完成!")
        print(f"{'='*70}")
        print(f"⏱️  耗时: {elapsed:.2f}秒")
        print(f"📊 种子: {len(seed_questions)} 个")
        print(f"✅ 成功: {success_count} 个")
        print(f"❌ 失败: {failure_count} 个")
        print(f"📝 生成: {total_generated} 个QA对")
        print(f"🚀 速度: {len(seed_questions)/elapsed:.2f} 种子/秒")
        print(f"{'='*70}\n")

        # 清理RAG客户端
        if rag_client:
            rag_client.close()

        return {
            'status': 'success',
            'seed_count': len(seed_questions),
            'success_count': success_count,
            'failure_count': failure_count,
            'total_generated': total_generated,
            'elapsed': elapsed,
            'success_rate': success_count / len(seed_questions) * 100 if len(seed_questions) > 0 else 0
        }

    except Exception as e:
        elapsed = time.time() - start_time
        print(f"\n❌ 专家问题扩增失败:")
        print(f"错误: {str(e)}")
        import traceback
        traceback.print_exc()

        # 清理RAG客户端
        if rag_client:
            rag_client.close()

        return {
            'status': 'failed',
            'error': str(e),
            'seed_count': len(seed_questions),
            'total_generated': 0,
            'elapsed': elapsed
        }

async def main():
    """主函数"""
    if len(sys.argv) < 2:
        print("使用方法: python run_expansion_from_dir_expert.py <专家问题Excel文件> [variants_per_seed] [--use-rag] [--rag-url URL] [--rag-top-k K] [--rag-data-source SOURCE] [--rag-timeout SECONDS] [--rag-enable-ratio RATIO] [--parallel-rag] [--no-parallel-rag] [--difficulty DIFFICULTY] [--max-similarity RATIO] [--no-prompt-enhancement] [--strategies STRATEGY1,STRATEGY2,...] [--variants-per-expand-class N] [--enforce-species-consistency] [--seed-deepening]")
        print("")
        print("参数说明:")
        print("  excel_file                    : 专家问题Excel文件路径（必需，默认：专家问题_扩增CoT.xlsx）")
        print("  variants_per_seed             : 每个种子生成的变体数（可选，默认1）")
        print("")
        print("多分类扩增参数:")
        print("  --variants-per-expand-class N : 每个扩展分类生成的QA对数量（可选，默认1）")
        print("")
        print("物种一致性参数:")
        print("  --enforce-species-consistency : 强制扩增问题的物种与种子问题物种一致（可选，默认关闭）")
        print("")
        print("提示词增强参数:")
        print("  --seed-deepening             : 启用种子问题深化模式，保持主题一致性，从不同扩展分类角度深化（可选，默认关闭）")
        print("  --no-prompt-enhancement     : 禁用提示词增强，不将扩展分类信息添加到提示词中（可选）")
        print("")
        print("RAG参数:")
        print("  --use-rag            : 启用RAG增强（可选）")
        print("  --rag-url URL        : RAG服务URL（可选，默认http://localhost:9487/retrieve）")
        print("  --rag-top-k K        : RAG检索文档数量（可选，默认5）")
        print("  --rag-data-source    : RAG数据源，多个用逗号分隔（可选，默认pubmed）")
        print("  --rag-timeout        : RAG超时时间（可选，默认300秒）")
        print("  --rag-enable-ratio   : RAG启用比例，0.0-1.0（可选，默认1.0全部启用）")
        print("  --parallel-rag       : 启用并行模式，RAG和QA生成同时进行（可选，默认启用）")
        print("  --no-parallel-rag    : 禁用并行模式，预先增强所有种子（可选）")
        print("")
        print("质量参数:")
        print("  --difficulty DIFFICULTY : 生成的QA对难度级别（easy/medium/hard，可选，默认hard）")
        print("  --max-similarity RATIO  : 最大相似度阈值，0.0-1.0（可选，默认0.30）")
        print("                          值越小，生成结果与种子问题差异越大（更多创新）")
        print("                          值越大，生成结果与种子问题更相似（更高一致性）")
        print("")
        print("策略参数:")
        print("  --strategies STRATEGIES   : 指定生成策略，多个用逗号分隔（可选）")
        print("                          可选策略: PARAPHRASE, ELABORATION, PERSPECTIVE_SHIFT, MULTI_TURN,")
        print("                                   CROSS_SPECIES, REVERSE_REASONING, INNOVATIVE_APPLICATION,")
        print("                                   COMPARATIVE_ANALYSIS, FUTURE_SCENARIO, HYPOTHETICAL,")
        print("                                   COUNTERFACTUAL, META_QUESTION, TEMPORAL_SHIFT, SPATIAL_SHIFT,")
        print("                                   DISCIPLINE_CROSS, SCALE_CHANGE, TIME_SERIES, CAUSAL_CHAIN,")
        print("                                   DIALOGUE_VARIATION")
        print("                          默认: 自动选择策略")
        print("")
        print("示例:")
        print("  # 处理专家问题_扩增CoT.xlsx文件")
        print("  python run_expansion_from_dir_expert.py 专家问题_扩增CoT.xlsx")
        print("  python run_expansion_from_dir_expert.py 专家问题_扩增CoT.xlsx 2")
        print("  # 启用种子问题深化模式，从不同扩展分类角度深化种子问题")
        print("  python run_expansion_from_dir_expert.py 专家问题_扩增CoT.xlsx --seed-deepening")
        print("  # 结合RAG增强")
        print("  python run_expansion_from_dir_expert.py 专家问题_扩增CoT.xlsx --use-rag")
        print("  python run_expansion_from_dir_expert.py 专家问题_扩增CoT.xlsx --use-rag --rag-url http://localhost:9487/retrieve --rag-top-k 5")
        print("  python run_expansion_from_dir_expert.py 专家问题_扩增CoT.xlsx --use-rag --rag-enable-ratio 0.5")
        print("  # 难度设置")
        print("  python run_expansion_from_dir_expert.py 专家问题_扩增CoT.xlsx --difficulty medium")
        print("  python run_expansion_from_dir_expert.py 专家问题_扩增CoT.xlsx --difficulty hard --use-rag")
        print("  # 控制相似度")
        print("  python run_expansion_from_dir_expert.py 专家问题_扩增CoT.xlsx --max-similarity 0.20")
        print("  python run_expansion_from_dir_expert.py 专家问题_扩增CoT.xlsx --max-similarity 0.50")
        print("  # 提示词增强")
        print("  python run_expansion_from_dir_expert.py 专家问题_扩增CoT.xlsx  # 默认启用提示词增强")
        print("  python run_expansion_from_dir_expert.py 专家问题_扩增CoT.xlsx --no-prompt-enhancement")
        print("  # 指定生成策略")
        print("  python run_expansion_from_dir_expert.py 专家问题_扩增CoT.xlsx --strategies ELABORATION,PARAPHRASE")
        print("  python run_expansion_from_dir_expert.py 专家问题_扩增CoT.xlsx --strategies ELABORATION,COMPARATIVE_ANALYSIS,PERSPECTIVE_SHIFT")
        print("  # 多分类扩增")
        print("  python run_expansion_from_dir_expert.py 专家问题_扩增CoT.xlsx --variants-per-expand-class 2")
        print("  python run_expansion_from_dir_expert.py 专家问题_扩增CoT.xlsx --variants-per-expand-class 3")
        print("")
        sys.exit(1)

    # 解析基本参数
    excel_file = sys.argv[1]
    variants_per_seed = 1  # 默认值

    # 所有参数都通过关键字传递，不再支持位置参数
    # 这样可以避免将策略参数误识别为位置参数
    # 后续通过 getarg() 函数提取关键字参数值

    # 解析RAG参数
    use_rag = '--use-rag' in sys.argv
    rag_url = None
    rag_top_k = 5
    rag_data_source = None
    rag_timeout = 300
    rag_enable_ratio = 1.0
    parallel_rag = True

    # 提取RAG参数值
    if '--rag-url' in sys.argv:
        idx = sys.argv.index('--rag-url')
        if idx + 1 < len(sys.argv):
            rag_url = sys.argv[idx + 1]

    if '--rag-top-k' in sys.argv:
        idx = sys.argv.index('--rag-top-k')
        if idx + 1 < len(sys.argv):
            rag_top_k = int(sys.argv[idx + 1])

    if '--rag-data-source' in sys.argv:
        idx = sys.argv.index('--rag-data-source')
        if idx + 1 < len(sys.argv):
            sources = sys.argv[idx + 1].split(',')
            rag_data_source = [s.strip() for s in sources if s.strip()]

    if '--rag-timeout' in sys.argv:
        idx = sys.argv.index('--rag-timeout')
        if idx + 1 < len(sys.argv):
            rag_timeout = int(sys.argv[idx + 1])

    if '--rag-enable-ratio' in sys.argv:
        idx = sys.argv.index('--rag-enable-ratio')
        if idx + 1 < len(sys.argv):
            rag_enable_ratio = float(sys.argv[idx + 1])

    # 解析并行模式参数
    if '--parallel-rag' in sys.argv:
        parallel_rag = True
    if '--no-parallel-rag' in sys.argv:
        parallel_rag = False

    # 解析难度参数
    difficulty_level = 'hard'  # 默认专家问题为困难级别
    if '--difficulty' in sys.argv:
        idx = sys.argv.index('--difficulty')
        if idx + 1 < len(sys.argv):
            difficulty_level = sys.argv[idx + 1]
            if difficulty_level not in ['easy', 'medium', 'hard']:
                print(f"❌ 错误: 难度值必须是 'easy', 'medium', 或 'hard'，收到: {difficulty_level}")
                sys.exit(1)

    # 解析相似度参数
    max_similarity = 0.30  # 默认相似度阈值
    if '--max-similarity' in sys.argv:
        idx = sys.argv.index('--max-similarity')
        if idx + 1 < len(sys.argv):
            max_similarity = float(sys.argv[idx + 1])
            if max_similarity < 0.0 or max_similarity > 1.0:
                print(f"❌ 错误: 相似度阈值必须在0.0-1.0之间，收到: {max_similarity}")
                sys.exit(1)

    # 解析提示词增强参数
    enable_prompt_enhancement = True  # 默认启用提示词增强
    if '--no-prompt-enhancement' in sys.argv:
        enable_prompt_enhancement = False

    # 解析多分类扩增参数
    variants_per_expand_class = 1  # 默认每个扩展分类生成1个QA对
    if '--variants-per-expand-class' in sys.argv:
        idx = sys.argv.index('--variants-per-expand-class')
        if idx + 1 < len(sys.argv):
            variants_per_expand_class = int(sys.argv[idx + 1])
            if variants_per_expand_class < 1:
                print(f"❌ 错误: 每个扩展分类的变体数必须 >= 1，收到: {variants_per_expand_class}")
                sys.exit(1)

    # 解析物种一致性参数
    enforce_species_consistency = False  # 默认不强制物种一致性（向后兼容）
    if '--enforce-species-consistency' in sys.argv:
        enforce_species_consistency = True
        print("✅ 启用物种一致性验证：扩增问题的物种必须与种子问题物种严格一致")

    # 解析种子问题深化参数
    enable_seed_deepening = False  # 默认关闭种子问题深化模式
    if '--seed-deepening' in sys.argv:
        enable_seed_deepening = True
        print("✅ 启用种子问题深化模式：保持主题一致性，从不同扩展分类角度深化种子问题")

    # 解析策略参数
    strategies = None  # 默认使用自动策略选择

    # 【修复】种子深化模式下，如果用户未指定策略，自动使用SEED_DEEPENING策略
    # 避免与其他策略（如PARAPHRASE的"跳出主题创新"）产生冲突
    if enable_seed_deepening and '--strategies' not in sys.argv:
        strategies = [GenerationMethod.SEED_DEEPENING]
        print(f"✅ 种子深化模式：自动使用 SEED_DEEPENING 策略（保持主题一致性）")
    elif enable_seed_deepening:
        print(f"🔍 调试: enable_seed_deepening={enable_seed_deepening}, '--strategies' in sys.argv={('--strategies' in sys.argv)}")

    if '--strategies' in sys.argv:
        idx = sys.argv.index('--strategies')
        if idx + 1 < len(sys.argv):
            strategy_names = sys.argv[idx + 1].split(',')
            strategies = []
            valid_methods = [m.name for m in GenerationMethod]
            for name in strategy_names:
                name = name.strip()
                if name in valid_methods:
                    strategies.append(getattr(GenerationMethod, name))
                else:
                    print(f"⚠️  警告: 无效的策略 '{name}'，有效选项: {', '.join(valid_methods)}")
            if strategies:
                print(f"✅ 使用指定的生成策略: {', '.join([s.name for s in strategies])}")
                # 【警告】检查种子深化模式与策略的兼容性
                if enable_seed_deepening:
                    conflicting_strategies = ['PARAPHRASE', 'ELABORATION', 'CROSS_SPECIES', 'INNOVATIVE_APPLICATION']
                    conflicts = [s.name for s in strategies if s.name in conflicting_strategies]
                    if conflicts:
                        print(f"⚠️  警告: 种子深化模式与 {', '.join(conflicts)} 策略可能存在冲突")
                        print(f"   这些策略设计为'跳出主题创新'，而种子深化要求'保持主题一致性'")
                        print(f"   建议使用 SEED_DEEPENING 策略或移除 --seed-deepening 参数")
            else:
                print(f"⚠️  警告: 没有有效的策略，将使用默认策略")

    # 检查输入文件
    if not Path(excel_file).exists():
        # 如果没有提供绝对路径，尝试相对路径
        default_path = Path(__file__).parent / excel_file
        if default_path.exists():
            excel_file = str(default_path)
        else:
            print(f"❌ 文件不存在: {excel_file}")
            sys.exit(1)

    print(f"{'='*70}")
    print(f"🔬 专家问题QA扩增脚本")
    print(f"{'='*70}")
    print(f"📄 输入文件: {excel_file}")
    print(f"📊 扩展分类扩增: {'启用' if enable_prompt_enhancement else '禁用'}")
    if enable_prompt_enhancement:
        print(f"   模式: 为每个扩展分类生成 {variants_per_expand_class} 个变体")
    print(f"🔍 RAG增强: {'启用' if use_rag else '禁用'}")
    if use_rag:
        print(f"   - URL: {rag_url or 'http://localhost:9487/retrieve'}")
        print(f"   - Top-K: {rag_top_k}")
        print(f"   - 数据源: {rag_data_source or ['pubmed']}")
        print(f"   - 超时: {rag_timeout}秒")
        print(f"   - 启用比例: {rag_enable_ratio*100:.0f}%")
        print(f"   - 处理模式: {'并行模式' if parallel_rag else '串行模式'}")
    print(f"🎯 难度级别: {difficulty_level}")
    print(f"🔬 相似度阈值: {max_similarity:.2f} ({'更创新' if max_similarity < 0.3 else '更一致' if max_similarity > 0.4 else '平衡'})")
    print(f"✨ 提示词增强: {'启用' if enable_prompt_enhancement else '禁用'}")
    if enable_seed_deepening:
        print(f"🎯 种子深化: 启用")
    if strategies:
        print(f"🎭 生成策略: {', '.join([s.name for s in strategies])}")
    else:
        print(f"🎭 生成策略: 自动选择")
    print(f"{'='*70}\n")

    result = await expand_expert_questions(
        excel_file=excel_file,
        output_suffix="expert_expanded",
        variants_per_seed=variants_per_seed,
        use_rag=use_rag,
        rag_url=rag_url,
        rag_top_k=rag_top_k,
        rag_data_source=rag_data_source,
        rag_timeout=rag_timeout,
        rag_enable_ratio=rag_enable_ratio,
        parallel_rag=parallel_rag,
        difficulty_level=difficulty_level,
        max_similarity=max_similarity,
        enable_prompt_enhancement=enable_prompt_enhancement,
        strategies=strategies,
        variants_per_expand_class=variants_per_expand_class,
        enforce_species_consistency=enforce_species_consistency,
        enable_seed_deepening=enable_seed_deepening
    )

    # 调试：输出最终选择的策略
    print(f"🔍 调试: 最终传递给函数的 strategies = {([s.name if s else None for s in strategies] if strategies else 'None')}")
    print(f"🔍 调试: enable_seed_deepening = {enable_seed_deepening}")

    # 输出最终结果
    print(f"\n{'='*70}")
    print(f"🎯 最终统计")
    print(f"{'='*70}")
    if result['status'] == 'success':
        print(f"✅ 状态: 成功")
        print(f"📊 种子数: {result['seed_count']}")
        print(f"✅ 成功: {result['success_count']}")
        print(f"❌ 失败: {result['failure_count']}")
        print(f"📝 生成: {result['total_generated']} 个QA对")
        print(f"⏱️  耗时: {result['elapsed']:.2f}秒")
        print(f"🚀 速率: {result['success_rate']:.1f}%")
    else:
        print(f"❌ 状态: 失败")
        print(f"错误: {result.get('error', 'Unknown')}")
    print(f"{'='*70}\n")

if __name__ == '__main__':
    asyncio.run(main())
