from pydantic import BaseModel, Field


class ChatRequest(BaseModel):
    query: str = Field(default="", description="Search query")

    is_web: bool = Field(
        default=False, description="Whether to use web search, default is False"
    )

    is_pubmed: bool = Field(
        default=True, description="Whether to use pubmed search, default is True"
    )

    is_personal_vector: bool = Field(
        default=False,
        description="Whether to use personal vector search, default is False, if True, user_id is required",
    )

    user_id: str = Field(default="", description="User ID for tracking purposes")

    language: str = Field(
        default="en", description="Response language (zh/en), default is English"
    )
