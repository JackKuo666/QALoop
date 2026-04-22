#!/usr/bin/env python3
"""
RAG缓存机制实现
避免重复查询，提升效率
"""
import json
import hashlib
import os
from pathlib import Path
from typing import Optional, List, Dict, Any

# Get the project root directory
PROJECT_ROOT = Path(__file__).parent.parent.parent
CACHE_DIR = PROJECT_ROOT / "data" / "processed" / "rag_cache"
CACHE_FILE = CACHE_DIR / "rag_cache.json"

def ensure_cache_dir():
    """确保缓存目录存在"""
    CACHE_DIR.mkdir(exist_ok=True)
    if not CACHE_FILE.exists():
        with open(CACHE_FILE, 'w') as f:
            json.dump({}, f, ensure_ascii=False, indent=2)

def get_cache_key(query: str, top_k: int, data_source: list) -> str:
    """
    生成缓存键

    Args:
        query: 查询内容
        top_k: 返回文档数量
        data_source: 数据源列表

    Returns:
        缓存键（MD5哈希）
    """
    # 创建规范化内容
    content = f"{query}:{top_k}:{','.join(sorted(data_source))}"
    return hashlib.md5(content.encode('utf-8')).hexdigest()

def get_cached_result(cache_key: str) -> Optional[List[Dict[str, Any]]]:
    """
    获取缓存结果

    Args:
        cache_key: 缓存键

    Returns:
        缓存的结果或None
    """
    try:
        ensure_cache_dir()
        with open(CACHE_FILE, 'r', encoding='utf-8') as f:
            cache = json.load(f)
            return cache.get(cache_key)
    except (FileNotFoundError, json.JSONDecodeError, Exception) as e:
        print(f"   ⚠️ 读取缓存失败: {e}")
        return None

def save_cache_result(cache_key: str, result: List[Dict[str, Any]]):
    """
    保存缓存结果

    Args:
        cache_key: 缓存键
        result: 检索结果
    """
    try:
        ensure_cache_dir()
        # 读取现有缓存
        cache = {}
        if CACHE_FILE.exists():
            with open(CACHE_FILE, 'r', encoding='utf-8') as f:
                cache = json.load(f)

        # 更新缓存
        cache[cache_key] = result

        # 保存（使用临时文件避免写入中断）
        temp_file = CACHE_FILE.with_suffix('.tmp')
        with open(temp_file, 'w', encoding='utf-8') as f:
            json.dump(cache, f, ensure_ascii=False, indent=2)
        temp_file.replace(CACHE_FILE)

        print(f"   💾 缓存已保存 (键: {cache_key[:16]}...)")

    except Exception as e:
        print(f"   ⚠️ 保存缓存失败: {e}")

def clear_cache():
    """清空缓存"""
    if CACHE_FILE.exists():
        CACHE_FILE.unlink()
        print("🗑️ 缓存已清空")
    else:
        print("ℹ️ 缓存不存在")

def get_cache_stats() -> Dict[str, Any]:
    """获取缓存统计信息"""
    ensure_cache_dir()
    if not CACHE_FILE.exists():
        return {
            'total_queries': 0,
            'cache_size_mb': 0,
            'oldest_query': None,
            'newest_query': None
        }

    try:
        with open(CACHE_FILE, 'r', encoding='utf-8') as f:
            cache = json.load(f)

        file_size = CACHE_FILE.stat().st_size / (1024 * 1024)  # MB

        return {
            'total_queries': len(cache),
            'cache_size_mb': round(file_size, 2),
            'oldest_query': min(cache.keys())[:16] + '...' if cache else None,
            'newest_query': max(cache.keys())[:16] + '...' if cache else None
        }
    except Exception as e:
        print(f"   ⚠️ 获取缓存统计失败: {e}")
        return {}

def print_cache_stats():
    """打印缓存统计信息"""
    stats = get_cache_stats()
    print("\n📊 RAG缓存统计:")
    print(f"   总查询数: {stats['total_queries']}")
    print(f"   缓存大小: {stats['cache_size_mb']} MB")
    if stats['oldest_query']:
        print(f"   最早查询: {stats['oldest_query']}")
    if stats['newest_query']:
        print(f"   最新查询: {stats['newest_query']}")

# 示例使用
if __name__ == "__main__":
    # 测试缓存功能
    query = "小麦育种技术"
    top_k = 5
    data_source = ['pubmed']

    cache_key = get_cache_key(query, top_k, data_source)
    print(f"缓存键: {cache_key}")

    # 模拟保存结果
    mock_result = [
        {"title": "示例文档1", "content": "内容1"},
        {"title": "示例文档2", "content": "内容2"}
    ]
    save_cache_result(cache_key, mock_result)

    # 获取缓存统计
    print_cache_stats()

    # 读取缓存
    cached = get_cached_result(cache_key)
    if cached:
        print(f"\n✅ 缓存命中: 找到 {len(cached)} 个结果")
    else:
        print("\n❌ 缓存未命中")
