import argparse
import json
import os
import sys
import logging
import time
import requests
from typing import List, Dict, Any, Optional
from pathlib import Path

# Add the project root to the Python path
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from src.core.qa_generator_v2 import DeepSeekGenerator, SeedQuestion, GeneratedQA, GenerationMethod, QualityConfig
from src.core.batch_processor import BatchQAGenerator
from config.config import GeneratorConfig, load_seed_questions_from_file, create_sample_seed_questions

# Set up logging configuration
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# ==== RAG 服务配置 ====
RAG_CONFIG = {
    'url': 'http://localhost:9487/retrieve',
    'headers': {
        'Content-Type': 'application/json'
    },
    'timeout': 300,  # 5分钟超时
    'max_retries': 3,
    'retry_delay': 2.0,
}

class RAGClient:
    """RAG 客户端，用于检索相关文档"""

    def __init__(self, config: Dict[str, Any] = None):
        self.config = config or RAG_CONFIG
        self.session = requests.Session()

        # 设置重试策略
        from requests.adapters import HTTPAdapter
        from urllib3.util.retry import Retry

        retry_strategy = Retry(
            total=self.config['max_retries'],
            connect=self.config['max_retries'],
            read=self.config['max_retries'],
            status_forcelist=[429, 500, 502, 503, 504],
            backoff_factor=1,
            allowed_methods=["HEAD", "GET", "OPTIONS", "POST"]
        )

        adapter = HTTPAdapter(max_retries=retry_strategy)
        self.session.mount("http://", adapter)
        self.session.mount("https://", adapter)

    def search(self, query: str, top_k: int = 5, data_source: List[str] = None) -> Optional[List[Dict]]:
        """
        搜索相关文档

        Args:
            query: 查询字符串
            top_k: 返回文档数量
            data_source: 数据源列表，默认使用 ['pubmed']

        Returns:
            文档列表，每个文档包含 title, abstract 等字段
        """
        if data_source is None:
            data_source = ['pubmed']

        payload = {
            "query": query,
            "top_k": top_k,
            "search_type": "keyword",
            "is_rewrite": True,
            "data_source": data_source,
            "user_id": "agri_sft_ds_user",
            "pubmed_topk": 10,
            "is_rerank": True,
            "language": "zh"
        }

        try:
            logger.info(f"调用 RAG 服务搜索: {query[:50]}...")
            start_time = time.time()

            response = self.session.post(
                self.config['url'],
                headers=self.config['headers'],
                json=payload,
                timeout=self.config['timeout']
            )

            response.raise_for_status()
            data = response.json()

            elapsed_time = time.time() - start_time
            logger.info(f"RAG 搜索完成，耗时: {elapsed_time:.2f}秒")

            if data.get('success') and 'data' in data:
                documents = data['data']
                logger.info(f"找到 {len(documents)} 篇相关文档")
                return documents
            else:
                logger.warning(f"RAG 搜索失败或无结果: {data.get('message', '未知错误')}")
                return []

        except requests.exceptions.Timeout:
            logger.error(f"RAG 搜索超时 (>{self.config['timeout']}秒)")
            return []
        except requests.exceptions.ConnectionError:
            logger.error("RAG 服务连接失败，请检查服务是否启动")
            return []
        except Exception as e:
            logger.error(f"RAG 搜索出错: {e}")
            return []

    def close(self):
        """关闭会话"""
        self.session.close()

def format_rag_context(documents: List[Dict], max_docs: int = 5) -> str:
    """
    将 RAG 检索结果格式化为上下文字符串

    Args:
        documents: RAG 检索的文档列表
        max_docs: 最大文档数量

    Returns:
        格式化的上下文字符串
    """
    if not documents:
        return ""

    context = "相关文献信息：\n\n"

    for i, doc in enumerate(documents[:max_docs], 1):
        title = doc.get('title', 'Unknown Title')
        abstract = doc.get('abstract', '') or doc.get('content', '') or doc.get('text', '')

        # 截断过长的摘要
        if len(abstract) > 800:
            abstract = abstract[:800] + "..."

        context += f"文献 {i}:\n"
        context += f"标题: {title}\n"
        context += f"摘要: {abstract}\n\n"

    return context

def generate_rag_enhanced_prompt(question: str, answer: str, rag_context: Optional[str] = None) -> str:
    """
    生成增强了RAG上下文的提示词
    用于从种子问答对扩增生成新的问答对
    让模型自动判断RAG内容是否与种子问答对相关，如果相关则使用，如果不相关则忽略

    Args:
        question: 种子问题
        answer: 种子答案
        rag_context: RAG检索的上下文

    Returns:
        增强后的提示词
    """
    if not rag_context:
        return f"种子问答对：\n问题：{question}\n答案：{answer}\n\n基于以上种子问答对，请生成10个新的问答对。"

    # 让模型自动判断RAG内容是否与种子问答对相关
    prompt = f"""请基于以下检索到的资料，从种子问答对扩增生成新的问答对。

检索到的相关资料：
{rag_context}

种子问答对：
问题：{question}
答案：{answer}

请首先判断资料内容是否与种子问答对相关：
- 如果资料内容与种子问答对属于同一领域、同一物种或同一主题（例如：都是关于油菜转基因、都是关于小麦育种、都是关于畜禽饲料等），则认为相关
- 如果资料内容与种子问答对完全无关（例如：种子问答对问油菜，资料却讲蜂蜜中的生物碱），则认为不相关

要求：
1. 如果相关：请基于种子问答对和检索资料中的信息，生成新的问答对。保持答案的科学性和准确性，适当引用资料中的关键信息
2. 如果不相关：请仅基于种子问答对的信息生成新的问答对，不使用检索资料
3. 无论是否使用资料，都不要在答案中标注"相关"或"不相关"
4. 生成的新问答对应该围绕种子问答对的主题进行扩展和深化

请生成新的问答对："""

    return prompt

def enhance_seeds_with_rag(seed_questions: List[SeedQuestion],
                          rag_client: Optional[RAGClient],
                          rag_top_k: int,
                          data_sources: List[str]) -> List[Dict[str, Any]]:
    """
    为种子问题添加 RAG 增强上下文

    Args:
        seed_questions: 种子问题列表
        rag_client: RAG 客户端
        rag_top_k: 检索文档数量
        data_sources: 数据源列表

    Returns:
        增强后的种子问题字典列表，包含 rag_context 字段
    """
    if not rag_client:
        logger.info("跳过 RAG 检索（未初始化 RAG 客户端）")
        return [{**seed.to_dict(), 'rag_context': '', 'rag_documents': []} for seed in seed_questions]

    logger.info(f"开始为 {len(seed_questions)} 个种子问题检索 RAG 文档...")

    enhanced_seeds = []
    rag_stats = {
        'total': len(seed_questions),
        'successful': 0,
        'failed': 0,
        'total_documents': 0
    }

    for i, seed in enumerate(seed_questions, 1):
        logger.info(f"[{i}/{len(seed_questions)}] 检索 RAG 文档: {seed.question[:50]}...")

        # 使用问题作为查询
        documents = rag_client.search(
            query=seed.question,
            top_k=rag_top_k,
            data_source=data_sources
        )

        if documents:
            rag_stats['successful'] += 1
            rag_stats['total_documents'] += len(documents)
            rag_context = format_rag_context(documents, max_docs=rag_top_k)
            logger.info(f"  找到 {len(documents)} 篇文档")
        else:
            rag_stats['failed'] += 1
            rag_context = ""
            logger.warning(f"  未找到相关文档")

        # 创建增强后的种子问题字典
        enhanced_seed = {
            **seed.to_dict(),
            'rag_context': rag_context,
            'rag_documents': documents if documents else []
        }
        enhanced_seeds.append(enhanced_seed)

    logger.info("RAG 检索完成:")
    logger.info(f"  总数: {rag_stats['total']}")
    logger.info(f"  成功: {rag_stats['successful']}")
    logger.info(f"  失败: {rag_stats['failed']}")
    logger.info(f"  总文档数: {rag_stats['total_documents']}")

    return enhanced_seeds

def generate_rag_enhanced_qa(generator: DeepSeekGenerator,
                           enhanced_seed: Dict[str, Any],
                           methods: List[GenerationMethod],
                           num_variants: int) -> List[GeneratedQA]:
    """
    基于 RAG 增强的种子问题生成 QA 对

    Args:
        generator: 生成器实例
        enhanced_seed: 增强后的种子问题字典，包含 rag_context
        methods: 生成方法列表
        num_variants: 变体数量

    Returns:
        生成的 QA 对列表
    """
    # 从增强种子中提取信息
    seed_question = enhanced_seed['question']
    seed_answer = enhanced_seed.get('answer', '')
    category = enhanced_seed.get('category', 'agriculture')
    difficulty = enhanced_seed.get('difficulty', 'medium')
    tags = enhanced_seed.get('tags', [])
    rag_context = enhanced_seed.get('rag_context', '')

    # 为每个生成方法生成 QA 对
    generated_qa_list = []

    for method in methods:
        try:
            # 基于 RAG 上下文生成增强的提示词
            enhanced_question = generate_rag_enhanced_prompt(seed_question, seed_answer, rag_context)

            # 调用生成器（这里需要修改 DeepSeekGenerator 来支持额外上下文）
            # 暂时使用标准生成，后续可以考虑扩展
            qa = generator.generate_single(
                question=enhanced_question,
                category=category,
                difficulty=difficulty,
                method=method,
                seed_question=seed_question,
                seed_answer=seed_answer
            )

            if qa:
                generated_qa_list.append(qa)

        except Exception as e:
            logger.error(f"生成 QA 失败 (方法: {method}): {e}")

    return generated_qa_list

def load_subspecies_mapping() -> Dict[str, list]:
    """
    从Excel文件加载子类别映射
    """
    import pandas as pd
    import os

    excel_file = os.path.join(os.path.dirname(__file__), "domain_task.xlsx")
    subspecies_keywords = {}

    if os.path.exists(excel_file):
        try:
            df = pd.read_excel(excel_file, sheet_name="domain_task")
            for _, row in df.iterrows():
                subspecies = row["subspecies"]
                keywords = [k.strip() for k in row["keywords"].split(",")]
                if subspecies not in subspecies_keywords:
                    subspecies_keywords[subspecies] = []
                subspecies_keywords[subspecies].extend(keywords)
            logger.info(f"从Excel文件加载了 {len(subspecies_keywords)} 个子类别映射")
        except Exception as e:
            logger.warning(f"读取Excel文件失败: {e}，使用默认映射")
    else:
        logger.warning(f"未找到Excel文件 {excel_file}")

    return subspecies_keywords


def extract_subspecies_from_seed(seed: SeedQuestion, subspecies_keywords: Dict[str, list]) -> str:
    """
    从种子问题中提取子类别
    优先从tags中提取，如果没有则从question中推断
    """
    # 优先从tags中查找子类别
    if seed.tags:
        tags_text = " ".join(seed.tags).lower()
        for subspecies, keywords in subspecies_keywords.items():
            if any(keyword.lower() in tags_text for keyword in keywords):
                return subspecies

    # 从问题文本中推断
    question_text = seed.question.lower()
    for subspecies, keywords in subspecies_keywords.items():
        if any(keyword.lower() in question_text for keyword in keywords):
            return subspecies

    # 如果没有匹配，返回空字符串
    return ""


def select_generation_methods(seed_questions: List[SeedQuestion], target_variants: int) -> List[GenerationMethod]:
    """
    根据Excel文件中的21个子类别智能选择生成策略
    """
    # 从Excel文件加载子类别映射
    subspecies_keywords = load_subspecies_mapping()

    # 统计各类别分布
    category_counts = {}
    subspecies_counts = {}
    subspecies_mapping = {}

    for i, seed in enumerate(seed_questions):
        category = seed.category if hasattr(seed, 'category') else 'unknown'
        category_counts[category] = category_counts.get(category, 0) + 1

        # 提取子类别
        subspecies = extract_subspecies_from_seed(seed, subspecies_keywords)
        subspecies_counts[subspecies] = subspecies_counts.get(subspecies, 0) + 1
        subspecies_mapping[i] = subspecies

    # 获取主要类别和子类别
    main_category = max(category_counts, key=category_counts.get) if category_counts else 'agriculture'
    main_subspecies = max(subspecies_counts, key=subspecies_counts.get) if subspecies_counts else ''

    logger.info(f"检测到主要类别: {main_category} (共{category_counts.get(main_category, 0)}个种子)")
    if main_subspecies:
        logger.info(f"检测到主要子类别: {main_subspecies} (共{subspecies_counts.get(main_subspecies, 0)}个种子)")

    # 根据Excel文件中的21个子类别选择策略
    method_strategies = {
        # 栽培类 - 强调实践应用和技术细节
        '栽培技术': [
            (GenerationMethod.SCENARIO_APPLICATION, 3),  # 场景应用 - 高权重
            (GenerationMethod.ELABORATION, 2),            # 详细阐述 - 高权重
            (GenerationMethod.PERSPECTIVE_SHIFT, 2),      # 视角转换 - 高权重
            (GenerationMethod.PARAPHRASE, 1),             # 同义改写 - 低权重
        ],

        # 病虫害防治 - 强调场景应用和实践
        '病虫害防治': [
            (GenerationMethod.SCENARIO_APPLICATION, 3),   # 场景应用 - 最高权重
            (GenerationMethod.ELABORATION, 2),            # 详细阐述 - 高权重
            (GenerationMethod.PERSPECTIVE_SHIFT, 2),      # 视角转换 - 高权重
            (GenerationMethod.PARAPHRASE, 1),             # 同义改写 - 低权重
        ],

        # 品种选育 - 强调不同视角和创新
        '品种选育': [
            (GenerationMethod.PERSPECTIVE_SHIFT, 3),      # 视角转换 - 最高权重
            (GenerationMethod.ELABORATION, 2),            # 详细阐述 - 高权重
            (GenerationMethod.DIFFICULTY_ADJUST, 2),      # 难度调整 - 高权重
            (GenerationMethod.SCENARIO_APPLICATION, 1),   # 场景应用 - 中等权重
        ],

        # 播种技术 - 强调精确操作和时机
        '播种技术': [
            (GenerationMethod.SCENARIO_APPLICATION, 3),   # 场景应用 - 最高权重
            (GenerationMethod.ELABORATION, 2),            # 详细阐述 - 高权重
            (GenerationMethod.PERSPECTIVE_SHIFT, 2),      # 视角转换 - 高权重
            (GenerationMethod.PARAPHRASE, 1),             # 同义改写 - 低权重
        ],

        # 田间管理 - 强调日常管理和实践
        '田间管理': [
            (GenerationMethod.SCENARIO_APPLICATION, 3),   # 场景应用 - 最高权重
            (GenerationMethod.ELABORATION, 2),            # 详细阐述 - 高权重
            (GenerationMethod.PERSPECTIVE_SHIFT, 2),      # 视角转换 - 高权重
            (GenerationMethod.PARAPHRASE, 1),             # 同义改写 - 低权重
        ],

        # 收获储存 - 强调时机和保存技术
        '收获储存': [
            (GenerationMethod.SCENARIO_APPLICATION, 3),   # 场景应用 - 最高权重
            (GenerationMethod.ELABORATION, 2),            # 详细阐述 - 高权重
            (GenerationMethod.PERSPECTIVE_SHIFT, 2),      # 视角转换 - 高权重
            (GenerationMethod.PARAPHRASE, 1),             # 同义改写 - 低权重
        ],

        # 养殖技术 - 强调饲养管理和环境
        '养殖技术': [
            (GenerationMethod.SCENARIO_APPLICATION, 3),   # 场景应用 - 最高权重
            (GenerationMethod.ELABORATION, 2),            # 详细阐述 - 高权重
            (GenerationMethod.PERSPECTIVE_SHIFT, 2),      # 视角转换 - 高权重
            (GenerationMethod.PARAPHRASE, 1),             # 同义改写 - 低权重
        ],

        # 饲料管理 - 强调营养和转化效率
        '饲料管理': [
            (GenerationMethod.ELABORATION, 3),            # 详细阐述 - 最高权重
            (GenerationMethod.SCENARIO_APPLICATION, 2),   # 场景应用 - 高权重
            (GenerationMethod.PERSPECTIVE_SHIFT, 2),      # 视角转换 - 高权重
            (GenerationMethod.PARAPHRASE, 1),             # 同义改写 - 低权重
        ],

        # 环境控制 - 强调技术参数和控制
        '环境控制': [
            (GenerationMethod.ELABORATION, 3),            # 详细阐述 - 最高权重
            (GenerationMethod.SCENARIO_APPLICATION, 2),   # 场景应用 - 高权重
            (GenerationMethod.PERSPECTIVE_SHIFT, 2),      # 视角转换 - 高权重
            (GenerationMethod.PARAPHRASE, 1),             # 同义改写 - 低权重
        ],

        # 疫病防控 - 强调预防和应急处理
        '疫病防控': [
            (GenerationMethod.SCENARIO_APPLICATION, 3),   # 场景应用 - 最高权重
            (GenerationMethod.ELABORATION, 2),            # 详细阐述 - 高权重
            (GenerationMethod.PERSPECTIVE_SHIFT, 2),      # 视角转换 - 高权重
            (GenerationMethod.PARAPHRASE, 1),             # 同义改写 - 低权重
        ],

        # 育苗技术 - 强调精细管理和技术细节
        '育苗技术': [
            (GenerationMethod.SCENARIO_APPLICATION, 3),   # 场景应用 - 最高权重
            (GenerationMethod.ELABORATION, 2),            # 详细阐述 - 高权重
            (GenerationMethod.PERSPECTIVE_SHIFT, 2),      # 视角转换 - 高权重
            (GenerationMethod.PARAPHRASE, 1),             # 同义改写 - 低权重
        ],

        # 移栽技术 - 强调时机和技术要点
        '移栽技术': [
            (GenerationMethod.SCENARIO_APPLICATION, 3),   # 场景应用 - 最高权重
            (GenerationMethod.ELABORATION, 2),            # 详细阐述 - 高权重
            (GenerationMethod.PERSPECTIVE_SHIFT, 2),      # 视角转换 - 高权重
            (GenerationMethod.PARAPHRASE, 1),             # 同义改写 - 低权重
        ],

        # 水肥管理 - 强调精准调控
        '水肥管理': [
            (GenerationMethod.ELABORATION, 3),            # 详细阐述 - 最高权重
            (GenerationMethod.SCENARIO_APPLICATION, 2),   # 场景应用 - 高权重
            (GenerationMethod.PERSPECTIVE_SHIFT, 2),      # 视角转换 - 高权重
            (GenerationMethod.PARAPHRASE, 1),             # 同义改写 - 低权重
        ],

        # 采收技术 - 强调时机和方法
        '采收技术': [
            (GenerationMethod.SCENARIO_APPLICATION, 3),   # 场景应用 - 最高权重
            (GenerationMethod.ELABORATION, 2),            # 详细阐述 - 高权重
            (GenerationMethod.PERSPECTIVE_SHIFT, 2),      # 视角转换 - 高权重
            (GenerationMethod.PARAPHRASE, 1),             # 同义改写 - 低权重
        ],

        # 种植技术 - 强调综合技术
        '种植技术': [
            (GenerationMethod.SCENARIO_APPLICATION, 3),   # 场景应用 - 最高权重
            (GenerationMethod.ELABORATION, 2),            # 详细阐述 - 高权重
            (GenerationMethod.PERSPECTIVE_SHIFT, 2),      # 视角转换 - 高权重
            (GenerationMethod.PARAPHRASE, 1),             # 同义改写 - 低权重
        ],

        # 砍收技术 - 强调时机和效率
        '砍收技术': [
            (GenerationMethod.SCENARIO_APPLICATION, 3),   # 场景应用 - 最高权重
            (GenerationMethod.ELABORATION, 2),            # 详细阐述 - 高权重
            (GenerationMethod.PERSPECTIVE_SHIFT, 2),      # 视角转换 - 高权重
            (GenerationMethod.PARAPHRASE, 1),             # 同义改写 - 低权重
        ],

        # 设施栽培 - 强调技术参数和管理
        '设施栽培': [
            (GenerationMethod.ELABORATION, 3),            # 详细阐述 - 最高权重
            (GenerationMethod.SCENARIO_APPLICATION, 2),   # 场景应用 - 高权重
            (GenerationMethod.PERSPECTIVE_SHIFT, 2),      # 视角转换 - 高权重
            (GenerationMethod.PARAPHRASE, 1),             # 同义改写 - 低权重
        ],

        # 修剪技术 - 强调艺术和技术
        '修剪技术': [
            (GenerationMethod.SCENARIO_APPLICATION, 3),   # 场景应用 - 最高权重
            (GenerationMethod.ELABORATION, 2),            # 详细阐述 - 高权重
            (GenerationMethod.PERSPECTIVE_SHIFT, 2),      # 视角转换 - 高权重
            (GenerationMethod.PARAPHRASE, 1),             # 同义改写 - 低权重
        ],

        # 采摘技术 - 强调时机和方法
        '采摘技术': [
            (GenerationMethod.SCENARIO_APPLICATION, 3),   # 场景应用 - 最高权重
            (GenerationMethod.ELABORATION, 2),            # 详细阐述 - 高权重
            (GenerationMethod.PERSPECTIVE_SHIFT, 2),      # 视角转换 - 高权重
            (GenerationMethod.PARAPHRASE, 1),             # 同义改写 - 低权重
        ],

        # 加工技术 - 强调工艺和品质
        '加工技术': [
            (GenerationMethod.ELABORATION, 3),            # 详细阐述 - 最高权重
            (GenerationMethod.SCENARIO_APPLICATION, 2),   # 场景应用 - 高权重
            (GenerationMethod.PERSPECTIVE_SHIFT, 2),      # 视角转换 - 高权重
            (GenerationMethod.PARAPHRASE, 1),             # 同义改写 - 低权重
        ],

        # 加工炮制 - 强调传统工艺和现代技术
        '加工炮制': [
            (GenerationMethod.ELABORATION, 3),            # 详细阐述 - 最高权重
            (GenerationMethod.PERSPECTIVE_SHIFT, 2),      # 视角转换 - 高权重
            (GenerationMethod.SCENARIO_APPLICATION, 2),   # 场景应用 - 高权重
            (GenerationMethod.PARAPHRASE, 1),             # 同义改写 - 低权重
        ],

        # 通用农业策略 - 未匹配到特定子类别时使用
        'agriculture': [
            (GenerationMethod.SCENARIO_APPLICATION, 3),
            (GenerationMethod.ELABORATION, 2),
            (GenerationMethod.PERSPECTIVE_SHIFT, 2),
            (GenerationMethod.PARAPHRASE, 1),
        ],

        # 核心知识问答类 - 知识密度高，强调深度
        '核心知识问答': [
            (GenerationMethod.ELABORATION, 3),            # 详细阐述 - 高权重
            (GenerationMethod.PERSPECTIVE_SHIFT, 2),      # 视角转换 - 高权重
            (GenerationMethod.DIFFICULTY_ADJUST, 2),      # 难度调整 - 高权重
            (GenerationMethod.SCENARIO_APPLICATION, 2),   # 场景应用 - 中等权重
            (GenerationMethod.PARAPHRASE, 1),             # 同义改写 - 低权重
        ],
        '核心知识问答类语料': [
            (GenerationMethod.ELABORATION, 3),
            (GenerationMethod.PERSPECTIVE_SHIFT, 2),
            (GenerationMethod.DIFFICULTY_ADJUST, 2),
            (GenerationMethod.SCENARIO_APPLICATION, 2),
            (GenerationMethod.PARAPHRASE, 1),
        ],

        # 场景化任务与指令遵循类 - 强调实际应用
        '场景化任务与指令遵循类语料': [
            (GenerationMethod.SCENARIO_APPLICATION, 3),   # 场景应用 - 最高权重
            (GenerationMethod.ELABORATION, 2),            # 详细阐述 - 高权重
            (GenerationMethod.PERSPECTIVE_SHIFT, 2),      # 视角转换 - 高权重
            (GenerationMethod.PARAPHRASE, 1),             # 同义改写 - 低权重
        ],

        # 默认策略 - 优化权重分配，提升高质量策略
        'default': [
            (GenerationMethod.ELABORATION, 3),            # 详细阐述 - 最高权重
            (GenerationMethod.PERSPECTIVE_SHIFT, 3),      # 视角转换 - 最高权重
            (GenerationMethod.SCENARIO_APPLICATION, 2),   # 场景应用 - 高权重
            (GenerationMethod.DIFFICULTY_ADJUST, 2),      # 难度调整 - 高权重
            (GenerationMethod.PARAPHRASE, 1),             # 同义改写 - 低权重
        ],
    }

    # 优先选择子类别策略，如果没有则选择类别策略
    strategies = None
    if main_subspecies and main_subspecies in method_strategies:
        strategies = method_strategies[main_subspecies]
        logger.info(f"使用子类别策略: {main_subspecies}")
    else:
        strategies = method_strategies.get(main_category, method_strategies['default'])
        logger.info(f"使用类别策略: {main_category}")

    # 计算实际变体数
    total_variants = sum(count for _, count in strategies)

    # 如果目标变体数大于总变体数，则调整每个策略的配额
    if target_variants > total_variants:
        # 按比例增加
        scale = target_variants / total_variants
        adjusted = []
        for method, count in strategies:
            new_count = max(1, int(count * scale))
            adjusted.append((method, new_count))
        strategies = adjusted

    # 生成最终的方法列表
    methods = []
    for method, count in strategies:
        methods.extend([method] * count)

    # 截断到目标数量
    methods = methods[:target_variants]

    logger.info(f"选择生成策略:")
    logger.info(f"  类别: {main_category}, 子类别: {main_subspecies}")
    for method in set(methods):
        count = methods.count(method)
        logger.info(f"  - {method.value}: {count}个变体")

    return methods


def main():
    # Argument parser for command-line options
    parser = argparse.ArgumentParser(description='基于种子问题的QA对生成系统 - 支持RAG增强')
    parser.add_argument('--config', type=str, help='配置文件路径')
    parser.add_argument('--seeds', type=str, help='种子问题文件路径')
    parser.add_argument('--output', type=str, default='output', help='输出目录')
    parser.add_argument('--variants', type=int, default=3, help='每个种子的变体数量')
    parser.add_argument('--batch-size', type=int, default=5, help='批处理大小')
    parser.add_argument('--species-ratios', type=str, help='物种比例JSON字符串，例如: \'{"玉米":0.4,"小麦":0.3,"畜禽":0.3}\'')
    parser.add_argument('--subspecies-ratios', type=str, help='子类别比例JSON字符串，例如: \'{"玉米":{"栽培技术":0.5,"病虫害防治":0.3,"品种选育":0.2}}\'')

    # RAG 参数
    parser.add_argument('--use-rag', action='store_true', help='启用RAG检索增强')
    parser.add_argument('--rag-url', type=str, default='http://localhost:9487/retrieve', help='RAG服务URL')
    parser.add_argument('--rag-top-k', type=int, default=5, help='RAG检索返回文档数量')
    parser.add_argument('--rag-data-source', type=str, default='pubmed', help='RAG数据源 (逗号分隔，如: pubmed,web)')
    parser.add_argument('--rag-timeout', type=int, default=300, help='RAG请求超时时间(秒)')

    # OpenAI API参数
    parser.add_argument('--model', type=str, default='gpt-5.1', help='模型名称')
    parser.add_argument('--api-base', type=str, help='API基础URL')
    parser.add_argument('--api-key', type=str, help='API密钥')

    args = parser.parse_args()

    # 解析物种比例参数
    species_ratios = None
    if args.species_ratios:
        try:
            import json
            species_ratios = json.loads(args.species_ratios)
            logger.info(f"使用物种比例控制: {species_ratios}")
        except json.JSONDecodeError as e:
            logger.error(f"物种比例JSON格式错误: {e}")
            species_ratios = None

    # 解析子类别比例参数
    subspecies_ratios = None
    if args.subspecies_ratios:
        try:
            import json
            subspecies_ratios = json.loads(args.subspecies_ratios)
            logger.info(f"使用子类别比例控制: {subspecies_ratios}")
        except json.JSONDecodeError as e:
            logger.error(f"子类别比例JSON格式错误: {e}")
            subspecies_ratios = None

    # 初始化 RAG 客户端
    rag_client = None
    if args.use_rag:
        logger.info("初始化 RAG 客户端...")
        rag_config = RAG_CONFIG.copy()
        rag_config['url'] = args.rag_url
        rag_config['timeout'] = args.rag_timeout

        # 解析数据源
        data_sources = [s.strip() for s in args.rag_data_source.split(',')]
        logger.info(f"RAG 数据源: {data_sources}")
        logger.info(f"RAG 检索数量: {args.rag_top_k}")
        logger.info(f"RAG 超时时间: {args.rag_timeout}秒")

        rag_client = RAGClient(config=rag_config)
        logger.info("RAG 客户端初始化完成")
    else:
        logger.info("未启用 RAG 检索增强")

    # 加载配置
    if args.config and os.path.exists(args.config):
        config = GeneratorConfig.from_yaml(args.config)
    else:
        config = GeneratorConfig(
            model_name=args.model,
            api_base=args.api_base,
            api_key=args.api_key,
            default_variants_per_seed=args.variants,
            default_batch_size=args.batch_size
        )

    # 加载种子问题
    if args.seeds and os.path.exists(args.seeds):
        seed_data = load_seed_questions_from_file(args.seeds)
    else:
        logger.info("未提供种子问题文件，使用示例数据...")
        seed_data = create_sample_seed_questions()

    seed_questions = []
    for data in seed_data:
        # 过滤掉种子问题不需要的字段
        filtered_data = {
            'question': data.get('question', ''),
            'answer': data.get('answer', ''),
            'category': data.get('metadata', {}).get('主分类', data.get('category', 'agriculture')),
            'species': data.get('metadata', {}).get('物种', data.get('species', 'unknown')),
            'difficulty': data.get('difficulty', 'medium'),
            'tags': data.get('tags', data.get('metadata', {}).get('亚类', '').split('/') if data.get('metadata', {}).get('亚类') else []),
            'source': 'agriculture_corpus'
        }
        seed_questions.append(SeedQuestion(**filtered_data))

    logger.info(f"加载了 {len(seed_questions)} 个种子问题")
    logger.info(f"使用模型: {config.model_name}")
    logger.info(f"使用方式: API")

    # 创建质量配置（平衡通过率和多样性）
    quality_cfg = QualityConfig(
        min_question_len=5,        # 基本要求
        min_answer_len=20,         # 基本要求
        max_answer_len=8000,       # 增加上限（API支持8000 tokens）
        base_quality_floor=0.01,   # 基础质量门槛
        enable_self_consistency=False,  # 关闭自一致性检查
        enable_model_judge=False,       # 关闭模型裁判
        self_consistency_weight=0.0,    # 权重设为0
        judge_weight=0.0,               # 权重设为0
        max_regen_rounds=1,             # 允许1次重试，给其他策略更多机会
        max_dup_similarity=0.65         # 适度相似度阈值，让不同策略都能通过
    )

    generator_kwargs = config.to_generator_kwargs()
    generator = DeepSeekGenerator(quality_cfg=quality_cfg, **generator_kwargs)

    # 初始化批量处理器
    batch_processor = BatchQAGenerator(generator, output_dir=args.output)

    # 根据种子问题类别自适应选择生成策略
    methods = select_generation_methods(seed_questions, config.default_variants_per_seed)

    # 解析RAG数据源
    data_sources = [s.strip() for s in args.rag_data_source.split(',')]

    # 增强种子问题（如果启用RAG）
    enhanced_seeds = enhance_seeds_with_rag(
        seed_questions=seed_questions,
        rag_client=rag_client,
        rag_top_k=args.rag_top_k,
        data_sources=data_sources
    )

    logger.info("开始生成QA对...")

    try:
        # 执行批量生成（传递增强后的种子）
        result = batch_processor.generate_from_seeds(
            seed_questions=seed_questions,  # 原始种子问题，保持向后兼容
            enhanced_seeds=enhanced_seeds,  # 增强后的种子，包含RAG上下文
            variants_per_seed=config.default_variants_per_seed,
            methods=methods,
            batch_size=config.default_batch_size,
            species_ratios=species_ratios,
            subspecies_ratios=subspecies_ratios
        )

        # 输出摘要报告
        logger.info("\n" + "=" * 50)
        logger.info("生成完成！摘要报告:")
        logger.info("=" * 50)

        stats = result["generation_stats"]
        diversity = result["diversity_report"]
        quality = result["quality_report"]

        logger.info(f"种子问题总数: {stats['total_seeds']}")
        logger.info(f"成功生成: {stats['successful_generations']}")
        logger.info(f"生成失败: {stats['failed_generations']}")
        logger.info(f"总QA对数量: {stats['total_generated']} (过滤前: {stats.get('total_generated_before_filter', 'N/A')})")
        logger.info(f"质量通过率: {quality['pass_rate']}")
        logger.info(f"多样性分数: {diversity.get('diversity_score', 'N/A')}")

        if stats['by_category']:
            logger.info(f"\n类别分布:")
            for category, count in stats['by_category'].items():
                logger.info(f"  {category}: {count}")

        if stats['by_method']:
            logger.info(f"\n生成方法分布:")
            for method, count in stats['by_method'].items():
                logger.info(f"  {method}: {count}")

        if quality.get('common_issues'):
            logger.info(f"\n常见质量问题:")
            for issue, count in quality['common_issues'].items():
                logger.info(f"  {issue}: {count}")

        logger.info(f"\n输出文件保存在: {args.output}")
        logger.info("=" * 50)

    except Exception as e:
        logger.error(f"生成过程中出现错误: {e}")
        import traceback
        traceback.print_exc()
    finally:
        # 清理资源
        if rag_client:
            logger.info("关闭 RAG 客户端...")
            rag_client.close()
            logger.info("RAG 客户端已关闭")
        # 无需清理GPU内存（API模式）

if __name__ == "__main__":
    main()
