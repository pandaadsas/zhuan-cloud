import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from .config import settings
from .database import Base, SessionLocal, db_mode, engine
from .migrate import run_migrations
from .rag.retriever import refresh_cache
from .seed import run_if_empty
from .services.knowledge import sync_builtin_knowledge

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")
logger = logging.getLogger("zhuan.main")

app = FastAPI(title="筑安云 API", version="1.0.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

from .routers import auth, chat, media, meta, orders, reports, stats, weekly  # noqa: E402
from .routers import settings as settings_router  # noqa: E402  # 避免与config.settings重名

app.include_router(auth.router)
app.include_router(meta.router)
app.include_router(reports.router)
app.include_router(orders.router)
app.include_router(chat.router)
app.include_router(stats.router)
app.include_router(weekly.router)
app.include_router(settings_router.router)
app.include_router(media.router)

app.mount("/uploads", StaticFiles(directory=str(settings.upload_dir)), name="uploads")


@app.on_event("startup")
def startup():
    Base.metadata.create_all(engine)
    run_migrations()
    db = SessionLocal()
    try:
        seeded = run_if_empty(db)
        logger.info("种子数据=%s", "已初始化" if seeded else "已存在")
        sync_builtin_knowledge(db)  # 内置规范切片入库（幂等）：替代旧版种子条款
    finally:
        db.close()

    mode = ""
    for attempt in range(3):  # 远程库偶发网络抖动：每次重试都用全新会话
        db = SessionLocal()
        try:
            mode = refresh_cache(db)
            break
        except Exception as e:
            logger.warning("知识库加载失败（第%d次）：%s", attempt + 1, e)
            db.rollback()
            import time

            time.sleep(2)
        finally:
            db.close()
    logger.info("筑安云启动完成 | 数据库=%s | 知识检索=%s", db_mode(), mode or "未就绪(稍后自动重试)")


dist = settings.frontend_dist
if dist.exists():
    app.mount("/", StaticFiles(directory=str(dist), html=True), name="spa")
