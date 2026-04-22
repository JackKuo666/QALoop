"""
严格关键词农业分类器 - 只使用精确的农业生产关键词匹配
完全排除商业、植物学、园艺学等非农业生产语境
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

class StrictKeywordAgriculturalClassifier:
    """严格关键词农业分类器 - 只匹配真正的农业生产内容"""

    def __init__(self, model_path: str, tokenizer_name: str = "dmis-lab/biobert-base-cased-v1.1",
                 threshold: float = 0.999, device: str = "auto", min_keyword_hits: int = 2):
        self.model_path = model_path
        self.tokenizer_name = tokenizer_name
        self.threshold = threshold
        self.min_keyword_hits = min_keyword_hits  # 最少关键词命中数
        self.logger = logging.getLogger(__name__)

        # 设备选择
        if device == "auto":
            self.device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
        else:
            self.device = torch.device(device)

        self.logger.info(f"使用设备: {self.device}")
        self.logger.info(f"超高精度设置: 阈值={threshold}, 最少关键词命中数={min_keyword_hits}")

        # 加载模型和tokenizer
        self._load_model()

        # 初始化严格的农业生产关键词
        self._init_strict_agriculture_keywords()

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

    def _init_strict_agriculture_keywords(self):
        """初始化最严格的中国专业农业关键词"""

        # 从Excel文件加载专业农业关键词
        try:
            import pandas as pd
            import os

            # 读取Excel文件
            excel_path = os.environ.get("CHINESE_AGRI_KEYWORD_PATH", "./data/中国农业关键词.xlsx")
            df = pd.read_excel(excel_path)

            # 提取清洗后的中文关键词
            chinese_keywords = df['中文关键词'].dropna().drop_duplicates().tolist()
            english_keywords = df['英文关键词'].dropna().drop_duplicates().tolist()

            # 合并为农业关键词库
            self.comprehensive_agricultural_keywords = chinese_keywords + english_keywords

            self.logger.info(f"✓ 从Excel加载专业农业关键词: {len(self.comprehensive_agricultural_keywords)} 个")
            self.logger.info(f"  - 中文关键词: {len(chinese_keywords)} 个")
            self.logger.info(f"  - 英文关键词: {len(english_keywords)} 个")

        except Exception as e:
            self.logger.warning(f"无法加载Excel关键词文件，使用默认关键词: {e}")
            # 如果Excel加载失败，使用保留的默认关键词
            self.comprehensive_agricultural_keywords = [
                'agriculture', 'farming', 'cultivation', 'harvesting', 'planting',
                'irrigation', 'fertilizer', 'pesticide', 'crop rotation', 'soil management',
                'tractor', 'combine harvester', 'livestock farming', 'animal husbandry',
                '农业', '农作物', '种植业', '养殖业', '农业技术', '农机', '收获', '播种', '施肥', '灌溉',
                'wheat', 'rice', 'corn', 'soybean', 'cotton', '蔬菜', '水果', '畜牧', '渔业', '林业'
            ]

        # === 保留核心生产关键词用于快速判断 ===
        self.strict_production_keywords = [
            'agriculture', 'farming', 'cultivation', 'harvesting', 'harvest',
            'planting', 'sowing', 'growing crops', 'crop production',
            'irrigation', 'fertilizer', 'pesticide', 'herbicide', 'manure',
            'tillage', 'plowing', 'ploughing', 'crop rotation', 'soil management',
            'tractor', 'combine harvester', 'farm machinery', 'agricultural equipment',
            'livestock farming', 'animal husbandry', 'poultry farming', 'dairy farming',
            '农业', '农业生产', '农作物', '种植业', '养殖业', '农业技术',
            '农机', '收获', '播种', '施肥', '灌溉', '耕作', '畜牧', '渔业', '林业'
        ]

        # === 具体农作物名称（用于更精确匹配） ===
        self.crop_names = [
            'wheat', 'rice', 'maize', 'corn', 'barley', 'oats', 'sorghum', 'millet',
            'soybean', 'peanut', 'sunflower', 'rapeseed', 'cotton', 'sugarcane',
            'tomato', 'potato', 'carrot', 'cabbage', 'onion', 'garlic',
            'apple', 'orange', 'banana', 'grape', '小麦', '水稻', '玉米', '大麦',
            '燕麦', '高粱', '谷子', '大豆', '花生', '向日葵', '油菜', '棉花',
            '甘蔗', '番茄', '土豆', '胡萝卜', '白菜', '洋葱', '大蒜',
            '苹果', '橙子', '香蕉', '葡萄'
        ]

        # === 严格排除词（出现即排除） ===
        self.exclude_keywords = [
            # 商业经济相关
            'business', 'company', 'corporate', 'commercial', 'industry', 'industrial',
            'market', 'economic', 'financial', 'investment', 'stock', 'trade',
            'enterprise', 'sector', 'revenue', 'profit', 'cost', 'price',

            # 植物学相关（排除！）
            'botany', 'botanical', 'plant species', 'taxonomy', 'morphology',
            'plant physiology', 'plant anatomy', 'plant ecology', 'flora',

            # 园艺学相关（排除！）
            'horticulture', 'gardening', 'ornamental plants', 'landscape',
            'decorative plants', 'house plants', 'flowering plants', 'garden',

            # 野生植物（排除！）
            'wild plants', 'native plants', 'natural habitat', 'forest',
            'conservation', 'endangered species', 'biodiversity', 'ecosystem',

            # 医学药学（排除！）
            'medicinal plants', 'herbal medicine', 'pharmaceutical', 'drug',
            'medicine', 'therapy', 'treatment', 'medical', 'clinical',

            # 食品工业（在非农业语境下排除）
            'food industry', 'food processing', 'food company', 'food retail',
            'food service', 'food market', 'food sector', 'food chain',

            # 媒体娱乐
            'media', 'film', 'television', 'entertainment', 'music',
            'movie', 'broadcasting', 'publishing',

            # 科技
            'computer', 'software', 'digital', 'electronic', 'technology',
            'algorithm', 'programming', 'internet', 'system',

            # 中文排除词
            '商业', '公司', '企业', '工业', '市场', '经济', '金融', '投资',
            '植物学', '园艺', '野生', '保护', '药用', '食品工业',
            '媒体', '科技', '计算机', '软件'
        ]

        self.logger.info(f"✓ 专业农业关键词库: {len(self.comprehensive_agricultural_keywords)} 个")
        self.logger.info(f"  - 中文关键词: {len([kw for kw in self.comprehensive_agricultural_keywords if not kw.isascii()])} 个")
        self.logger.info(f"  - 英文关键词: {len([kw for kw in self.comprehensive_agricultural_keywords if kw.isascii()])} 个")
        self.logger.info(f"核心生产关键词: {len(self.strict_production_keywords)} 个")
        self.logger.info(f"作物名称: {len(self.crop_names)} 个")
        self.logger.info(f"排除词: {len(self.exclude_keywords)} 个")

    def _contains_strict_agriculture(self, text: str) -> Tuple[bool, List[str], List[str]]:
        """使用中国专业农业关键词匹配检查是否包含农业生产内容"""
        text_lower = text.lower()
        text_original = text  # 保留原文用于中文匹配

        # 第一步：检查排除词，如果出现任何一个直接排除
        found_excluded = [word for word in self.exclude_keywords if word in text_lower]
        if found_excluded:
            return False, [], found_excluded

        # 第二步：使用新的专业农业关键词库进行匹配
        found_agricultural = []

        # 匹配英文关键词
        for keyword in self.comprehensive_agricultural_keywords:
            if isinstance(keyword, str) and keyword.isascii():
                # 英文关键词
                if keyword.lower() in text_lower:
                    found_agricultural.append(keyword)

        # 匹配中文关键词
        for keyword in self.comprehensive_agricultural_keywords:
            if isinstance(keyword, str) and not keyword.isascii():
                # 中文关键词
                if keyword in text_original:
                    found_agricultural.append(keyword)

        # 第三步：增强判断逻辑 - 基于专业农业关键词的精确匹配
        total_count = len(found_agricultural)

        # 使用更智能的农业内容判断
        is_agricultural = False

        if total_count >= self.min_keyword_hits:
            # 基本条件：至少命中指定数量的农业关键词
            # 检查是否包含核心农业概念
            core_concepts = ['农业', 'agriculture', '种植', 'cultivation', '收获', 'harvesting',
                           '作物', 'crop', '畜牧', 'livestock', '渔业', 'fishery', '林业', 'forestry']

            has_core_concept = any(concept in text_lower or concept in text_original
                                 for concept in core_concepts)

            if has_core_concept or total_count >= self.min_keyword_hits * 2:
                # 如果有核心农业概念，或者关键词数量足够多，判定为农业内容
                is_agricultural = True
            else:
                # 没有核心概念时，检查是否为专业农业技术词汇
                technical_terms = ['基因', 'gene', '育种', 'breeding', '施肥', 'fertilizer',
                                 '灌溉', 'irrigation', '农药', 'pesticide', '土壤', 'soil']
                technical_count = sum(1 for term in technical_terms
                                    if term in text_lower or term in text_original)

                if technical_count >= 1:
                    is_agricultural = True

        return is_agricultural, found_agricultural[:15], found_excluded[:5]

    def _extract_agricultural_sections(self, text: str, max_length: int = 512) -> List[str]:
        """提取包含农业生产内容的章节"""
        sections = []

        # 文档开头
        sections.append(text[:max_length])

        # 分割段落
        paragraphs = [p.strip() for p in text.split('\n') if p.strip() and len(p) > 50]

        # 查找包含农业生产内容的段落
        agri_paragraphs = []
        for para in paragraphs:
            is_agri, _, _ = self._contains_strict_agriculture(para)
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
        """严格关键词农业分类"""
        # 第一重过滤：严格关键词检查
        is_agri, agri_keywords, excluded_keywords = self._contains_strict_agriculture(doc.text)

        processing_details = {
            "strategy": "ultra_strict_keyword_filter",
            "document_length": doc.char_length,
            "estimated_tokens": doc.estimated_tokens,
            "has_production_keywords": is_agri,
            "production_keywords": agri_keywords[:8],
            "excluded_keywords": excluded_keywords[:5],
            "min_keyword_hits": self.min_keyword_hits,
            "threshold": self.threshold,
            "total_keywords_found": len(agri_keywords),
            "production_count": len([kw for kw in agri_keywords if kw in self.strict_production_keywords]),
            "crops_count": len([kw for kw in agri_keywords if kw in self.crop_names])
        }

        # 如果没有严格的生产关键词，直接返回非农业
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

        # 极严格最终判断：所有章节都必须达到超高阈值
        final_prob = min(section_probs) if section_probs else first_prob  # 使用最低概率作为最终判断
        # 极严格要求：所有章节都必须达到0.999阈值
        all_sections_met_threshold = all(prob >= self.threshold for prob in section_probs)
        is_agri = 1 if (all_sections_met_threshold and final_prob >= self.threshold) else 0
        confidence = min(final_prob, min(section_probs)) if section_probs else final_prob  # 所有章节的最小置信度

        processing_details.update({
            "agri_sections_analyzed": len(agri_sections),
            "section_probabilities": section_probs,
            "high_prob_sections": high_prob_sections,
            "all_sections_met_threshold": all_sections_met_threshold,
            "final_probability": final_prob,
            "final_threshold_met": is_agri == 1,
            "strict_standard": "all_sections_must_meet_0.999_threshold"
        })

        return ClassificationResult(
            is_agricultural=is_agri,
            confidence=confidence,
            probability=final_prob,
            processing_details=processing_details
        )

if __name__ == "__main__":
    # 测试严格关键词分类器
    logging.basicConfig(level=logging.INFO)
    import os
    model_path = os.environ.get("BIOBERT_MODEL_PATH", "./models/best_model.bin")

    print("=== 严格关键词农业分类器测试 ===")

    classifier = StrictKeywordAgriculturalClassifier(
        model_path=model_path,
        threshold=0.999,
        min_keyword_hits=2
    )

    # 测试文本
    test_texts = [
        ("现代农业技术包括精准灌溉、智能农机和可持续农业生产方法，提高作物产量和农业效率", "应该农业"),
        ("Aloe pretoriensis is a plant species native to South Africa, studied for its botanical characteristics and conservation status", "应该非农业 - 植物学"),
        ("The food production industry includes companies that manufacture and distribute food products through commercial supply chains", "应该非农业 - 食品工业"),
        ("Wheat farming and crop rotation are essential agricultural practices for sustainable food production and soil management", "应该农业"),
        ("Plant conservation efforts focus on protecting endangered species and their natural habitats from ecosystem damage", "应该非农业 - 野生植物保护"),
        ("Business executive with expertise in market development and financial services for the corporate sector", "应该非农业 - 商业人物"),
        ("农业机械化使用拖拉机和联合收割机进行耕作、播种和收获，提高农业生产效率", "应该农业"),
        ("Botanical research focuses on plant taxonomy, morphology, and ecological relationships in natural ecosystems", "应该非农业 - 植物学研究")
    ]

    print("\n=== 严格关键词分类测试 ===")
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