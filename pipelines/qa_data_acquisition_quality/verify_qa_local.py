#!/usr/bin/env python3

import json
import os
import sys
import jsonlines
from pathlib import Path
from dotenv import load_dotenv
load_dotenv(Path(__file__).parent / ".env")
try:
    import torch
    from transformers import AutoModelForCausalLM, AutoTokenizer, TextStreamer
except ImportError:
    torch = None
from tqdm import tqdm
import logging
from typing import List, Dict, Any
import argparse

import call_api


logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class Qwen3QAVerifier:
    def __init__(self, model_name: str, model_path: str, key: str):
        """
        初始化本地Qwen3模型
        
        Args:
            model_path: 模型本地路径
            device: 设备 (cuda:0, cpu, auto)
        """
        logger.info(f"加载模型: {model_path}")
        
        self.model_api = model_path
        
        self.generation_config = {
            "max_new_tokens": 1024,
            "temperature": 0.3,
            "top_p": 0.9,
            "do_sample": True,
            "repetition_penalty": 1.1,
        }
        
        logger.info("模型加载完成")

        self.PC = call_api.ProxyCaller("external", self.model_api, key, model=model_name)
    
    def generate_prompt(self, instruction: str, output: str) -> str:
        """构建评估提示"""
        prompt = f"""请评估以下问答对的质量，给出详细分析和评分（1-5分）。

问题: {instruction}

回答: {output}

请从以下维度进行评估:
1. 答案准确性 (1-5分): 回答是否正确、准确？
2. 相关性 (1-5分): 回答是否直接回应问题？
3. 完整性 (1-5分): 回答是否完整、全面？
4. 清晰度 (1-5分): 回答是否清晰、易懂？

请按照以下格式输出:
## 分析
[详细的分析说明]

## 评分
- 准确性: [分数]
- 相关性: [分数]
- 完整性: [分数]
- 清晰度: [分数]
- 总分: [平均分]

## 建议
[改进建议]
"""
        return prompt
    
    def extract_scores(self, response: str) -> Dict:
        """从模型回复中提取评分"""
        scores = {
            "accuracy": 0,
            "relevance": 0,
            "completeness": 0,
            "clarity": 0,
            "total": 0
        }
        
        try:
            lines = response.split('\n')
            for line in lines:
                line = line.strip()
                if '准确性:' in line:
                    scores['accuracy'] = float(line.split(':')[1].strip())
                elif '相关性:' in line:
                    scores['relevance'] = float(line.split(':')[1].strip())
                elif '完整性:' in line:
                    scores['completeness'] = float(line.split(':')[1].strip())
                elif '清晰度:' in line:
                    scores['clarity'] = float(line.split(':')[1].strip())
            total_score = (scores['accuracy'] + scores['relevance'] + scores['completeness'] + scores['clarity']) / 4
            scores['total'] = round(total_score, 1) 
        
        except:
            pass
        
        return scores
    
    def verify_single(self, instruction: str, output: str) -> Dict[str, Any]:
        """验证单个QA对"""
        try:
            prompt = self.generate_prompt(instruction, output)

            R = self.PC(prompt, enable_thinking=True)
            response = R['content']
            
            scores = self.extract_scores(response)
            
            return {
                "instruction": instruction,
                "output": output,
                "verification": {
                    "model_response": response,
                    "scores": scores,
                    "is_passing": scores['total'] >= 3.5 if scores['total'] > 0 else False
                }
            }
            
        except Exception as e:
            logger.error(f"验证失败: {e}")
            return {
                "instruction": instruction,
                "output": output,
                "verification": {
                    "error": str(e),
                    "scores": {
                        "accuracy": 0,
                        "relevance": 0,
                        "completeness": 0,
                        "clarity": 0,
                        "total": 0
                    },
                    "is_passing": False
                }
            }
    
    def verify_batch(self, qa_pairs: List[Dict], batch_size: int = 2) -> List[Dict]:
        """批量验证QA对"""
        results = []
        
        # 分批处理
        for i in tqdm(range(0, len(qa_pairs), batch_size), desc="验证QA对"):
            batch = qa_pairs[i:i+batch_size]
            
            for qa in batch:
                result = self.verify_single(
                    qa.get("instruction", ""),
                    qa.get("output", "")
                )
                results.append(result)

                if len(results) % 10 == 0:
                    self._save_checkpoint(results, f"checkpoint_{len(results)}.jsonl")
        
        return results
    
    def _save_checkpoint(self, results: List, filename: str):
        """保存检查点"""
        output_dir = Path("outputs/checkpoints")
        output_dir.mkdir(parents=True, exist_ok=True)
        
        with jsonlines.open(output_dir / filename, 'w') as f:
            for result in results:
                f.write(result)

def main():
    parser = argparse.ArgumentParser(description="QA质量验证工具")
    parser.add_argument("--input", default="examples/sample_qa.jsonl", help="输入QA JSONL文件路径")
    parser.add_argument("--output", default="outputs/verified_qa.jsonl", help="输出文件路径")
    parser.add_argument("--model-name", default="qwen3-30b-a3b-instruct-2507", help="模型名称")
    parser.add_argument("--model-path", default=None, help="模型API地址（默认从.env读取 OPENAI_BASE_URL）")
    parser.add_argument("--batch-size", type=int, default=3, help="批处理大小")
    args = parser.parse_args()

    # 配置参数
    MODEL_NAME = args.model_name
    MODEL_PATH = args.model_path or os.getenv("OPENAI_BASE_URL", "")
    API_KEY = os.getenv("OPENAI_API_KEY", "")
    QA_FILE = args.input
    OUTPUT_FILE = args.output
    BATCH_SIZE = args.batch_size

    if not MODEL_PATH:
        logger.error("未设置模型API地址，请通过 --model-path 参数或 OPENAI_BASE_URL 环境变量设置")
        sys.exit(1)

    # 加载QA数据
    logger.info(f"加载QA数据: {QA_FILE}")
    qa_pairs = []
    with jsonlines.open(QA_FILE) as f:
        for item in f:
            qa_pairs.append(item)

    logger.info(f"加载了 {len(qa_pairs)} 个QA对")

    # 初始化验证器
    verifier = Qwen3QAVerifier(
        model_name=MODEL_NAME,
        model_path=MODEL_PATH,
        key=API_KEY
    )
    
    # 执行验证
    results = verifier.verify_batch(qa_pairs, batch_size=BATCH_SIZE)
    
    # 保存结果
    logger.info(f"保存结果到: {OUTPUT_FILE}")
    with jsonlines.open(OUTPUT_FILE, 'w') as f:
        for result in results:
            f.write(result)
    
    # 生成统计报告
    generate_statistics(results)

def generate_statistics(results: List[Dict]):
    """生成统计报告"""
    total = len(results)
    passing = sum(1 for r in results if r['verification'].get('is_passing', False))
    avg_scores = {
        'accuracy': 0,
        'relevance': 0,
        'completeness': 0,
        'clarity': 0,
        'total': 0
    }
    
    valid_results = []
    for r in results:
        scores = r['verification'].get('scores', {})
        if scores.get('total', 0) > 0:
            valid_results.append(r)
            for key in avg_scores:
                avg_scores[key] += scores.get(key, 0)
    
    valid_count = len(valid_results)
    if valid_count > 0:
        for key in avg_scores:
            avg_scores[key] /= valid_count
    
    report = {
        "total_qa_pairs": total,
        "valid_verifications": valid_count,
        "passing_rate": passing / total if total > 0 else 0,
        "average_scores": avg_scores,
        "passing_count": passing,
        "failing_count": total - passing
    }
    
    report_dir = Path(__file__).parent / "outputs"
    report_dir.mkdir(parents=True, exist_ok=True)
    with open(report_dir / "qa_verification_report.json", 'w', encoding='utf-8') as f:
        json.dump(report, f, indent=2, ensure_ascii=False)
    
    print("\n" + "="*50)
    print("QA对验证报告")
    print("="*50)
    print(f"总QA对: {total}")
    print(f"通过数量: {passing}")
    print(f"通过率: {report['passing_rate']:.2%}")
    print(f"平均总分: {avg_scores['total']:.2f}")
    print(f"准确性: {avg_scores['accuracy']:.2f}")
    print(f"相关性: {avg_scores['relevance']:.2f}")
    print(f"完整性: {avg_scores['completeness']:.2f}")
    print(f"清晰度: {avg_scores['clarity']:.2f}")
    print("="*50)

if __name__ == "__main__":
    main()