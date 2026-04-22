import json
from typing import Any, List
from agents import Agent, OpenAIChatCompletionsModel, Runner
from agents.agent_output import AgentOutputSchemaBase
from openai import AsyncOpenAI
from config.global_storage import get_model_config
from utils.bio_logger import bio_logger as logger
from typing import List, Dict
from pydantic import BaseModel, Field,ConfigDict


class DateRange(BaseModel):
    # model_config = ConfigDict(strict=True)
    model_config = ConfigDict(strict=True, extra="forbid",json_schema_extra={"required": ["start", "end"]}) 
    start: str = Field('', description="Start date in YYYY-MM-DD format")
    end: str = Field('', description="End date in YYYY-MM-DD format")

class Journal(BaseModel):
    # model_config = ConfigDict(strict=True)
    model_config = ConfigDict(strict=True, extra="forbid",json_schema_extra={"required": ["name", "EISSN"]})
    name: str = Field(..., description="Journal name")
    EISSN: str = Field(..., description="Journal EISSN")

class AuthorFilter(BaseModel):
    # model_config = ConfigDict(strict=True)
    model_config = ConfigDict(strict=True, extra="forbid",json_schema_extra={"required": ["name", "first_author", "last_author"]}) 
    name: str = Field("", description="Author name to filter")
    first_author: bool = Field(False, description="Is first author?")
    last_author: bool = Field(False, description="Is last author?")


class Filters(BaseModel):
    # model_config = ConfigDict(strict=True)
    model_config = ConfigDict(strict=True, extra="forbid",json_schema_extra={"required": ["date_range", "article_types", "languages", "subjects", "journals", "author"]}) 
    date_range: DateRange = Field(...,default_factory=DateRange)
    article_types: List[str] = Field(...,default_factory=list)
    languages: List[str] = Field(["English"],)
    subjects: List[str] = Field(...,default_factory=list)
    journals: List[str] = Field([""])
    author: AuthorFilter = Field(...,default_factory=AuthorFilter)

class RewriteJsonOutput(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid",json_schema_extra={"required": ["category", "key_words", "key_journals", "queries", "filters"]}) 
    category: str = Field(..., description="Query category")
    key_words: List[str] = Field(...,default_factory=list)
    key_journals: List[Journal] = Field(...,default_factory=list)
    queries: List[str] = Field(...,default_factory=list)
    filters: Filters = Field(...,default_factory=Filters)


class SimpleJsonOutput(BaseModel):
    key_words: List[str] = Field(...,default_factory=list)
    

class RewriteJsonOutputSchema(AgentOutputSchemaBase):
    def is_plain_text(self):
        return False
    def name(self):
        return "RewriteJsonOutput"
    def json_schema(self):
        return RewriteJsonOutput.model_json_schema()
    def is_strict_json_schema(self):
        return True 
    def validate_json(self, json_data: Dict[str, Any]) -> bool:
        try:
            if isinstance(json_data, str):
                json_data = json.loads(json_data)  
            return RewriteJsonOutput.model_validate(json_data)
        
        except Exception as e:
            logger.error(f"Validation error: {e}")
            # return False
    def parse(self, json_data: Dict[str, Any]) -> Any:
        if isinstance(json_data, str):
            json_data = json.loads(json_data)  
        return json_data

class RewriteAgent:
    def __init__(self):
        self.model_config = get_model_config()
        self.agent_name = "rewrite agent"
        self.selected_model = OpenAIChatCompletionsModel(
            model=self.model_config["rewrite-llm"]["main"]["model"],
            openai_client=AsyncOpenAI(
                api_key=self.model_config["rewrite-llm"]["main"]["api_key"],
                base_url=self.model_config["rewrite-llm"]["main"]["base_url"],
                timeout=120.0,
                max_retries=2,
            ),
        )
        
        # self.openai_client = AsyncOpenAI(
        #     api_key=self.model_config["llm"]["api_key"],
        #     base_url=self.model_config["llm"]["base_url"],
        # )
        
        

    async def rewrite_query(self, query: str,INSTRUCTIONS: str,simple_version=False) -> List[str]:
        try:
            logger.info(f"Rewriting query with main configuration.")
            if not simple_version:
                rewrite_agent = Agent(
                    name=self.agent_name,
                    instructions=' Your task is to rewrite the query into a structured JSON format. Please do not answer the question.',
                    model=self.selected_model,
                    output_type=RewriteJsonOutputSchema(),  # Use the Pydantic model for structured output
                )
            else:
                rewrite_agent = Agent(
                    name=self.agent_name,
                    instructions=' Your task is to rewrite the query into a structured JSON format. Please do not answer the question.',
                    model=self.selected_model,
                    output_type=SimpleJsonOutput,  # Use the Pydantic model for structured output
                )
            result = await Runner.run(rewrite_agent, input=INSTRUCTIONS + 'Here is the question: '+query)
            # completion = await self.openai_client.chat.completions.create(
            #     model=self.model_config["llm"]["model"],
            #     messages=[
            #         # {
            #         #     "role": "system",
            #         #     "content": "You are a helpful assistant.",
            #         # },
            #         {
            #             "role": "user",
            #             "content": INSTRUCTIONS +' Here is the question: ' + query,
            #         },
            #     ],
            #     temperature=self.model_config["llm"]["temperature"],
            #     # max_tokens=self.model_config["llm"]["max_tokens"],
            # )
            try:
                # query_result = self.parse_json_output(completion.choices[0].message.content)
                query_result = self.parse_json_output(result.final_output.model_dump_json())
                # query_result = self.parse_json_output(completion.model_dump_json())
            except Exception as e:
                # print(completion.choices[0].message.content)
                logger.error(f"Failed to parse JSON output: {e}")
            return query_result
        except Exception as main_error:
            self.selected_model_backup = OpenAIChatCompletionsModel(
            model=self.model_config["rewrite-llm"]["backup"]["model"],
            openai_client=AsyncOpenAI(
                api_key=self.model_config["rewrite-llm"]["backup"]["api_key"],
                base_url=self.model_config["rewrite-llm"]["backup"]["base_url"],
                timeout=120.0,
                max_retries=2,
                ),
            )
            logger.error(f"Error with main model: {main_error}", exc_info=main_error)
            logger.info("Trying backup model for rewriting query.")
            if not simple_version:
                rewrite_agent = Agent(
                    name=self.agent_name,
                    instructions=' Your task is to rewrite the query into a structured JSON format. Please do not answer the question.',
                    model=self.selected_model_backup,
                    output_type=RewriteJsonOutputSchema(),  # Use the Pydantic model for structured output
                )
            else:
                rewrite_agent = Agent(
                    name=self.agent_name,
                    instructions=' Your task is to rewrite the query into a structured JSON format. Please do not answer the question.',
                    model=self.selected_model_backup,
                    output_type=SimpleJsonOutput,  # Use the Pydantic model for structured output
                )
            result = await Runner.run(rewrite_agent, input=INSTRUCTIONS + 'Here is the question: '+query)
            # completion = await self.openai_client.chat.completions.create(
            #     model=self.model_config["llm"]["model"],
            #     messages=[
            #         # {
            #         #     "role": "system",
            #         #     "content": "You are a helpful assistant.",
            #         # },
            #         {
            #             "role": "user",
            #             "content": INSTRUCTIONS +' Here is the question: ' + query,
            #         },
            #     ],
            #     temperature=self.model_config["llm"]["temperature"],
            #     # max_tokens=self.model_config["llm"]["max_tokens"],
            # )
            try:
                # query_result = self.parse_json_output(completion.choices[0].message.content)
                query_result = self.parse_json_output(result.final_output.model_dump_json())
                # query_result = self.parse_json_output(completion.model_dump_json())
            except Exception as e:
                # print(completion.choices[0].message.content)
                logger.error(f"Failed to parse JSON output: {e}")
            return query_result

    def parse_json_output(self, output: str) -> Any:
        """Take a string output and parse it as JSON"""
        # First try to load the string as JSON
        try:
            return json.loads(output)
        except json.JSONDecodeError as e:
            logger.info(f"Output is not valid JSON: {output}")
            logger.error(f"Failed to parse output as direct JSON: {e}")

        # If that fails, assume that the output is in a code block - remove the code block markers and try again
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
        
        # As a last attempt, try to manually find the JSON object in the output and parse it
        parsed_output = self.find_json_in_string(output)
        if parsed_output:
            try:
                return json.loads(parsed_output)
            except json.JSONDecodeError as e:
                logger.error(f"Failed to parse extracted JSON: {e}")
                logger.error(f"Extracted JSON: {parsed_output}")
                return {"queries": []}
        else:
            logger.error("No valid JSON found in the output:{output}")
        # If all fails, raise an error
        return {"queries": []}

    def find_json_in_string(self, string: str) -> str:
        """
        Method to extract all text in the left-most brace that appears in a string.
        Used to extract JSON from a string (note that this function does not validate the JSON).

        Example:
            string = "bla bla bla {this is {some} text{{}and it's sneaky}} because {it's} confusing"
            output = "{this is {some} text{{}and it's sneaky}}"
        """
        stack = 0
        start_index = None

        for i, c in enumerate(string):
            if c == "{":
                if stack == 0:
                    start_index = i  # Start index of the first '{'
                stack += 1  # Push to stack
            elif c == "}":
                stack -= 1  # Pop stack
                if stack == 0:
                    # Return the substring from the start of the first '{' to the current '}'
                    return (
                        string[start_index : i + 1] if start_index is not None else ""
                    )

        # If no complete set of braces is found, return an empty string
        return ""
