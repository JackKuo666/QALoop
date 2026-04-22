#!/usr/bin/env python3
"""
从合并的物种QA目录中批量提取种子，并运行种子问答对扩增
支持异步并行处理多个物种，支持RAG增强
基于domain_task.xlsx进行子类别映射和关键词匹配
支持RAG（检索增强生成）功能
"""
import asyncio
import json
import sys
import os

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

# 全局变量存储子类别映射
_SUBSPECIES_MAPPING = None
_SPECIES_KEYWORDS = None

# 全局变量存储比例配置
_RATIOS_CONFIG = None

def load_ratios_config(config_path=None):
    """
    加载生成比例配置文件

    Args:
        config_path: 配置文件路径

    Returns:
        dict: 配置字典，如果加载失败则返回None
    """
    if config_path is None:
        # Try to load from config/ directory (new structure) first, then fall back to old location
        config_path = Path(__file__).parent.parent / 'config' / 'generation_ratios_config.yaml'
        if not config_path.exists():
            config_path = Path(__file__).parent / 'generation_ratios_config.yaml'

    if not Path(config_path).exists():
        print(f"⚠️  比例配置文件不存在: {config_path}")
        print("将使用默认配置...")
        return None

    try:
        with open(config_path, 'r', encoding='utf-8') as f:
            config = yaml.safe_load(f)

        print(f"✅ 成功加载比例配置文件: {config_path}")

        # 显示加载的配置信息
        species_ratios = config.get('species_ratios', {})
        subspecies_ratios = config.get('subspecies_ratios', {})

        print(f"📊 配置摘要:")
        print(f"   - 物种权重: {len(species_ratios)} 个")
        print(f"   - 子类别权重: {len(subspecies_ratios)} 个")

        strategy = config.get('generation_strategy', {})
        if strategy.get('enable_ratio_filtering'):
            print(f"   - 启用比例筛选: ✅")
        if strategy.get('enable_ratio_sorting'):
            print(f"   - 启用比例排序: ✅")

        return config

    except Exception as e:
        print(f"❌ 加载比例配置文件失败: {e}")
        import traceback
        traceback.print_exc()
        return None

def apply_weighted_classification(matched_subspecies, subspecies_ratios, strategy_config):
    """
    基于权重配置调整匹配的子类别列表

    Args:
        matched_subspecies: 原始匹配的子类别列表
        subspecies_ratios: 子类别权重配置
        strategy_config: 生成策略配置

    Returns:
        tuple: (adjusted_category, weight_info)
    """
    if not matched_subspecies or not subspecies_ratios:
        return matched_subspecies[0] if matched_subspecies else None, None

    enable_filtering = strategy_config.get('enable_ratio_filtering', False)
    enable_sorting = strategy_config.get('enable_ratio_sorting', False)
    min_threshold = strategy_config.get('min_weight_threshold', 0.5)

    # 计算每个子类别的权重
    weighted_subspecies = []
    for subs in matched_subspecies:
        weight = subspecies_ratios.get(subs, 1.0)
        weighted_subspecies.append((subs, weight))

    # 筛选低权重项
    if enable_filtering:
        filtered_subspecies = [(s, w) for s, w in weighted_subspecies if w >= min_threshold]
        if filtered_subspecies:
            weighted_subspecies = filtered_subspecies

    # 按权重排序
    if enable_sorting:
        weighted_subspecies.sort(key=lambda x: x[1], reverse=True)

    # 选择最终分类
    final_category = weighted_subspecies[0][0] if weighted_subspecies else matched_subspecies[0]

    # 返回分类和权重信息
    weight_info = {
        'selected_category': final_category,
        'all_matches': [(s, w) for s, w in weighted_subspecies],
        'strategy_used': {
            'filtering': enable_filtering,
            'sorting': enable_sorting,
            'threshold': min_threshold
        }
    }

    return final_category, weight_info

def load_domain_task_mapping(excel_path=None):
    """
    加载domain_task.xlsx文件，构建关键词到子类别映射

    Args:
        excel_path: Excel文件路径，默认使用当前目录下的domain_task.xlsx

    Returns:
        tuple: (subspecies_mapping, species_keywords)
    """
    if excel_path is None:
        # Try to load from data/raw/ directory (new structure) first, then fall back to old location
        excel_path = Path(__file__).parent.parent / 'data' / 'raw' / 'domain_task.xlsx'
        if not excel_path.exists():
            excel_path = Path(__file__).parent / 'domain_task.xlsx'

    if not Path(excel_path).exists():
        print(f"⚠️  domain_task.xlsx 文件不存在: {excel_path}")
        print("将使用默认映射...")
        return {}, {}

    try:
        df = pd.read_excel(excel_path, sheet_name='domain_task')
        print(f"✅ 成功加载 domain_task.xlsx: {len(df)} 条记录")

        # 构建关键词到子类别映射
        subspecies_mapping = {}
        species_keywords = {}

        for _, row in df.iterrows():
            species = row['species']
            subspecies = row['subspecies']
            keywords_str = row['keywords']
            description = row['description']

            # 解析关键词（逗号分隔）
            if pd.notna(keywords_str):
                keywords = [kw.strip() for kw in str(keywords_str).split(',') if kw.strip()]

                # 为每个关键词建立映射
                for keyword in keywords:
                    if keyword not in subspecies_mapping:
                        subspecies_mapping[keyword] = []
                    subspecies_mapping[keyword].append({
                        'subspecies': subspecies,
                        'species': species,
                        'description': description
                    })

            # 收集物种的特定关键词
            if species not in species_keywords:
                species_keywords[species] = set()
            if pd.notna(keywords_str):
                keywords = [kw.strip() for kw in str(keywords_str).split(',') if kw.strip()]
                species_keywords[species].update(keywords)

        # 将set转换为list以便JSON序列化
        species_keywords = {k: list(v) for k, v in species_keywords.items()}

        print(f"✅ 构建映射完成:")
        print(f"   - 关键词数量: {len(subspecies_mapping)}")
        print(f"   - 物种数量: {len(species_keywords)}")

        return subspecies_mapping, species_keywords

    except Exception as e:
        print(f"❌ 加载domain_task.xlsx失败: {e}")
        import traceback
        traceback.print_exc()
        return {}, {}

def match_subspecies(text, subspecies_mapping, species_name, species_keywords):
    """
    基于文本内容匹配最相关的子类别

    Args:
        text: 待匹配的文本（问题+答案）
        subspecies_mapping: 关键词到子类别的映射
        species_name: 物种名称
        species_keywords: 物种特定关键词映射

    Returns:
        list: 匹配的子类别列表
    """
    if not text or not subspecies_mapping:
        return []

    # 合并所有文本
    combined_text = (text if isinstance(text, str) else str(text)).lower()

    # 统计匹配的关键词及其权重
    keyword_scores = {}
    species_specific_kws = species_keywords.get(species_name, [])

    for keyword, subspecies_list in subspecies_mapping.items():
        keyword_lower = keyword.lower()
        if keyword_lower in combined_text:
            # 基础分数
            score = 1

            # 如果是物种特定关键词，增加权重
            if keyword in species_specific_kws:
                score *= 2

            # 长关键词权重更高（更具体）
            score += len(keyword) * 0.1

            # 累计该子类别分数
            for item in subspecies_list:
                subspecies = item['subspecies']
                if subspecies not in keyword_scores:
                    keyword_scores[subspecies] = 0
                keyword_scores[subspecies] += score

    # 按分数排序，返回前5个
    sorted_subspecies = sorted(keyword_scores.items(), key=lambda x: x[1], reverse=True)
    matched_subspecies = [s[0] for s in sorted_subspecies[:5]]

    # 如果没有匹配到，使用默认分类
    if not matched_subspecies:
        # 尝试基于物种推断默认子类别
        if species_name in ['玉米', '大豆', '水稻', '油菜', '小麦']:
            matched_subspecies = ['物种特异性知识问答', '基础理论问答']
        elif species_name == '畜禽':
            matched_subspecies = ['物种特异性知识问答', '营养与饲料管理']
        elif species_name == '合成生物技术':
            matched_subspecies = ['生物技术与方法论', '生物安全与伦理']
        else:
            matched_subspecies = ['物种特异性知识问答']

    return matched_subspecies

async def expand_single_species(
    species_name,
    input_file,
    output_suffix="expanded",
    variants_per_seed=1,
    unified_output_dir=None,
    file_suffix="",
    use_rag=False,
    rag_url=None,
    rag_top_k=5,
    rag_data_source=None,
    rag_timeout=300,
    rag_enable_ratio=1.0,
    parallel_rag=True,
    difficulty_level=None
):
    """
    扩增单个物种的QA对

    Args:
        species_name: 物种名称
        input_file: 输入的JSONL文件路径
        output_suffix: 输出目录后缀
        variants_per_seed: 每个种子生成的变体数
        unified_output_dir: 统一的输出目录（所有物种都保存到此处）
        file_suffix: 文件后缀（如'_A'、'_B'或''）
        use_rag: 是否使用RAG增强
        rag_url: RAG服务URL
        rag_top_k: RAG检索文档数量
        rag_data_source: RAG数据源
        rag_timeout: RAG超时时间
        rag_enable_ratio: RAG启用比例
        parallel_rag: 是否并行处理RAG
        difficulty_level: 生成的QA对难度级别（easy/medium/hard）
    """
    print(f"\n{'='*70}")
    print(f"🌾 开始处理物种: {species_name}{file_suffix if file_suffix else ''}")
    print(f"{'='*70}")

    # 加载合并文件中的QA对
    qa_pairs = []
    print(f"📂 加载文件: {input_file}")

    try:
        with open(input_file, 'r', encoding='utf-8') as f:
            for line in f:
                qa = json.loads(line.strip())
                qa_pairs.append(qa)

        print(f"✅ 加载完成: {len(qa_pairs)} 条QA对")

    except Exception as e:
        print(f"❌ 加载文件失败: {e}")
        return {
            'species': species_name,
            'status': 'failed',
            'error': str(e),
            'seed_count': 0,
            'total_generated': 0,
            'elapsed': 0
        }

    # 转换为SeedQuestion对象
    seed_questions = []
    global _SUBSPECIES_MAPPING, _SPECIES_KEYWORDS, _RATIOS_CONFIG

    # 准备权重配置
    subspecies_ratios = {}
    strategy_config = {}
    if _RATIOS_CONFIG:
        subspecies_ratios = _RATIOS_CONFIG.get('subspecies_ratios', {})
        strategy_config = _RATIOS_CONFIG.get('generation_strategy', {})

    # 统计信息
    subspecies_stats = {}
    weight_stats = {
        'total_processed': 0,
        'weighted_adjustments': 0,
        'original_matches_used': 0
    }

    for qa in qa_pairs:
        metadata = qa.get('metadata', {})
        original_category = metadata.get('主分类', '核心知识问答')
        species = metadata.get('物种', species_name)

        weight_stats['total_processed'] += 1

        # 优先使用子类别匹配，如果没有则使用原metadata
        combined_text = f"{qa['question']} {qa['answer']}"
        matched_subspecies = match_subspecies(combined_text, _SUBSPECIES_MAPPING, species_name, _SPECIES_KEYWORDS)

        # 应用权重调整
        if matched_subspecies and subspecies_ratios and strategy_config:
            category, weight_info = apply_weighted_classification(
                matched_subspecies,
                subspecies_ratios,
                strategy_config
            )
            if weight_info and weight_info['strategy_used']['filtering']:
                weight_stats['weighted_adjustments'] += 1
        else:
            category = matched_subspecies[0] if matched_subspecies else original_category
            weight_stats['original_matches_used'] += 1

        seed = SeedQuestion(
            question=qa['question'],
            answer=qa['answer'],
            category=category,
            species=species,
            difficulty='medium',
            tags=[species]
        )
        seed_questions.append(seed)

        # 更新统计信息
        if category not in subspecies_stats:
            subspecies_stats[category] = 0
        subspecies_stats[category] += 1

    print(f"🔄 转换为种子: {len(seed_questions)} 个")

    # 初始化RAG客户端（如果启用RAG）
    rag_client = None
    if use_rag:
        print(f"\n🔍 初始化RAG客户端...")
        rag_config = RAG_CONFIG.copy()
        if rag_url:
            rag_config['url'] = rag_url
        if rag_timeout:
            rag_config['timeout'] = rag_timeout

        print(f"   正在连接到RAG服务: {rag_config['url']}")
        try:
            rag_client = RAGClient(config=rag_config)
            print(f"✅ RAG客户端已初始化")
            print(f"   URL: {rag_config['url']}")
            print(f"   数据源: {rag_data_source or ['pubmed']}")
            print(f"   Top-K: {rag_top_k}")
            print(f"   启用比例: {rag_enable_ratio*100:.0f}%")
            print(f"   处理模式: {'并行模式（立即加载RAG检索）' if parallel_rag else '串行模式（预先增强所有种子）'}")
            if parallel_rag:
                print(f"   ✓ 并行模式现已支持立即加载RAG，确保RAG文档正确保存")
        except Exception as e:
            print(f"❌ RAG客户端初始化失败: {e}")
            print(f"⚠️ 将继续运行但不使用RAG增强")
            use_rag = False

    # RAG增强处理
    if rag_client:
        print(f"\n🔍 开始RAG增强处理...")
        print(f"   种子数量: {len(seed_questions)}")
        print(f"   Top-K: {rag_top_k}")
        print(f"   数据源: {rag_data_source or ['pubmed']}")
        print(f"   启用比例: {rag_enable_ratio*100:.0f}%")
        print(f"   处理模式: {'并行模式（立即加载RAG检索）' if parallel_rag else '串行模式（预先增强所有种子）'}")
        if parallel_rag:
            print(f"   ✓ 并行模式现已支持立即加载RAG，确保RAG文档正确保存")
        try:
            # 根据parallel_rag参数选择不同的处理模式
            if parallel_rag:
                # 并行模式：标记需要RAG的种子，通过立即加载在QA生成时动态检索
                seed_questions = enhance_seeds_with_rag(
                    seed_questions,
                    rag_client,
                    top_k=rag_top_k,
                    data_source=rag_data_source,
                    enable_ratio=rag_enable_ratio,
                    parallel=True
                )
                print(f"   ⚡ 并行模式：已标记需要RAG的种子，将在QA生成时立即加载RAG")
            else:
                # 串行模式：预先增强所有种子
                seed_questions = enhance_seeds_with_rag(
                    seed_questions,
                    rag_client,
                    top_k=rag_top_k,
                    data_source=rag_data_source,
                    enable_ratio=rag_enable_ratio,
                    parallel=False
                )
        except Exception as e:
            print(f"❌ RAG增强失败: {e}")
            print(f"⚠️ 将使用原始种子继续执行")

    # 显示权重调整统计
    if _RATIOS_CONFIG and strategy_config.get('show_weight_adjustment_logs', False):
        print(f"\n⚖️  权重调整统计:")
        print(f"   总处理: {weight_stats['total_processed']} 个")
        print(f"   权重调整: {weight_stats['weighted_adjustments']} 个")
        print(f"   直接匹配: {weight_stats['original_matches_used']} 个")
        if weight_stats['total_processed'] > 0:
            adjustment_rate = weight_stats['weighted_adjustments'] / weight_stats['total_processed'] * 100
            print(f"   调整率: {adjustment_rate:.1f}%")

    # 显示子类别统计
    print(f"📊 子类别分布 (前10):")
    sorted_stats = sorted(subspecies_stats.items(), key=lambda x: x[1], reverse=True)
    for i, (subs, count) in enumerate(sorted_stats[:10], 1):
        # 显示权重信息
        weight_info = f""
        if subspecies_ratios and subs in subspecies_ratios:
            weight = subspecies_ratios[subs]
            if weight > 1.0:
                weight_info = f" (↑{weight:.1f}x)"
            elif weight < 1.0 and weight >= 0.5:
                weight_info = f" (↓{weight:.1f}x)"
            elif weight < 0.5:
                weight_info = f" (过滤阈值: {weight:.1f})"
        print(f"   {i:2d}. {subs:25s}: {count:3d} 个{weight_info}")

    # 优化质量配置
    quality_cfg = QualityConfig(
        min_question_len=3,
        min_answer_len=5,
        max_answer_len=8000,
        base_quality_floor=0.0,
        enable_self_consistency=False,
        enable_model_judge=False,
        max_dup_similarity=0.30,  # 使用默认30%相似度阈值
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
        rag_client=rag_client,  # 传递RAG客户端，支持并行模式下懒加载
        use_embedding_deduplication=True  # 默认开启Embedding去重
    )

    # 使用统一输出目录
    if unified_output_dir:
        output_dir = unified_output_dir
    else:
        output_dir = f'./output_{species_name.lower()}_{output_suffix}'

    batch_processor = BatchQAGenerator(
        generator,
        output_dir,
        target_species=species_name
    )

    print(f"🚀 开始生成 (每个种子{variants_per_seed}个变体)")
    start_time = time.time()

    try:
        result = await batch_processor.generate_from_seeds_async(
            seed_questions=seed_questions,
            variants_per_seed=variants_per_seed,
            batch_size=10,
            concurrent_batches=3,
            methods=[
                # 基础策略
                GenerationMethod.PARAPHRASE,
                GenerationMethod.ELABORATION,
                GenerationMethod.PERSPECTIVE_SHIFT,
                GenerationMethod.MULTI_TURN,
                # 差异性增强策略
                GenerationMethod.CROSS_SPECIES,
                GenerationMethod.REVERSE_REASONING,
                GenerationMethod.INNOVATIVE_APPLICATION,
                GenerationMethod.COMPARATIVE_ANALYSIS,
                GenerationMethod.FUTURE_SCENARIO,
                GenerationMethod.HYPOTHETICAL,
                GenerationMethod.COUNTERFACTUAL,
                GenerationMethod.META_QUESTION,
                # 时间/空间/学科等维度差异化策略
                GenerationMethod.TEMPORAL_SHIFT,
                GenerationMethod.SPATIAL_SHIFT,
                GenerationMethod.DISCIPLINE_CROSS,
                GenerationMethod.SCALE_CHANGE,
                GenerationMethod.TIME_SERIES,
                GenerationMethod.CAUSAL_CHAIN
            ],
            difficulty_level=difficulty_level
        )

        elapsed = time.time() - start_time

        # 统计信息
        stats = result['generation_stats']
        total_generated = stats['total_generated']
        success_count = stats['successful_generations']
        failure_count = stats['failed_generations']

        print(f"\n{'='*70}")
        print(f"✅ {species_name} 处理完成!")
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
            'species': species_name,
            'file_suffix': file_suffix,
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
        print(f"\n❌ {species_name}{file_suffix if file_suffix else ''} 处理失败:")
        print(f"错误: {str(e)}")
        import traceback
        traceback.print_exc()

        # 清理RAG客户端
        if rag_client:
            rag_client.close()

        return {
            'species': species_name,
            'file_suffix': file_suffix,
            'status': 'failed',
            'error': str(e),
            'seed_count': len(seed_questions),
            'total_generated': 0,
            'elapsed': elapsed
        }

async def process_all_species(
    input_dir,
    output_suffix="expanded",
    variants_per_seed=1,
    max_concurrent=3,
    use_rag=False,
    rag_url=None,
    rag_top_k=5,
    rag_data_source=None,
    rag_timeout=300,
    rag_enable_ratio=1.0,
    parallel_rag=True,
    difficulty_level=None
):
    """
    异步处理所有物种文件
    支持处理合并文件(*_合并.jsonl)、分割文件A(*_A.jsonl)和分割文件B(*_B.jsonl)

    Args:
        input_dir: 输入目录路径
        output_suffix: 输出目录后缀
        variants_per_seed: 每个种子生成的变体数
        max_concurrent: 最大并发物种数
        use_rag: 是否使用RAG增强
        rag_url: RAG服务URL
        rag_top_k: RAG检索文档数量
        rag_data_source: RAG数据源列表
        rag_timeout: RAG超时时间
        rag_enable_ratio: RAG启用比例
        parallel_rag: 是否并行处理RAG
        difficulty_level: 生成的QA对难度级别（easy/medium/hard）
    """
    input_path = Path(input_dir)

    if not input_path.exists():
        print(f"❌ 目录不存在: {input_dir}")
        return

    # 扫描目录下的所有jsonl和json文件
    jsonl_files = list(input_path.glob('*.jsonl'))
    json_files = list(input_path.glob('*.json'))
    all_files = jsonl_files + json_files
    all_files = sorted(list(all_files))

    if not all_files:
        print(f"❌ 目录中没有找到任何JSON/JSONL文件")
        print(f"目录内容: {list(input_path.iterdir())}")
        return

    print(f"\n{'='*70}")
    print(f"📁 扫描目录: {input_dir}")
    print(f"{'='*70}")
    print(f"找到 {len(all_files)} 个文件 (JSON: {len(json_files)}, JSONL: {len(jsonl_files)}):")
    for f in all_files:
        # 计算文件行数和大小
        try:
            with open(f, 'r', encoding='utf-8') as file:
                count = sum(1 for _ in file)
            size_mb = f.stat().st_size / (1024*1024)
            print(f"  - {f.name}: {count} 行, {size_mb:.1f} MB")
        except Exception as e:
            print(f"  - {f.name}: 无法读取 ({e})")

    print(f"\n🚀 开始异步处理 {len(all_files)} 个文件 (并发数: {max_concurrent})")
    print(f"{'='*70}\n")

    # 创建统一输出目录（带时间戳）
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    unified_output_dir = Path(f'./output/output_全部物种_expanded_{timestamp}')
    unified_output_dir.mkdir(parents=True, exist_ok=True)
    print(f"📁 统一输出目录: {unified_output_dir}")

    # 创建信号量限制并发数
    semaphore = asyncio.Semaphore(max_concurrent)

    async def process_with_semaphore(file_path):
        async with semaphore:
            # 提取物种名 - 支持任意文件名格式
            file_name = file_path.stem
            # 去掉常见的后缀，获取物种名
            # 支持：物种名_xxx, 物种名-xxx, 或直接是物种名

            # 方法：优先使用下划线分割
            # 如果文件名包含下划线，取第一部分
            if '_' in file_name:
                species_name = file_name.split('_')[0]
                file_suffix = file_name[len(species_name):]
            else:
                # 没有下划线，则整个文件名作为物种名
                species_name = file_name
                file_suffix = ''

            return await expand_single_species(
                species_name,
                str(file_path),
                output_suffix,
                variants_per_seed,
                unified_output_dir,
                file_suffix,
                use_rag,
                rag_url,
                rag_top_k,
                rag_data_source,
                rag_timeout,
                rag_enable_ratio,
                parallel_rag,
                difficulty_level
            )

    # 并发处理所有文件
    tasks = [process_with_semaphore(f) for f in all_files]
    results = await asyncio.gather(*tasks, return_exceptions=True)

    # 汇总结果
    print(f"\n{'='*70}")
    print(f"📊 所有物种处理完成汇总")
    print(f"{'='*70}\n")

    total_seeds = 0
    total_generated = 0
    total_success = 0
    total_failure = 0
    total_elapsed = 0

    for result in results:
        if isinstance(result, Exception):
            print(f"❌ 处理异常: {result}")
            continue

        species = result['species']
        file_suffix = result.get('file_suffix', '')
        status = result['status']

        if status == 'success':
            seeds = result['seed_count']
            generated = result['total_generated']
            success = result['success_count']
            failure = result['failure_count']
            elapsed = result['elapsed']
            rate = result['success_rate']

            file_suffix = result.get('file_suffix', '')
            species_display = f"{species}{file_suffix}" if file_suffix else species
            print(f"✅ {species_display:18s} | 种子: {seeds:4d} | 生成: {generated:4d} | 成功: {success:3d} | 失败: {failure:3d} | 耗时: {elapsed:6.1f}s | 速率: {rate:5.1f}%")

            total_seeds += seeds
            total_generated += generated
            total_success += success
            total_failure += failure
            total_elapsed = max(total_elapsed, elapsed)  # 取最大耗时作为总时间
        else:
            file_suffix = result.get('file_suffix', '')
            species_display = f"{species}{file_suffix}" if file_suffix else species
            print(f"❌ {species_display:18s} | 状态: 失败 | 错误: {result.get('error', 'Unknown')}")

    print(f"\n{'='*70}")
    print(f"🎯 总体统计:")
    print(f"{'='*70}")
    print(f"总文件数: {len(all_files)}")
    print(f"总种子数: {total_seeds}")
    print(f"总生成数: {total_generated}")
    print(f"总成功数: {total_success}")
    print(f"总失败数: {total_failure}")
    print(f"总耗时: {total_elapsed:.2f}秒")
    if total_seeds > 0:
        print(f"平均速率: {total_seeds/total_elapsed:.2f} 种子/秒")
    print(f"{'='*70}\n")

async def main():
    """主函数"""
    if len(sys.argv) < 2:
        print("使用方法: python run_expansion_from_dir.py <输入目录> [variants_per_seed] [max_concurrent] [--use-rag] [--rag-url URL] [--rag-top-k K] [--rag-data-source SOURCE] [--rag-timeout SECONDS] [--rag-enable-ratio RATIO] [--parallel-rag] [--no-parallel-rag] [--difficulty DIFFICULTY]")
        print("")
        print("参数说明:")
        print("  input_dir          : 输入目录路径（必需）")
        print("                     目录下的JSON/JSONL文件将被自动扫描和处理")
        print("                     支持格式: .json (JSON数组或单个对象) 和 .jsonl (每行一个JSON对象)")
        print("  variants_per_seed  : 每个种子生成的变体数（可选，默认1）")
        print("  max_concurrent     : 最大并发物种数（可选，默认3）")
        print("")
        print("权重配置:")
        print("  自动加载当前目录下的 generation_ratios_config.yaml 文件（可选）")
        print("  该文件控制物种和子类别的生成权重和策略")
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
        print("注意：并行模式现已支持立即加载RAG检索，可确保RAG文档正确保存")
        print("")
        print("难度参数:")
        print("  --difficulty DIFFICULTY : 生成的QA对难度级别（easy/medium/hard，可选，默认继承种子难度）")
        print("")
        print("示例:")
        print("  # 扫描目录下的所有JSON/JSONL文件")
        print("  python run_expansion_from_dir.py merged_species_qa")
        print("  python run_expansion_from_dir.py merged_species_qa 1 3")
        print("  # 结合RAG增强")
        print("  python run_expansion_from_dir.py merged_species_qa --use-rag")
        print("  python run_expansion_from_dir.py merged_species_qa --use-rag --rag-url http://localhost:9487/retrieve --rag-top-k 5")
        print("  python run_expansion_from_dir.py merged_species_qa --use-rag --rag-enable-ratio 0.3")
        print("  python run_expansion_from_dir.py merged_species_qa --use-rag --no-parallel-rag")
        print("  # 难度设置")
        print("  python run_expansion_from_dir.py merged_species_qa --difficulty medium")
        print("  python run_expansion_from_dir.py merged_species_qa --difficulty hard --use-rag")
        print("")
        print("权重配置文件示例 (generation_ratios_config.yaml):")
        print("  species_ratios:")
        print("    大豆: 1.2")
        print("    玉米: 0.8")
        print("  subspecies_ratios:")
        print("    育种技术: 2.0")
        print("    病虫害防治: 1.5")
        print("    基础理论问答: 0.5")
        print("  generation_strategy:")
        print("    enable_ratio_filtering: true")
        print("    enable_ratio_sorting: true")
        print("    min_weight_threshold: 0.5")
        sys.exit(1)

    # 解析基本参数（使用位置参数逻）
    input_dir = sys.argv[1]

    # 解析位置参数，考虑关键字参数可能插入其中
    variants_per_seed = 1
    max_concurrent = 3

    # 收集所有非关键字参数（跳过关键字参数及其值）
    positional_args = []
    skip_next = False
    for arg in sys.argv[2:]:
        if skip_next:
            skip_next = False
            continue

        if arg.startswith('--'):
            # 这是一个关键字参数，跳过它及其值（如果下一个参数不以'--'开头）
            skip_next = True
        else:
            positional_args.append(arg)

    # 根据位置分配参数
    if len(positional_args) >= 1:
        variants_per_seed = int(positional_args[0])
    if len(positional_args) >= 2:
        max_concurrent = int(positional_args[1])

    # 解析RAG参数
    use_rag = '--use-rag' in sys.argv
    rag_url = None
    rag_top_k = 5
    rag_data_source = None
    rag_timeout = 300
    rag_enable_ratio = 1.0
    parallel_rag = True  # 默认使用并行模式，现已支持立即加载RAG

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
    difficulty_level = None
    if '--difficulty' in sys.argv:
        idx = sys.argv.index('--difficulty')
        if idx + 1 < len(sys.argv):
            difficulty_level = sys.argv[idx + 1]
            # 验证难度值
            if difficulty_level not in ['easy', 'medium', 'hard']:
                print(f"❌ 错误: 难度值必须是 'easy', 'medium', 或 'hard'，收到: {difficulty_level}")
                sys.exit(1)

    # 检查输入目录
    if not Path(input_dir).exists():
        print(f"❌ 目录不存在: {input_dir}")
        sys.exit(1)

    # 加载比例配置文件
    print(f"{'='*70}")
    print(f"⚖️  加载生成比例配置")
    print(f"{'='*70}")

    global _RATIOS_CONFIG
    _RATIOS_CONFIG = load_ratios_config()

    # 显示配置状态
    if _RATIOS_CONFIG:
        print(f"✅ 比例配置加载成功")
    else:
        print(f"⚠️  未加载比例配置，将使用默认权重（全部为1.0）")

    # 加载 domain_task.xlsx 映射
    print(f"\n{'='*70}")
    print(f"📋 加载 domain_task.xlsx 子类别映射")
    print(f"{'='*70}")

    global _SUBSPECIES_MAPPING, _SPECIES_KEYWORDS
    _SUBSPECIES_MAPPING, _SPECIES_KEYWORDS = load_domain_task_mapping()

    if _SUBSPECIES_MAPPING:
        print(f"✅ 成功加载 {len(_SUBSPECIES_MAPPING)} 个关键词映射")
    else:
        print(f"⚠️  未找到有效的子类别映射，将使用原始分类")

    # 显示RAG状态
    if use_rag:
        print(f"\n{'='*70}")
        print(f"🔍 RAG增强已启用")
        print(f"{'='*70}")
        print(f"   URL: {rag_url or 'http://localhost:9487/retrieve'}")
        print(f"   Top-K: {rag_top_k}")
        print(f"   数据源: {rag_data_source or ['pubmed']}")
        print(f"   超时: {rag_timeout}秒")
        print(f"   启用比例: {rag_enable_ratio*100:.0f}%")
        print(f"   处理模式: {'并行模式（立即加载RAG检索）' if parallel_rag else '串行模式（预先增强所有种子）'}")
        if parallel_rag:
            print(f"   ✓ 并行模式现已支持立即加载RAG，确保RAG文档正确保存")

    await process_all_species(
        input_dir=input_dir,
        output_suffix="expanded",
        variants_per_seed=variants_per_seed,
        max_concurrent=max_concurrent,
        use_rag=use_rag,
        rag_url=rag_url,
        rag_top_k=rag_top_k,
        rag_data_source=rag_data_source,
        rag_timeout=rag_timeout,
        rag_enable_ratio=rag_enable_ratio,
        parallel_rag=parallel_rag,
        difficulty_level=difficulty_level
    )

if __name__ == '__main__':
    asyncio.run(main())
