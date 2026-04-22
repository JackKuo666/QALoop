"""
BioBERT分类器模块
实现农业内容分类功能
"""
import torch
import torch.nn.functional as F
from transformers import AutoTokenizer, AutoModelForSequenceClassification
from typing import Dict, List, Tuple, Optional
import logging
import re
from dataclasses import dataclass

@dataclass
class DocumentInfo:
    """文档信息结构"""
    id: str
    text: str
    title: Optional[str] = None
    url: Optional[str] = None
    source: Optional[str] = None
    language: Optional[str] = None
    file_path: Optional[str] = None
    char_length: int = 0
    estimated_tokens: int = 0

@dataclass
class ClassificationResult:
    """分类结果结构"""
    is_agricultural: int  # 0=非农业, 1=农业
    confidence: float     # 置信度
    probability: float    # 农业概率
    processing_details: Dict

class BioBERTClassifier:
    """BioBERT农业内容分类器"""

    def __init__(self, model_path: str, tokenizer_name: str = "dmis-lab/biobert-base-cased-v1.1",
                 threshold: float = 0.6, device: str = "auto"):
        self.model_path = model_path
        self.tokenizer_name = tokenizer_name
        self.threshold = threshold
        self.logger = logging.getLogger(__name__)

        # 设备选择
        if device == "auto":
            self.device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
        else:
            self.device = torch.device(device)

        self.logger.info(f"使用设备: {self.device}")

        # 加载模型和tokenizer
        self._load_model()

    def _load_model(self):
        """加载模型和tokenizer"""
        try:
            self.logger.info("加载tokenizer...")
            self.tokenizer = AutoTokenizer.from_pretrained(self.tokenizer_name)

            self.logger.info("加载模型架构...")
            self.model = AutoModelForSequenceClassification.from_pretrained(self.tokenizer_name)

            self.logger.info("加载自定义权重...")
            checkpoint = torch.load(self.model_path, map_location=self.device)
            self.model.load_state_dict(checkpoint)

            self.model.to(self.device)
            self.model.eval()

            self.logger.info("✓ 模型加载完成")

        except Exception as e:
            self.logger.error(f"模型加载失败: {e}")
            raise

    def _extract_key_sections(self, text: str, max_length: int = 512) -> List[str]:
        """提取文档的关键章节"""
        sections = []

        # 1. 文档开头（最重要）
        sections.append(text[:max_length])

        # 2. 查找农业相关的关键词段落
        agriculture_keywords = [
            'farm', 'agriculture', 'crop', 'crops', 'harvest', 'planting',
            'soil', 'irrigation', 'fertilizer', 'pesticide', 'livestock',
            'cattle', 'farming', 'agricultural', 'cultivation', 'yield',
            '农', '农业', '作物', '收获', '种植', '土壤', '灌溉', '施肥'
        ]

        # 分割文本为段落
        paragraphs = [p.strip() for p in text.split('\n') if p.strip()]

        # 查找包含农业关键词的段落
        agri_paragraphs = []
        for para in paragraphs:
            if any(keyword.lower() in para.lower() for keyword in agriculture_keywords):
                agri_paragraphs.append(para)

        # 取前3个相关段落
        for para in agri_paragraphs[:3]:
            if len(para) > 50:  # 忽略太短的段落
                sections.append(para[:max_length])

        # 3. 如果没有找到农业关键词段落，添加一些通用重要段落
        if len(agri_paragraphs) == 0 and len(paragraphs) > 1:
            # 添加第二个段落（通常是介绍部分）
            if len(paragraphs) > 1:
                sections.append(paragraphs[1][:max_length])

        return sections

    def _classify_text(self, text: str) -> Tuple[float, float]:
        """对单个文本进行分类"""
        try:
            # Tokenize
            inputs = self.tokenizer(
                text,
                return_tensors='pt',
                max_length=512,
                truncation=True,
                padding=True
            ).to(self.device)

            # 推理
            with torch.no_grad():
                outputs = self.model(**inputs)
                probabilities = F.softmax(outputs.logits, dim=-1)

                # 获取农业类别的概率
                agri_prob = probabilities[0][1].item()
                non_agri_prob = probabilities[0][0].item()

                return agri_prob, non_agri_prob

        except Exception as e:
            self.logger.error(f"分类推理错误: {e}")
            return 0.0, 1.0  # 默认返回非农业

    def classify_document(self, doc: DocumentInfo) -> ClassificationResult:
        """使用分层策略分类文档"""
        char_length = doc.char_length
        estimated_tokens = doc.estimated_tokens

        # 分层处理策略
        if estimated_tokens <= 512:
            # 短文档：直接处理
            return self._classify_short_document(doc)
        else:
            # 长文档：分层处理
            return self._classify_long_document(doc)

    def _classify_short_document(self, doc: DocumentInfo) -> ClassificationResult:
        """处理短文档"""
        text = doc.text
        agri_prob, non_agri_prob = self._classify_text(text)

        is_agri = 1 if agri_prob >= self.threshold else 0
        confidence = max(agri_prob, non_agri_prob)

        return ClassificationResult(
            is_agricultural=is_agri,
            confidence=confidence,
            probability=agri_prob,
            processing_details={
                "strategy": "direct",
                "document_length": doc.char_length,
                "estimated_tokens": doc.estimated_tokens
            }
        )

    def _classify_long_document(self, doc: DocumentInfo) -> ClassificationResult:
        """处理长文档（分层策略）"""
        text = doc.text

        # 第一层：快速筛选（处理开头512字符）
        first_section = text[:512]
        first_prob, _ = self._classify_text(first_section)

        processing_details = {
            "strategy": "layered",
            "document_length": doc.char_length,
            "estimated_tokens": doc.estimated_tokens,
            "first_section_prob": first_prob
        }

        if first_prob < self.threshold:
            # 开头部分非农业，直接返回
            return ClassificationResult(
                is_agricultural=0,
                confidence=1 - first_prob,
                probability=first_prob,
                processing_details=processing_details
            )

        # 第二层：关键章节处理
        key_sections = self._extract_key_sections(text)
        section_probs = []

        for i, section in enumerate(key_sections):
            prob, _ = self._classify_text(section)
            section_probs.append(prob)
            processing_details[f"section_{i+1}_prob"] = prob

        # 最终判断：任一关键章节农业概率 ≥ threshold
        final_prob = max(section_probs) if section_probs else first_prob
        is_agri = 1 if final_prob >= self.threshold else 0
        confidence = max(final_prob, 1 - final_prob)

        processing_details.update({
            "key_sections_analyzed": len(key_sections),
            "section_probabilities": section_probs,
            "final_probability": final_prob
        })

        return ClassificationResult(
            is_agricultural=is_agri,
            confidence=confidence,
            probability=final_prob,
            processing_details=processing_details
        )

    def classify_batch(self, documents: List[DocumentInfo]) -> List[ClassificationResult]:
        """批量分类文档"""
        results = []
        for doc in documents:
            result = self.classify_document(doc)
            results.append(result)
        return results

if __name__ == "__main__":
    # 测试分类器
    logging.basicConfig(level=logging.INFO)

    print("=== BioBERT分类器测试 ===")
    import os
    model_path = os.environ.get("BIOBERT_MODEL_PATH", "./models/best_model.bin")

    # 创建分类器
    classifier = BioBERTClassifier(
        model_path=model_path,
        threshold=0.6
    )

    # 测试文本
    test_texts = [
        ("This article discusses modern farming techniques and crop management strategies.", "农业相关"),
        ("The computer algorithm processes large datasets for machine learning applications.", "非农业"),
        ("Farmers use advanced irrigation systems to water their crops during dry seasons.", "农业相关"),
        ("The quantum computing research focuses on developing new processing units.", "非农业")
    ]

    print("\n=== 分类测试 ===")
    for text, expected in test_texts:
        # 创建测试文档
        doc = DocumentInfo(
            id="test",
            text=text,
            char_length=len(text),
            estimated_tokens=len(text) // 4
        )

        result = classifier.classify_document(doc)

        print(f"文本: {text[:50]}...")
        print(f"期望: {expected}, 预测: {'农业' if result.is_agricultural else '非农业'}")
        print(f"置信度: {result.confidence:.3f}, 概率: {result.probability:.3f}")
        print(f"处理策略: {result.processing_details['strategy']}")
        print()