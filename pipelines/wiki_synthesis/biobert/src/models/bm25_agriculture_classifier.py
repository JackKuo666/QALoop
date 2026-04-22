"""
BM25农业分类器 - 使用BM25算法进行精确的关键词匹配，避免误匹配
"""
import torch
import torch.nn.functional as F
from transformers import AutoTokenizer, AutoModelForSequenceClassification
from typing import Dict, List, Tuple, Optional
import logging
import re
import math
from collections import Counter, defaultdict
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

class BM25AgriculturalClassifier:
    """基于BM25的农业分类器 - 精确关键词匹配"""

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

        # 初始化BM25农业关键词
        self._init_bm25_agriculture_keywords()

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

    def _init_bm25_agriculture_keywords(self):
        """初始化用于BM25的农业关键词"""

        # 精确的农业关键词（避免误匹配）
        self.precise_agriculture_keywords = [
            # 传统农业生产
            'agriculture', 'farming', 'cultivation', 'harvest', 'harvesting',
            'planting', 'sowing', 'crop production', 'food production',
            'agricultural', 'farm', 'farmer', 'farmers', 'livestock',
            'irrigation', 'fertilizer', 'pesticide', 'manure', 'tillage',
            'plowing', 'ploughing', 'crop rotation', 'soil management',
            '农业', '农作物', '农产品', '粮食', '种植', '收获', '土壤', '灌溉',
            '养殖业', '畜牧业', '农业生产', '农业技术', '农机',

            # 具体农作物
            'wheat', 'rice', 'maize', 'corn', 'barley', 'oats', 'millet',
            'soybean', 'cotton', 'sugarcane', 'potato', 'tomato', 'onion',
            '小麦', '水稻', '玉米', '大麦', '燕麦', '大豆', '棉花', '土豆',
            '番茄', '洋葱', '蔬菜', '水果', '谷物',

            # 农业机械和设备
            'tractor', 'combine harvester', 'farm equipment', 'agricultural machinery',
            'harvester', 'seeder', 'sprayer', 'plow', 'cultivator', 'irrigation system',
            '拖拉机', '收割机', '联合收割机', '农业机械', '播种机', '灌溉系统',

            # 园艺学
            'horticulture', 'gardening', 'garden', 'ornamental plants',
            'landscape', 'landscaping', 'floriculture', 'pomology',
            '园艺', '花卉', '果树', '蔬菜种植', '观赏植物', '园林',

            # 植物学
            'botany', 'botanical', 'plant science', 'plant species',
            'plant ecology', 'plant physiology', 'morphology', 'plant anatomy',
            '植物学', '植物科学', '植物生态', '植物生理', '植物形态',

            # 林业
            'forestry', 'forest management', 'silviculture', 'reforestation',
            'timber', 'woodland', '林业', '森林管理', '造林', '木材',

            # 食品加工
            'food processing', 'agri-food', 'organic food', 'food safety',
            '食品加工', '有机食品', '食品安全'
        ]

        # BM25参数
        self.k1 = 1.2  # 控制词频饱和度
        self.b = 0.75  # 控制文档长度归一化程度
        self.epsilon = 0.25  # IDF下限

        # 预计算关键词长度
        self.keyword_lengths = {kw.lower(): len(kw.split()) for kw in self.precise_agriculture_keywords}

        self.logger.info(f"BM25关键词数量: {len(self.precise_agriculture_keywords)}")
        self.logger.info(f"BM25参数: k1={self.k1}, b={self.b}, epsilon={self.epsilon}")

    def _tokenize_text(self, text: str) -> List[str]:
        """文本分词（简化版，用于BM25）"""
        # 转换为小写并分割
        text = text.lower()

        # 简单的单词分割（可以替换为更复杂的分词器）
        words = re.findall(r'\b[a-zA-Z]+\b', text)

        # 过滤短词
        words = [w for w in words if len(w) >= 2]

        return words

    def _calculate_bm25_score(self, text: str, query_terms: List[str]) -> float:
        """计算BM25得分"""
        tokens = self._tokenize_text(text)

        if not tokens or not query_terms:
            return 0.0

        # 词频统计
        doc_length = len(tokens)
        tf = Counter(tokens)

        # 平均文档长度（假设值，可以预先计算）
        avg_doc_length = 100

        score = 0.0

        for term in query_terms:
            if term not in tf:
                continue

            # TF计算
            tf_term = tf[term]
            tf_normalized = tf_term / (tf_term + self.k1 * (1 - self.b + self.b * doc_length / avg_doc_length))

            # IDF计算（简化版）
            idf = math.log((len(self.precise_agriculture_keywords) + 1) / 1) + 1

            score += tf_normalized * idf

        return score

    def _contains_agriculture_terms_bm25(self, text: str, min_score: float = 1.0) -> Tuple[bool, List[str], float]:
        """使用BM25检查是否包含农业术语"""
        # 将文本分成句子进行更精确的匹配
        sentences = re.split(r'[.!?;]+', text)
        sentences = [s.strip() for s in sentences if s.strip() and len(s) > 10]

        best_score = 0.0
        best_matches = []

        # 排除非农业的常见搭配
        non_agriculture_contexts = [
            # 系统相关
            'computer system', 'operating system', 'system software', 'system architecture',
            'financial system', 'economic system', 'political system', 'social system',
            'management system', 'control system', 'monitoring system',

            # 医学相关
            'stem cells', 'stem cell research', 'stem cell therapy',
            'operating room', 'operation manual', 'surgical operation',

            # 商业经济相关
            'price analysis', 'price comparison', 'stock price', 'market price',
            'business development', 'economic development', 'commercial production',
            'industrial production', 'manufacturing production', 'corporate production',
            'real estate', 'property development', 'urban development',
            'business model', 'business strategy', 'corporate strategy',
            'financial services', 'investment services', 'banking services',
            'market analysis', 'market research', 'business analysis',
            'company profile', 'executive profile', 'business leader',
            'detroit business', 'business professional', 'entrepreneur',

            # 食品在非农业语境
            'food industry', 'food service', 'food retail', 'food sector',
            'food company', 'food brand', 'food chain', 'food market',
            'production process', 'production system', 'production facility',

            # 媒体娱乐
            'media production', 'film production', 'music production',
            'television production', 'entertainment production'
        ]

        # 检查是否包含排除的上下文
        text_lower = text.lower()
        for non_agri_context in non_agriculture_contexts:
            if non_agri_context in text_lower:
                return False, [], 0.0

        for sentence in sentences:
            # 检查每个关键词
            for keyword in self.precise_agriculture_keywords:
                # 分解关键词为多个词
                query_terms = keyword.lower().split()

                # 计算BM25得分
                score = self._calculate_bm25_score(sentence, query_terms)

                # 额外检查：确保关键词不在非农业上下文中
                if score > 0:
                    sentence_lower = sentence.lower()
                    # 检查这个关键词是否出现在非农业上下文中
                    context_safe = True
                    for term in query_terms:
                        # 需要上下文检查的词汇
                        if term in ['system', 'stem', 'operation', 'price', 'production', 'food']:
                            # 检查周围的词
                            words = sentence_lower.split()
                            term_index = words.index(term) if term in words else -1

                            if term_index >= 0:
                                # 检查前后5个词的上下文
                                context_words = words[max(0, term_index-5):term_index+6]
                                context_text = ' '.join(context_words)

                                # 扩展的非农业上下文检查
                                non_agricultural_contexts = [
                                    # 科技系统
                                    'computer', 'software', 'digital', 'electronic', 'algorithm',
                                    # 商业经济
                                    'financial', 'economic', 'business', 'corporate', 'company',
                                    'commercial', 'industrial', 'manufacturing', 'market', 'investment',
                                    'stock', 'bank', 'real estate', 'property', 'entrepreneur',
                                    # 医学
                                    'cell', 'therapy', 'surgery', 'medical', 'hospital',
                                    'pharmaceutical', 'drug', 'treatment', 'clinic',
                                    # 媒体娱乐
                                    'media', 'film', 'television', 'entertainment', 'music',
                                    'movie', 'broadcasting', 'publishing',
                                    # 特殊组合检查
                                    'food industry', 'food company', 'food market', 'food service',
                                    'production facility', 'production process', 'production system'
                                ]

                                # 如果发现非农业上下文，标记为不安全
                                if any(neg_ctx in context_text for neg_ctx in non_agricultural_contexts):
                                    context_safe = False
                                    break

                            # 特殊检查：food production 的商业组合
                            if term == 'food' and 'production' in sentence_lower:
                                # 检查food production是否出现在商业语境中
                                business_indicators = [
                                    'business', 'company', 'corporate', 'industry', 'commercial',
                                    'economic', 'financial', 'market', 'sector', 'enterprise'
                                ]
                                if any(biz in sentence_lower for biz in business_indicators):
                                    context_safe = False
                                    break

                    if not context_safe:
                        score = 0.0  # 重置得分

                if score > best_score:
                    best_score = score
                    best_matches = [keyword]
                elif score > 0 and score == best_score:
                    best_matches.append(keyword)

        # 如果最高得分超过阈值，认为包含农业内容
        has_agriculture = best_score >= min_score

        return has_agriculture, best_matches[:10], best_score

    def _extract_agricultural_sections(self, text: str, max_length: int = 512) -> List[str]:
        """提取包含农业内容的章节"""
        sections = []

        # 文档开头
        sections.append(text[:max_length])

        # 分割段落
        paragraphs = [p.strip() for p in text.split('\n') if p.strip() and len(p) > 50]

        # 查找包含农业内容的段落
        agri_paragraphs = []
        for para in paragraphs:
            has_agri, matches, score = self._contains_agriculture_terms_bm25(para)
            if has_agri:
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
        """BM25农业分类文档"""
        # 第一重过滤：BM25农业关键词检查
        has_agri, agri_keywords, bm25_score = self._contains_agriculture_terms_bm25(doc.text)

        processing_details = {
            "strategy": "bm25_agriculture_filter",
            "document_length": doc.char_length,
            "estimated_tokens": doc.estimated_tokens,
            "has_agriculture_keywords": has_agri,
            "agriculture_keywords": agri_keywords,
            "bm25_score": bm25_score,
            "min_score_threshold": 1.0
        }

        # 如果BM25得分太低，直接返回非农业
        if not has_agri or bm25_score < 0.5:
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
        agri_sections = self._extract_agricultural_sections(text)
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
    # 测试BM25分类器
    logging.basicConfig(level=logging.INFO)
    import os
    model_path = os.environ.get("BIOBERT_MODEL_PATH", "./models/best_model.bin")

    print("=== BM25农业分类器测试 ===")

    classifier = BM25AgriculturalClassifier(
        model_path=model_path,
        threshold=0.98
    )

    # 测试字符串匹配问题
    test_texts = [
        ("This is about rice production and wheat farming techniques", "应该农业"),
        ("The price of the product is very reasonable", "应该非农业 - price不匹配rice"),
        ("The computer system has advanced features", "应该非农业 - system不匹配stem"),
        ("Modern agriculture includes irrigation and fertilization", "应该农业"),
        ("Botanical research focuses on plant species classification", "应该农业 - 植物学"),
        ("The operating system runs smoothly", "应该非农业"),
        ("The operation was successful", "应该非农业"),
        ("Stem cells have great potential in medicine", "应该非农业 - 医学语境"),
        ("Plant stems are important for water transport", "应该农业 - 植物学语境")
    ]

    print("\n=== BM25精确匹配测试 ===")
    for text, expected in test_texts:
        doc = DocumentInfo(
            id="test",
            text=text,
            char_length=len(text),
            estimated_tokens=len(text) // 4
        )

        result = classifier.classify_document(doc)

        print(f"文本: {text}")
        print(f"期望: {expected}")
        print(f"预测: {'农业' if result.is_agricultural else '非农业'}")
        print(f"BM25得分: {result.processing_details.get('bm25_score', 0):.2f}")
        print(f"匹配关键词: {result.processing_details.get('agriculture_keywords', [])}")
        print()