import json
from typing import Any, Dict
from openai import AsyncOpenAI
from config.global_storage import get_model_config
from utils.bio_logger import bio_logger as logger


class HypotheticalAnswerAgent:
    def __init__(self):
        self.model_config = get_model_config()
        self.agent_name = "hypothetical answer agent"

        # 初始化主模型
        self.main_client = AsyncOpenAI(
            api_key=self.model_config["hypothetical-answer-llm"]["main"]["api_key"],
            base_url=self.model_config["hypothetical-answer-llm"]["main"]["base_url"],
            timeout=120.0,
            max_retries=2,
        )
        self.main_model = self.model_config["hypothetical-answer-llm"]["main"]["model"]

        # 初始化备用模型
        self.backup_client = AsyncOpenAI(
            api_key=self.model_config["hypothetical-answer-llm"]["backup"]["api_key"],
            base_url=self.model_config["hypothetical-answer-llm"]["backup"]["base_url"],
            timeout=120.0,
            max_retries=2,
        )
        self.backup_model = self.model_config["hypothetical-answer-llm"]["backup"][
            "model"
        ]

        # 获取假设性回答的prompt配置
        self.hypothetical_prompt = self.model_config.get("hypothetical_answer", {}).get(
            "prompt", ""
        )
        if not self.hypothetical_prompt:
            logger.warning(
                "hypothetical_answer prompt not found in config, using default prompt"
            )
            self.hypothetical_prompt = self._get_default_prompt()

    def _get_default_prompt(self) -> str:
        """获取默认的假设性回答prompt"""
        return """
        # Role Definition
        You are an information retrieval specialist. Your task is to generate hypothetical answers for query vectorization optimization.
        
        # Core Instructions
        Generate a **HYPOTHETICAL ANSWER** based on user queries that must:
        1. **Maximize information density** - Cover core intent with key entities, terminology, and related concepts
        2. **Maintain structural discipline** - Use objective, expository writing style (third-person perspective)
        3. **Control token length** - Contain 2-4 complete sentences (40-70 tokens exactly)
        4. **Expand semantics** - Include relevant synonyms, hypernyms, and contextual scenarios
        5. **Prioritize retrieval over facts** - Accuracy is not required; focus on vectorization-friendly expressions
        
        # Generation Rules
        - If query is ambiguous: Respond: "Clarification needed: Please refine your query"
        - For sensitive topics: Respond: "Query containment alert: Suggest reformulating"
        - Language style: Technical documentation tone (avoid colloquialisms)
        
        # Output Format
        STRICTLY use this JSON structure:
        ```json
        {
          "query": "Original user query",
          "hypothetical_answer": "Generated answer text" 
        }
        ```
        
        # The user's message is:
        {query}
        """

    async def generate_hypothetical_answer(self, query: str) -> Dict[str, Any]:
        """
        生成假设性回答

        Args:
            query: 用户查询

        Returns:
            包含原始查询和假设性回答的字典
        """
        try:
            logger.info(
                f"Generating hypothetical answer with main model for query: {query}"
            )

            # 使用主模型生成假设性回答
            result = await self._generate_with_model(
                query, self.main_client, self.main_model, "main"
            )
            return result

        except Exception as main_error:
            logger.error(f"Error with main model: {main_error}", exc_info=main_error)
            logger.info("Trying backup model for hypothetical answer generation.")

            try:
                # 使用备用模型生成假设性回答
                result = await self._generate_with_model(
                    query, self.backup_client, self.backup_model, "backup"
                )
                return result

            except Exception as backup_error:
                logger.error(
                    f"Error with backup model: {backup_error}", exc_info=backup_error
                )
                # 如果主备模型都失败，返回默认响应
                return self._get_fallback_response(query)

    async def _generate_with_model(
        self, query: str, client: AsyncOpenAI, model: str, model_type: str
    ) -> Dict[str, Any]:
        """
        使用指定模型生成假设性回答

        Args:
            query: 用户查询
            client: OpenAI客户端
            model: 模型名称
            model_type: 模型类型（main/backup）

        Returns:
            生成的假设性回答
        """
        # 格式化prompt
        formatted_prompt = self.hypothetical_prompt.replace("{query}", query)

        try:
            # 直接使用chat completion
            response = await client.chat.completions.create(
                model=model,
                messages=[
                    {
                        "role": "system",
                        "content": "You are an information retrieval specialist. Your task is to generate hypothetical answers for query vectorization optimization.",
                    },
                    {"role": "user", "content": formatted_prompt},
                ],
                temperature=0.1,
                max_tokens=500,
            )

            # 获取响应内容
            output_text = response.choices[0].message.content
            if not output_text:
                logger.error(f"Empty response from {model_type} model")
                raise Exception("Empty response from model")

            logger.info(f"Raw output from {model_type} model: {output_text}")

            # 解析输出
            output_data = self.parse_json_output(output_text)
            logger.info(
                f"Successfully generated hypothetical answer with {model_type} model"
            )
            return output_data

        except Exception as e:
            logger.error(f"Failed to generate with {model_type} model: {e}")
            raise e

    def parse_json_output(self, output: str) -> Dict[str, Any]:
        """解析JSON输出"""
        if not output or not isinstance(output, str):
            logger.error(f"Invalid output type: {type(output)}")
            return self._get_fallback_response("")

        try:
            return json.loads(output)
        except json.JSONDecodeError as e:
            logger.info(f"Output is not valid JSON: {output}")
            logger.error(f"Failed to parse output as direct JSON: {e}")

        # 如果直接解析失败，尝试从代码块中提取JSON
        parsed_output = output
        if "```" in parsed_output:
            try:
                parts = parsed_output.split("```")
                if len(parts) >= 3:
                    parsed_output = parts[1]
                    if parsed_output.startswith("json") or parsed_output.startswith(
                        "JSON"
                    ):
                        parsed_output = parsed_output[4:].strip()
                    return json.loads(parsed_output)
            except (IndexError, json.JSONDecodeError) as e:
                logger.error(f"Failed to parse output from code block: {e}")

        # 最后尝试手动查找JSON对象
        parsed_output = self.find_json_in_string(output)
        if parsed_output:
            try:
                return json.loads(parsed_output)
            except json.JSONDecodeError as e:
                logger.error(f"Failed to parse extracted JSON: {e}")
                logger.error(f"Extracted JSON: {parsed_output}")
                return self._get_fallback_response("")
        else:
            logger.error(f"No valid JSON found in the output: {output}")

        return self._get_fallback_response("")

    def find_json_in_string(self, string: str) -> str:
        """
        从字符串中提取JSON对象
        """
        if not string or not isinstance(string, str):
            return ""

        stack = 0
        start_index = None

        for i, c in enumerate(string):
            if c == "{":
                if stack == 0:
                    start_index = i
                stack += 1
            elif c == "}":
                stack -= 1
                if stack == 0 and start_index is not None:
                    extracted = string[start_index : i + 1]
                    # 验证提取的字符串是否是有效的JSON
                    try:
                        json.loads(extracted)
                        return extracted
                    except json.JSONDecodeError:
                        # 如果不是有效JSON，继续查找下一个
                        stack = 0
                        start_index = None

        return ""

    def _get_fallback_response(self, query: str) -> Dict[str, Any]:
        """获取fallback响应"""
        return {
            "query": query,
            "hypothetical_answer": "Unable to generate hypothetical answer due to model error. Please try again.",
        }
