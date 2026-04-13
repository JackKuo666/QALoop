"""数据库基础配置"""

from sqlalchemy import create_engine, event
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker

from qa_annotate.config import settings

# 数据库 URL（SQLite）
DATABASE_URL = settings.database_url

# 为了向后兼容，导出这些变量（供脚本使用）
DB_PATH = settings.db_path
DB_DIR = settings.db_path.parent

# 创建引擎
engine = create_engine(
    DATABASE_URL,
    connect_args={"check_same_thread": False},
    echo=settings.SQLALCHEMY_ECHO,
)


@event.listens_for(engine, "connect")
def set_sqlite_pragma(dbapi_conn, connection_record):
    """在每次连接建立时启用 SQLite 外键约束"""
    cursor = dbapi_conn.cursor()
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.close()


# 创建会话工厂
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# 创建基类
Base = declarative_base()


def get_db():
    """获取数据库会话（生成器函数）"""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db():
    """初始化数据库（创建所有表）"""
    Base.metadata.create_all(bind=engine)
    print(f"数据库已初始化: {settings.db_path}")
