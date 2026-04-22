"""
泛农业分类器 - 包含传统农业、园艺学、植物学、林业等广义农业内容
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

class BroadAgriculturalClassifier:
    """泛农业分类器 - 包含所有与植物和农作物相关的内容"""

    def __init__(self, model_path: str, tokenizer_name: str = "dmis-lab/biobert-base-cased-v1.1",
                 threshold: float = 0.98, device: str = "auto"):
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

        # 加载泛农业关键词
        self._load_broad_agriculture_keywords()

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

    def _load_broad_agriculture_keywords(self):
        """加载泛农业关键词，包含所有相关专业领域"""

        try:
            # 加载专业农业关键词文件
            chinese_keywords = []
            english_keywords = []

            try:
                with open('chinese_agriculture_keywords.txt', 'r', encoding='utf-8') as f:
                    for line in f:
                        keyword = line.strip()
                        if keyword:
                            chinese_keywords.append(keyword.lower())

                with open('english_agriculture_keywords.txt', 'r', encoding='utf-8') as f:
                    for line in f:
                        keyword = line.strip()
                        if keyword:
                            english_keywords.append(keyword.lower())
            except FileNotFoundError:
                self.logger.warning("农业关键词文件未找到，使用默认关键词")
                chinese_keywords = ['农业', '作物', '种植', '收获']
                english_keywords = ['agriculture', 'farming', 'crop']

            # 扩展泛农业关键词
            self.broad_agriculture_keywords = chinese_keywords + english_keywords + [
                # 传统农业生产
                'farming', 'agriculture', 'cultivation', 'harvest', 'planting',
                'soil', 'irrigation', 'fertilizer', 'livestock', 'crops',
                'agricultural', 'farm', 'crop production', 'food production',
                '农业', '农作物', '农产品', '粮食', '种植', '收获', '土壤', '灌溉',

                # 园艺学
                'horticulture', 'gardening', 'garden', 'ornamental plants',
                'landscape', 'landscaping', 'floriculture', 'pomology',
                'olericulture', 'fruit trees', 'vegetable growing',
                '园艺', '花卉', '果树', '蔬菜', '观赏植物', '园林',

                # 植物学
                'botany', 'botanical', 'plant', 'plants', 'flora',
                'plant species', 'plant ecology', 'plant physiology',
                'morphology', 'plant anatomy', 'taxonomy', 'plant science',
                '植物学', '植物', '植物科学', '植物生态', '植物生理',

                # 林业和野生植物
                'forestry', 'forest', 'trees', 'timber', 'woodland',
                'wild plants', 'native plants', 'natural habitat',
                'forest management', 'silviculture', 'reforestation',
                '林业', '森林', '树木', '野生植物', '原生植物',

                # 农作物和作物科学
                'wheat', 'rice', 'maize', 'corn', 'barley', 'oats', 'millet',
                'soybean', 'cotton', 'sugarcane', 'vegetables', 'fruits',
                'cereal', 'grain', 'legumes', 'tuber', 'root crops',
                '小麦', '水稻', '玉米', '大豆', '棉花', '蔬菜', '水果', '谷物',

                # 具体植物学术语
                'leaf', 'leaves', 'stem', 'root', 'flower', 'flowers',
                'fruit', 'fruits', 'seed', 'seeds', 'growth', 'growing',
                '叶', '茎', '根', '花', '果', '种子', '生长',

                # 农业技术和设备
                'tractor', 'harvester', 'irrigation system', 'farm equipment',
                'agricultural machinery', 'greenhouse', 'hydroponic',
                '拖拉机', '收割机', '农业机械', '温室', '无土栽培',

                # 食品加工和农产品
                'food processing', 'food industry', 'agri-food',
                'organic food', 'food safety', 'nutrition',
                '食品加工', '食品工业', '有机食品', '食品安全'
            ]

            # 排除词 - 真正不相关的内容
            self.exclude_keywords = [
                # 科技和工程
                'computer', 'software', 'algorithm', 'programming', 'technology',
                'internet', 'digital', 'electronic', 'machine learning',
                'computer', 'software', 'algorithm', 'programming', 'technology',

                # 商业和金融
                'bank', 'finance', 'investment', 'stock', 'economy',
                'business', 'corporate', 'marketing', 'sales',
                'bank', 'finance', 'investment', 'stock', 'economy',

                # 医学和健康
                'medical', 'medicine', 'hospital', 'disease', 'health',
                'pharmaceutical', 'drug', 'treatment', 'therapy',
                'medical', 'medicine', 'hospital', 'disease', 'health',

                # 教育和学术
                'university', 'education', 'research', 'academic', 'student',
                'school', 'college', 'teaching', 'learning',
                'university', 'education', 'research', 'academic', 'student',

                # 法律和政治
                'law', 'legal', 'court', 'government', 'policy', 'politics',
                'election', 'vote', 'parliament', 'congress',
                'law', 'legal', 'court', 'government', 'policy', 'politics',

                # 娱乐和媒体
                'movie', 'music', 'game', 'sport', 'entertainment',
                'television', 'radio', 'celebrity', 'media',
                'movie', 'music', 'game', 'sport', 'entertainment'
            ]

            # 核心农业词汇（权重更高）
            self.core_agriculture_keywords = [
                'agriculture', 'farming', 'crops', 'harvest', 'planting',
                'livestock', 'irrigation', 'cultivation', 'farm',
                '农业', '农作物', '种植', '收获', '养殖业', '农产品',
                'botany', 'plant science', 'horticulture', 'forestry',
                '植物学', '园艺', '林业'
            ]

            self.logger.info(f"泛农业关键词总数: {len(self.broad_agriculture_keywords)}")
            self.logger.info(f"排除词数量: {len(self.exclude_keywords)}")
            self.logger.info(f"核心农业关键词: {len(self.core_agriculture_keywords)}")

        except Exception as e:
            self.logger.error(f"加载关键词失败: {e}")
            # 使用默认关键词
            self.broad_agriculture_keywords = ['agriculture', 'farming', 'plant', '农业', '植物']
            self.exclude_keywords = ['computer', 'software', 'business']
            self.core_agriculture_keywords = ['agriculture', '农业']

    def _contains_broad_agriculture_keywords(self, text: str) -> Tuple[bool, List[str], List[str]]:
        """检查是否包含泛农业关键词"""
        text_lower = text.lower()
        found_agri_keywords = []
        found_exclude_keywords = []

        # 检查排除词
        for exclude_word in self.exclude_keywords:
            if exclude_word in text_lower:
                found_exclude_keywords.append(exclude_word)

        # 如果排除词过多，可能不是农业相关
        if len(found_exclude_keywords) >= 3:
            return False, [], found_exclude_keywords

        # 检查农业关键词
        for keyword in self.broad_agriculture_keywords:
            if keyword in text_lower and len(keyword) > 2:
                found_agri_keywords.append(keyword)

        # 检查核心农业关键词
        core_found = any(kw in text_lower for kw in self.core_agriculture_keywords)

        # 判断逻辑：
        # 1. 有核心农业关键词，或者
        # 2. 有多个普通农业关键词（至少2个）
        is_agricultural = core_found or len(found_agri_keywords) >= 2

        return is_agricultural, found_agri_keywords, found_exclude_keywords

    def _extract_agriculture_sections(self, text: str, max_length: int = 512) -> List[str]:
        """提取包含农业内容的章节"""
        sections = []

        # 文档开头
        sections.append(text[:max_length])

        # 分割段落
        paragraphs = [p.strip() for p in text.split('\n') if p.strip() and len(p) > 50]

        # 查找包含农业内容的段落
        agri_paragraphs = []
        for para in paragraphs:
            is_agri, keywords, _ = self._contains_broad_agriculture_keywords(para)
            if is_agri:
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
        """泛农业分类文档"""
        # 第一重过滤：泛农业关键词检查
        is_agri, agri_keywords, exclude_keywords = self._contains_broad_agriculture_keywords(doc.text)

        processing_details = {
            "strategy": "broad_agriculture_filter",
            "document_length": doc.char_length,
            "estimated_tokens": doc.estimated_tokens,
            "has_agriculture_keywords": is_agri,
            "agriculture_keywords": agri_keywords[:10],
            "exclude_keywords": exclude_keywords[:5]
        }

        # 如果没有农业关键词，直接返回非农业
        if not is_agri:
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

        # 第二层：农业章节处理
        agri_sections = self._extract_agriculture_sections(text)
        section_probs = []
        high_prob_sections = 0

        for i, section in enumerate(agri_sections):
            prob, _ = self._classify_text(section)
            section_probs.append(prob)

            if prob >= self.threshold:
                high_prob_sections += 1

            processing_details[f"section_{i+1}_prob"] = prob

        # 最终判断：至少1个章节达到阈值即可
        final_prob = max(section_probs) if section_probs else first_prob
        is_agri = 1 if final_prob >= self.threshold else 0
        confidence = max(final_prob, 1 - final_prob)

        processing_details.update({
            "agri_sections_analyzed": len(agri_sections),
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
    # 测试泛农业分类器
    logging.basicConfig(level=logging.INFO)
    import os
    model_path = os.environ.get("BIOBERT_MODEL_PATH", "./models/best_model.bin")

    print("=== 泛农业分类器测试 ===")

    classifier = BroadAgriculturalClassifier(
        model_path=model_path,
        threshold=0.98
    )

    # 测试文本
    test_texts = [
        ("现代农业技术包括精准灌溉和智能农机设备", "应该农业"),
        ("This article describes Aloe pretoriensis, a plant species native to South Africa", "应该农业 - 植物学"),
        ("Gardening and horticulture techniques for growing ornamental plants and vegetables", "应该农业 - 园艺学"),
        ("Plant conservation efforts focus on protecting endangered species in natural habitats", "应该农业 - 野生植物保护"),
        ("Wheat farming and crop production methods for sustainable agriculture", "应该农业 - 传统农业"),
        ("Computer algorithms for machine learning and artificial intelligence applications", "应该非农业"),
        ("Financial investment strategies and stock market analysis for business development", "应该非农业")
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

        print(f"文本: {text[:50]}...")
        print(f"期望: {expected}")
        print(f"预测: {'农业' if result.is_agricultural else '非农业'}")
        print(f"概率: {result.probability:.3f}, 置信度: {result.confidence:.3f}")
        print(f"农业关键词: {result.processing_details.get('agriculture_keywords', [])[:5]}")
        print()