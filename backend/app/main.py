import logging
import time

from colorama import just_fix_windows_console
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from .config import settings
from .database import Base, SessionLocal, db_mode, engine
from .migrate import run_migrations
from .rag.retriever import refresh_cache
from .seed import run_if_empty
from .services.knowledge import sync_builtin_knowledge

just_fix_windows_console()  # 让旧版 Windows 控制台也能显示 ANSI 颜色

_LEVEL_COLORS = {
    "DEBUG": "\033[36m",  # 青
    "INFO": "\033[32m",  # 绿
    "WARNING": "\033[33m",  # 黄
    "ERROR": "\033[1;31m",  # 亮红
    "CRITICAL": "\033[1;97;41m",  # 红底白字
}
_RESET = "\033[0m"


class ColorFormatter(logging.Formatter):
    """按日志级别着色：DEBUG/INFO/WARNING 只染级别标签，ERROR 及以上整行高亮。"""

    def format(self, record: logging.LogRecord) -> str:
        text = super().format(record)
        color = _LEVEL_COLORS.get(record.levelname)
        if not color:
            return text
        tag = f"[{record.levelname}]"
        if record.levelno >= logging.ERROR:
            return color + text + _RESET
        return text.replace(tag, color + tag + _RESET, 1)


logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s", datefmt="%m-%d %H:%M:%S")
logging.root.handlers[0].setFormatter(ColorFormatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s", datefmt="%m-%d %H:%M:%S"))
logger = logging.getLogger("zhuan.main")

# 关闭 uvicorn 自带的 access log：zhuan.http 中间件已输出同样的信息（含耗时，格式统一）
logging.getLogger("uvicorn.access").disabled = True

http_logger = logging.getLogger("zhuan.http")
SLOW_REQUEST_MS = 3000  # 超过该耗时的请求以 WARNING 级别提示（远程库串行往返易拖慢）

app = FastAPI(title="筑安云 API", version="1.0.0")


@app.middleware("http")
async def log_requests(request, call_next):
    path = request.url.path
    if not path.startswith("/api"):  # 静态资源/前端文件不再重复记录
        return await call_next(request)
    start = time.perf_counter()
    client = request.client.host if request.client else "-"
    try:
        response = await call_next(request)
    except Exception:
        cost = (time.perf_counter() - start) * 1000
        http_logger.exception("接口异常 %s %s from %s（耗时%.0fms）", request.method, path, client, cost)
        raise
    cost = (time.perf_counter() - start) * 1000
    if response.status_code >= 500:
        http_logger.warning("%s %s -> %d from %s（耗时%.0fms）", request.method, path, response.status_code, client, cost)
    elif cost >= SLOW_REQUEST_MS:
        http_logger.warning("慢请求 %s %s -> %d from %s（耗时%.0fms）", request.method, path, response.status_code, client, cost)
    else:
        http_logger.info("%s %s -> %d from %s（耗时%.0fms）", request.method, path, response.status_code, client, cost)
    return response

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
        logger.info("演示数据=%s", "已初始化" if seeded else "已存在")
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
