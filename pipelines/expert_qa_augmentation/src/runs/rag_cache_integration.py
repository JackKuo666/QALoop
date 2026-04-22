#!/usr/bin/env python3
"""
集成缓存机制的RAG客户端
修改自 run_expansion_from_merged.py 的 RAGClient 类
"""
import sys
import requests
import time
from typing import Dict, Any, Optional, List
from pathlib import Path

# Add parent directory to Python path to allow imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from quality.rag_cache import get_cache_key, get_cached_result, save_cache_result

class CachedRAGClient:
    """带缓存的RAG客户端"""

    def __init__(self, config: Dict[str, Any] = None):
        self.config = config or {
            'url': 'http://localhost:9487/retrieve',
            'headers': {'Content-Type': 'application/json'},
            'timeout': 15,  # 减少超时时间
            'max_retries': 2,
        }
        self.session = requests.Session()

        # 配置重试策略
        from requests.adapters import HTTPAdapter
        from urllib3.util.retry import Retry

        retry_strategy = Retry(
            total=self.config.get('max_retries', 2),
            backoff_factor=0.5,
            status_forcelist=[429, 500, 502, 503, 504],
        )
        adapter = HTTPAdapter(max_retries=retry_strategy)
        self.session.mount("http://", adapter)
        self.session.mount("https://", adapter)

    def retrieve(self, query: str, top_k: int = 5, data_source: Optional[List[str]] = None, language: str = "zh") -> List[Dict[str, Any]]:
        """
        检索文档（带缓存）
        """
        if not data_source:
            data_source = ["pubmed"]

        # 生成缓存键
        cache_key = get_cache_key(query, top_k, data_source)

        # 先查缓存
        cached_result = get_cached_result(cache_key)
        if cached_result is not None:
            print(f"   💾 缓存命中: {query[:50]}...")
            return cached_result

        # 缓存未命中，执行检索
        start_time = time.time()
        payload = {
            "query": query,
            "top_k": top_k,
            "data_source": data_source,
            "language": language
        }

        try:
            print(f"   🔍 正在检索: {query[:50]}...")
            response = self.session.post(
                self.config['url'],
                headers=self.config['headers'],
                json=payload,
                timeout=self.config['timeout']
            )
            response.raise_for_status()
            result = response.json()

            # 标准化返回格式
            if isinstance(result, dict) and 'results' in result:
                final_result = result['results']
            elif isinstance(result, list):
                final_result = result
            else:
                final_result = []

            # 保存到缓存
            save_cache_result(cache_key, final_result)

            elapsed = time.time() - start_time
            print(f"   ⏱️ 检索耗时: {elapsed:.2f}秒 (找到 {len(final_result)} 篇文档)")

            return final_result

        except requests.exceptions.Timeout:
            print(f"   ⏰ 检索超时 ({self.config['timeout']}秒)")
            return []
        except requests.exceptions.RequestException as e:
            print(f"   ❌ RAG检索失败: {e}")
            return []
        except Exception as e:
            print(f"   ❌ RAG处理错误: {e}")
            return []

    def close(self):
        """关闭客户端"""
        self.session.close()

# 使用示例
if __name__ == "__main__":
    client = CachedRAGClient()

    # 第一次查询（无缓存）
    print("=== 第一次查询 ===")
    docs1 = client.retrieve("小麦育种技术", top_k=3)
    print(f"结果: {len(docs1)} 个文档\n")

    # 第二次相同查询（命中缓存）
    print("=== 第二次查询（相同内容）===")
    docs2 = client.retrieve("小麦育种技术", top_k=3)
    print(f"结果: {len(docs2)} 个文档\n")

    client.close()
