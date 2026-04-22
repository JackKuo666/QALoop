from dataclasses import dataclass, field
from typing import Optional
from utils.snowflake_id import snowflake_id_str


@dataclass
class BaseBioDocument:
    """生物医学文档基础类"""

    bio_id: Optional[str] = field(default_factory=snowflake_id_str)
    title: Optional[str] = None
    text: Optional[str] = None
    source: Optional[str] = None
    source_id: Optional[str] = None


@dataclass
class PubMedDocument(BaseBioDocument):
    """PubMed学术文献文档"""

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
class WebDocument(BaseBioDocument):
    """Web搜索文档"""

    url: Optional[str] = None
    description: Optional[str] = None

    def __post_init__(self):
        if self.source is None:
            self.source = "web"


@dataclass
class BioDocument(BaseBioDocument):
    """生物医学文档（向后兼容）"""

    abstract: Optional[str] = None
    authors: Optional[str] = None
    doi: Optional[str] = None
    journal: Optional[str] = None
    pub_date: Optional[str] = None
    if_score: Optional[float] = None
    url: Optional[str] = None


def create_bio_document(source: str, **kwargs) -> BaseBioDocument:
    """根据source类型创建相应的文档对象"""
    if source == "pubmed":
        return PubMedDocument(**kwargs)
    elif source == "web":
        return WebDocument(**kwargs)
    else:
        return BioDocument(**kwargs)
