import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from .config import settings
from .database import Base, SessionLocal, db_mode, engine
from .rag.retriever import refresh_cache
from .seed import run_if_empty

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

app.include_router(auth.router)
app.include_router(meta.router)
app.include_router(reports.router)
app.include_router(orders.router)
app.include_router(chat.router)
app.include_router(stats.router)
app.include_router(weekly.router)
app.include_router(media.router)

app.mount("/uploads", StaticFiles(directory=str(settings.upload_dir)), name="uploads")


@app.on_event("startup")
def startup():
    Base.metadata.create_all(engine)
    db = SessionLocal()
    try:
        seeded = run_if_empty(db)
        mode = refresh_cache(db)
        logger.info(
            "筑安云启动完成 | 数据库=%s | 知识检索=%s | 种子数据=%s",
            db_mode(),
            mode,
            "已初始化" if seeded else "已存在",
        )
    finally:
        db.close()


dist = settings.frontend_dist
if dist.exists():
    app.mount("/", StaticFiles(directory=str(dist), html=True), name="spa")
