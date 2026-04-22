"""
主要的分类处理脚本
使用BioBERT模型对Dolma1.7维基百科文档进行农业内容分类
"""
import os
import sys
import json
import logging
import time
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Any
import argparse

# 添加src路径
sys.path.append(os.path.join(os.path.dirname(__file__), 'src'))

from data.loader import DataLoader, DocumentInfo
from models.strict_keyword_classifier import StrictKeywordAgriculturalClassifier, ClassificationResult

class AgriculturalContentClassifier:
    """农业内容分类器主程序"""

    def __init__(self,
                 model_path: str,
                 data_dir: str,
                 output_dir: str = "output",
                 threshold: float = 0.6,
                 batch_size_gb: float = 2.0):

        self.model_path = model_path
        self.data_dir = data_dir
        self.output_dir = Path(output_dir)
        self.threshold = threshold
        self.batch_size_gb = batch_size_gb

        # 创建输出目录
        self.output_dir.mkdir(exist_ok=True)
        (self.output_dir / "agricultural_content").mkdir(exist_ok=True)
        (self.output_dir / "processing_logs").mkdir(exist_ok=True)
        (self.output_dir / "statistics").mkdir(exist_ok=True)

        # 设置日志
        self._setup_logging()

        # 初始化组件
        self.data_loader = DataLoader(data_dir)
        self.classifier = StrictKeywordAgriculturalClassifier(
            model_path=model_path,
            threshold=threshold
        )

        # 统计信息
        self.stats = {
            'total_documents': 0,
            'agricultural_documents': 0,
            'non_agricultural_documents': 0,
            'processing_time': 0,
            'errors': 0,
            'batches_processed': 0,
            'files_processed': 0,
            'start_time': None,
            'end_time': None
        }

    def _setup_logging(self):
        """设置日志"""
        log_file = self.output_dir / "processing_logs" / f"classification_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"

        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
            handlers=[
                logging.FileHandler(log_file, encoding='utf-8'),
                logging.StreamHandler()
            ]
        )

        self.logger = logging.getLogger(__name__)

    def save_agricultural_document(self, doc: DocumentInfo, result: ClassificationResult, batch_num: int):
        """保存农业相关文档"""
        # 构建输出文档
        output_doc = {
            "original_data": {
                "id": doc.id,
                "text": doc.text,
                "title": doc.title,
                "url": doc.url,
                "source": doc.source,
                "language": doc.language,
                "char_length": doc.char_length,
                "estimated_tokens": doc.estimated_tokens,
                "file_path": doc.file_path
            },
            "classification": {
                "is_agricultural": result.is_agricultural,
                "confidence": result.confidence,
                "probability": result.probability,
                "processing_details": result.processing_details
            },
            "timestamp": datetime.now().isoformat()
        }

        # 保存到批次文件夹
        batch_dir = self.output_dir / "agricultural_content" / f"batch_{batch_num:04d}"
        batch_dir.mkdir(exist_ok=True)

        filename = f"{doc.id.replace('/', '_')}.json"
        output_file = batch_dir / filename

        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(output_doc, f, ensure_ascii=False, indent=2)

    def process_batch(self, file_batch: List[Path], batch_num: int) -> Dict:
        """处理一个文件批次"""
        batch_stats = {
            'documents_processed': 0,
            'agricultural_found': 0,
            'non_agricultural': 0,
            'errors': 0,
            'processing_time': 0
        }

        start_time = time.time()
        self.logger.info(f"开始处理批次 {batch_num} ({len(file_batch)} 个文件)")

        for file_path in file_batch:
            try:
                self.logger.info(f"处理文件: {file_path.name}")
                file_agri_count = 0

                for doc in self.data_loader.load_documents_from_file(file_path):
                    try:
                        # 分类文档
                        result = self.classifier.classify_document(doc)

                        # 更新统计
                        batch_stats['documents_processed'] += 1
                        if result.is_agricultural == 1:
                            batch_stats['agricultural_found'] += 1
                            self.stats['agricultural_documents'] += 1
                            file_agri_count += 1

                            # 保存农业文档
                            self.save_agricultural_document(doc, result, batch_num)
                        else:
                            batch_stats['non_agricultural'] += 1
                            self.stats['non_agricultural_documents'] += 1

                        # 每1000个文档报告一次进度
                        if batch_stats['documents_processed'] % 1000 == 0:
                            self.logger.info(f"已处理 {batch_stats['documents_processed']} 个文档，发现 {batch_stats['agricultural_found']} 个农业相关")

                    except Exception as e:
                        self.logger.error(f"处理文档 {doc.id} 时出错: {e}")
                        batch_stats['errors'] += 1
                        self.stats['errors'] += 1

                self.logger.info(f"文件 {file_path.name} 完成，发现 {file_agri_count} 个农业相关文档")

            except Exception as e:
                self.logger.error(f"处理文件 {file_path} 时出错: {e}")
                batch_stats['errors'] += 1
                self.stats['errors'] += 1

        batch_stats['processing_time'] = time.time() - start_time
        self.logger.info(f"批次 {batch_num} 完成: {batch_stats}")

        return batch_stats

    def save_statistics(self):
        """保存统计信息"""
        self.stats['end_time'] = datetime.now().isoformat()
        if self.stats['start_time']:
            start = datetime.fromisoformat(self.stats['start_time'])
            end = datetime.fromisoformat(self.stats['end_time'])
            self.stats['processing_time'] = (end - start).total_seconds()

        stats_file = self.output_dir / "statistics" / "classification_stats.json"
        with open(stats_file, 'w', encoding='utf-8') as f:
            json.dump(self.stats, f, ensure_ascii=False, indent=2)

        # 打印总结
        print("\n" + "="*50)
        print("分类完成总结:")
        print(f"总文档数: {self.stats['total_documents']:,}")
        print(f"农业相关: {self.stats['agricultural_documents']:,} ({self.stats['agricultural_documents']/self.stats['total_documents']*100:.1f}%)")
        print(f"非农业: {self.stats['non_agricultural_documents']:,} ({self.stats['non_agricultural_documents']/self.stats['total_documents']*100:.1f}%)")
        print(f"处理时间: {self.stats['processing_time']:.1f}秒")
        print(f"处理速度: {self.stats['total_documents']/self.stats['processing_time']:.1f}文档/秒")
        print(f"错误数: {self.stats['errors']}")
        print("="*50)

    def _clear_old_output(self):
        """清空旧的输出文件"""
        import shutil
        import glob

        dirs_to_clear = [
            self.output_dir / "agricultural_content",
            self.output_dir / "processing_logs"
        ]

        for dir_path in dirs_to_clear:
            if dir_path.exists():
                self.logger.info(f"清空旧文件: {dir_path}")
                # 先删除所有文件和子目录
                for item in dir_path.glob('*'):
                    if item.is_file():
                        item.unlink()
                    elif item.is_dir():
                        shutil.rmtree(item)

        # 清空统计目录但保留目录结构
        stats_dir = self.output_dir / "statistics"
        if stats_dir.exists():
            for file_path in stats_dir.glob("*.json"):
                file_path.unlink()
                self.logger.info(f"删除统计文件: {file_path}")

        self.logger.info("旧文件清空完成")

    def run_classification(self):
        """运行完整的分类流程"""
        self.logger.info("开始农业内容分类流程")

        # 清空旧文件
        self._clear_old_output()

        self.stats['start_time'] = datetime.now().isoformat()

        # 获取文件批次
        file_batches = list(self.data_loader.get_batch_files(self.batch_size_gb))
        total_batches = len(file_batches)

        self.logger.info(f"总共 {total_batches} 个批次，每批约 {self.batch_size_gb}GB")

        # 处理每个批次
        for batch_num, file_batch in enumerate(file_batches, 1):
            batch_stats = self.process_batch(file_batch, batch_num)

            # 更新全局统计
            self.stats['total_documents'] += batch_stats['documents_processed']
            self.stats['batches_processed'] = batch_num
            self.stats['files_processed'] += len(file_batch)

            # 保存中间统计
            if batch_num % 5 == 0 or batch_num == total_batches:
                self.save_statistics()
                self.logger.info(f"已完成 {batch_num}/{total_batches} 批次")

        # 最终统计
        self.save_statistics()
        self.logger.info("分类流程完成")

def main():
    parser = argparse.ArgumentParser(description="BioBERT农业内容分类器")
    parser.add_argument("--model-path", default="best_model.bin", help="模型权重文件路径")
    parser.add_argument("--data-dir", default=os.getenv("WIKI_DATA_DIR", "examples"), help="数据目录")
    parser.add_argument("--output-dir", default="output", help="输出目录")
    parser.add_argument("--threshold", type=float, default=0.6, help="分类阈值")
    parser.add_argument("--batch-size", type=float, default=2.0, help="每批处理数据大小(GB)")

    args = parser.parse_args()

    # 检查输入
    if not os.path.exists(args.model_path):
        print(f"错误: 模型文件 {args.model_path} 不存在")
        sys.exit(1)

    if not os.path.exists(args.data_dir):
        print(f"错误: 数据目录 {args.data_dir} 不存在")
        sys.exit(1)

    # 创建分类器并运行
    try:
        classifier = AgriculturalContentClassifier(
            model_path=args.model_path,
            data_dir=args.data_dir,
            output_dir=args.output_dir,
            threshold=args.threshold,
            batch_size_gb=args.batch_size
        )

        classifier.run_classification()

    except KeyboardInterrupt:
        print("\n用户中断分类流程")
        sys.exit(1)
    except Exception as e:
        print(f"分类流程出错: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()