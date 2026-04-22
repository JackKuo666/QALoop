#!/usr/bin/env python3
"""
策略平衡器 - 简化版实现
用于平衡不同生成策略的使用频率
"""
from typing import Dict, List, Any, Optional
import random
import logging
from collections import defaultdict, Counter

logger = logging.getLogger(__name__)


class StrategyBalancer:
    """策略平衡器"""

    def __init__(self, max_history: int = 1000):
        """
        初始化策略平衡器

        Args:
            max_history: 最大历史记录数
        """
        self.max_history = max_history
        self.strategy_usage: Counter = Counter()
        self.recent_strategies: List[str] = []
        logger.info(f"初始化策略平衡器，最大历史记录: {max_history}")

    def record_usage(self, strategy: str):
        """
        记录策略使用

        Args:
            strategy: 策略名称
        """
        self.strategy_usage[strategy] += 1
        self.recent_strategies.append(strategy)

        # 限制历史记录长度
        if len(self.recent_strategies) > self.max_history:
            removed_strategy = self.recent_strategies.pop(0)
            if self.strategy_usage[removed_strategy] > 0:
                self.strategy_usage[removed_strategy] -= 1

    def get_least_used_strategy(self, available_strategies: List[str]) -> Optional[str]:
        """
        获取使用最少的策略

        Args:
            available_strategies: 可用策略列表

        Returns:
            str: 使用最少的策略名，如果没有可用策略则返回None
        """
        if not available_strategies:
            return None

        # 找到使用次数最少的策略
        min_usage = min(self.strategy_usage.get(s, 0) for s in available_strategies)
        least_used = [s for s in available_strategies if self.strategy_usage.get(s, 0) == min_usage]

        # 如果有多个使用次数相同的策略，随机选择一个
        selected = random.choice(least_used)
        logger.debug(f"选择策略 {selected} (使用次数: {self.strategy_usage.get(selected, 0)})")

        return selected

    def get_balanced_strategies(self, strategies: List[str], count: int) -> List[str]:
        """
        获取平衡的策略列表

        Args:
            strategies: 可用策略列表
            count: 需要选择的策略数量

        Returns:
            List[str]: 平衡选择的策略列表
        """
        if count <= 0 or not strategies:
            return []

        if count >= len(strategies):
            return strategies.copy()

        # 使用轮询方式选择策略
        selected = []
        available = strategies.copy()

        for _ in range(count):
            if not available:
                available = strategies.copy()

            # 选择使用最少的策略
            strategy = self.get_least_used_strategy(available)
            if strategy:
                selected.append(strategy)
                available.remove(strategy)
                self.record_usage(strategy)

        return selected

    def get_stats(self) -> Dict[str, int]:
        """
        获取策略使用统计

        Returns:
            Dict[str, int]: 策略使用统计
        """
        return dict(self.strategy_usage)

    def reset(self):
        """重置统计"""
        self.strategy_usage.clear()
        self.recent_strategies.clear()
        logger.info("重置策略平衡器")


# 全局策略平衡器实例
_global_balancer = None


def get_global_balancer(max_history: int = 1000) -> StrategyBalancer:
    """
    获取全局策略平衡器实例

    Args:
        max_history: 最大历史记录数

    Returns:
        StrategyBalancer: 全局策略平衡器实例
    """
    global _global_balancer
    if _global_balancer is None:
        _global_balancer = StrategyBalancer(max_history=max_history)
    return _global_balancer
