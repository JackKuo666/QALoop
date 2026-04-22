import json
import pandas as pd
import os
import sys
import asyncio
from typing import List, Dict, Any, Optional
from dataclasses import asdict
from collections import defaultdict, Counter
from pathlib import Path
import logging

# Add the project root to the Python path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from src.core.qa_generator_v2 import DeepSeekGenerator, SeedQuestion, GeneratedQA, GenerationMethod

logger = logging.getLogger(__name__)

class QualityFilter:
    def __init__(self):
        self.quality_rules = self._initialize_quality_rules()
        self.filter_stats = {
            "total_processed": 0,
            "passed_quality": 0,
            "failed_quality": 0,
            "common_issues": Counter()
        }
    
    def _initialize_quality_rules(self):
        return {
            "min_length": {
                "question": 5,  # 降低最小长度要求
                "answer": 15    # 降低最小长度要求
            },
            "max_length": {
                "question": 500,
                "answer": 8000  # 增加上限（API支持8000 tokens）
            },
            "required_elements": {
                "question": ["?", "？", "什么", "如何", "为什么", "怎样", "哪些", "请", "解释", "介绍"],
                "answer": []
            },
            "banned_phrases": [
                "我不知道", "我不确定", "这个问题很难", "作为AI模型",
                "根据我的训练数据", "我无法回答", "抱歉", "很抱歉",
                "作为一个大语言模型", "在我的知识库中", "AI模型"
            ],
            "similarity_threshold": 0.8
        }
    
    def filter_qa_pairs(self, qa_pairs: List[GeneratedQA]) -> List[GeneratedQA]:
        if not qa_pairs:
            return []
            
        filtered_pairs = []
        
        for qa in qa_pairs:
            self.filter_stats["total_processed"] += 1
            
            if self._passes_quality_check(qa):
                filtered_pairs.append(qa)
                self.filter_stats["passed_quality"] += 1
            else:
                self.filter_stats["failed_quality"] += 1
        
        logger.info(f"质量过滤: 处理 {self.filter_stats['total_processed']} 个，通过 {self.filter_stats['passed_quality']} 个，过滤 {self.filter_stats['failed_quality']} 个")
        return filtered_pairs
    
    def _passes_quality_check(self, qa_pair: GeneratedQA) -> bool:
        question = qa_pair.question.strip()
        answer = qa_pair.answer.strip()
        
        # 检查空值
        if not question or not answer:
            self.filter_stats["common_issues"]["empty_content"] += 1
            return False
            
        # 检查问题长度
        if len(question) < self.quality_rules["min_length"]["question"]:
            self.filter_stats["common_issues"]["question_too_short"] += 1
            return False
            
        if len(answer) < self.quality_rules["min_length"]["answer"]:
            self.filter_stats["common_issues"]["answer_too_short"] += 1
            return False
            
        if len(question) > self.quality_rules["max_length"]["question"]:
            self.filter_stats["common_issues"]["question_too_long"] += 1
            return False
            
        if len(answer) > self.quality_rules["max_length"]["answer"]:
            self.filter_stats["common_issues"]["answer_too_long"] += 1
            return False
        
        # 检查问题格式 - 放宽要求
        required_elements = self.quality_rules["required_elements"]["question"]
        if required_elements and not any(element in question for element in required_elements):
            # 警告但不拒绝
            logger.debug(f"问题可能格式不佳: {question}")
        
        # 检查禁止短语
        banned_phrases = self.quality_rules["banned_phrases"]
        if any(phrase in answer for phrase in banned_phrases):
            self.filter_stats["common_issues"]["banned_phrases"] += 1
            return False
        
        # 检查是否与种子问题相同
        if question == qa_pair.seed_question:
            self.filter_stats["common_issues"]["duplicate_question"] += 1
            return False
        
        # 检查回答详细程度 - 降低要求
        if len(answer.split()) < 5:  # 降低到至少5个词
            self.filter_stats["common_issues"]["answer_too_brief"] += 1
            return False
        
        return True
    
    def get_quality_report(self) -> Dict:
        total_processed = self.filter_stats["total_processed"]
        if total_processed > 0:
            pass_rate = (self.filter_stats["passed_quality"] / total_processed) * 100
        else:
            pass_rate = 0
        
        return {
            "quality_rules": self.quality_rules,
            "statistics": dict(self.filter_stats),
            "pass_rate": f"{pass_rate:.1f}%",
            "pass_rate_numeric": pass_rate,
            "common_issues": dict(self.filter_stats["common_issues"].most_common(10))
        }

class DiversityAnalyzer:
    def __init__(self):
        self.analysis_results = {}
    
    def analyze_diversity(self, qa_pairs: List[GeneratedQA]) -> Dict:
        if not qa_pairs:
            return {
                "total_pairs": 0,
                "unique_seeds": 0,
                "method_distribution": {},
                "difficulty_distribution": {},
                "category_distribution": {},
                "length_statistics": {},
                "diversity_score": 0
            }
        
        method_distribution = Counter([qa.generation_method for qa in qa_pairs])
        difficulty_distribution = Counter([qa.difficulty for qa in qa_pairs])
        category_distribution = Counter([qa.category for qa in qa_pairs])
        
        question_lengths = [len(qa.question) for qa in qa_pairs]
        answer_lengths = [len(qa.answer) for qa in qa_pairs]
        
        unique_seeds = len(set([qa.seed_id for qa in qa_pairs]))
        
        diversity_score = self._calculate_diversity_score(
            len(qa_pairs), 
            method_distribution, 
            category_distribution,
            unique_seeds
        )
        
        return {
            "total_pairs": len(qa_pairs),
            "unique_seeds": unique_seeds,
            "method_distribution": dict(method_distribution),
            "difficulty_distribution": dict(difficulty_distribution),
            "category_distribution": dict(category_distribution),
            "length_statistics": {
                "question_avg_length": sum(question_lengths) / len(question_lengths) if question_lengths else 0,
                "answer_avg_length": sum(answer_lengths) / len(answer_lengths) if answer_lengths else 0,
                "question_min_length": min(question_lengths) if question_lengths else 0,
                "question_max_length": max(question_lengths) if question_lengths else 0
            },
            "diversity_score": diversity_score
        }
    
    def _calculate_diversity_score(self, total_pairs: int, method_dist: Counter, 
                                 category_dist: Counter, unique_seeds: int) -> float:
        if total_pairs == 0:
            return 0.0
            
        # 方法多样性
        method_diversity = len(method_dist) / len(GenerationMethod) if GenerationMethod else 1.0
        
        # 类别多样性
        category_diversity = len(category_dist) / max(unique_seeds, 1)
        
        # 种子多样性
        seed_diversity = unique_seeds / max(total_pairs, 1)
        
        # 综合多样性分数
        diversity_score = (method_diversity * 0.4 + category_diversity * 0.3 + seed_diversity * 0.3) * 100
        
        return round(diversity_score, 2)

class BatchQAGenerator:
    def __init__(self, generator: DeepSeekGenerator, output_dir: str = "output", target_species: str = None):
        self.generator = generator
        self.quality_filter = QualityFilter()
        self.diversity_analyzer = DiversityAnalyzer()
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(exist_ok=True)
        self.target_species = target_species  # 目标物种，根据输入种子文件决定

        logger.info("批量QA生成器初始化完成")
    
    def generate_from_seeds(self,
                          seed_questions: List[SeedQuestion],
                          variants_per_seed: int = 5,
                          methods: List[GenerationMethod] = None,
                          batch_size: int = 10,
                          species_ratios: Optional[Dict[str, float]] = None,
                          subspecies_ratios: Optional[Dict[str, Dict[str, float]]] = None,
                          enhanced_seeds: Optional[List[Dict[str, Any]]] = None) -> Dict[str, Any]:
        """
        批量生成QA对

        Args:
            seed_questions: 种子问题列表
            variants_per_seed: 每个种子问题生成的变体数量
            methods: 使用的生成方法
            batch_size: 批处理大小
            species_ratios: 物种比例控制字典
            subspecies_ratios: 物种内子类别比例控制字典
            enhanced_seeds: 增强后的种子问题列表，包含RAG上下文等额外信息
        """
        if methods is None:
            methods = [
                GenerationMethod.PARAPHRASE,
                GenerationMethod.ELABORATION,
                GenerationMethod.PERSPECTIVE_SHIFT,
                GenerationMethod.SCENARIO_APPLICATION
            ]

        # 如果提供了物种比例，先分析种子问题并调整每个种子的变体数量
        seed_variants_map = self._calculate_variants_by_species(
            seed_questions, variants_per_seed, species_ratios, subspecies_ratios
        )

        all_generated = []
        generation_stats = {
            "total_seeds": len(seed_questions),
            "successful_generations": 0,
            "failed_generations": 0,
            "total_generated": 0,
            "total_generated_before_filter": 0,
            "by_category": defaultdict(int),
            "by_method": defaultdict(int),
            "by_difficulty": defaultdict(int)
        }

        logger.info(f"开始批量生成，种子问题数量: {len(seed_questions)}")
        logger.info(f"使用生成方法: {[method.value for method in methods]}")
        if species_ratios:
            logger.info(f"物种比例控制: {species_ratios}")
        
        for i in range(0, len(seed_questions), batch_size):
            batch = seed_questions[i:i + batch_size]
            batch_num = i // batch_size + 1
            total_batches = (len(seed_questions) - 1) // batch_size + 1
            logger.info(f"处理批次 {batch_num}/{total_batches}")

            for j, seed in enumerate(batch):
                seed_index = i + j + 1
                try:
                    # 获取该种子问题应生成的变体数量
                    # seed_variants_map使用索引作为键
                    seed_variants = seed_variants_map.get(seed_index, variants_per_seed)
                    logger.info(f"处理种子 {seed_index}/{len(seed_questions)}: {seed.question[:50]}... (变体数: {seed_variants})")

                    # 生成QA对
                    generated = self.generator.generate_from_seed(
                        seed_question=seed,
                        methods=methods,
                        num_variants=seed_variants
                    )

                    generation_stats["total_generated_before_filter"] += len(generated)

                    # 质量过滤
                    filtered = self.quality_filter.filter_qa_pairs(generated)

                    all_generated.extend(filtered)
                    generation_stats["successful_generations"] += 1
                    generation_stats["total_generated"] += len(filtered)

                    self._update_stats(generation_stats, seed, filtered)

                    logger.info(f"种子 {seed_index}/{len(seed_questions)}: 生成 {len(generated)} → 过滤后 {len(filtered)} 个QA对")

                except Exception as e:
                    generation_stats["failed_generations"] += 1
                    logger.error(f"种子问题生成失败: {seed.question[:50]}... 错误: {e}")
                    import traceback
                    logger.debug(traceback.format_exc())
                    continue
        
        # 生成报告
        diversity_report = self.diversity_analyzer.analyze_diversity(all_generated)
        quality_report = self.quality_filter.get_quality_report()
        
        # 保存结果
        self._save_results(all_generated, generation_stats, diversity_report, quality_report)
        
        logger.info(f"批量生成完成: 成功 {generation_stats['successful_generations']}, "
                   f"失败 {generation_stats['failed_generations']}, "
                   f"生成 {generation_stats['total_generated_before_filter']} → 过滤后 {generation_stats['total_generated']} 个QA对")
        
        return {
            "generated_qa_pairs": all_generated,
            "generation_stats": generation_stats,
            "diversity_report": diversity_report,
            "quality_report": quality_report
        }
    
    def _update_stats(self, stats: Dict, seed: SeedQuestion, generated: List[GeneratedQA]):
        stats["by_category"][seed.category] += len(generated)

        for qa_pair in generated:
            stats["by_method"][qa_pair.generation_method] += 1
            stats["by_difficulty"][qa_pair.difficulty] += 1

    # ---------- 异步批处理 ----------
    async def generate_from_seeds_async(self,
                                       seed_questions: List[SeedQuestion],
                                       variants_per_seed: int = 5,
                                       methods: List[GenerationMethod] = None,
                                       batch_size: int = 10,
                                       concurrent_batches: int = 3,  # 并发批次数
                                       species_ratios: Optional[Dict[str, float]] = None,
                                       subspecies_ratios: Optional[Dict[str, Dict[str, float]]] = None,
                                       difficulty_level: Optional[str] = None,
                                       enforce_species_consistency: bool = False) -> Dict[str, Any]:
        """
        异步批量生成QA对

        Args:
            seed_questions: 种子问题列表
            variants_per_seed: 每个种子问题生成的变体数量
            methods: 使用的生成方法
            batch_size: 批处理大小
            concurrent_batches: 并发批次数
            species_ratios: 物种比例控制字典
            subspecies_ratios: 物种内子类别比例控制字典
            enforce_species_consistency: 是否强制扩增问题的物种与种子问题物种一致
        """
        if methods is None:
            methods = [
                GenerationMethod.PARAPHRASE,
                GenerationMethod.ELABORATION,
                GenerationMethod.PERSPECTIVE_SHIFT,
                GenerationMethod.SCENARIO_APPLICATION
            ]

        # 如果提供了物种比例，先分析种子问题并调整每个种子的变体数量
        seed_variants_map = self._calculate_variants_by_species(
            seed_questions, variants_per_seed, species_ratios, subspecies_ratios
        )

        all_generated = []
        generation_stats = {
            "total_seeds": len(seed_questions),
            "successful_generations": 0,
            "failed_generations": 0,
            "total_generated": 0,
            "total_generated_before_filter": 0,
            "by_category": defaultdict(int),
            "by_method": defaultdict(int),
            "by_difficulty": defaultdict(int)
        }

        logger.info(f"开始异步批量生成，种子问题数量: {len(seed_questions)}")
        logger.info(f"使用生成方法: {[method.value for method in methods]}")
        logger.info(f"并发批次数: {concurrent_batches}")
        if species_ratios:
            logger.info(f"物种比例控制: {species_ratios}")

        # 分批处理，每批并发处理
        batches = []
        for i in range(0, len(seed_questions), batch_size):
            batch = seed_questions[i:i + batch_size]
            batches.append((i, batch))

        # 创建信号量限制并发数
        semaphore = asyncio.Semaphore(concurrent_batches)

        async def process_batch(batch_info):
            i, batch = batch_info
            async with semaphore:
                batch_results = []
                batch_num = i // batch_size + 1
                total_batches = len(batches)
                logger.info(f"处理异步批次 {batch_num}/{total_batches}")

                for j, seed in enumerate(batch):
                    seed_index = i + j + 1
                    try:
                        # 获取该种子问题应生成的变体数量
                        seed_variants = seed_variants_map.get(seed_index, variants_per_seed)
                        logger.info(f"异步生成种子 {seed_index}/{len(seed_questions)}: {seed.question[:50]}... (变体数: {seed_variants})")

                        # 异步生成QA对
                        generated = await self.generator.generate_from_seed_async(
                            seed_question=seed,
                            methods=methods,
                            num_variants=seed_variants,
                            difficulty_level=difficulty_level,
                            enforce_species_consistency=enforce_species_consistency
                        )

                        batch_results.extend(generated)
                        generation_stats["successful_generations"] += 1
                        generation_stats["total_generated"] += len(generated)
                        generation_stats["total_generated_before_filter"] += len(generated)
                        self._update_stats(generation_stats, seed, generated)

                        logger.info(f"  ✅ 成功生成 {len(generated)} 个QA对")

                    except Exception as e:
                        generation_stats["failed_generations"] += 1
                        logger.error(f"  ❌ 种子 {seed_index} 生成失败: {e}")
                        import traceback
                        traceback.print_exc()

                return batch_results

        # 并发执行所有批次
        logger.info(f"开始并发处理 {len(batches)} 个批次...")
        batch_tasks = [process_batch(batch) for batch in batches]
        batch_results = await asyncio.gather(*batch_tasks, return_exceptions=True)

        # 合并所有结果
        for result in batch_results:
            if isinstance(result, list):
                all_generated.extend(result)
            elif isinstance(result, Exception):
                logger.error(f"批次处理异常: {result}")

        logger.info(f"异步批量生成完成，总共生成了 {len(all_generated)} 个QA对")

        # 质量过滤和多样性分析
        quality_report = self.quality_filter.get_quality_report()
        diversity_report = self.diversity_analyzer.analyze_diversity(all_generated)

        # 更新统计信息
        generation_stats["by_category"] = dict(generation_stats["by_category"])
        generation_stats["by_method"] = dict(generation_stats["by_method"])
        generation_stats["by_difficulty"] = dict(generation_stats["by_difficulty"])

        # 保存结果
        self._save_results(all_generated, generation_stats, diversity_report, quality_report)

        return {
            "generation_stats": generation_stats,
            "diversity_report": diversity_report,
            "quality_report": quality_report
        }
    
    def _save_results(self, qa_pairs: List[GeneratedQA], stats: Dict,
                     diversity_report: Dict, quality_report: Dict):
        import pandas as pd
        from datetime import datetime

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

        # 按物种分类QA对
        qa_by_species = defaultdict(list)
        non_agricultural_count = 0  # 统计非农业类别数量

        for qa in qa_pairs:
            species = self._extract_species(qa)
            logger.debug(f"[DEBUG MAIN] QA pair extracted species: {species}")
            if species == "其他":
                # 跳过非农业类别
                logger.debug(f"[DEBUG MAIN] Filtering out non-agricultural QA pair")
                non_agricultural_count += 1
                continue
            qa_by_species[species].append(qa)

        logger.info(f"检测到 {len(qa_by_species)} 个农业物种，"
                   f"已过滤掉 {non_agricultural_count} 个非农业类别")

        if len(qa_by_species) == 0:
            logger.warning("未检测到任何农业物种，所有QA对已被过滤！")
            return

        logger.info(f"开始保存农业QA对...")

        # 创建输出目录
        self.output_dir.mkdir(parents=True, exist_ok=True)

        # 每个物种保存独立的JSONL文件
        total_saved = 0
        species_stats = {}

        for species, qa_list in qa_by_species.items():
            species_stats[species] = len(qa_list)
            # 保存JSONL格式，每个物种一个文件
            jsonl_file = self.output_dir / f"{species}_QA_集合_{timestamp}.jsonl"
            with open(jsonl_file, "w", encoding="utf-8") as f:
                for qa in qa_list:
                    qa_dict = asdict(qa)
                    # 确保seed_question字段只保存原始问题（不包含RAG增强内容）
                    if 'original_question' in qa_dict and qa_dict['original_question']:
                        qa_dict['seed_question'] = qa_dict['original_question']
                    # 确保中文正常显示
                    f.write(json.dumps(qa_dict, ensure_ascii=False) + "\n")
                    total_saved += 1

            logger.info(f"  {species}: {len(qa_list)} 个QA对已保存到 {jsonl_file.name}")

        logger.info(f"  总计: {total_saved} 个QA对已保存")

        # 确保报告包含RAG统计信息
        rag_enhanced_count = sum(1 for qa in qa_pairs if 'rag_enhanced' in qa.tags or 'needs_rag' in qa.tags)

        # 保存完整报告
        report = {
            "generation_stats": stats,
            "diversity_report": diversity_report,
            "quality_report": quality_report,
            "timestamp": timestamp,
            "total_qa_pairs": len(qa_pairs),
            "filtered_non_agricultural": non_agricultural_count,
            "agricultural_species_count": species_stats,
            "agricultural_species_list": list(qa_by_species.keys()),
            "rag_stats": {
                'rag_enhanced_pairs': rag_enhanced_count,
                'total_pairs': len(qa_pairs),
                'rag_usage_rate': f"{rag_enhanced_count/len(qa_pairs)*100:.1f}%" if qa_pairs else "0%",
                'rag_enabled': rag_enhanced_count > 0
            }
        }

        report_file = self.output_dir / f"generation_report_{timestamp}.json"
        with open(report_file, "w", encoding="utf-8") as f:
            json.dump(report, f, ensure_ascii=False, indent=2)

        logger.info(f"总报告已保存到 {report_file}")
        logger.info(f"农业QA对已保存到 {self.output_dir}")
        logger.info(f"农业物种列表: {', '.join(qa_by_species.keys())}")

    def _extract_species(self, qa: GeneratedQA) -> str:
        """
        从QA对中提取物种信息
        优先从seed_question或seed_answer中查找已知物种关键词
        只返回真正的农业物种，排除非农业类别
        """
        # 已知农业物种关键词映射（只包含农业物种）
        species_keywords = {
            "玉米": [
                "玉米", "苞米", "苞谷", "玉蜀黍", "corn", "maize",
                "甜玉米", "糯玉米", "青贮玉米"
            ],
            "小麦": [
                "小麦", "麦子", "wheat", "冬小麦", "春小麦",
                "强筋小麦", "弱筋小麦", "中筋小麦"
            ],
            "大豆": [
                "大豆", "黄豆", "豆类", "豆粕", "soybean", "soy",
                "大豆蛋白", "豆油"
            ],
            "油菜": [
                "油菜", "菜籽", "油菜籽", "rapeseed", "canola",
                "菜籽油", "油菜籽"
            ],
            "水稻": [
                "水稻", "稻子", "稻谷", "rice", "paddy",
                "籼稻", "粳稻", "杂交水稻", "有机稻"
            ],
            "畜禽": [
                "猪", "牛", "羊", "鸡", "鸭", "鹅", "畜牧", "养殖",
                "pig", "cattle", "sheep", "chicken", "duck", "goose",
                "肉牛", "奶牛", "山羊", "绵羊", "肉鸡", "蛋鸡",
                "生猪", "肉", "奶", "蛋", "畜禽"
            ],
            "棉花": [
                "棉花", "cotton", "皮棉", "籽棉", "长绒棉", "细绒棉"
            ],
            "甘蔗": [
                "甘蔗", "sugarcane", "甘蔗糖", "蔗糖"
            ],
            "花生": [
                "花生", "peanut", "花生油", "果仁"
            ],
            "马铃薯": [
                "马铃薯", "土豆", "potato", "薯类"
            ],
            "蔬菜": [
                "蔬菜", "vegetable", "白菜", "甘蓝", "萝卜",
                "胡萝卜", "西红柿", "黄瓜", "茄子", "辣椒",
                "叶菜", "果菜", "根茎菜"
            ],
            "水果": [
                "水果", "fruit", "苹果", "梨", "桃", "葡萄",
                "柑橘", "香蕉", "西瓜", "草莓", "果树"
            ],
            "茶叶": [
                "茶叶", "tea", "绿茶", "红茶", "乌龙茶",
                "普洱", "白茶", "黄茶"
            ],
            "中草药": [
                "中药", "中草药", "草药", "herb", "药用植物",
                "人参", "当归", "黄芪", "枸杞", "三七"
            ]
        }

        # 排除的非农业类别（不作为物种输出）
        non_agricultural_categories = {
            "自我认知类", "场景化任务与指令遵循语料类",
            "编程", "编程基础", "数据库", "计算机", "软件",
            "数学", "物理", "化学", "历史", "文学",
            "人工智能", "机器学习", "深度学习"
        }

        # 调试信息
        logger.debug(f"[DEBUG _extract_species] Processing QA pair:")
        logger.debug(f"  Question: {qa.question[:100]}...")
        logger.debug(f"  Answer: {qa.answer[:100]}...")
        logger.debug(f"  Category: {qa.category}")
        logger.debug(f"  Target species: {self.target_species}")

        # 【关键修复】优先使用种子物种字段（最准确）
        if qa.seed_species:
            logger.debug(f"[DEBUG _extract_species] Using seed_species: {qa.seed_species}")
            # 确保返回的物种在已知列表中
            if qa.seed_species in species_keywords:
                return qa.seed_species

        # 其次使用目标物种（基于输入种子文件）
        if self.target_species:
            logger.debug(f"[DEBUG _extract_species] Returning target_species: {self.target_species}")
            return self.target_species

        # 如果没有指定目标物种，才根据生成内容识别物种
        # 优先从生成的问题和答案中识别物种（这是最准确的）
        # 1. 优先检查生成的问题（权重最高）
        question_text = qa.question.lower()
        question_scores = {}
        for species, keywords in species_keywords.items():
            score = sum(1 for keyword in keywords if keyword in question_text)
            question_scores[species] = score

        # 2. 检查生成的答案（权重中等）
        answer_text = qa.answer.lower()
        answer_scores = {}
        for species, keywords in species_keywords.items():
            score = sum(1 for keyword in keywords if keyword in answer_text)
            answer_scores[species] = score

        # 3. 检查种子问题（权重极低，仅当生成内容无匹配时作为参考）
        seed_text = (
            qa.seed_question + " " + qa.seed_answer
        ).lower()
        seed_scores = {}
        for species, keywords in species_keywords.items():
            score = sum(1 for keyword in keywords if keyword in seed_text)
            seed_scores[species] = score

        logger.debug(f"[DEBUG _extract_species] Question scores: {question_scores}")
        logger.debug(f"[DEBUG _extract_species] Answer scores: {answer_scores}")
        logger.debug(f"[DEBUG _extract_species] Seed scores: {seed_scores}")

        # 计算加权总分：问题权重10，答案权重5，种子权重0.1
        # 如果生成的问题或答案中已经明确提到某个物种，种子问题的贡献几乎可以忽略
        combined_scores = {}
        for species in species_keywords.keys():
            combined_scores[species] = (
                question_scores[species] * 10 +
                answer_scores[species] * 5 +
                seed_scores[species] * 0.1
            )

        logger.debug(f"[DEBUG _extract_species] Combined scores: {combined_scores}")

        # 返回得分最高的物种
        if combined_scores:
            best_species = max(combined_scores, key=combined_scores.get)
            logger.debug(f"[DEBUG _extract_species] Best species: {best_species}, score: {combined_scores[best_species]}")
            if combined_scores[best_species] > 0:
                # 额外检查：如果生成的问题中已经有明确匹配，可以直接返回
                if question_scores[best_species] > 0:
                    logger.debug(f"[DEBUG _extract_species] Returning {best_species} (question match)")
                    return best_species
                # 如果问题无匹配但答案有明确匹配，也可以返回
                if question_scores[best_species] == 0 and answer_scores[best_species] > 0:
                    logger.debug(f"[DEBUG _extract_species] Returning {best_species} (answer match)")
                    return best_species
                # 只有当生成内容有匹配时才返回，否则继续下一步检查
                if question_scores[best_species] > 0 or answer_scores[best_species] > 0:
                    logger.debug(f"[DEBUG _extract_species] Returning {best_species} (content match)")
                    return best_species

        # 【修复】如果内容中未找到明确物种匹配，尝试使用种子物种作为后备
        # 这样可以避免因内容生成时的轻微偏差而导致正确的QA对被过滤
        if qa.seed_species:
            logger.debug(f"[DEBUG _extract_species] No species found in content, checking seed_species: {qa.seed_species}")
            # 如果种子物种在已知物种列表中，返回它
            for species in species_keywords.keys():
                if species == qa.seed_species:
                    logger.debug(f"[DEBUG _extract_species] Using seed_species: {species}")
                    return species

        # 如果没有匹配到已知物种，检查category是否是非农业类别
        logger.debug(f"[DEBUG _extract_species] Checking category '{qa.category}' against non_agricultural_categories")
        if qa.category in non_agricultural_categories:
            # 对于非农业类别，返回"其他"但不在日志中输出
            logger.debug(f"[DEBUG _extract_species] Category is non-agricultural, returning '其他'")
            return "其他"

        # 如果category是农业相关但不在预定义列表中，尝试推断
        category = qa.category.lower() if qa.category else ""
        logger.debug(f"[DEBUG _extract_species] Checking category '{category}' for species keywords")
        for species in species_keywords.keys():
            if species.lower() in category:
                logger.debug(f"[DEBUG _extract_species] Found species '{species}' in category")
                return species

        # 最后后备：如果都没有匹配，返回"其他"
        logger.debug(f"[DEBUG _extract_species] No match found, returning '其他'")
        return "其他"

    def _calculate_variants_by_species(self,
                                       seed_questions: List[SeedQuestion],
                                       base_variants: int,
                                       species_ratios: Optional[Dict[str, float]] = None,
                                       subspecies_ratios: Optional[Dict[str, Dict[str, float]]] = None) -> Dict[int, int]:
        """
        根据物种比例和子类别比例计算每个种子问题应生成的变体数量

        Args:
            seed_questions: 种子问题列表
            base_variants: 基础变体数量
            species_ratios: 物种比例字典
            subspecies_ratios: 物种内子类别比例字典，例如：
                {
                    "玉米": {
                        "栽培技术": 0.5,
                        "病虫害防治": 0.3,
                        "品种选育": 0.2
                    }
                }

        Returns:
            字典，键为种子问题索引，值为应生成的变体数量
        """
        if not species_ratios and not subspecies_ratios:
            # 如果没有提供任何比例，返回默认数量
            return {i: base_variants for i in range(len(seed_questions))}

        # 分析种子问题的物种和子类别分布
        seed_species_map = {}
        seed_subspecies_map = {}
        species_counts = defaultdict(int)
        subspecies_counts = defaultdict(lambda: defaultdict(int))

        for i, seed in enumerate(seed_questions):
            # 创建一个虚拟的GeneratedQA对象来提取物种
            temp_qa = GeneratedQA(
                question="",
                answer="",
                category=seed.category,
                difficulty=seed.difficulty,
                tags=seed.tags,
                generation_method="",
                seed_question=seed.question,
                seed_answer=seed.answer,
                seed_id=seed.get_id(),
                rag_used=seed.rag_used,  # 传递RAG使用状态
                rag_documents_count=seed.rag_documents_count,  # 传递RAG文献数量
                rag_context=seed.rag_context  # 传递RAG上下文
            )
            species = self._extract_species(temp_qa)
            subspecies = self._extract_subspecies(seed)

            seed_species_map[i] = species
            seed_subspecies_map[i] = subspecies

            species_counts[species] += 1
            if subspecies:
                subspecies_counts[species][subspecies] += 1

        logger.info(f"种子问题物种分布: {dict(species_counts)}")
        logger.info(f"种子问题子类别分布: {dict({k: dict(v) for k, v in subspecies_counts.items()})}")

        # 初始化变体分配
        seed_variants_map = {}

        # 优先使用子类别比例控制
        if subspecies_ratios:
            for species, subspecies_ratio_dict in subspecies_ratios.items():
                # 归一化该物种的子类别比例
                total_subspecies_ratio = sum(subspecies_ratio_dict.values())
                if total_subspecies_ratio != 1.0:
                    logger.warning(f"物种{species}的子类别比例总和为{total_subspecies_ratio:.2f}，将进行归一化处理")
                    subspecies_ratio_dict = {k: v / total_subspecies_ratio for k, v in subspecies_ratio_dict.items()}

                # 计算该物种的种子数量
                species_seed_indices = [i for i, s in seed_species_map.items() if s == species]

                # 计算每个子类别应该分配的种子数量
                total_species_seeds = len(species_seed_indices)
                subspecies_target_counts = {}

                for subspecies, ratio in subspecies_ratio_dict.items():
                    subspecies_target_counts[subspecies] = max(1, int(total_species_seeds * ratio))

                # 调整以确保总和等于总种子数
                current_total = sum(subspecies_target_counts.values())
                if current_total != total_species_seeds:
                    diff = total_species_seeds - current_total
                    if diff > 0:
                        max_subspecies = max(subspecies_target_counts, key=subspecies_target_counts.get)
                        subspecies_target_counts[max_subspecies] += diff
                    elif diff < 0:
                        min_subspecies = min(subspecies_target_counts, key=subspecies_target_counts.get)
                        subspecies_target_counts[min_subspecies] = max(1, subspecies_target_counts[min_subspecies] + diff)

                logger.info(f"物种{species}的子类别目标数量: {subspecies_target_counts}")

                # 分配每个种子问题的变体数量
                for subspecies, target_count in subspecies_target_counts.items():
                    # 获取该子类别在种子中的索引
                    subspecies_seed_indices = [
                        i for i in species_seed_indices
                        if seed_subspecies_map.get(i) == subspecies
                    ]

                    # 实际该子类别种子数量
                    actual_subspecies_count = len(subspecies_seed_indices)

                    if actual_subspecies_count > 0:
                        # 该子类别每个种子问题的平均变体数量
                        avg_variants = max(1, target_count // actual_subspecies_count)
                        for seed_idx in subspecies_seed_indices:
                            seed_variants_map[seed_idx] = avg_variants

            # 处理未指定子类别比例的物种（如果提供了物种比例）
            if species_ratios:
                unprocessed_species = set(species_counts.keys()) - set(subspecies_ratios.keys())
                if unprocessed_species:
                    logger.info(f"未指定子类别比例的物种: {unprocessed_species}，将使用物种比例控制")

                    # 计算剩余物种的种子数量
                    total_unprocessed_seeds = sum(species_counts[s] for s in unprocessed_species)
                    if total_unprocessed_seeds > 0:
                        # 归一化剩余物种的比例
                        remaining_ratios = {s: species_ratios[s] for s in unprocessed_species if s in species_ratios}
                        total_remaining_ratio = sum(remaining_ratios.values())

                        if total_remaining_ratio > 0:
                            remaining_ratios = {k: v / total_remaining_ratio for k, v in remaining_ratios.items()}

                            for species, ratio in remaining_ratios.items():
                                target_count = max(1, int(total_unprocessed_seeds * ratio))
                                actual_count = species_counts[species]
                                avg_variants = max(1, target_count // actual_count)

                                species_seed_indices = [i for i, s in seed_species_map.items() if s == species]
                                for seed_idx in species_seed_indices:
                                    if seed_idx not in seed_variants_map:
                                        seed_variants_map[seed_idx] = avg_variants

        # 如果没有使用子类别比例控制，使用物种比例控制
        elif species_ratios:
            # 处理比例字典
            ratios = species_ratios.copy()

            # 归一化比例（如果总和不为1.0）
            total_ratio = sum(ratios.values())
            if total_ratio != 1.0:
                logger.warning(f"物种比例总和为{total_ratio:.2f}，将进行归一化处理")
                ratios = {k: v / total_ratio for k, v in ratios.items()}

            # 计算每个物种应该生成的变体数量
            total_seeds = len(seed_questions)
            species_target_counts = {}

            for species, ratio in ratios.items():
                species_target_counts[species] = max(1, int(total_seeds * ratio))

            # 调整以确保总和等于总种子数
            current_total = sum(species_target_counts.values())
            if current_total != total_seeds:
                diff = total_seeds - current_total
                # 将差值分配给数量最多的物种
                if diff > 0:
                    max_species = max(species_target_counts, key=species_target_counts.get)
                    species_target_counts[max_species] += diff
                elif diff < 0:
                    min_species = min(species_target_counts, key=species_target_counts.get)
                    species_target_counts[min_species] = max(1, species_target_counts[min_species] + diff)

            logger.info(f"物种目标数量: {species_target_counts}")

            # 分配每个种子问题的变体数量
            for i, seed in enumerate(seed_questions):
                species = seed_species_map[i]
                target_count = species_target_counts.get(species, 1)
                actual_count = species_counts[species]

                # 该物种每个种子问题的平均变体数量
                avg_variants = max(1, target_count // actual_count)
                seed_variants_map[i] = avg_variants

        # 处理未分配变体数量的种子（使用默认数量）
        for i in range(len(seed_questions)):
            if i not in seed_variants_map:
                seed_variants_map[i] = base_variants

        logger.info(f"各种子问题变体数量分配: {seed_variants_map}")
        return seed_variants_map

    def _extract_subspecies(self, seed: SeedQuestion) -> str:
        """
        从种子问题中提取子类别信息
        优先从tags中提取，如果没有则从question中推断
        支持从Excel文件动态加载子类别映射
        """
        # 尝试从Excel文件加载子类别映射
        subspecies_keywords = self._load_subspecies_mapping()

        # 优先从tags中查找子类别
        if seed.tags:
            tags_text = " ".join(seed.tags).lower()
            for subspecies, keywords in subspecies_keywords.items():
                if any(keyword.lower() in tags_text for keyword in keywords):
                    return subspecies

        # 从问题文本中推断
        question_text = seed.question.lower()
        for subspecies, keywords in subspecies_keywords.items():
            if any(keyword.lower() in question_text for keyword in keywords):
                return subspecies

        # 如果没有匹配，返回空字符串
        return ""

    def _load_subspecies_mapping(self) -> Dict[str, list]:
        """
        从Excel文件加载子类别关键词映射
        返回格式：{子类别名称: [关键词列表]}
        """
        import pandas as pd
        import os

        # Excel文件路径
        excel_file = os.path.join(os.path.dirname(__file__), "domain_task.xlsx")

        # 如果文件不存在，返回默认映射
        if not os.path.exists(excel_file):
            logger.warning(f"未找到Excel文件 {excel_file}，使用默认子类别映射")
            return self._get_default_subspecies_mapping()

        try:
            # 读取Excel文件
            df = pd.read_excel(excel_file, sheet_name="domain_task")

            # 构建关键词映射（去重）
            subspecies_mapping = {}
            for _, row in df.iterrows():
                subspecies = row["subspecies"]
                keywords = [k.strip() for k in row["keywords"].split(",")]

                if subspecies not in subspecies_mapping:
                    subspecies_mapping[subspecies] = set()

                subspecies_mapping[subspecies].update(keywords)

            # 转换set为list
            subspecies_mapping = {k: list(v) for k, v in subspecies_mapping.items()}

            logger.info(f"从Excel文件加载了 {len(subspecies_mapping)} 个子类别映射")
            return subspecies_mapping

        except Exception as e:
            logger.error(f"读取Excel文件失败: {e}，使用默认子类别映射")
            return self._get_default_subspecies_mapping()

    def _get_default_subspecies_mapping(self) -> Dict[str, list]:
        """
        获取默认的子类别关键词映射
        当Excel文件不存在或读取失败时使用
        """
        return {
            "栽培技术": ["播种", "密植", "田间管理", "施肥", "灌溉", "栽培", "种植"],
            "病虫害防治": ["病害", "虫害", "防治", "农药", "防治技术"],
            "品种选育": ["品种", "选育", "育种", "杂交", "转基因", "品种改良"],
            "播种技术": ["播种", "播种期", "播种深度", "播种量"],
            "田间管理": ["管理", "施肥", "灌溉", "中耕", "除草"],
            "收获储存": ["收获", "储存", "干燥", "仓储"],
            "饲料管理": ["饲料", "饲养", "营养", "饲料转化"],
            "养殖技术": ["养殖", "饲养", "繁育", "养殖模式"],
            "环境控制": ["温度", "湿度", "通风", "环境"],
            "育苗技术": ["育苗", "秧苗", "苗床", "温室"],
            "移栽技术": ["移栽", "插秧", "行距", "株距"],
            "水肥管理": ["灌溉", "施肥", "水层", "排水"],
            "疫病防控": ["疫病", "疫苗", "防治", "检疫"],
            "采收技术": ["采收", "采摘", "棉花", "纤维"],
            "种植技术": ["种植", "育苗", "移栽", "行距"],
            "砍收技术": ["砍收", "收获", "糖分", "成熟度"],
            "设施栽培": ["温室", "大棚", "设施", "保护地"],
            "修剪技术": ["修剪", "整形", "疏花", "疏果"],
            "采摘技术": ["采摘", "嫩芽", "标准", "时机"],
            "加工技术": ["加工", "杀青", "发酵", "干燥"],
            "加工炮制": ["加工", "炮制", "干燥", "储存"],
            "其他": ["技术", "方法", "问题"]
        }








# import json
# import pandas as pd
# import os
# from typing import List, Dict, Any, Optional
# from dataclasses import asdict
# from collections import defaultdict, Counter
# from pathlib import Path
# import logging

# # 根据你的main_no_bitsandbytes.py使用正确的导入
# from qa_generator_v2 import DeepSeekGenerator, SeedQuestion, GeneratedQA, GenerationMethod

# logger = logging.getLogger(__name__)

# class QualityFilter:
#     def __init__(self):
#         self.quality_rules = self._initialize_quality_rules()
#         self.filter_stats = {
#             "total_processed": 0,
#             "passed_quality": 0,
#             "failed_quality": 0,
#             "common_issues": Counter()
#         }
    
#     def _initialize_quality_rules(self):
#         return {
#             "min_length": {
#                 "question": 10,
#                 "answer": 20
#             },
#             "max_length": {
#                 "question": 500, 
#                 "answer": 2000
#             },
#             "required_elements": {
#                 "question": ["?", "？", "什么", "如何", "为什么", "怎样", "哪些"],
#                 "answer": []
#             },
#             "banned_phrases": [
#                 "我不知道", "我不确定", "这个问题很难", "作为AI模型",
#                 "根据我的训练数据", "我无法回答", "抱歉", "很抱歉",
#                 "作为一个大语言模型", "在我的知识库中"
#             ],
#             "similarity_threshold": 0.8
#         }
    
#     def filter_qa_pairs(self, qa_pairs: List[GeneratedQA]) -> List[GeneratedQA]:
#         filtered_pairs = []
        
#         for qa in qa_pairs:
#             self.filter_stats["total_processed"] += 1
            
#             if self._passes_quality_check(qa):
#                 filtered_pairs.append(qa)
#                 self.filter_stats["passed_quality"] += 1
#             else:
#                 self.filter_stats["failed_quality"] += 1
        
#         return filtered_pairs
    
#     def _passes_quality_check(self, qa_pair: GeneratedQA) -> bool:
#         question = qa_pair.question
#         answer = qa_pair.answer
        
#         # 检查问题长度
#         if len(question) < self.quality_rules["min_length"]["question"]:
#             self.filter_stats["common_issues"]["question_too_short"] += 1
#             logger.debug(f"问题过短: {question}")
#             return False
            
#         if len(answer) < self.quality_rules["min_length"]["answer"]:
#             self.filter_stats["common_issues"]["answer_too_short"] += 1
#             logger.debug(f"回答过短: {answer[:50]}...")
#             return False
            
#         if len(question) > self.quality_rules["max_length"]["question"]:
#             self.filter_stats["common_issues"]["question_too_long"] += 1
#             return False
            
#         if len(answer) > self.quality_rules["max_length"]["answer"]:
#             self.filter_stats["common_issues"]["answer_too_long"] += 1
#             return False
        
#         # 检查问题格式
#         required_elements = self.quality_rules["required_elements"]["question"]
#         if required_elements and not any(element in question for element in required_elements):
#             self.filter_stats["common_issues"]["question_format_issue"] += 1
#             logger.debug(f"问题格式问题: {question}")
#             return False
        
#         # 检查禁止短语
#         banned_phrases = self.quality_rules["banned_phrases"]
#         if any(phrase in answer for phrase in banned_phrases):
#             self.filter_stats["common_issues"]["banned_phrases"] += 1
#             logger.debug(f"包含禁止短语: {answer[:100]}...")
#             return False
        
#         # 检查是否与种子问题相同
#         if question.strip() == qa_pair.seed_question.strip():
#             self.filter_stats["common_issues"]["duplicate_question"] += 1
#             return False
        
#         # 检查回答详细程度
#         if len(answer.split()) < 10:  # 至少10个词
#             self.filter_stats["common_issues"]["answer_too_brief"] += 1
#             logger.debug(f"回答过于简短: {answer[:50]}...")
#             return False
        
#         return True
    
#     def get_quality_report(self) -> Dict:
#         total_processed = self.filter_stats["total_processed"]
#         if total_processed > 0:
#             pass_rate = (self.filter_stats["passed_quality"] / total_processed) * 100
#         else:
#             pass_rate = 0
        
#         return {
#             "quality_rules": self.quality_rules,
#             "statistics": dict(self.filter_stats),
#             "pass_rate": f"{pass_rate:.1f}%",
#             "pass_rate_numeric": pass_rate,
#             "common_issues": dict(self.filter_stats["common_issues"].most_common(5))
#         }

# class DiversityAnalyzer:
#     def __init__(self):
#         self.analysis_results = {}
    
#     def analyze_diversity(self, qa_pairs: List[GeneratedQA]) -> Dict:
#         if not qa_pairs:
#             return {
#                 "total_pairs": 0,
#                 "unique_seeds": 0,
#                 "method_distribution": {},
#                 "difficulty_distribution": {},
#                 "category_distribution": {},
#                 "length_statistics": {},
#                 "diversity_score": 0
#             }
        
#         method_distribution = Counter([qa.generation_method for qa in qa_pairs])
#         difficulty_distribution = Counter([qa.difficulty for qa in qa_pairs])
#         category_distribution = Counter([qa.category for qa in qa_pairs])
        
#         question_lengths = [len(qa.question) for qa in qa_pairs]
#         answer_lengths = [len(qa.answer) for qa in qa_pairs]
        
#         unique_seeds = len(set([qa.seed_id for qa in qa_pairs]))
        
#         diversity_score = self._calculate_diversity_score(
#             len(qa_pairs), 
#             method_distribution, 
#             category_distribution,
#             unique_seeds
#         )
        
#         return {
#             "total_pairs": len(qa_pairs),
#             "unique_seeds": unique_seeds,
#             "method_distribution": dict(method_distribution),
#             "difficulty_distribution": dict(difficulty_distribution),
#             "category_distribution": dict(category_distribution),
#             "length_statistics": {
#                 "question_avg_length": sum(question_lengths) / len(question_lengths) if question_lengths else 0,
#                 "answer_avg_length": sum(answer_lengths) / len(answer_lengths) if answer_lengths else 0,
#                 "question_min_length": min(question_lengths) if question_lengths else 0,
#                 "question_max_length": max(question_lengths) if question_lengths else 0
#             },
#             "diversity_score": diversity_score
#         }
    
#     def _calculate_diversity_score(self, total_pairs: int, method_dist: Counter, 
#                                  category_dist: Counter, unique_seeds: int) -> float:
#         if total_pairs == 0:
#             return 0.0
            
#         # 方法多样性
#         method_diversity = len(method_dist) / len(GenerationMethod) if GenerationMethod else 1.0
        
#         # 类别多样性
#         category_diversity = len(category_dist) / max(unique_seeds, 1)
        
#         # 种子多样性
#         seed_diversity = unique_seeds / max(total_pairs, 1)
        
#         # 综合多样性分数
#         diversity_score = (method_diversity * 0.4 + category_diversity * 0.3 + seed_diversity * 0.3) * 100
        
#         return round(diversity_score, 2)

# class BatchQAGenerator:
#     def __init__(self, generator: DeepSeekGenerator, output_dir: str = "output"):
#         self.generator = generator
#         self.quality_filter = QualityFilter()
#         self.diversity_analyzer = DiversityAnalyzer()
#         self.output_dir = Path(output_dir)
#         self.output_dir.mkdir(exist_ok=True)
        
#         logger.info("批量QA生成器初始化完成")
    
#     def generate_from_seeds(self, 
#                           seed_questions: List[SeedQuestion],
#                           variants_per_seed: int = 5,
#                           methods: List[GenerationMethod] = None,
#                           batch_size: int = 10) -> Dict[str, Any]:
        
#         if methods is None:
#             methods = [
#                 GenerationMethod.PARAPHRASE,
#                 GenerationMethod.ELABORATION, 
#                 GenerationMethod.PERSPECTIVE_SHIFT,
#                 GenerationMethod.SCENARIO_APPLICATION
#             ]
        
#         all_generated = []
#         generation_stats = {
#             "total_seeds": len(seed_questions),
#             "successful_generations": 0,
#             "failed_generations": 0,
#             "total_generated": 0,
#             "by_category": defaultdict(int),
#             "by_method": defaultdict(int),
#             "by_difficulty": defaultdict(int)
#         }
        
#         logger.info(f"开始批量生成，种子问题数量: {len(seed_questions)}")
        
#         for i in range(0, len(seed_questions), batch_size):
#             batch = seed_questions[i:i + batch_size]
#             batch_num = i // batch_size + 1
#             total_batches = (len(seed_questions) - 1) // batch_size + 1
#             logger.info(f"处理批次 {batch_num}/{total_batches}")
            
#             for j, seed in enumerate(batch):
#                 seed_index = i + j + 1
#                 try:
#                     logger.info(f"开始从种子问题生成QA对，目标数量: {variants_per_seed * len(methods)}")
                    
#                     # 使用与main_no_bitsandbytes.py一致的参数
#                     generated = self.generator.generate_from_seed(
#                         seed_question=seed,
#                         num_variants=variants_per_seed
#                     )
                    
#                     filtered = self.quality_filter.filter_qa_pairs(generated)
                    
#                     all_generated.extend(filtered)
#                     generation_stats["successful_generations"] += 1
#                     generation_stats["total_generated"] += len(filtered)
                    
#                     self._update_stats(generation_stats, seed, filtered)
                    
#                     logger.info(f"种子 {seed_index}/{len(seed_questions)}: 生成 {len(filtered)} 个QA对")
                    
#                 except Exception as e:
#                     generation_stats["failed_generations"] += 1
#                     logger.error(f"种子问题生成失败: {seed.question[:50]}... 错误: {e}")
#                     import traceback
#                     logger.debug(traceback.format_exc())
#                     continue
        
#         # 生成报告
#         diversity_report = self.diversity_analyzer.analyze_diversity(all_generated)
#         quality_report = self.quality_filter.get_quality_report()
        
#         # 保存结果
#         self._save_results(all_generated, generation_stats, diversity_report, quality_report)
        
#         logger.info(f"批量生成完成: 成功 {generation_stats['successful_generations']}, "
#                    f"失败 {generation_stats['failed_generations']}, "
#                    f"总计 {generation_stats['total_generated']} 个QA对")
        
#         return {
#             "generated_qa_pairs": all_generated,
#             "generation_stats": generation_stats,
#             "diversity_report": diversity_report,
#             "quality_report": quality_report
#         }
    
#     def _update_stats(self, stats: Dict, seed: SeedQuestion, generated: List[GeneratedQA]):
#         stats["by_category"][seed.category] += len(generated)
        
#         for qa_pair in generated:
#             stats["by_method"][qa_pair.generation_method] += 1
#             stats["by_difficulty"][qa_pair.difficulty] += 1
    
#     def _save_results(self, qa_pairs: List[GeneratedQA], stats: Dict, 
#                      diversity_report: Dict, quality_report: Dict):
#         import pandas as pd
#         from datetime import datetime
        
#         timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        
#         # 保存JSON格式的QA对
#         qa_data = [asdict(qa) for qa in qa_pairs]
#         with open(self.output_dir / f"generated_qa_{timestamp}.json", "w", encoding="utf-8") as f:
#             json.dump(qa_data, f, ensure_ascii=False, indent=2)
        
#         # 保存生成报告
#         report = {
#             "generation_stats": stats,
#             "diversity_report": diversity_report,
#             "quality_report": quality_report,
#             "timestamp": timestamp,
#             "total_qa_pairs": len(qa_pairs)
#         }
        
#         with open(self.output_dir / f"generation_report_{timestamp}.json", "w", encoding="utf-8") as f:
#             json.dump(report, f, ensure_ascii=False, indent=2)
        
#         # 保存CSV格式
#         if qa_pairs:
#             df_data = []
#             for qa in qa_pairs:
#                 df_data.append({
#                     "question": qa.question,
#                     "answer": qa.answer,
#                     "category": qa.category,
#                     "difficulty": qa.difficulty,
#                     "generation_method": qa.generation_method,
#                     "tags": ", ".join(qa.tags) if qa.tags else "",
#                     "seed_question": qa.seed_question,
#                     "seed_id": qa.seed_id
#                 })
            
#             df = pd.DataFrame(df_data)
#             df.to_csv(self.output_dir / f"generated_qa_{timestamp}.csv", index=False, encoding="utf-8-sig")
        
#         logger.info(f"结果已保存到 {self.output_dir}")


# import json
# import pandas as pd
# import os
# from typing import List, Dict, Any
# from dataclasses import asdict
# from collections import defaultdict, Counter
# from pathlib import Path
# import logging

# from qa_generator import QAGenerator, SeedQuestion, GeneratedQA, GenerationMethod

# logger = logging.getLogger(__name__)

# class QualityFilter:
#     def __init__(self):
#         self.quality_rules = self._initialize_quality_rules()
#         self.filter_stats = {
#             "total_processed": 0,
#             "passed_quality": 0,
#             "failed_quality": 0,
#             "common_issues": Counter()
#         }
    
#     def _initialize_quality_rules(self):
#         return {
#             "min_length": {
#                 "question": 10,
#                 "answer": 20
#             },
#             "max_length": {
#                 "question": 500, 
#                 "answer": 2000
#             },
#             "required_elements": {
#                 "question": ["?", "？", "什么", "如何", "为什么"],
#                 "answer": []
#             },
#             "banned_phrases": [
#                 "我不知道", "我不确定", "这个问题很难", "作为AI模型",
#                 "根据我的训练数据", "我无法回答", "抱歉"
#             ],
#             "similarity_threshold": 0.8
#         }
    
#     def filter_qa_pairs(self, qa_pairs: List[GeneratedQA]) -> List[GeneratedQA]:
#         filtered_pairs = []
        
#         for qa in qa_pairs:
#             self.filter_stats["total_processed"] += 1
            
#             if self._passes_quality_check(qa):
#                 filtered_pairs.append(qa)
#                 self.filter_stats["passed_quality"] += 1
#             else:
#                 self.filter_stats["failed_quality"] += 1
        
#         return filtered_pairs
    
#     def _passes_quality_check(self, qa_pair: GeneratedQA) -> bool:
#         question = qa_pair.question
#         answer = qa_pair.answer
        
#         if len(question) < self.quality_rules["min_length"]["question"]:
#             self.filter_stats["common_issues"]["question_too_short"] += 1
#             return False
            
#         if len(answer) < self.quality_rules["min_length"]["answer"]:
#             self.filter_stats["common_issues"]["answer_too_short"] += 1
#             return False
            
#         if len(question) > self.quality_rules["max_length"]["question"]:
#             self.filter_stats["common_issues"]["question_too_long"] += 1
#             return False
            
#         if len(answer) > self.quality_rules["max_length"]["answer"]:
#             self.filter_stats["common_issues"]["answer_too_long"] += 1
#             return False
        
#         required_elements = self.quality_rules["required_elements"]["question"]
#         if required_elements and not any(element in question for element in required_elements):
#             self.filter_stats["common_issues"]["question_format_issue"] += 1
#             return False
        
#         banned_phrases = self.quality_rules["banned_phrases"]
#         if any(phrase in answer for phrase in banned_phrases):
#             self.filter_stats["common_issues"]["banned_phrases"] += 1
#             return False
        
#         if question == qa_pair.seed_question:
#             self.filter_stats["common_issues"]["duplicate_question"] += 1
#             return False
        
#         if len(answer.split()) < 10:
#             self.filter_stats["common_issues"]["answer_too_brief"] += 1
#             return False
        
#         return True
    
#     def get_quality_report(self) -> Dict:
#         pass_rate = (self.filter_stats["passed_quality"] / self.filter_stats["total_processed"] * 100 
#                     if self.filter_stats["total_processed"] > 0 else 0)
        
#         return {
#             "quality_rules": self.quality_rules,
#             "statistics": self.filter_stats,
#             "pass_rate": f"{pass_rate:.1f}%",
#             "common_issues": dict(self.filter_stats["common_issues"].most_common(5))
#         }

# class DiversityAnalyzer:
#     def __init__(self):
#         self.analysis_results = {}
    
#     def analyze_diversity(self, qa_pairs: List[GeneratedQA]) -> Dict:
#         if not qa_pairs:
#             return {}
        
#         method_distribution = Counter([qa.generation_method for qa in qa_pairs])
#         difficulty_distribution = Counter([qa.difficulty for qa in qa_pairs])
#         category_distribution = Counter([qa.category for qa in qa_pairs])
        
#         question_lengths = [len(qa.question) for qa in qa_pairs]
#         answer_lengths = [len(qa.answer) for qa in qa_pairs]
        
#         unique_seeds = len(set([qa.seed_id for qa in qa_pairs]))
        
#         return {
#             "total_pairs": len(qa_pairs),
#             "unique_seeds": unique_seeds,
#             "method_distribution": dict(method_distribution),
#             "difficulty_distribution": dict(difficulty_distribution),
#             "category_distribution": dict(category_distribution),
#             "length_statistics": {
#                 "question_avg_length": sum(question_lengths) / len(question_lengths),
#                 "answer_avg_length": sum(answer_lengths) / len(answer_lengths),
#                 "question_min_length": min(question_lengths),
#                 "question_max_length": max(question_lengths)
#             },
#             "diversity_score": self._calculate_diversity_score(method_distribution, category_distribution)
#         }
    
#     def _calculate_diversity_score(self, method_dist: Counter, category_dist: Counter) -> float:
#         method_diversity = len(method_dist) / len(GenerationMethod)
#         category_diversity = len(category_dist)
        
#         return (method_diversity + category_diversity / 10) * 50




# # class BatchQAGenerator:
# #     def __init__(self, generator: QAGenerator, output_dir: str = "output"):
# #         self.generator = generator
# #         self.quality_filter = QualityFilter()
# #         self.diversity_analyzer = DiversityAnalyzer()
# #         self.output_dir = Path(output_dir)
# #         self.output_dir.mkdir(exist_ok=True)
        
# #         logger.info("批量QA生成器初始化完成")
    
# #     def generate_from_seeds(self, seed_questions: List[SeedQuestion],
# #                           variants_per_seed: int = 5,
# #                           methods: List[GenerationMethod] = None,
# #                           batch_size: int = 10) -> Dict[str, Any]:
# #         all_generated = []
# #         generation_stats = {
# #             "total_seeds": len(seed_questions),
# #             "successful_generations": 0,
# #             "failed_generations": 0,
# #             "total_generated": 0,
# #             "by_category": defaultdict(int),
# #             "by_method": defaultdict(int),
# #             "by_difficulty": defaultdict(int)
# #         }
        
# #         logger.info(f"开始批量生成，种子问题数量: {len(seed_questions)}")
        
# #         for i in range(0, len(seed_questions), batch_size):
# #             batch = seed_questions[i:i + batch_size]
# #             logger.info(f"处理批次 {i//batch_size + 1}/{(len(seed_questions)-1)//batch_size + 1}")
            
# #             for j, seed in enumerate(batch):
# #                 try:
# #                     generated = self.generator.generate_from_seed(
# #                         seed, methods, variants_per_seed
# #                     )
                    
# #                     filtered = self.quality_filter.filter_qa_pairs(generated)
                    
# #                     all_generated.extend(filtered)
# #                     generation_stats["successful_generations"] += 1
# #                     generation_stats["total_generated"] += len(filtered)
                    
# #                     self._update_stats(generation_stats, seed, filtered)
                    
# #                     logger.info(f"种子 {i+j+1}/{len(seed_questions)}: 生成 {len(filtered)} 个QA对")
                    
# #                 except Exception as e:
# #                     generation_stats["failed_generations"] += 1
# #                     logger.error(f"种子问题生成失败: {seed.question[:50]}... 错误: {e}")
# #                     continue
        
# #         diversity_report = self.diversity_analyzer.analyze_diversity(all_generated)
# #         quality_report = self.quality_filter.get_quality_report()
        
# #         self._save_results(all_generated, generation_stats, diversity_report, quality_report)
        
# #         logger.info(f"批量生成完成: 成功 {generation_stats['successful_generations']}, "
# #                    f"失败 {generation_stats['failed_generations']}, "
# #                    f"总计 {generation_stats['total_generated']} 个QA对")
        
# #         return {
# #             "generated_qa_pairs": all_generated,
# #             "generation_stats": generation_stats,
# #             "diversity_report": diversity_report,
# #             "quality_report": quality_report
# #         }
    
# #     def _update_stats(self, stats: Dict, seed: SeedQuestion, generated: List[GeneratedQA]):
# #         stats["by_category"][seed.category] += len(generated)
        
# #         for qa_pair in generated:
# #             stats["by_method"][qa_pair.generation_method] += 1
# #             stats["by_difficulty"][qa_pair.difficulty] += 1
    
# #     def _save_results(self, qa_pairs: List[GeneratedQA], stats: Dict, 
# #                      diversity_report: Dict, quality_report: Dict):
# #         import pandas as pd
# #         timestamp = pd.Timestamp.now().strftime("%Y%m%d_%H%M%S")
        
# #         qa_data = [asdict(qa) for qa in qa_pairs]
# #         with open(self.output_dir / f"generated_qa_{timestamp}.json", "w", encoding="utf-8") as f:
# #             json.dump(qa_data, f, ensure_ascii=False, indent=2)
        
# #         report = {
# #             "generation_stats": stats,
# #             "diversity_report": diversity_report,
# #             "quality_report": quality_report,
# #             "timestamp": timestamp,
# #             "total_qa_pairs": len(qa_pairs)
# #         }
        
# #         with open(self.output_dir / f"generation_report_{timestamp}.json", "w", encoding="utf-8") as f:
# #             json.dump(report, f, ensure_ascii=False, indent=2)
        
# #         df_data = []
# #         for qa in qa_pairs:
# #             df_data.append({
# #                 "question": qa.question,
# #                 "answer": qa.answer,
# #                 "category": qa.category,
# #                 "difficulty": qa.difficulty,
# #                 "generation_method": qa.generation_method,
# #                 "tags": ", ".join(qa.tags),
# #                 "seed_question": qa.seed_question
# #             })
        
# #         df = pd.DataFrame(df_data)
# #         df.to_csv(self.output_dir / f"generated_qa_{timestamp}.csv", index=False, encoding="utf-8-sig")
        
# #         logger.info(f"结果已保存到 {self.output_dir}")