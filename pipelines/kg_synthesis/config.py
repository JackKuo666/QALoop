from dotenv import load_dotenv
import os

load_dotenv()

NEO4J_URI = os.getenv("NEO4J_URI", "bolt://localhost:7687")
NEO4J_USER = os.getenv("NEO4J_USER", "neo4j")
NEO4J_PASSWORD = os.getenv("NEO4J_PASSWORD", "")

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
OPENAI_BASE_URL = os.getenv("OPENAI_BASE_URL")
LLM_MODEL = "gpt-4o-mini"   # 或你本地的 Qwen / DeepSeek

# 本地OSS配置
USE_LOCAL_OSS = os.getenv("USE_LOCAL_OSS", "false").lower() == "true"
LOCAL_OSS_API_KEY = os.getenv("LOCAL_OSS_API_KEY")
LOCAL_OSS_BASE_URL = os.getenv("LOCAL_OSS_BASE_URL")

# 模型别名映射（参考argi_filter_v4_local.py）
MODEL_ALIASES = {
    "gpt-oss-120b": "gpt-4",
    "qwen-local": "Qwen/Qwen2.5-72B-Instruct",
    "deepseek-local": "deepseek-chat",
    "local-120b": "gpt-4",
}

def get_current_api_config():
    """
    根据USE_LOCAL_OSS配置返回当前使用的API配置
    Returns:
        tuple: (api_key, base_url, model_name)
    """
    if USE_LOCAL_OSS:
        # 使用本地OSS配置
        return (
            LOCAL_OSS_API_KEY or OPENAI_API_KEY,
            LOCAL_OSS_BASE_URL or OPENAI_BASE_URL,
            LLM_MODEL
        )
    else:
        # 使用标准OpenAI配置
        return OPENAI_API_KEY, OPENAI_BASE_URL, LLM_MODEL

def get_model_id(model_name: str) -> str:
    """获取模型ID（应用别名映射）"""
    return MODEL_ALIASES.get(model_name, model_name)
