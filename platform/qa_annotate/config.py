"""全局配置模块，支持从环境变量和.env文件读取配置"""

from pathlib import Path
from typing import Optional

from dotenv import load_dotenv
from pydantic_settings import BaseSettings, SettingsConfigDict

# 加载.env文件（如果存在）
# 从项目根目录查找.env文件
env_path = Path(__file__).parent.parent.parent / ".env"
load_dotenv(dotenv_path=env_path)


class Settings(BaseSettings):
    """应用配置类"""

    # 数据库配置（SQLite only）
    DB_DIR: Optional[str] = None  # 数据库目录路径，默认使用项目根目录下的data目录
    DB_NAME: str = "annotations.db"  # 数据库文件名

    # 服务器配置
    HOST: str = "0.0.0.0"  # 服务器监听地址
    PORT: int = 8000  # 服务器端口
    RELOAD: bool = False  # 是否启用自动重载（开发模式）

    # 环境配置
    ENVIRONMENT: str = "development"  # 环境类型：development 或 production
    PRODUCTION: bool = (
        False  # 是否为生产环境（PRODUCTION=true 等同于 ENVIRONMENT=production）
    )

    # 认证配置
    TOKEN_EXPIRE_DAYS: int = 7  # Token过期天数
    SECRET_KEY: str = "qaloop-demo-jwt-secret-key-32bytes"  # JWT密钥，Demo 默认值，生产环境务必修改
    ALGORITHM: str = "HS256"  # JWT算法

    # SQLAlchemy配置
    SQLALCHEMY_ECHO: bool = False  # 是否打印SQL语句

    # LLM 默认配置（可通过环境变量覆盖；API Key 建议用 LLM_API_KEY 注入）
    LLM_API_KEY: Optional[str] = None
    LLM_BASE_URL: str = "http://43.159.131.233:3001/v1"
    LLM_MODEL_NAME: str = "gpt-5.1"

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra="ignore",
    )

    @property
    def db_path(self) -> Path:
        """获取数据库文件路径"""
        # 使用DB_DIR或默认路径
        if self.DB_DIR:
            db_dir = Path(self.DB_DIR)
        else:
            # 默认使用项目根目录下的data目录
            db_dir = Path(__file__).parent.parent.parent / "data"

        db_dir.mkdir(parents=True, exist_ok=True)
        return db_dir / self.DB_NAME

    @property
    def database_url(self) -> str:
        """获取数据库URL（SQLite）"""
        return f"sqlite:///{self.db_path}"

    @property
    def is_production(self) -> bool:
        """判断是否为生产环境"""
        return self.ENVIRONMENT == "production" or self.PRODUCTION is True


# 创建全局配置实例
settings = Settings()
