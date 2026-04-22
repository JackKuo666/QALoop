#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
大模型客户端 - 支持多种LLM API，包含.env文件支持
"""

import json
import requests
import time
import os
from pathlib import Path
from typing import Dict, Optional, List
import re


def load_env():
    """加载.env文件（从脚本所在目录）"""
    # 优先从脚本目录加载，其次从当前工作目录
    script_dir = Path(__file__).parent
    env_file = script_dir / '.env'
    if not env_file.exists():
        env_file = Path('.env')
    if env_file.exists():
        with open(env_file, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith('#'):
                    if '=' in line:
                        key, value = line.split('=', 1)
                        os.environ[key.strip()] = value.strip()


# ================================
# API配置（参考 argi_filter_v4_local.py）
# ================================

# 本地OSS模型配置
LOCAL_API_BASE_URL = os.getenv("LOCAL_API_BASE_URL", "https://api.deepseek.com/v1")
LOCAL_API_KEY = os.getenv("LOCAL_API_KEY", "local")

# OpenAI API配置
OPENAI_API_BASE_URL = os.getenv("OPENAI_API_BASE_URL", "https://api.openai.com/v1")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")

# Anthropic API配置
ANTHROPIC_API_BASE_URL = os.getenv("ANTHROPIC_API_BASE_URL", "https://api.anthropic.com")
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")

# 当前使用的API端点（可动态切换）
CURRENT_API_BASE_URL = OPENAI_API_BASE_URL
CURRENT_API_KEY = OPENAI_API_KEY
CURRENT_API_TYPE = "openai"  # 默认使用OpenAI


def set_api_endpoint(use_local: bool = True):
    """
    设置API端点（参考 argi_filter_v4_local.py）

    Args:
        use_local: True 使用本地模型，False 使用OpenAI
    """
    global CURRENT_API_BASE_URL, CURRENT_API_KEY, CURRENT_API_TYPE

    if use_local:
        CURRENT_API_BASE_URL = LOCAL_API_BASE_URL
        CURRENT_API_KEY = LOCAL_API_KEY
        CURRENT_API_TYPE = "local"
    else:
        # 优先使用环境变量中的OPENAI_BASE_URL，如果没有则使用默认值
        CURRENT_API_BASE_URL = os.environ.get('OPENAI_BASE_URL') or OPENAI_API_BASE_URL
        CURRENT_API_KEY = os.environ.get('OPENAI_API_KEY') or OPENAI_API_KEY
        CURRENT_API_TYPE = "openai"

    # 打印当前配置
    print(f"✅ API端点已切换到: {CURRENT_API_TYPE}")
    print(f"   Base URL: {CURRENT_API_BASE_URL}")


class LLMClient:
    """大模型客户端"""

    def __init__(self, config: Optional[Dict] = None):
        """
        初始化LLM客户端

        Args:
            config: 配置字典，包含API类型和参数
        """
        # 加载.env文件
        load_env()

        self.config = config or self._default_config()
        self.api_type = self.config.get('api_type', 'mock')

    def _default_config(self) -> Dict:
        """默认配置"""
        # 优先从环境变量读取，默认使用openai
        api_type = os.environ.get('LLM_API_TYPE', 'openai').lower()
        return {
            'api_type': api_type,
            'timeout': int(os.environ.get('TIMEOUT', 60)),
            'max_retries': int(os.environ.get('MAX_RETRIES', 3)),
            'mock_responses': False  # 默认不启用mock模式
        }

    def generate_response(self, prompt: str, **kwargs) -> str:
        """
        生成LLM响应

        Args:
            prompt: 输入提示词
            **kwargs: 其他参数

        Returns:
            生成的文本响应
        """
        if self.api_type == 'mock':
            return self._mock_response(prompt, **kwargs)
        elif self.api_type == 'openai':
            return self._openai_call(prompt, **kwargs)
        elif self.api_type == 'anthropic':
            return self._anthropic_call(prompt, **kwargs)
        elif self.api_type == 'local':
            return self._local_call(prompt, **kwargs)
        else:
            raise ValueError(f"Unsupported API type: {self.api_type}")

    def _mock_response(self, prompt: str, **kwargs) -> str:
        """模拟LLM响应 - 简化版本"""
        # 简化模拟响应，只做基本格式化
        # 不硬编码基因知识，让用户配置真实API
        
        if "基因" in prompt and ("功能" in prompt or "作用" in prompt):
            # 提取基因名
            gene_match = re.search(r'基因名称[：:]\s*([^\n]+)', prompt)
            if gene_match:
                gene_name = gene_match.group(1).strip()
                # 不硬编码具体功能，而是生成通用回答
                return f"基因{gene_name}在植物中发挥重要的调控作用。具体功能需要查阅最新的科学文献或使用真实的大模型API来获取准确信息。建议配置OpenAI API密钥以获得更详细和准确的答案。"
            
        elif "调控" in prompt or "机制" in prompt:
            return "基因调控是一个复杂的多层次过程，涉及转录因子与DNA的相互作用。如需详细信息，请配置真实的大模型API。"
        
        elif "表型" in prompt:
            return "表型是基因型与环境相互作用的结果。如需详细信息，请配置真实的大模型API。"
        
        else:
            return "这是一个植物生物学问题。如需详细回答，请配置真实的大模型API。"

    def _openai_call(self, prompt: str, **kwargs) -> str:
        """调用OpenAI API（支持本地/远程端点动态切换）"""
        try:
            # 使用全局API配置（支持本地/远程切换）
            global CURRENT_API_BASE_URL, CURRENT_API_KEY, CURRENT_API_TYPE

            # 如果当前是本地模型，直接使用本地调用
            if CURRENT_API_TYPE == "local":
                return self._local_openai_compatible_call(prompt, **kwargs)

            # 检查API密钥（仅远程API需要）
            api_key = CURRENT_API_KEY or os.environ.get('OPENAI_API_KEY')
            if not api_key or api_key == 'your-openai-api-key-here':
                raise ValueError("未配置有效的OpenAI API密钥。请在.env文件中设置OPENAI_API_KEY。")

            import openai
            from openai import OpenAI

            # 使用当前配置的base_url（set_api_endpoint已经处理了环境变量）
            base_url = CURRENT_API_BASE_URL
            timeout = float(os.environ.get('OPENAI_TIMEOUT', '60.0'))

            client = OpenAI(api_key=api_key, base_url=base_url, timeout=timeout)

            model = os.environ.get('OPENAI_MODEL', os.environ.get('DEFAULT_MODEL', 'gpt-5.1'))
            temperature = float(os.environ.get('OPENAI_TEMPERATURE', '0.7'))
            max_tokens = int(os.environ.get('OPENAI_MAX_TOKENS', '8000'))

            response = client.chat.completions.create(
                model=model,
                messages=[{"role": "user", "content": prompt}],
                temperature=temperature,
                max_tokens=max_tokens,
                stream=False,
            )

            return response.choices[0].message.content.strip()

        except ValueError as ve:
            print(f"\n⚠️  配置错误: {ve}")
            print("\n📝 配置步骤:")
            print("1. 在.env文件中设置: OPENAI_API_KEY=your-real-api-key")
            print("2. 或者将LLM_API_TYPE设置为mock进行测试")
            print("\n🔄 正在使用mock响应进行测试...")
            return self._mock_response(prompt)
        except ImportError:
            print("\n⚠️  错误: openai包未安装")
            print("请运行: pip install openai")
            print("\n🔄 正在使用mock响应进行测试...")
            return self._mock_response(prompt)
        except Exception as e:
            print(f"\n⚠️  OpenAI API调用失败: {e}")
            print("请检查API密钥、网络连接或API额度")
            print("\n🔄 正在使用mock响应进行测试...")
            return self._mock_response(prompt)

    def _local_openai_compatible_call(self, prompt: str, **kwargs) -> str:
        """
        调用本地OpenAI兼容API（参考 argi_filter_v4_local.py）
        """
        try:
            import openai
            from openai import OpenAI

            # 使用本地API配置
            client = OpenAI(
                api_key=LOCAL_API_KEY,
                base_url=LOCAL_API_BASE_URL,
                timeout=60.0
            )

            # 默认使用 gpt-oss-120b 模型
            model = os.environ.get('LOCAL_MODEL', 'gpt-oss-120b')
            temperature = float(os.environ.get('OPENAI_TEMPERATURE', '0.7'))
            max_tokens = int(os.environ.get('OPENAI_MAX_TOKENS', '8000'))

            response = client.chat.completions.create(
                model=model,
                messages=[{"role": "user", "content": prompt}],
                temperature=temperature,
                max_tokens=max_tokens,
                stream=False,
            )

            return response.choices[0].message.content.strip()

        except ImportError:
            print("⚠️  错误: openai包未安装")
            return self._mock_response(prompt)
        except Exception as e:
            print(f"⚠️  本地API调用失败: {e}")
            return self._mock_response(prompt)

    def _anthropic_call(self, prompt: str, **kwargs) -> str:
        """调用Anthropic Claude API"""
        try:
            import anthropic

            client = anthropic.Anthropic(
                api_key=os.environ.get('ANTHROPIC_API_KEY', self.config.get('api_key'))
            )

            model = os.environ.get('ANTHROPIC_MODEL', 'claude-3-sonnet-20240229')
            max_tokens = int(os.environ.get('ANTHROPIC_MAX_TOKENS', '1000'))
            temperature = float(os.environ.get('ANTHROPIC_TEMPERATURE', '0.7'))

            response = client.messages.create(
                model=model,
                max_tokens=max_tokens,
                messages=[{"role": "user", "content": prompt}],
                temperature=temperature,
                timeout=self.config.get('timeout', 60)
            )

            return response.content[0].text.strip()

        except ImportError:
            print("Warning: anthropic package not installed. Run: pip install anthropic")
            return self._mock_response(prompt)
        except Exception as e:
            print(f"Anthropic API调用失败: {e}")
            return self._mock_response(prompt)

    def _local_call(self, prompt: str, **kwargs) -> str:
        """调用本地LLM API（如Ollama）"""
        try:
            url = self.config.get('local_api_url', 'http://localhost:11434/api/generate')
            model = self.config.get('model', 'llama2')

            payload = {
                "model": model,
                "prompt": prompt,
                "stream": False
            }

            response = requests.post(
                url,
                json=payload,
                timeout=self.config.get('timeout', 60)
            )

            if response.status_code == 200:
                result = response.json()
                return result.get('response', '').strip()
            else:
                print(f"本地API调用失败: {response.status_code}")
                return self._mock_response(prompt)

        except Exception as e:
            print(f"本地API调用失败: {e}")
            return self._mock_response(prompt)

    def batch_generate(self, prompts: List[str], **kwargs) -> List[str]:
        """
        批量生成响应

        Args:
            prompts: 提示词列表
            **kwargs: 其他参数

        Returns:
            响应列表
        """
        responses = []
        for i, prompt in enumerate(prompts):
            try:
                print(f"  处理 {i+1}/{len(prompts)}...")
                response = self.generate_response(prompt, **kwargs)
                responses.append(response)
                time.sleep(0.1)  # 避免过快调用
            except Exception as e:
                print(f"    警告: {e}")
                responses.append(self._mock_response(prompt))

        return responses


class EnhancedLLMQAGenerator:
    """增强的LLM QA生成器"""

    def __init__(self, llm_client: Optional[LLMClient] = None):
        """
        初始化

        Args:
            llm_client: LLM客户端实例
        """
        self.llm_client = llm_client or LLMClient()
        self.qa_pairs = []

    def generate_enhanced_qa(self, qa_data: Dict) -> Dict:
        """
        基于知识图谱数据生成增强QA

        Args:
            qa_data: 知识图谱QA数据

        Returns:
            增强后的QA数据
        """
        # 提取基本信息
        question = qa_data.get('question', '')
        entity = qa_data.get('entity', '')
        entities = qa_data.get('entities', [])
        relations = qa_data.get('relations', [])

        # 构建提示词
        prompt = self._build_prompt(question, entity, entities, relations)

        # 调用LLM生成增强答案
        enhanced_answer = self.llm_client.generate_response(prompt)

        # 构建增强QA
        enhanced_qa = qa_data.copy()
        enhanced_qa['enhanced_answer'] = enhanced_answer
        enhanced_qa['prompt'] = prompt
        enhanced_qa['llm_used'] = True

        return enhanced_qa

    def _build_prompt(self, question: str, entity: str, entities: List[str], relations: List[str]) -> str:
        """构建提示词"""
        prompt = f"""
请基于以下知识图谱信息，用自然流畅的语言回答问题：

问题：{question}

"""

        if entity:
            prompt += f"核心实体：{entity}\n"

        if entities:
            prompt += f"涉及实体：{', '.join(entities)}\n"

        if relations:
            prompt += f"关系：{', '.join(relations)}\n"

        prompt += """
要求：
1. 回答要自然流畅，符合人类问答习惯
2. 用通俗易懂的语言解释复杂的生物学概念
3. 可以适当补充背景知识，帮助理解
4. 保持科学严谨性
5. 字数控制在200-300字
6. 可以使用生动的比喻和例子

请直接给出答案：
"""
        return prompt

    def enhance_existing_qa(self, qa_file: str, output_file: str):
        """
        增强现有的QA文件

        Args:
            qa_file: 输入QA文件路径
            output_file: 输出文件路径
        """
        print(f"📥 加载QA文件: {qa_file}")

        with open(qa_file, 'r', encoding='utf-8') as f:
            qa_data = json.load(f)

        print(f"✅ 加载了 {len(qa_data)} 个QA对")

        print(f"\n🤖 开始LLM增强...")
        enhanced_qa = []

        for i, qa in enumerate(qa_data):
            print(f"  处理 {i+1}/{len(qa_data)}...")
            try:
                enhanced = self.generate_enhanced_qa(qa)
                enhanced_qa.append(enhanced)
            except Exception as e:
                print(f"    警告: {e}")
                enhanced_qa.append(qa)

        print(f"✅ LLM增强完成")

        # 保存增强后的QA
        print(f"💾 保存到: {output_file}")
        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(enhanced_qa, f, ensure_ascii=False, indent=2)

        print(f"✅ 保存完成")


# 使用示例
if __name__ == "__main__":
    # 测试LLM客户端
    client = LLMClient()

    # 测试单个响应
    response = client.generate_response(
        "请解释基因RVE4的主要功能和作用机制？"
    )
    print(f"LLM响应:\n{response}\n")

    # 测试批量生成
    prompts = [
        "请解释基因WRKY26的功能？",
        "请解释表型enhanced suberization的形成机制？",
        "请解释MYB83对Secondary Wall Biosynthesis的调控机制？"
    ]

    responses = client.batch_generate(prompts)
    for prompt, response in zip(prompts, responses):
        print(f"问题: {prompt}")
        print(f"答案: {response}\n")
