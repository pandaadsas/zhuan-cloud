"""安全知识库检索（Chroma 本地向量库版）。

条款规模（百条级）不需要独立向量库服务：
- 真实模式：qwen text-embedding 向量化，向量存入 Chroma 本地持久化目录
  （knowledge/chroma_data），按条款内容哈希增量更新——只重算新增或变动的条款；
- 模拟模式：字符 bigram Jaccard 相似度，零 API 消耗。
两种模式接口一致，后续可平滑升级为独立向量服务（Chroma Server / Qdrant / Milvus）。
"""
import hashlib
import logging
import re
from pathlib import Path

import chromadb
from chromadb.config import Settings as ChromaSettings
from sqlalchemy.orm import Session

from ..models import Regulation
from ..agents.llm import client, llm_ready
from ..config_runtime import get_cfg

logger = logging.getLogger("zhuan.rag")

CHROMA_DIR = Path(__file__).resolve().parents[2] / "knowledge" / "chroma_data"

_cache: list[dict] = []
_col = None  # chroma Collection，按 embedding 模型区分；refresh 时重置


def _bigrams(s: str) -> set[str]:
    s = re.sub(r"\s", "", s)
    return {s[i : i + 2] for i in range(len(s) - 1)} if len(s) > 1 else {s}


def embed_texts(texts: list[str]) -> list[list[float]] | None:
    cfg = get_cfg()
    if not llm_ready(cfg):
        return None
    try:
        vecs: list[list[float]] = []
        for i in range(0, len(texts), 10):  # text-embedding-v4 单批上限10条
            resp = client(cfg).embeddings.create(
                model=cfg.qwen_embed_model, input=texts[i : i + 10]
            )
            data = sorted(resp.data, key=lambda d: d.index)
            vecs.extend([d.embedding for d in data])
        return vecs
    except Exception as e:
        logger.warning("向量化失败，降级关键词检索：%s", e)
        return None


def _collection():
    global _col
    if _col is not None:
        return _col
    model = get_cfg().qwen_embed_model
    # 集合名带模型名：换 embedding 模型时自动落到新集合全量重建，避免新旧向量混算
    name = f"regulations_{model}".lower().replace("/", "_")
    _col = chromadb.PersistentClient(
        path=str(CHROMA_DIR), settings=ChromaSettings(anonymized_telemetry=False)
    ).get_or_create_collection(name=name, metadata={"hnsw:space": "cosine"})
    return _col


def _content_hash(r) -> str:
    h = hashlib.md5()
    h.update(f"{r.id}|{r.doc_name}|{r.clause_no}|{r.title}|{r.content}".encode("utf-8"))
    return h.hexdigest()


def _sync_vectors(rows) -> str:
    """将条款向量同步进 Chroma：删除失效条目，只对新增/变动的条款重新向量化。"""
    col = _collection()
    data = col.get(include=["metadatas"])
    existing = {
        int(cid): (m or {}).get("content_hash", "")
        for cid, m in zip(data["ids"], data["metadatas"])
    }
    row_ids = {r.id for r in rows}

    stale = [str(i) for i in existing if i not in row_ids]
    if stale:
        col.delete(ids=stale)

    changed = [r for r in rows if existing.get(r.id) != _content_hash(r)]
    if changed:
        vecs = embed_texts([f"{r.doc_name}{r.clause_no}{r.title}{r.content}" for r in changed])
        if not vecs:
            return "keyword"
        col.upsert(
            ids=[str(r.id) for r in changed],
            embeddings=vecs,
            documents=[r.content for r in changed],
            metadatas=[
                {
                    "doc_name": r.doc_name,
                    "clause_no": r.clause_no,
                    "title": r.title,
                    "content_hash": _content_hash(r),
                }
                for r in changed
            ],
        )
    return "vector"


def refresh_cache(db: Session) -> str:
    """加载条款并就绪检索模式。向量存 Chroma 本地库；keyword 模式仅依赖内存 bigram。"""
    global _cache, _col
    _col = None
    rows = db.query(
        Regulation.id,
        Regulation.doc_name,
        Regulation.clause_no,
        Regulation.title,
        Regulation.content,
        Regulation.tags,
    ).all()
    if not rows:
        _cache = []
        return "keyword"

    # _cache 保留条款文本元数据：keyword 模式的检索底料 + 向量结果的详情回填
    _cache = [
        {
            "id": r.id,
            "doc_name": r.doc_name,
            "clause_no": r.clause_no,
            "title": r.title,
            "content": r.content,
            "tags": r.tags or [],
            "grams": _bigrams(f"{r.doc_name}{r.clause_no}{r.title}{r.content}"),
        }
        for r in rows
    ]

    mode = "keyword"
    if llm_ready():
        try:
            mode = _sync_vectors(rows)
        except Exception as e:
            logger.warning("Chroma 向量库同步失败，降级关键词检索：%s", e)
    logger.info("知识库缓存就绪：%d条，检索模式=%s", len(_cache), mode)
    return mode


def _search_vector(query: str, k: int) -> list[dict]:
    qv = embed_texts([query])
    if not qv:
        return []
    col = _collection()
    total = col.count()
    if total == 0:
        return []
    res = col.query(query_embeddings=qv[:1], n_results=min(k, total), include=["distances"])
    by_id = {e["id"]: e for e in _cache}
    out = []
    for dist, cid in zip(res["distances"][0], res["ids"][0]):
        entry = by_id.get(int(cid))
        if entry is None:  # Chroma 有向量但内存缓存没有：条款刚被删除，跳过
            continue
        out.append(
            {
                "doc_name": entry["doc_name"],
                "clause_no": entry["clause_no"],
                "title": entry["title"],
                "content": entry["content"],
                "tags": entry["tags"],
                "score": round(max(0.0, 1.0 - float(dist)), 4),  # cosine distance → 相似度
            }
        )
    return out


def _search_keyword(query: str, k: int) -> list[dict]:
    q_grams = _bigrams(query)
    scored = []
    for item in _cache:
        union = len(q_grams | item["grams"]) or 1
        scored.append((len(q_grams & item["grams"]) / union, item))
    scored.sort(key=lambda x: -x[0])
    results = []
    for score, item in scored[:k]:
        if score <= 0.02:
            continue
        results.append(
            {
                "doc_name": item["doc_name"],
                "clause_no": item["clause_no"],
                "title": item["title"],
                "content": item["content"],
                "tags": item["tags"],
                "score": round(score, 4),
            }
        )
    return results


def search(db: Session, query: str, k: int = 4) -> list[dict]:
    if not _cache:
        refresh_cache(db)
    if not _cache:
        return []
    try:
        results = _search_vector(query, k)
    except Exception as e:
        logger.warning("Chroma 检索失败，降级关键词检索：%s", e)
        results = []
    return results or _search_keyword(query, k)
