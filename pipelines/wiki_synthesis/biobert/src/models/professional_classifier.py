"""
专业农业分类器 - 使用5566个专业农业关键词
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

class ProfessionalAgriculturalClassifier:
    """专业农业内容分类器 - 使用5566个专业农业关键词"""

    def __init__(self, model_path: str, tokenizer_name: str = "dmis-lab/biobert-base-cased-v1.1",
                 threshold: float = 0.99, device: str = "auto"):
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

        # 加载专业农业关键词
        self._load_professional_keywords()

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

    def _load_professional_keywords(self):
        """加载专业农业关键词"""
        try:
            # 加载中文农业关键词
            chinese_keywords = []
            with open('chinese_agriculture_keywords.txt', 'r', encoding='utf-8') as f:
                for line in f:
                    keyword = line.strip()
                    if keyword:
                        chinese_keywords.append(keyword.lower())

            # 加载英文农业关键词
            english_keywords = []
            with open('english_agriculture_keywords.txt', 'r', encoding='utf-8') as f:
                for line in f:
                    keyword = line.strip()
                    if keyword:
                        english_keywords.append(keyword.lower())

            # 核心农业关键词（必须包含这些才认为是农业）
            self.core_agriculture_keywords = [
                'agriculture', 'farming', 'crops', 'harvest', 'planting',
                'soil', 'irrigation', 'fertilizer', 'pesticide', 'livestock',
                'cattle', 'cultivation', 'agricultural', 'farm', 'farmers',
                '农业', '作物', '种植', '收获', '土壤', '灌溉', '施肥',
                '农药', '农作物', '畜牧业', '养殖', '农产品', '农场'
            ]

            # 专业农业关键词（来自5566个词汇）
            self.professional_agriculture_keywords = chinese_keywords + english_keywords

            # 排除词 - 这些词可能出现在农业上下文中但单独不算农业
            self.exclude_keywords = [
                'yield',  # 财务收益
                'growth', # 经济增长
                'plant',  # 工厂（plant factory）
                'garden', # 花园、植物园
                'produce', # 生产、产品（不仅是农产品）
                'industry', # 行业
                'production', # 生产
                'development', # 发展
                'management', # 管理
                'technology', # 技术
                'science' # 科学
            ]

            self.logger.info(f"加载了 {len(chinese_keywords)} 个中文农业关键词")
            self.logger.info(f"加载了 {len(english_keywords)} 个英文农业关键词")
            self.logger.info(f"总专业关键词: {len(self.professional_agriculture_keywords)}")

        except Exception as e:
            self.logger.error(f"加载农业关键词失败: {e}")
            # 使用默认关键词
            self.professional_agriculture_keywords = [
                'agriculture', 'farming', 'crops', 'harvest', 'planting',
                'soil', 'irrigation', 'fertilizer', 'livestock',
                'wheat', 'corn', 'rice', '蔬菜', '水果'
            ]

    def _contains_professional_agriculture_keywords(self, text: str) -> Tuple[bool, List[str]]:
        """检查是否包含专业农业关键词"""
        text_lower = text.lower()
        found_keywords = []

        # 查找专业农业关键词
        for keyword in self.professional_agriculture_keywords:
            if keyword in text_lower and len(keyword) > 1:  # 忽略单字符
                # 确保不是排除词
                is_valid = True
                for exclude_word in self.exclude_keywords:
                    if keyword == exclude_word or (len(keyword) > 3 and exclude_word in keyword):
                        is_valid = False
                        break

                if is_valid:
                    found_keywords.append(keyword)

        # 必须包含核心农业关键词
        has_core_keyword = any(kw in text_lower for kw in self.core_agriculture_keywords)

        # 判断是否符合条件：必须有核心关键词 + 至少1个专业关键词
        meets_criteria = has_core_keyword and len(found_keywords) >= 1

        return meets_criteria, found_keywords

    def _extract_key_sections(self, text: str, max_length: int = 512) -> List[str]:
        """提取包含农业关键词的关键章节"""
        sections = []

        # 1. 文档开头
        sections.append(text[:max_length])

        # 2. 查找包含农业关键词的段落
        paragraphs = [p.strip() for p in text.split('\n') if p.strip()]

        agri_paragraphs = []
        for para in paragraphs:
            has_keywords, keywords = self._contains_professional_agriculture_keywords(para)
            if has_keywords and len(para) > 50:
                agri_paragraphs.append(para)

        # 取前3个相关段落
        for para in agri_paragraphs[:3]:
            sections.append(para[:max_length])

        return sections

    def _classify_text(self, text: str) -> Tuple[float, float]:
        """对单个文本进行分类"""
        try:
            inputs = self.tokenizer(
                text,
                return_tensors='pt',
                max_length=512,
                truncation=True,
                padding=True
            ).to(self.device)

            with torch.no_grad():
                outputs = self.model(**inputs)
                probabilities = F.softmax(outputs.logits, dim=-1)

                agri_prob = probabilities[0][1].item()
                non_agri_prob = probabilities[0][0].item()

                return agri_prob, non_agri_prob

        except Exception as e:
            self.logger.error(f"分类推理错误: {e}")
            return 0.0, 1.0

    def classify_document(self, doc: DocumentInfo) -> ClassificationResult:
        """专业分类文档"""
        # 第一重过滤：专业关键词检查
        has_keywords, keywords = self._contains_professional_agriculture_keywords(doc.text)

        processing_details = {
            "strategy": "professional_dual_filter",
            "document_length": doc.char_length,
            "estimated_tokens": doc.estimated_tokens,
            "has_professional_keywords": has_keywords,
            "found_keywords": keywords[:10]  # 只保存前10个关键词避免日志过长
        }

        # 如果没有专业关键词，直接返回非农业
        if not has_keywords:
            return ClassificationResult(
                is_agricultural=0,
                confidence=1.0,
                probability=0.0,
                processing_details=processing_details
            )

        # 第二重过滤：模型概率检查
        char_length = doc.char_length
        estimated_tokens = doc.estimated_tokens

        if estimated_tokens <= 512:
            return self._classify_short_document(doc, processing_details)
        else:
            return self._classify_long_document(doc, processing_details)

    def _classify_short_document(self, doc: DocumentInfo, processing_details: Dict) -> ClassificationResult:
        """处理短文档"""
        agri_prob, non_agri_prob = self._classify_text(doc.text)

        # 严格阈值判断
        is_agri = 1 if agri_prob >= self.threshold else 0
        confidence = max(agri_prob, non_agri_prob)

        processing_details.update({
            "classification_method": "direct",
            "model_probability": agri_prob,
            "threshold_met": agri_prob >= self.threshold
        })

        return ClassificationResult(
            is_agricultural=is_agri,
            confidence=confidence,
            probability=agri_prob,
            processing_details=processing_details
        )

    def _classify_long_document(self, doc: DocumentInfo, processing_details: Dict) -> ClassificationResult:
        """处理长文档"""
        text = doc.text

        # 第一层：快速筛选
        first_section = text[:512]
        first_prob, _ = self._classify_text(first_section)

        processing_details.update({
            "classification_method": "layered",
            "first_section_prob": first_prob,
            "first_section_threshold_met": first_prob >= self.threshold
        })

        # 如果第一层就不达标，直接返回非农业
        if first_prob < self.threshold:
            return ClassificationResult(
                is_agricultural=0,
                confidence=1 - first_prob,
                probability=first_prob,
                processing_details=processing_details
            )

        # 第二层：关键章节处理
        key_sections = self._extract_key_sections(text)
        section_probs = []
        high_prob_sections = 0

        for i, section in enumerate(key_sections):
            prob, _ = self._classify_text(section)
            section_probs.append(prob)

            if prob >= self.threshold:
                high_prob_sections += 1

            processing_details[f"section_{i+1}_prob"] = prob

        # 最终判断：至少2个章节达到严格阈值
        final_prob = max(section_probs) if section_probs else first_prob
        is_agri = 1 if (high_prob_sections >= 2 and final_prob >= self.threshold) else 0
        confidence = max(final_prob, 1 - final_prob)

        processing_details.update({
            "key_sections_analyzed": len(key_sections),
            "section_probabilities": section_probs,
            "high_prob_sections": high_prob_sections,
            "final_probability": final_prob,
            "final_threshold_met": is_agri == 1
        })

        return ClassificationResult(
            is_agricultural=is_agri,
            confidence=confidence,
            probability=final_prob,
            processing_details=processing_details
        )

if __name__ == "__main__":
    # 测试专业分类器
    logging.basicConfig(level=logging.INFO)
    import os
    model_path = os.environ.get("BIOBERT_MODEL_PATH", "./models/best_model.bin")

    print("=== 专业农业分类器测试 (5566个专业关键词) ===")

    classifier = ProfessionalAgriculturalClassifier(
        model_path=model_path,
        threshold=0.99
    )

    # 测试文本
    test_texts = [
        ("现代农业采用精准农业技术和智慧农业系统来提高农作物产量和农业发展", "应该农业"),
        ("The computer algorithm processes large datasets for machine learning applications", "应该非农业"),
        ("可持续农业和生态农业的发展需要有机农业技术和绿色农业方法", "应该农业"),
        ("This software development company focuses on technology solutions and management systems", "应该非农业"),
        ("农业机械化包括拖拉机、收割机等农业机械的使用以及农业技术创新", "应该农业"),
        ("The quantum computing research focuses on computational methods and data processing", "应该非农业")
    ]

    print("\n=== 分类测试 ===")
    for text, expected in test_texts:
        doc = DocumentInfo(
            id="test",
            text=text,
            char_length=len(text),
            estimated_tokens=len(text) // 4
        )

        result = classifier.classify_document(doc)

        print(f"文本: {text[:60]}...")
        print(f"期望: {expected}")
        print(f"预测: {'农业' if result.is_agricultural else '非农业'}")
        print(f"概率: {result.probability:.3f}, 置信度: {result.confidence:.3f}")
        print(f"关键词: {result.processing_details.get('found_keywords', [])[:5]}")
        print()