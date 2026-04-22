from typing import Dict, Any
from bio_agent.hypothetical_answer_agent import HypotheticalAnswerAgent
from utils.bio_logger import bio_logger as logger


class HypotheticalAnswerService:
    """假设性回答服务"""

    def __init__(self):
        self.agent = HypotheticalAnswerAgent()

    async def generate_hypothetical_answer(self, query: str) -> str:
        """
        生成假设性回答

        Args:
            query: 用户查询字符串

        Returns:
            包含原始查询和假设性回答的字典
            格式: {
                "query": "原始查询",
                "hypothetical_answer": "生成的假设性回答"
            }
        """
        try:
            logger.info(f"Starting hypothetical answer generation for query: {query}")

            if not query or not query.strip():
                logger.warning(
                    "Empty query provided for hypothetical answer generation"
                )
                return query

            # 调用agent生成假设性回答
            result = await self.agent.generate_hypothetical_answer(query)

            logger.info(
                f"Successfully generated hypothetical answer for query: {query}"
            )
            return result["hypothetical_answer"]

        except Exception as e:
            logger.error(
                f"Error generating hypothetical answer for query '{query}': {e}",
                exc_info=e,
            )
            return query

    async def batch_generate_hypothetical_answers(
        self, queries: list[str]
    ) -> list[Dict[str, Any]]:
        """
        批量生成假设性回答

        Args:
            queries: 查询字符串列表

        Returns:
            假设性回答字典列表
        """
        results = []

        for query in queries:
            try:
                result = await self.generate_hypothetical_answer(query)
                results.append(result)
            except Exception as e:
                logger.error(f"Error processing query '{query}' in batch: {e}")
                results.append(
                    {
                        "query": query,
                        "hypothetical_answer": "Failed to generate hypothetical answer for this query.",
                    }
                )

        return results

    def get_agent_status(self) -> Dict[str, Any]:
        """
        获取agent状态信息

        Returns:
            agent状态信息
        """
        return {
            "agent_name": self.agent.agent_name,
            "model_config": {
                "main_model": self.agent.model_config["hypothetical-answer-llm"][
                    "main"
                ]["model"],
                "has_backup": hasattr(self.agent, "backup_model"),
                "prompt_configured": bool(self.agent.hypothetical_prompt),
            },
        }
