from dataclasses import dataclass, field
from typing import Optional
from utils.snowflake_id import snowflake_id_str


@dataclass
class BaseBioDocument:
    """
    生物医学文档基础类
    包含所有搜索类型共有的字段
    """

    bio_id: Optional[str] = field(default_factory=snowflake_id_str)
    title: Optional[str] = None
    text: Optional[str] = None
    source: Optional[str] = None
    source_id: Optional[str] = None


@dataclass
class PubMedDocument(BaseBioDocument):
    """
    PubMed学术文献文档
    包含学术文献特有的字段
    """

    abstract: Optional[str] = None
    authors: Optional[str] = None
    doi: Optional[str] = None
    journal: Optional[str] = None
    pub_date: Optional[str] = None
    if_score: Optional[float] = None
    url: Optional[str] = None

    def __post_init__(self):
        if self.source is None:
            self.source = "pubmed"


@dataclass
class PersonalDocument(BaseBioDocument):
    """
    个人向量搜索文档
    包含个人文档特有的字段
    """

    if_score: Optional[float] = None
    doc_id: Optional[str] = None
    index: Optional[int] = 0
    user_id: Optional[str] = None
    file_name: Optional[str] = None

    def __post_init__(self):
        if self.source is None:
            self.source = "personal_vector"


@dataclass
class WebDocument(BaseBioDocument):
    """
    Web搜索文档
    包含网页内容特有的字段
    """

    url: Optional[str] = None
    description: Optional[str] = None

    def __post_init__(self):
        if self.source is None:
            self.source = "web"


# 为了保持向后兼容，保留原有的BioDocument类
@dataclass
class BioDocument(BaseBioDocument):
    """
    生物医学文档（向后兼容）
    包含所有可能的字段，但建议使用专门的文档类型
    """

    abstract: Optional[str] = None
    authors: Optional[str] = None
    doi: Optional[str] = None
    journal: Optional[str] = None
    pub_date: Optional[str] = None
    if_score: Optional[float] = None
    url: Optional[str] = None
    doc_id: Optional[str] = None


# 工厂函数，根据source类型创建相应的文档对象
def create_bio_document(source: str, **kwargs) -> BaseBioDocument:
    """
    根据source类型创建相应的文档对象

    Args:
        source: 文档来源类型 ("pubmed", "personal_vector", "web")
        **kwargs: 文档字段

    Returns:
        相应的文档对象
    """
    if source == "pubmed":
        return PubMedDocument(**kwargs)
    elif source == "personal_vector":
        return PersonalDocument(**kwargs)
    elif source == "web":
        return WebDocument(**kwargs)
    else:
        # 默认使用通用BioDocument
        return BioDocument(**kwargs)
