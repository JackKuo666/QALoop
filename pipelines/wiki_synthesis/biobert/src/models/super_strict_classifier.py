"""
超级严格农业分类器 - 专门针对农业生产，排除植物学、园艺学内容
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

class SuperStrictAgriculturalClassifier:
    """超级严格农业分类器 - 只识别真正的农业生产内容"""

    def __init__(self, model_path: str, tokenizer_name: str = "dmis-lab/biobert-base-cased-v1.1",
                 threshold: float = 0.995, device: str = "auto"):
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

        # 初始化严格的农业生产关键词
        self._init_agricultural_keywords()

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

    def _init_agricultural_keywords(self):
        """初始化严格的农业生产关键词"""

        # === 真正的农业生产关键词 ===
        self.farm_production_keywords = [
            # 核心农业生产活动
            'agriculture', 'farming', 'cultivation', 'harvesting', 'harvest',
            'planting', 'sowing', 'growing crops', 'crop production',

            # 农业技术和管理
            'irrigation', 'fertilizer', 'pesticide', 'herbicide', 'manure',
            'tillage', 'plowing', 'ploughing', 'crop rotation', 'soil management',

            # 农业机械和设备
            'tractor', 'combine harvester', 'farm machinery', 'agricultural equipment',
            'harvester', 'seeder', 'sprayer', 'plow', 'cultivator',

            # 农作物和产量
            'crop yield', 'grain production', 'food production', 'cereal crops',
            'cash crops', 'staple crops', 'food crops', 'agricultural output',

            # 畜牧业
            'livestock farming', 'animal husbandry', 'poultry farming',
            'dairy farming', 'cattle ranching', 'meat production',

            # 农业经济和政策
            'agricultural economics', 'farm income', 'agricultural policy',
            'food security', 'agricultural development', 'rural development',

            # 中文农业生产关键词
            '农业', '农作物', '农产品', '粮食', '种植业', '养殖业',
            '农业生产', '农业技术', '农机', '收获', '播种', '施肥', '灌溉'
        ]

        # === 农作物具体名称 ===
        self.crop_names = [
            # 粮食作物
            'wheat', 'rice', 'maize', 'corn', 'barley', 'oats', 'sorghum', 'millet',
            '小麦', '水稻', '玉米', '大麦', '燕麦', '高粱', '谷子',

            # 经济作物
            'cotton', 'sugarcane', 'tobacco', 'coffee', 'tea', 'rubber',
            'soybean', 'peanut', 'sunflower', 'rapeseed',
            '棉花', '甘蔗', '烟草', '咖啡', '茶叶', '橡胶',
            '大豆', '花生', '向日葵', '油菜',

            # 蔬菜水果
            'tomato', 'potato', 'carrot', 'cabbage', 'onion', 'garlic',
            'apple', 'orange', 'banana', 'grape',
            '番茄', '土豆', '胡萝卜', '白菜', '洋葱', '大蒜',
            '苹果', '橙子', '香蕉', '葡萄'
        ]

        # === 严格的排除词（植物学、园艺学、野生植物相关）===
        self.exclude_keywords = [
            # 植物学术语
            'botany', 'botanical', 'flora', 'plant species', 'taxonomy',
            'plant ecology', 'plant physiology', 'morphology', 'plant anatomy',

            # 园艺学
            'horticulture', 'ornamental plants', 'gardening', 'landscape',
            'garden', 'decorative plants', 'house plants', 'flowering plants',

            # 野生植物和自然环境
            'wild plants', 'native species', 'natural habitat', 'forest',
            'grassland', 'wetland', 'desert plants', 'mountain flora',

            # 植物保护和保育
            'conservation', 'endangered species', 'red list', 'biodiversity',
            'plant protection', 'wildlife', 'ecosystem', 'environmental',

            # 基础植物术语（单独出现时不表示农业）
            'leaf', 'stem', 'root', 'flower', 'fruit', 'seed', 'growth',
            'species', 'genus', 'family', 'plant', 'herb', 'shrub', 'tree',

            # 医学和药理
            'medicinal plants', 'herbal medicine', 'traditional medicine',
            'pharmacology', 'pharmacy', 'drug', 'medicine',

            # 排除的通用词汇
            'nature', 'natural', 'organic', 'green', 'sustainable',
            'ecological', 'environment', 'climate', 'weather',

            # 中文排除词
            '植物', '花卉', '园艺', '野生', '原生', '保护', '濒危',
            '药用植物', '观赏植物', '自然', '生态', '环境'
        ]

        # === 农业生产上下文指示词 ===
        self.production_context_keywords = [
            # 生产活动词汇
            'production', 'yield', 'output', 'harvest', 'cultivation',
            'farm', 'farming', 'agricultural', 'grower', 'producer',
            '农田', '农场', '种植', '收获', '产量', '生产'
        ]

        self.logger.info(f"生产关键词: {len(self.farm_production_keywords)}")
        self.logger.info(f"作物名称: {len(self.crop_names)}")
        self.logger.info(f"排除词: {len(self.exclude_keywords)}")

    def _contains_agricultural_production_keywords(self, text: str) -> Tuple[bool, List[str], List[str]]:
        """检查是否包含农业生产关键词"""
        text_lower = text.lower()
        found_agri_keywords = []
        found_excluded_keywords = []

        # 检查排除词
        for exclude_word in self.exclude_keywords:
            if exclude_word in text_lower:
                found_excluded_keywords.append(exclude_word)

        # 如果包含大量排除词，直接认为不是农业
        if len(found_excluded_keywords) >= 3:
            return False, [], found_excluded_keywords

        # 检查农业生产关键词
        for keyword in self.farm_production_keywords:
            if keyword in text_lower:
                found_agri_keywords.append(keyword)

        # 检查作物名称
        for crop in self.crop_names:
            if crop in text_lower:
                found_agri_keywords.append(crop)

        # 必须同时满足：
        # 1. 有农业生产关键词
        # 2. 有生产上下文词汇
        # 3. 排除词不过多
        has_production_context = any(ctx in text_lower for ctx in self.production_context_keywords)

        is_agricultural = (
            len(found_agri_keywords) >= 1 and
            has_production_context and
            len(found_excluded_keywords) <= 1  # 最多1个排除词
        )

        return is_agricultural, found_agri_keywords, found_excluded_keywords

    def _extract_agricultural_sections(self, text: str, max_length: int = 512) -> List[str]:
        """提取包含农业生产内容的章节"""
        sections = []

        # 文档开头
        sections.append(text[:max_length])

        # 分割段落
        paragraphs = [p.strip() for p in text.split('\n') if p.strip() and len(p) > 100]

        # 查找包含农业生产的段落
        agri_paragraphs = []
        for para in paragraphs:
            is_agri, keywords, excluded = self._contains_agricultural_production_keywords(para)
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
        """超级严格分类文档"""
        # 第一重过滤：农业生产关键词检查
        is_agri, agri_keywords, excluded_keywords = self._contains_agricultural_production_keywords(doc.text)

        processing_details = {
            "strategy": "super_strict_production_filter",
            "document_length": doc.char_length,
            "estimated_tokens": doc.estimated_tokens,
            "has_production_keywords": is_agri,
            "production_keywords": agri_keywords[:8],
            "excluded_keywords": excluded_keywords[:5]
        }

        # 如果没有农业生产关键词，直接返回非农业
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

        # 超严格阈值判断
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

        # 第二层：农业生产章节处理
        agri_sections = self._extract_agricultural_sections(text)
        section_probs = []
        high_prob_sections = 0

        for i, section in enumerate(agri_sections):
            prob, _ = self._classify_text(section)
            section_probs.append(prob)

            if prob >= self.threshold:
                high_prob_sections += 1

            processing_details[f"section_{i+1}_prob"] = prob

        # 最终判断：至少2个章节达到超级严格阈值
        final_prob = max(section_probs) if section_probs else first_prob
        is_agri = 1 if (high_prob_sections >= 2 and final_prob >= self.threshold) else 0
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
    # 测试超级严格分类器
    logging.basicConfig(level=logging.INFO)
    import os
    model_path = os.environ.get("BIOBERT_MODEL_PATH", "./models/best_model.bin")

    print("=== 超级严格农业分类器测试 ===")

    classifier = SuperStrictAgriculturalClassifier(
        model_path=model_path,
        threshold=0.995
    )

    # 测试文本
    test_texts = [
        ("现代农业技术包括精准灌溉、智能农机和可持续农业生产方法", "应该农业"),
        ("This article describes the botanical characteristics and habitat of Aloe pretoriensis species", "应该非农业"),
        ("Wheat farming and crop production are essential for food security and agricultural development", "应该农业"),
        ("Plant conservation efforts focus on protecting endangered species and their natural habitats", "应该非农业"),
        ("农业机械化使用拖拉机和联合收割机提高粮食产量和农业生产效率", "应该农业"),
        ("Gardening and horticulture involve growing ornamental plants for landscape decoration", "应该非农业")
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
        print(f"生产关键词: {result.processing_details.get('production_keywords', [])}")
        print(f"排除词: {result.processing_details.get('excluded_keywords', [])}")
        print()