"""
测试分类器在实际数据上的效果
"""
import os
import sys
import logging
from pathlib import Path

# 添加src路径
sys.path.append(os.path.join(os.path.dirname(__file__), 'src'))

from data.loader import DataLoader, DocumentInfo
from models.biobert_classifier import BioBERTClassifier

def test_on_sample_data():
    """在样本数据上测试分类器"""
    logging.basicConfig(level=logging.INFO)
    logger = logging.getLogger(__name__)

    print("=== 测试BioBERT分类器在真实数据上的效果 ===")

    # 初始化组件
    data_dir = os.getenv("WIKI_DATA_DIR", "examples")
    loader = DataLoader(data_dir)
    classifier = BioBERTClassifier(
        model_path="best_model.bin",
        threshold=0.6
    )

    # 获取第一个文件的一些文档进行测试
    files = loader.get_file_list()
    test_file = files[0]  # 第一个文件

    print(f"\n测试文件: {test_file.name}")
    print(f"文件大小: {test_file.stat().st_size / (1024**2):.1f} MB")

    # 处理前20个文档
    docs_processed = 0
    agri_found = 0
    max_docs = 20

    for doc in loader.load_documents_from_file(test_file):
        if docs_processed >= max_docs:
            break

        # 分类文档
        result = classifier.classify_document(doc)

        print(f"\n--- 文档 {docs_processed + 1} ---")
        print(f"ID: {doc.id}")
        print(f"标题: {doc.title}")
        print(f"长度: {doc.char_length} 字符 (约{doc.estimated_tokens} tokens)")
        print(f"分类: {'农业' if result.is_agricultural else '非农业'}")
        print(f"置信度: {result.confidence:.3f}")
        print(f"农业概率: {result.probability:.3f}")
        print(f"处理策略: {result.processing_details['strategy']}")

        # 显示文本预览
        preview = doc.text[:200].replace('\n', ' ')
        print(f"内容预览: {preview}...")

        if result.is_agricultural == 1:
            agri_found += 1

        docs_processed += 1

    print(f"\n=== 测试结果 ===")
    print(f"处理文档数: {docs_processed}")
    print(f"农业相关: {agri_found}")
    print(f"农业比例: {agri_found/docs_processed*100:.1f}%")

def test_long_document():
    """测试长文档处理"""
    logging.basicConfig(level=logging.INFO)

    print("\n=== 测试长文档分层处理 ===")

    # 创建一个长文档（模拟）
    long_text = """
    Agriculture and farming have been fundamental to human civilization for thousands of years. Modern agricultural practices include crop rotation, irrigation systems, and the use of advanced machinery. Farmers today face challenges such as climate change, soil degradation, and the need for sustainable practices.

    The development of new crop varieties through genetic engineering has revolutionized food production. These genetically modified crops can resist pests, survive drought conditions, and provide higher yields. However, there are ongoing debates about the safety and environmental impact of GMOs.

    Sustainable agriculture focuses on maintaining soil health, conserving water, and reducing chemical inputs. Organic farming methods avoid synthetic pesticides and fertilizers, instead relying on natural methods to control pests and maintain soil fertility.

    The future of agriculture lies in precision farming, which uses GPS technology, sensors, and data analytics to optimize crop management. Drones and autonomous vehicles are being deployed for monitoring and harvesting operations.

    Agricultural economics plays a crucial role in global trade and food security. Government policies, subsidies, and international agreements all influence farming practices and food distribution systems.
    """ * 10  # 重复10次创建长文档

    from models.biobert_classifier import DocumentInfo

    doc = DocumentInfo(
        id="long_test_doc",
        text=long_text,
        char_length=len(long_text),
        estimated_tokens=len(long_text) // 4
    )

    classifier = BioBERTClassifier(
        model_path="best_model.bin",
        threshold=0.6
    )

    print(f"文档长度: {doc.char_length} 字符 (约{doc.estimated_tokens} tokens)")

    result = classifier.classify_document(doc)

    print(f"\n分类结果:")
    print(f"分类: {'农业' if result.is_agricultural else '非农业'}")
    print(f"置信度: {result.confidence:.3f}")
    print(f"农业概率: {result.probability:.3f}")
    print(f"处理策略: {result.processing_details['strategy']}")

    details = result.processing_details
    if 'first_section_prob' in details:
        print(f"第一层概率: {details['first_section_prob']:.3f}")
    if 'key_sections_analyzed' in details:
        print(f"分析的关键章节数: {details['key_sections_analyzed']}")
    if 'section_probabilities' in details:
        print(f"章节概率: {[f'{p:.3f}' for p in details['section_probabilities']]}")

if __name__ == "__main__":
    test_on_sample_data()
    test_long_document()