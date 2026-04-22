#!/usr/bin/env python3
"""
RAG异步优化方案
实现并行RAG检索，提升整体效率
"""
import asyncio
import aiohttp
import time
from typing import List, Dict, Any, Optional
from run_expansion_from_merged import RAGClient, format_rag_context, generate_rag_enhanced_prompt, SeedQuestion

class AsyncRAGClient:
    """异步RAG客户端，支持并行检索"""

    def __init__(self, config: Dict[str, Any] = None, max_concurrent: int = 5):
        self.config = config or {
            'url': 'http://localhost:9487/retrieve',
            'headers': {'Content-Type': 'application/json'},
            'timeout': 15,  # 减少超时时间
            'max_retries': 2,
        }
        self.max_concurrent = max_concurrent  # 最大并发数
        self.semaphore = asyncio.Semaphore(max_concurrent)
        self.session = None

    async def __aenter__(self):
        self.session = aiohttp.ClientSession(
            timeout=aiohttp.ClientTimeout(total=self.config['timeout'])
        )
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self.session:
            await self.session.close()

    async def retrieve_batch(self, queries: List[str], top_k: int = 5, data_source: Optional[List[str]] = None) -> List[List[Dict[str, Any]]]:
        """批量检索多个查询"""
        print(f"🚀 启动异步RAG检索，并发数: {self.max_concurrent}")

        # 创建所有任务
        tasks = []
        for query in queries:
            task = self._retrieve_single(query, top_k, data_source)
            tasks.append(task)

        # 等待所有任务完成
        results = await asyncio.gather(*tasks, return_exceptions=True)

        # 处理结果
        processed_results = []
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                print(f"   ⚠️ 查询 {i+1} 失败: {result}")
                processed_results.append([])
            else:
                processed_results.append(result)

        return processed_results

    async def _retrieve_single(self, query: str, top_k: int, data_source: Optional[List[str]]):
        """检索单个查询"""
        async with self.semaphore:  # 限制并发数
            payload = {
                "query": query,
                "top_k": top_k,
                "data_source": data_source or ["pubmed"],
                "language": "zh"
            }

            try:
                async with self.session.post(
                    self.config['url'],
                    headers=self.config['headers'],
                    json=payload
                ) as response:
                    result = await response.json()

                    # 标准化返回格式
                    if isinstance(result, dict) and 'results' in result:
                        return result['results']
                    elif isinstance(result, list):
                        return result
                    else:
                        return []

            except Exception as e:
                print(f"   ❌ 检索失败: {e}")
                return []

def enhance_seeds_with_async_rag(
    seed_questions: List[SeedQuestion],
    async_rag_client: AsyncRAGClient,
    top_k: int = 5,
    data_source: Optional[List[str]] = None,
    enable_ratio: float = 1.0
) -> List[SeedQuestion]:
    """
    使用异步RAG增强种子问题
    """
    import random
    random.seed(42)

    enhanced_seeds = []
    total_seeds = len(seed_questions)
    rag_seed_count = int(total_seeds * enable_ratio)

    if rag_seed_count < total_seeds:
        print(f"\n⚡ 性能优化：仅对 {rag_seed_count}/{total_seeds} ({enable_ratio*100:.0f}%) 个种子启用异步RAG增强")
    else:
        print(f"\n🚀 启动异步RAG增强处理 ({total_seeds} 个种子)")

    # 准备查询列表
    queries = []
    seed_indices = []
    for i, seed in enumerate(seed_questions):
        query = f"{seed.question} {seed.answer[:200]}"
        queries.append(query)
        seed_indices.append(i)

    # 执行异步批量检索
    start_time = time.time()
    results = asyncio.run(async_rag_client.retrieve_batch(queries, top_k, data_source))
    elapsed = time.time() - start_time

    print(f"✅ 异步检索完成！总耗时: {elapsed:.2f}秒，平均每查询: {elapsed/total_seeds:.2f}秒\n")

    # 构建增强的种子
    for i, (seed, documents) in enumerate(zip(seed_questions, results)):
        if documents:
            # 格式化RAG上下文
            rag_context = format_rag_context(documents)

            # 生成增强的提示词
            enhanced_prompt = generate_rag_enhanced_prompt(
                seed.question,
                seed.answer,
                rag_context
            )

            # 创建新的种子问题
            enhanced_seed = SeedQuestion(
                question=enhanced_prompt,
                answer=seed.answer,
                category=seed.category,
                difficulty=seed.difficulty,
                tags=seed.tags + ['rag_enhanced']
            )
            enhanced_seeds.append(enhanced_seed)
        else:
            enhanced_seeds.append(seed)

        if (i + 1) % 10 == 0 or (i + 1) == total_seeds:
            print(f"  ✓ 已处理 {i+1}/{total_seeds} ({(i+1)/total_seeds*100:.1f}%)")

    enhanced_count = len([s for s in enhanced_seeds if 'rag_enhanced' in s.tags])
    print(f"✅ RAG增强完成！增强了 {enhanced_count} 个种子\n")

    return enhanced_seeds

# 使用示例
async def main():
    """使用示例"""
    # 准备种子问题（假设已有）
    seed_questions = [...]  # 您的种子问题列表

    # 使用异步RAG客户端（并发数=5）
    async with AsyncRAGClient(max_concurrent=5) as client:
        enhanced_seeds = enhance_seeds_with_async_rag(
            seed_questions,
            client,
            top_k=3,
            data_source=['pubmed'],
            enable_ratio=1.0  # 对所有种子启用RAG
        )

    print(f"增强完成！总共 {len(enhanced_seeds)} 个种子")

if __name__ == "__main__":
    asyncio.run(main())
