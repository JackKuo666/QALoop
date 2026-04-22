from openai import OpenAI
from config import get_current_api_config, get_model_id

# 动态获取当前API配置
api_key, base_url, model_name = get_current_api_config()

# 创建客户端
client = OpenAI(
    api_key=api_key,
    base_url=base_url
)

def call_llm(prompt, model: str = None):
    """
    调用LLM模型

    Args:
        prompt: 输入提示
        model: 可选的模型名称，如果未指定则使用配置中的默认模型
    """
    # 获取实际使用的模型ID（应用别名映射）
    actual_model = get_model_id(model) if model else get_model_id(model_name)

    resp = client.chat.completions.create(
        model=actual_model,
        messages=[{"role": "user", "content": prompt}],
        temperature=0.2
    )
    return resp.choices[0].message.content

def get_current_api_info():
    """
    获取当前使用的API信息
    Returns:
        dict: 包含api_key状态、base_url、model_name的信息
    """
    return {
        "api_key_configured": bool(api_key),
        "base_url": base_url,
        "model_name": model_name,
        "actual_model": get_model_id(model_name)
    }
