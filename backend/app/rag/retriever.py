"""安全知识库检索。

条款规模（百条级）不需要独立向量库服务：
- 真实模式：qwen text-embedding 向量化后存 MySQL，查询时内存余弦计算；
- 模拟模式：字符 bigram Jaccard 相似度，同样返回 Top-K 条款。
两种模式接口一致，便于答辩时说明可平滑升级为专业向量库（Milvus/Chroma）。
"""
import logging
import re

import numpy as np
from sqlalchemy.orm import Session

from ..config import settings
from ..models import Regulation
from .llm import client, llm_ready

logger = logging.getLogger("zhuan.rag")

_cache: list[dict] = []


def _bigrams(s: str) -> set[str]:
    s = re.sub(r"\s", "", s)
    return {s[i : i + 2] for i in range(len(s) - 1)} if len(s) > 1 else {s}


def embed_texts(texts: list[str]) -> list[list[float]] | None:
    if not llm_ready():
        return None
    try:
        vecs: list[list[float]] = []
        for i in range(0, len(texts), 10):  # text-embedding-v4 单批上限10条
            resp = client().embeddings.create(
                model=settings.qwen_embed_model, input=texts[i : i + 10]
            )
            data = sorted(resp.data, key=lambda d: d.index)
            vecs.extend([d.embedding for d in data])
        return vecs
    except Exception as e:
        logger.warning("向量化失败，降级关键词检索：%s", e)
        return None


def refresh_cache(db: Session) -> str:
    """全量加载条款；真实模式补算缺失向量并持久化。返回 'vector' 或 'keyword'。"""
    global _cache
    regs = db.query(Regulation).all()
    _cache = []
    mode = "keyword"

    if llm_ready() and regs:
        missing = [r for r in regs if not r.embedding]
        if missing:
            vecs = embed_texts([f"{r.doc_name}{r.clause_no}{r.title}{r.content}" for r in missing])
            if vecs:
                for r, v in zip(missing, vecs):
                    r.embedding = v
                db.commit()
        if all(r.embedding for r in regs):
            mode = "vector"

    for r in regs:
        item = {
            "id": r.id,
            "doc_name": r.doc_name,
            "clause_no": r.clause_no,
            "title": r.title,
            "content": r.content,
            "tags": r.tags or [],
            "vec": np.array(r.embedding, dtype=np.float32) if r.embedding else None,
            "grams": None if r.embedding else _bigrams(f"{r.doc_name}{r.clause_no}{r.title}{r.content}"),
        }
        _cache.append(item)
    logger.info("知识库缓存就绪：%d条，检索模式=%s", len(_cache), mode)
    return mode


def search(db: Session, query: str, k: int = 4) -> list[dict]:
    if not _cache:
        refresh_cache(db)
    if not _cache:
        return []

    q_grams = _bigrams(query)
    scored = []
    if _cache[0]["vec"] is not None and llm_ready():
        qv = embed_texts([query])
        if qv:
            q = np.array(qv[0], dtype=np.float32)
            for item in _cache:
                denom = float(np.linalg.norm(q) * np.linalg.norm(item["vec"])) or 1.0
                score = float(np.dot(q, item["vec"]) / denom)
                scored.append((score, item))
    if not scored:
        for item in _cache:
            grams = item["grams"] or set()
            union = len(q_grams | grams) or 1
            scored.append((len(q_grams & grams) / union, item))

    scored.sort(key=lambda x: -x[0])
    results = []
    for score, item in scored[:k]:
        if score <= 0.02 and item["vec"] is None:
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
