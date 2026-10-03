"""内置知识库：规范 Markdown 文档 → 条款级切片 → Regulation 表同步。

内置规范以仓库文件为"原始文档层"（backend/knowledge/*.md）：
- parse_regulation_md() 把全文切成"一条 = 一个 chunk"的条款列表（结构化切分，非通用窗口切分）；
- sync_builtin_knowledge() 在启动时做幂等同步：按内容哈希逐条比对，只增改变动条款；
  source='builtin' 的行归本函数管辖，source='import'（未来文档导入管线）的行不受影响；
  旧版种子条款（source 为空/''）首次同步时一次性清理。
向量索引由 rag/retriever.refresh_cache() 按现有内容哈希机制派生，本模块不触碰。
"""
import hashlib
import logging
import re
from pathlib import Path

from sqlalchemy.orm import Session

from ..models import Regulation

logger = logging.getLogger("zhuan.knowledge")

KNOWLEDGE_DIR = Path(__file__).resolve().parents[2] / "knowledge"

# 内置规范：doc_name 与工单引用展示一致（`《doc_name》第N.M.K条`）
BUILTIN_DOC_NAME = "建筑与市政施工现场安全卫生与职业健康通用规范GB 55034-2022"
BUILTIN_MD_FILE = KNOWLEDGE_DIR / "建筑与市政施工现场安全卫生与职业健康通用规范.md"

# 小节/章 → 检索标签（确定性映射，与种子 tags 风格对齐；未列出的回退到章标签）
_CHAPTER_TAGS = {
    "1": ["总体要求"],
    "2": ["基本规定"],
    "4": ["环境保护"],
    "5": ["卫生防疫"],
    "6": ["职业健康"],
}
_SECTION_TAGS = {
    "3.1": ["安全管理"],
    "3.2": ["高处作业"],
    "3.3": ["高处作业", "物体打击"],
    "3.4": ["起重吊装"],
    "3.5": ["基坑工程", "坍塌"],
    "3.6": ["机械设备"],
    "3.7": ["地下工程", "冒顶片帮"],
    "3.8": ["车辆伤害"],
    "3.9": ["有限空间", "中毒和窒息"],
    "3.10": ["临时用电", "触电"],
    "3.11": ["爆炸"],
    "3.12": ["爆破作业"],
    "3.13": ["地下工程", "透水"],
    "3.14": ["淹溺"],
    "3.15": ["灼烫"],
}

_RE_CHAPTER = re.compile(r"^##\s*(\d+)\s*([^\s].*?)\s*$")
_RE_SECTION = re.compile(r"^###\s*(\d+(?:\.\d+)*)\s*([^\s].*?)\s*$")
_RE_CLAUSE = re.compile(r"^\*\*(\d+(?:\.\d+)*)\*\*\s*(.*)$")


def _clean(text: str) -> str:
    """去掉行内加粗标记（保留'严禁'等文字本身），压缩空白。"""
    return re.sub(r"\s+", " ", text.replace("**", "")).strip()


def _clean_title(text: str) -> str:
    """标题专用：去掉全部空白（含全角空格，如'总　则'→'总则'）。"""
    return re.sub(r"[\s\u3000]+", "", text.replace("**", ""))


def parse_regulation_md(text: str) -> list[dict]:
    """把规范 Markdown 切成条款列表：一条（N.M.K）= 一个 chunk，子项列表并入该条。

    返回 [{clause_no, title, content, tags}]，clause_no 统一为 `第N.M.K条` 格式；
    title 取所在小节名（无小节的章条款取章名，如 2.0.x → 基本规定）。
    前言/目次等非编号章节自动跳过。
    """
    chapter_no, chapter_title = "", ""
    section_no, section_title = "", ""
    clauses: list[dict] = []
    cur: dict | None = None

    def flush():
        nonlocal cur
        if cur and cur["content"]:
            clauses.append(cur)
        cur = None

    for line in text.splitlines():
        if not line.strip():
            continue  # 空行是子项列表的分隔，不参与内容

        m = _RE_CHAPTER.match(line)
        if m:
            flush()
            chapter_no, chapter_title = m.group(1), _clean_title(m.group(2))
            section_no, section_title = "", ""
            continue
        m = _RE_SECTION.match(line)
        if m:
            flush()
            section_no, section_title = m.group(1), _clean_title(m.group(2))
            continue
        m = _RE_CLAUSE.match(line)
        if m:
            flush()
            if not chapter_no:  # 前言/目次等非编号章节，整体跳过
                continue
            key = section_no or chapter_no
            cur = {
                "clause_no": f"第{m.group(1)}条",
                "title": section_title or chapter_title,
                "tags": list(_SECTION_TAGS.get(key) or _CHAPTER_TAGS.get(key, [])),
                "content": _clean(m.group(2)),
            }
            continue

        if cur is not None:  # 条款正文的续行/子项列表
            cur["content"] += "\n" + _clean(line)

    flush()
    return clauses


def _row_hash(title: str, content: str, tags: list | None) -> str:
    h = hashlib.md5()
    h.update(f"{title}|{content}|{','.join(tags or [])}".encode("utf-8"))
    return h.hexdigest()


def sync_builtin_knowledge(db: Session) -> dict:
    """内置知识库幂等同步（启动时调用）。返回统计 dict 供日志使用。"""
    clauses = parse_regulation_md(BUILTIN_MD_FILE.read_text(encoding="utf-8"))
    if not clauses:
        return {"total": 0, "added": 0, "updated": 0, "removed": 0, "removed_legacy": 0}

    # 旧版种子条款（source 为空）一次性清理：演示知识库全面退役
    removed_legacy = (
        db.query(Regulation)
        .filter((Regulation.source.is_(None)) | (Regulation.source == ""))
        .delete(synchronize_session=False)
    )

    existing = {
        r.clause_no: r
        for r in db.query(Regulation).filter(Regulation.source == "builtin").all()
    }
    added = updated = 0
    seen = set()
    for item in clauses:
        seen.add(item["clause_no"])
        row = existing.get(item["clause_no"])
        new_hash = _row_hash(item["title"], item["content"], item["tags"])
        if row is None:
            db.add(
                Regulation(
                    doc_name=BUILTIN_DOC_NAME,
                    clause_no=item["clause_no"],
                    title=item["title"],
                    content=item["content"],
                    tags=item["tags"],
                    source="builtin",
                )
            )
            added += 1
        elif _row_hash(row.title, row.content, row.tags) != new_hash:
            row.title, row.content, row.tags = item["title"], item["content"], item["tags"]
            updated += 1

    removed = 0
    for row in existing.values():
        if row.clause_no not in seen:
            db.delete(row)
            removed += 1

    db.commit()
    stats = {
        "total": len(clauses),
        "added": added,
        "updated": updated,
        "removed": removed,
        "removed_legacy": removed_legacy,
    }
    if any(v for k, v in stats.items() if k != "total"):
        logger.info("内置知识库同步：%s", stats)
    return stats
