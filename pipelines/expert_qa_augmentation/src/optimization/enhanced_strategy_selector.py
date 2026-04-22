#!/usr/bin/env python3
"""
基于扩展种子问题分类的策略选择器
根据专家问题的扩展分类智能选择最适合的QA生成策略
"""

from typing import List, Dict, Set
from enum import Enum

# 定义策略枚举
class GenerationMethod:
    """QA生成策略枚举"""
    PARAPHRASE = "paraphrase"
    ELABORATION = "elaboration"
    PERSPECTIVE_SHIFT = "perspective_shift"
    MULTI_TURN = "multi_turn"
    CROSS_SPECIES = "cross_species"
    REVERSE_REASONING = "reverse_reasoning"
    INNOVATIVE_APPLICATION = "innovative_application"
    COMPARATIVE_ANALYSIS = "comparative_analysis"
    FUTURE_SCENARIO = "future_scenario"
    HYPOTHETICAL = "hypothetical"
    COUNTERFACTUAL = "counterfactual"
    META_QUESTION = "meta_question"
    TEMPORAL_SHIFT = "temporal_shift"
    SPATIAL_SHIFT = "spatial_shift"
    DISCIPLINE_CROSS = "discipline_cross"
    SCALE_CHANGE = "scale_change"
    TIME_SERIES = "time_series"
    CAUSAL_CHAIN = "causal_chain"

class StrategyCategory(Enum):
    """策略类别"""
    BASIC = "基础策略"
    MOLECULAR = "分子生物学策略"
    PHYSIOLOGY = "生理学策略"
    BREEDING = "育种学策略"
    BIOSTATISTICS = "生物统计学策略"
    ECOLOGY = "生态学策略"
    GENETICS = "遗传学策略"
    PHENOTYPING = "表型学策略"
    BIOINFORMATICS = "生物信息学策略"
    BIOCHEMISTRY = "生物化学策略"
    CROP_SCIENCE = "作物学策略"
    STRESS_BIOLOGY = "逆境生物学策略"

# 扩展分类关键词映射
EXPANDED_CATEGORY_KEYWORDS = {
    # 分子生物学相关
    "分子生物学": StrategyCategory.MOLECULAR,
    "分子遗传学": StrategyCategory.MOLECULAR,
    "功能基因组学": StrategyCategory.MOLECULAR,
    "转录组": StrategyCategory.MOLECULAR,
    "转录调控": StrategyCategory.MOLECULAR,
    "基因编辑": StrategyCategory.MOLECULAR,
    "载体工程": StrategyCategory.MOLECULAR,
    "转化": StrategyCategory.MOLECULAR,
    "组织培养": StrategyCategory.MOLECULAR,
    "蛋白": StrategyCategory.MOLECULAR,
    "表达": StrategyCategory.MOLECULAR,
    "调控": StrategyCategory.MOLECULAR,

    # 生理学相关
    "生理学": StrategyCategory.PHYSIOLOGY,
    "植物生理": StrategyCategory.PHYSIOLOGY,
    "生理生态": StrategyCategory.PHYSIOLOGY,
    "光合作用": StrategyCategory.PHYSIOLOGY,
    "呼吸作用": StrategyCategory.PHYSIOLOGY,
    "代谢": StrategyCategory.PHYSIOLOGY,
    "同化物": StrategyCategory.PHYSIOLOGY,
    "运输": StrategyCategory.PHYSIOLOGY,
    "激素": StrategyCategory.PHYSIOLOGY,
    "信号": StrategyCategory.PHYSIOLOGY,
    "发育生物学": StrategyCategory.PHYSIOLOGY,
    "繁殖生物学": StrategyCategory.PHYSIOLOGY,

    # 育种学相关
    "育种": StrategyCategory.BREEDING,
    "育种学": StrategyCategory.BREEDING,
    "分子育种": StrategyCategory.BREEDING,
    "经典育种": StrategyCategory.BREEDING,
    "回交导入": StrategyCategory.BREEDING,
    "材料创制": StrategyCategory.BREEDING,
    "品种": StrategyCategory.BREEDING,
    "种质资源": StrategyCategory.BREEDING,

    # 生物统计学相关
    "统计": StrategyCategory.BIOSTATISTICS,
    "生物统计": StrategyCategory.BIOSTATISTICS,
    "实验设计": StrategyCategory.BIOSTATISTICS,
    "数据分析": StrategyCategory.BIOSTATISTICS,
    "统计遗传": StrategyCategory.BIOSTATISTICS,
    "数量遗传": StrategyCategory.BIOSTATISTICS,

    # 生态学相关
    "生态": StrategyCategory.ECOLOGY,
    "群体生态": StrategyCategory.ECOLOGY,
    "冠层": StrategyCategory.ECOLOGY,
    "群体": StrategyCategory.ECOLOGY,
    "环境": StrategyCategory.ECOLOGY,
    "适应": StrategyCategory.ECOLOGY,

    # 遗传学相关
    "遗传": StrategyCategory.GENETICS,
    "群体遗传": StrategyCategory.GENETICS,
    "基因组": StrategyCategory.GENETICS,
    "遗传变异": StrategyCategory.GENETICS,
    "关联分析": StrategyCategory.GENETICS,
    "基因组选择": StrategyCategory.GENETICS,

    # 表型学相关
    "表型": StrategyCategory.PHENOTYPING,
    "表型组": StrategyCategory.PHENOTYPING,
    "高通量表型": StrategyCategory.PHENOTYPING,
    "时序表型": StrategyCategory.PHENOTYPING,
    "性状": StrategyCategory.PHENOTYPING,
    "成像": StrategyCategory.PHENOTYPING,
    "显微成像": StrategyCategory.PHENOTYPING,

    # 生物信息学相关
    "生物信息": StrategyCategory.BIOINFORMATICS,
    "组学": StrategyCategory.BIOINFORMATICS,
    "系统生物学": StrategyCategory.BIOINFORMATICS,
    "网络生物学": StrategyCategory.BIOINFORMATICS,
    "机器学习": StrategyCategory.BIOINFORMATICS,
    "深度学习": StrategyCategory.BIOINFORMATICS,
    "图模型": StrategyCategory.BIOINFORMATICS,

    # 生物化学相关
    "生物化学": StrategyCategory.BIOCHEMISTRY,
    "酶学": StrategyCategory.BIOCHEMISTRY,
    "代谢工程": StrategyCategory.BIOCHEMISTRY,
    "催化": StrategyCategory.BIOCHEMISTRY,

    # 作物学相关
    "作物学": StrategyCategory.CROP_SCIENCE,
    "栽培": StrategyCategory.CROP_SCIENCE,
    "耕作": StrategyCategory.CROP_SCIENCE,
    "田间": StrategyCategory.CROP_SCIENCE,
    "管理": StrategyCategory.CROP_SCIENCE,

    # 逆境生物学相关
    "逆境": StrategyCategory.STRESS_BIOLOGY,
    "胁迫": StrategyCategory.STRESS_BIOLOGY,
    "抗性": StrategyCategory.STRESS_BIOLOGY,
    "耐盐": StrategyCategory.STRESS_BIOLOGY,
    "耐旱": StrategyCategory.STRESS_BIOLOGY,
    "耐高温": StrategyCategory.STRESS_BIOLOGY,
    "耐低温": StrategyCategory.STRESS_BIOLOGY,
}

# 每个策略类别对应的生成策略
CATEGORY_STRATEGIES = {
    StrategyCategory.BASIC: [
        GenerationMethod.PARAPHRASE,
        GenerationMethod.ELABORATION,
        GenerationMethod.PERSPECTIVE_SHIFT,
        GenerationMethod.MULTI_TURN,
    ],

    StrategyCategory.MOLECULAR: [
        GenerationMethod.ELABORATION,  # 详细阐述分子机制
        GenerationMethod.MULTI_TURN,  # 多轮深入探讨
        GenerationMethod.COMPARATIVE_ANALYSIS,  # 比较不同分子途径
        GenerationMethod.CAUSAL_CHAIN,  # 因果链条分析
        GenerationMethod.HYPOTHETICAL,  # 假设性推理
        GenerationMethod.DISCIPLINE_CROSS,  # 跨学科整合
        GenerationMethod.SCALE_CHANGE,  # 从分子到细胞
    ],

    StrategyCategory.PHYSIOLOGY: [
        GenerationMethod.ELABORATION,  # 详细解释生理过程
        GenerationMethod.CAUSAL_CHAIN,  # 因果关系
        GenerationMethod.COMPARATIVE_ANALYSIS,  # 比较不同生理状态
        GenerationMethod.TEMPORAL_SHIFT,  # 时间维度变化
        GenerationMethod.SCALE_CHANGE,  # 从分子到器官
        GenerationMethod.SPATIAL_SHIFT,  # 空间结构差异
        GenerationMethod.FUTURE_SCENARIO,  # 未来情景模拟
    ],

    StrategyCategory.BREEDING: [
        GenerationMethod.COMPARATIVE_ANALYSIS,  # 比较育种方案
        GenerationMethod.INNOVATIVE_APPLICATION,  # 创新应用
        GenerationMethod.FUTURE_SCENARIO,  # 未来育种趋势
        GenerationMethod.PERSPECTIVE_SHIFT,  # 视角转换
        GenerationMethod.META_QUESTION,  # 元问题
        GenerationMethod.HYPOTHETICAL,  # 假设性选择
        GenerationMethod.SCALE_CHANGE,  # 不同育种规模
    ],

    StrategyCategory.BIOSTATISTICS: [
        GenerationMethod.COMPARATIVE_ANALYSIS,  # 比较分析方法
        GenerationMethod.MULTI_TURN,  # 深入统计分析
        GenerationMethod.CAUSAL_CHAIN,  # 因果推断
        GenerationMethod.REVERSE_REASONING,  # 反向推理
        GenerationMethod.DISCIPLINE_CROSS,  # 统计方法跨学科应用
        GenerationMethod.META_QUESTION,  # 关于方法的元问题
    ],

    StrategyCategory.ECOLOGY: [
        GenerationMethod.COMPARATIVE_ANALYSIS,  # 比较生态环境
        GenerationMethod.SPATIAL_SHIFT,  # 空间分布差异
        GenerationMethod.TEMPORAL_SHIFT,  # 时间序列分析
        GenerationMethod.FUTURE_SCENARIO,  # 气候变化情景
        GenerationMethod.SCALE_CHANGE,  # 从个体到群体
        GenerationMethod.CROSS_SPECIES,  # 跨物种比较
        GenerationMethod.HYPOTHETICAL,  # 生态假设
    ],

    StrategyCategory.GENETICS: [
        GenerationMethod.COMPARATIVE_ANALYSIS,  # 比较遗传变异
        GenerationMethod.CAUSAL_CHAIN,  # 基因-表型因果链
        GenerationMethod.HYPOTHETICAL,  # 遗传假设
        GenerationMethod.MULTI_TURN,  # 深入遗传机制
        GenerationMethod.DISCIPLINE_CROSS,  # 遗传学跨学科整合
        GenerationMethod.SCALE_CHANGE,  # 从基因到群体
    ],

    StrategyCategory.PHENOTYPING: [
        GenerationMethod.COMPARATIVE_ANALYSIS,  # 比较表型数据
        GenerationMethod.INNOVATIVE_APPLICATION,  # 创新检测方法
        GenerationMethod.SPATIAL_SHIFT,  # 成像空间差异
        GenerationMethod.TEMPORAL_SHIFT,  # 时序表型分析
        GenerationMethod.SCALE_CHANGE,  # 从细胞到植株
        GenerationMethod.META_QUESTION,  # 关于表型的元问题
    ],

    StrategyCategory.BIOINFORMATICS: [
        GenerationMethod.COMPARATIVE_ANALYSIS,  # 比较算法
        GenerationMethod.INNOVATIVE_APPLICATION,  # 创新应用
        GenerationMethod.MULTI_TURN,  # 深入技术细节
        GenerationMethod.DISCIPLINE_CROSS,  # 跨学科数据整合
        GenerationMethod.HYPOTHETICAL,  # 计算假设
        GenerationMethod.FUTURE_SCENARIO,  # 技术发展趋势
    ],

    StrategyCategory.BIOCHEMISTRY: [
        GenerationMethod.ELABORATION,  # 详细生化过程
        GenerationMethod.CAUSAL_CHAIN,  # 生化反应链
        GenerationMethod.COMPARATIVE_ANALYSIS,  # 比较代谢途径
        GenerationMethod.SCALE_CHANGE,  # 从分子到细胞器
        GenerationMethod.TEMPORAL_SHIFT,  # 代谢时间序列
    ],

    StrategyCategory.CROP_SCIENCE: [
        GenerationMethod.COMPARATIVE_ANALYSIS,  # 比较栽培措施
        GenerationMethod.INNOVATIVE_APPLICATION,  # 创新栽培技术
        GenerationMethod.FUTURE_SCENARIO,  # 未来农业模式
        GenerationMethod.SPATIAL_SHIFT,  # 不同地区栽培
        GenerationMethod.TEMPORAL_SHIFT,  # 季节性管理
        GenerationMethod.SCALE_CHANGE,  # 不同种植规模
    ],

    StrategyCategory.STRESS_BIOLOGY: [
        GenerationMethod.COMPARATIVE_ANALYSIS,  # 比较抗逆机制
        GenerationMethod.CAUSAL_CHAIN,  # 胁迫-响应因果链
        GenerationMethod.HYPOTHETICAL,  # 抗逆假设
        GenerationMethod.FUTURE_SCENARIO,  # 气候变化应对
        GenerationMethod.SCALE_CHANGE,  # 从分子到个体
        GenerationMethod.MULTI_TURN,  # 多角度抗逆分析
    ],
}

class EnhancedStrategySelector:
    """增强的策略选择器"""

    def __init__(self):
        self.category_keywords = EXPANDED_CATEGORY_KEYWORDS
        self.category_strategies = CATEGORY_STRATEGIES
        self.base_strategies = CATEGORY_STRATEGIES[StrategyCategory.BASIC]

    def categorize_expanded_question(self, expanded_categories: List[str]) -> List[StrategyCategory]:
        """
        将扩展种子问题分类映射到策略类别

        Args:
            expanded_categories: 扩展分类列表，如 ['植物发育生物学', '植物生理生态学', ...]

        Returns:
            匹配的策略类别列表
        """
        matched_categories = []

        for category in expanded_categories:
            category_lower = category.lower()

            # 精确匹配关键词
            for keyword, strategy_category in self.category_keywords.items():
                if keyword in category_lower:
                    if strategy_category not in matched_categories:
                        matched_categories.append(strategy_category)

        # 如果没有匹配到任何分类，返回基础策略
        if not matched_categories:
            matched_categories = [StrategyCategory.BASIC]

        return matched_categories

    def select_strategies_for_question(
        self,
        expanded_categories: List[str],
        num_strategies: int = 8
    ) -> List[str]:
        """
        为单个问题选择最合适的策略

        Args:
            expanded_categories: 扩展分类列表
            num_strategies: 返回的策略数量

        Returns:
            选择的策略列表
        """
        # 获取匹配的策略类别
        matched_categories = self.categorize_expanded_question(expanded_categories)

        # 收集所有相关策略
        selected_strategies = []

        # 1. 添加基础策略（总是包含）
        selected_strategies.extend(self.base_strategies)

        # 2. 根据匹配的分类添加特定策略
        for category in matched_categories:
            if category in self.category_strategies:
                strategies = self.category_strategies[category]
                for strategy in strategies:
                    if strategy not in selected_strategies:
                        selected_strategies.append(strategy)

        # 3. 如果策略数量不足，添加通用策略
        universal_strategies = [
            GenerationMethod.COMPARATIVE_ANALYSIS,
            GenerationMethod.HYPOTHETICAL,
            GenerationMethod.FUTURE_SCENARIO,
            GenerationMethod.META_QUESTION,
        ]

        for strategy in universal_strategies:
            if strategy not in selected_strategies and len(selected_strategies) < num_strategies:
                selected_strategies.append(strategy)

        # 返回指定数量的策略
        return selected_strategies[:num_strategies]

    def generate_strategy_report(self, expert_questions: List[Dict]) -> Dict:
        """
        为所有专家问题生成策略选择报告

        Args:
            expert_questions: 专家问题列表

        Returns:
            策略选择报告
        """
        report = {
            "总问题数": len(expert_questions),
            "策略分布": {},
            "分类分布": {},
            "问题策略示例": []
        }

        for eq in expert_questions:
            # 获取扩展分类
            expanded_cats = eq.get('extended_categories', [])

            # 选择策略
            strategies = self.select_strategies_for_question(expanded_cats, num_strategies=6)

            # 统计策略分布
            for strategy in strategies:
                if strategy not in report["策略分布"]:
                    report["策略分布"][strategy] = 0
                report["策略分布"][strategy] += 1

            # 统计分类分布
            categories = self.categorize_expanded_question(expanded_cats)
            for cat in categories:
                cat_name = cat.value if hasattr(cat, 'value') else str(cat)
                if cat_name not in report["分类分布"]:
                    report["分类分布"][cat_name] = 0
                report["分类分布"][cat_name] += 1

            # 收集示例（前5个）
            if len(report["问题策略示例"]) < 5:
                report["问题策略示例"].append({
                    "问题": eq['question'][:80] + "..." if len(eq['question']) > 80 else eq['question'],
                    "方向": eq.get('direction', '未知'),
                    "扩展分类": expanded_cats[:3],  # 只显示前3个分类
                    "选择的策略": strategies
                })

        return report

def print_strategy_report(report: Dict):
    """打印策略选择报告"""
    print("\n" + "=" * 70)
    print("📊 策略选择报告")
    print("=" * 70)

    print(f"\n📋 总计: {report['总问题数']} 个专家问题")

    # 策略分布
    print(f"\n🔧 策略分布 (前10):")
    sorted_strategies = sorted(report["策略分布"].items(), key=lambda x: x[1], reverse=True)
    for i, (strategy, count) in enumerate(sorted_strategies[:10], 1):
        percentage = count / report['总问题数'] * 100
        print(f"  {i:2d}. {strategy:35s}: {count:3d} 次 ({percentage:5.1f}%)")

    # 分类分布
    print(f"\n🏷️  分类分布:")
    sorted_categories = sorted(report["分类分布"].items(), key=lambda x: x[1], reverse=True)
    for i, (category, count) in enumerate(sorted_categories, 1):
        percentage = count / report['总问题数'] * 100
        print(f"  {i:2d}. {category:30s}: {count:3d} 次 ({percentage:5.1f}%)")

    # 示例
    print(f"\n💡 问题策略示例:")
    for i, example in enumerate(report["问题策略示例"], 1):
        print(f"\n  [{i}] {example['问题']}")
        print(f"      方向: {example['方向']}")
        print(f"      分类: {', '.join(example['扩展分类'])}")
        print(f"      策略: {', '.join(example['选择的策略'][:4])}")

# 使用示例
if __name__ == "__main__":
    from run_expansion_from_dir_expert import parse_expert_questions

    # 读取专家问题
    expert_questions = parse_expert_questions('专家问题_扩增CoT.xlsx')

    # 创建策略选择器
    selector = EnhancedStrategySelector()

    # 生成报告
    report = selector.generate_strategy_report(expert_questions)

    # 打印报告
    print_strategy_report(report)

    # 为第一个问题选择策略
    if expert_questions:
        print("\n" + "=" * 70)
        print("🎯 为第一个专家问题选择策略示例")
        print("=" * 70)

        first_q = expert_questions[0]
        strategies = selector.select_strategies_for_question(
            first_q['extended_categories'],
            num_strategies=8
        )

        print(f"\n问题: {first_q['question']}")
        print(f"方向: {first_q['direction']}")
        print(f"扩展分类: {', '.join(first_q['extended_categories'])}")
        print(f"\n选择的8个策略:")
        for i, strategy in enumerate(strategies, 1):
            print(f"  {i}. {strategy}")
