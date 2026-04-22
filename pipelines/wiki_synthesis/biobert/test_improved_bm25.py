#!/usr/bin/env python3
"""
测试改进后的BM25分类器对商业语境的处理
"""
import sys
import os
sys.path.append(os.path.join(os.path.dirname(__file__), 'src'))

from src.models.bm25_agriculture_classifier import BM25AgriculturalClassifier, DocumentInfo
import logging

def test_business_context_cases():
    """测试商业语境案例"""
    logging.basicConfig(level=logging.INFO)

    print("=== 测试改进后的BM25分类器对商业语境的处理 ===\n")

    classifier = BM25AgriculturalClassifier(
        model_path=os.getenv("BIIOBERT_MODEL_PATH", "best_model.bin"),
        threshold=0.98
    )

    # 测试案例
    test_cases = [
        # 原始问题案例
        {
            "text": """Shelly Gauna is a well-known business professional and entrepreneur from Detroit,
            Michigan. She has extensive experience in business development and has contributed significantly
            to the economic growth of the region. Her expertise includes market analysis, business strategy,
            and corporate development. She has been recognized for her work in food production industry
            development and has helped numerous companies establish their presence in the market.""",
            "expected": "非农业",
            "reason": "商业人物传记，food production在商业语境下"
        },

        # 真正的农业内容
        {
            "text": """Modern agricultural techniques include irrigation systems, crop rotation, and
            sustainable farming practices. Farmers use various methods to improve soil fertility and
            increase crop yields. Food production has become more efficient with the introduction
            of mechanized farming equipment and advanced pest management strategies.""",
            "expected": "农业",
            "reason": "真正的农业生产技术"
        },

        # 更多商业语境测试
        {
            "text": """The food industry is a major economic sector that includes food processing companies,
            food service establishments, and food retail chains. Food production facilities are
            important for the food company supply chain and commercial food distribution.""",
            "expected": "非农业",
            "reason": "食品工业和商业语境"
        },

        # 植物学内容（应该算农业）
        {
            "text": """Plant physiology studies how plants function, including photosynthesis, nutrient
            uptake, and growth patterns. Plant species classification helps scientists understand
            the relationships between different plants and their ecological roles in natural habitats.""",
            "expected": "农业",
            "reason": "植物学内容，属于泛农业"
        }
    ]

    print(f"测试案例数量: {len(test_cases)}\n")

    correct_count = 0
    for i, test_case in enumerate(test_cases, 1):
        doc = DocumentInfo(
            id=f"test_case_{i}",
            text=test_case["text"],
            char_length=len(test_case["text"]),
            estimated_tokens=len(test_case["text"]) // 4
        )

        result = classifier.classify_document(doc)

        predicted = "农业" if result.is_agricultural else "非农业"
        is_correct = predicted == test_case["expected"]

        if is_correct:
            correct_count += 1

        print(f"案例 {i}: {test_case['reason']}")
        print(f"期望: {test_case['expected']}")
        print(f"预测: {predicted}")
        print(f"正确: {'✓' if is_correct else '✗'}")
        print(f"BM25得分: {result.processing_details.get('bm25_score', 0):.2f}")
        print(f"匹配关键词: {result.processing_details.get('agriculture_keywords', [])[:5]}")
        print(f"概率: {result.probability:.3f}")
        print("-" * 60)

    print(f"\n测试结果:")
    print(f"正确: {correct_count}/{len(test_cases)} ({correct_count/len(test_cases)*100:.1f}%)")

    if correct_count == len(test_cases):
        print("🎉 所有测试案例都通过！改进后的BM25分类器成功解决了商业语境误匹配问题。")
    else:
        print("⚠️ 仍有部分案例分类错误，需要进一步优化。")

if __name__ == "__main__":
    test_business_context_cases()