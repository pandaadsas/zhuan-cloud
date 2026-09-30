"""轻量启动迁移：为已有库补充列 / 清理数据中的旧标注。幂等，失败容忍。"""
import logging

from sqlalchemy import text

from .database import engine

logger = logging.getLogger("zhuan.migrate")

_STATEMENTS = [
    # MySQL 与 SQLite 均支持 ADD COLUMN；列已存在时报重复列错误，忽略即可
    "ALTER TABLE users ADD COLUMN email VARCHAR(120) DEFAULT ''",
    "ALTER TABLE users ADD COLUMN phone VARCHAR(20) DEFAULT ''",
    "ALTER TABLE work_orders ADD COLUMN rect_images JSON",
    # 项目归属外键（方案：业务数据挂到 projects 下，列可空以兼容存量）
    "ALTER TABLE subcontractors ADD COLUMN project_id INT NULL",
    "ALTER TABLE zones ADD COLUMN project_id INT NULL",
    "ALTER TABLE reports ADD COLUMN project_id INT NULL",
    "ALTER TABLE work_orders ADD COLUMN project_id INT NULL",
    "ALTER TABLE weekly_reports ADD COLUMN project_id INT NULL",
    # 知识库条款来源标记（builtin=内置规范 / import=文档导入；空=旧版种子，启动时清理）
    "ALTER TABLE regulations ADD COLUMN source VARCHAR(20) DEFAULT ''",
]

# 存量数据回填到唯一项目；WHERE 过滤保证重复执行无副作用
_BACKFILL_TABLES = ["subcontractors", "zones", "reports", "work_orders", "weekly_reports"]


def run_migrations():
    with engine.begin() as conn:
        for sql in _STATEMENTS:
            try:
                conn.execute(text(sql))
            except Exception as e:
                logger.debug("迁移跳过：%s（%s）", sql.split("TABLE ")[1].split(" ADD")[0], str(e)[:60])

        # 把还没有项目归属的业务数据挂到第一个项目上
        for table in _BACKFILL_TABLES:
            try:
                conn.execute(
                    text(
                        f"UPDATE {table} SET project_id = (SELECT id FROM projects LIMIT 1) "
                        "WHERE project_id IS NULL"
                    )
                )
            except Exception as e:
                logger.warning("回填 %s 失败（不影响运行）：%s", table, e)

        # 清理历史数据中的旧版"演示"标注（正式版不展示）
        try:
            conn.execute(text("UPDATE projects SET name = REPLACE(name, '（演示）', '') WHERE name LIKE '%（演示）%'"))
            conn.execute(text("UPDATE projects SET scale_desc = REPLACE(scale_desc, '（数据基于公开招标信息提炼，人员与分包为演示虚构）', '') WHERE scale_desc LIKE '%演示虚构%'"))
            conn.execute(text("UPDATE regulations SET doc_name = REPLACE(doc_name, '（演示）', '') WHERE doc_name LIKE '%（演示）%'"))
            conn.execute(text("UPDATE weekly_reports SET content_md = REPLACE(content_md, '（演示模式）', '') WHERE content_md LIKE '%（演示模式）%'"))
        except Exception as e:
            logger.warning("数据清理失败（不影响运行）：%s", e)
