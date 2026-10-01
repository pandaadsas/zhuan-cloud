import logging

from sqlalchemy import create_engine, event
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from .config import settings

logger = logging.getLogger("zhuan.db")

_db_mode = "mysql"


class Base(DeclarativeBase):
    pass


def _attach_engine_logging(eng) -> None:
    """记录连接池关键事件：新建连接/连接失效，便于排查远程库断连问题。"""

    @event.listens_for(eng, "connect")
    def _on_connect(dbapi_conn, record):
        logger.info("新建数据库连接 [%s]", eng.pool.status())

    @event.listens_for(eng, "invalidate")
    def _on_invalidate(dbapi_conn, exc):
        logger.warning("数据库连接失效即将重建：%s", exc)


def _make_engine():
    global _db_mode
    try:
        eng = create_engine(
            f"mysql+pymysql://{settings.db_user}:{settings.db_password}"
            f"@{settings.db_host}:{settings.db_port}/{settings.db_name}?charset=utf8mb4",
            pool_pre_ping=True,
            pool_recycle=1800,
            connect_args={"connect_timeout": 6, "read_timeout": 30, "write_timeout": 30},
        )
        _attach_engine_logging(eng)
        with eng.connect():
            pass
        _db_mode = "mysql"
        logger.info("数据库模式：MySQL(%s:%s/%s)", settings.db_host, settings.db_port, settings.db_name)
        return eng
    except Exception as e:  # 演示兜底：断网/数据库不可达时本地SQLite继续可用
        logger.warning("MySQL不可用(%s)，回退本地SQLite演示库", e)
        _db_mode = "sqlite"
        eng = create_engine(
            "sqlite:///./local_fallback.db",
            connect_args={"check_same_thread": False},
        )
        _attach_engine_logging(eng)
        return eng


engine = _make_engine()


def db_mode() -> str:
    return _db_mode


SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
