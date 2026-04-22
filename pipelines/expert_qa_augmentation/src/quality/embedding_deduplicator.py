#!/usr/bin/env python3
"""
Embedding去重器 - 基于预训练多语言模型
用于基于向量相似度的QA对去重
"""
from typing import List, Dict, Any, Optional, Union
import numpy as np
import logging
from dataclasses import dataclass
from sentence_transformers import SentenceTransformer
from sklearn.metrics.pairwise import cosine_similarity
import torch

logger = logging.getLogger(__name__)


@dataclass
class QAItem:
    """QA项目结构"""
    question: str
    answer: str
    metadata: Optional[Dict[str, Any]] = None


class EmbeddingDeduplicator:
    """基于预训练多语言模型的Embedding去重器"""

    def __init__(
        self,
        threshold: float = 0.30,
        model_name: str = "paraphrase-multilingual-MiniLM-L12-v2",
        device: Optional[str] = None,
        cache_size: int = 1000
    ):
        """
        初始化去重器

        Args:
            threshold: 相似度阈值，超过此阈值认为是重复
            model_name: 预训练模型名称
                推荐模型:
                - paraphrase-multilingual-MiniLM-L12-v2: 多语言支持，推荐
                - multilingual-E5-base: 多语言支持，性能更好但占用内存更多
                - all-MiniLM-L6-v2: 仅英语，但性能优秀
            device: 计算设备，'cuda' 或 'cpu'，默认自动选择
            cache_size: embedding缓存大小，用于提升重复文本的查询速度
        """
        self.threshold = threshold
        self.items: List[QAItem] = []
        self.cache_size = cache_size
        self._embedding_cache: Dict[str, np.ndarray] = {}

        # 选择计算设备
        if device is None:
            self.device = 'cuda' if torch.cuda.is_available() else 'cpu'
        else:
            self.device = device

        # 加载预训练模型
        logger.info(f"正在加载模型: {model_name}，设备: {self.device}")
        try:
            self.model = SentenceTransformer(model_name, device=self.device)
            logger.info("模型加载成功")
        except Exception as e:
            logger.error(f"模型加载失败: {e}")
            raise

        logger.info(f"初始化Embedding去重器完成，阈值: {threshold}")

    def add_item(self, question: str, answer: str, metadata: Optional[Dict] = None) -> bool:
        """
        添加QA项

        Args:
            question: 问题
            answer: 答案
            metadata: 元数据

        Returns:
            bool: 是否为重复项
        """
        new_item = QAItem(question=question, answer=answer, metadata=metadata)

        # 基于embedding的去重检查
        for existing_item in self.items:
            # 计算问题和答案的相似度
            question_sim = self._calculate_similarity(question, existing_item.question)
            answer_sim = self._calculate_similarity(answer, existing_item.answer)

            # 如果问题和答案都很相似，认为是重复
            if question_sim > self.threshold and answer_sim > self.threshold:
                logger.debug(f"发现重复项: {question[:50]}...")
                return True

        # 不是重复项，添加到列表
        self.items.append(new_item)
        return False

    def _get_embedding(self, text: str) -> np.ndarray:
        """
        获取文本的embedding向量

        Args:
            text: 输入文本

        Returns:
            np.ndarray: embedding向量
        """
        # 先检查缓存
        text_key = text.strip()
        if text_key in self._embedding_cache:
            return self._embedding_cache[text_key]

        # 计算embedding
        embedding = self.model.encode(text_key, convert_to_numpy=True)

        # 缓存embedding（如果缓存未满）
        if len(self._embedding_cache) < self.cache_size:
            self._embedding_cache[text_key] = embedding

        return embedding

    def _calculate_similarity(self, text1: str, text2: str) -> float:
        """
        使用预训练模型计算两个文本的余弦相似度

        Args:
            text1: 文本1
            text2: 文本2

        Returns:
            float: 余弦相似度分数 (0-1，1表示完全相似)
        """
        # 处理空文本
        if not text1.strip() or not text2.strip():
            return 0.0

        # 获取两个文本的embedding
        embedding1 = self._get_embedding(text1)
        embedding2 = self._get_embedding(text2)

        # 确保embedding是一维的
        if embedding1.ndim > 1:
            embedding1 = embedding1[0]
        if embedding2.ndim > 1:
            embedding2 = embedding2[0]

        # 计算余弦相似度
        similarity = cosine_similarity(
            embedding1.reshape(1, -1),
            embedding2.reshape(1, -1)
        )[0][0]

        # 确保相似度在[0, 1]范围内
        return max(0.0, min(1.0, float(similarity)))

    def clear(self):
        """清空所有项"""
        self.items.clear()
        self._embedding_cache.clear()
        logger.info("清空去重器和缓存")

    def add_items_batch(
        self,
        qa_pairs: List[tuple],
        metadata_list: Optional[List[Dict]] = None,
        show_progress: bool = True
    ) -> Dict[str, int]:
        """
        批量添加QA项

        Args:
            qa_pairs: QA对列表，格式为 [(question, answer), ...]
            metadata_list: 元数据列表
            show_progress: 是否显示进度

        Returns:
            Dict[str, int]: 统计信息 {'total': 总数, 'duplicates': 重复数, 'unique': 唯一数}
        """
        total = len(qa_pairs)
        duplicates = 0
        unique = 0

        if metadata_list is None:
            metadata_list = [None] * total

        logger.info(f"开始批量添加 {total} 个QA对")

        for idx, (question, answer) in enumerate(qa_pairs):
            is_duplicate = self.add_item(question, answer, metadata_list[idx])

            if is_duplicate:
                duplicates += 1
            else:
                unique += 1

            if show_progress and (idx + 1) % 100 == 0:
                logger.info(f"已处理 {idx + 1}/{total}")

        logger.info(
            f"批量添加完成 - 总数: {total}, 重复: {duplicates}, 唯一: {unique}"
        )

        return {
            'total': total,
            'duplicates': duplicates,
            'unique': unique
        }

    def get_embedding_dim(self) -> int:
        """
        获取embedding维度

        Returns:
            int: embedding向量维度
        """
        # 使用一个简单的文本获取embedding维度
        test_embedding = self._get_embedding("测试")
        return test_embedding.shape[0]

    def get_stats(self) -> Dict[str, Any]:
        """
        获取去重器统计信息

        Returns:
            Dict[str, Any]: 统计信息
        """
        return {
            'total_items': len(self.items),
            'threshold': self.threshold,
            'model_name': str(self.model),
            'embedding_dim': self.get_embedding_dim(),
            'cache_size': len(self._embedding_cache),
            'cache_capacity': self.cache_size,
            'device': self.device,
        }

    def find_similar_items(
        self,
        question: str,
        answer: str,
        top_k: int = 5
    ) -> List[Dict[str, Any]]:
        """
        查找相似的QA项

        Args:
            question: 问题
            answer: 答案
            top_k: 返回最相似的k个结果

        Returns:
            List[Dict]: 相似项列表，每个元素包含 {'item': QAItem, 'similarity': float}
        """
        results = []

        for item in self.items:
            question_sim = self._calculate_similarity(question, item.question)
            answer_sim = self._calculate_similarity(answer, item.answer)

            # 计算综合相似度（问题和答案相似度的平均值）
            avg_similarity = (question_sim + answer_sim) / 2

            results.append({
                'item': item,
                'similarity': avg_similarity,
                'question_similarity': question_sim,
                'answer_similarity': answer_sim
            })

        # 按相似度排序并返回top_k
        results.sort(key=lambda x: x['similarity'], reverse=True)
        return results[:top_k]


# 全局去重器实例
_global_deduplicator = None


def get_global_deduplicator(
    threshold: float = 0.30,
    model_name: str = "paraphrase-multilingual-MiniLM-L12-v2",
    device: Optional[str] = None,
    cache_size: int = 1000
) -> EmbeddingDeduplicator:
    """
    获取全局去重器实例

    Args:
        threshold: 相似度阈值
        model_name: 预训练模型名称
        device: 计算设备
        cache_size: embedding缓存大小

    Returns:
        EmbeddingDeduplicator: 全局去重器实例
    """
    global _global_deduplicator
    if _global_deduplicator is None:
        _global_deduplicator = EmbeddingDeduplicator(
            threshold=threshold,
            model_name=model_name,
            device=device,
            cache_size=cache_size
        )
    return _global_deduplicator


# QA组合器 - 用于将QA对组合后进行去重
QA_COMBINERS = {
    'concat': lambda q, a: f"{q}|||{a}",
    'question_first': lambda q, a: f"{q} [SEP] {a}",
    'answer_first': lambda q, a: f"{a} [SEP] {q}",
}


# 使用示例
if __name__ == "__main__":
    # 配置日志
    logging.basicConfig(level=logging.INFO)

    # 创建去重器实例
    deduplicator = EmbeddingDeduplicator(
        threshold=0.30,
        model_name="paraphrase-multilingual-MiniLM-L12-v2",
        cache_size=1000
    )

    # 单个添加示例
    qa_pairs = [
        ("什么是机器学习？", "机器学习是人工智能的一个分支。", None),
        ("机器学习是什么？", "机器学习是AI的一个分支领域。", None),  # 这个很相似，会被识别为重复
        ("什么是深度学习？", "深度学习是机器学习的一个子集。", None),
    ]

    for question, answer, metadata in qa_pairs:
        is_dup = deduplicator.add_item(question, answer, metadata)
        print(f"问题: {question}")
        print(f"是否为重复: {is_dup}\n")

    # 批量添加示例
    batch_qa = [
        ("什么是神经网络？", "神经网络是模拟人脑结构的计算模型。", None),
        ("神经网络是什么？", "神经网络是模仿人脑的计算模型。", None),  # 重复
    ]

    stats = deduplicator.add_items_batch(batch_qa)
    print(f"批量添加统计: {stats}\n")

    # 获取统计信息
    print("去重器统计信息:")
    for key, value in deduplicator.get_stats().items():
        print(f"  {key}: {value}")

    # 查找相似项
    print("\n查找相似项:")
    similar = deduplicator.find_similar_items(
        "机器学习是什么？",
        "机器学习是人工智能领域的一个分支。",
        top_k=3
    )
    for idx, result in enumerate(similar, 1):
        print(f"{idx}. 相似度: {result['similarity']:.4f}")
        print(f"   问题: {result['item'].question}")
        print(f"   答案: {result['item'].answer}\n")
