"""安全知识库检索。

条款规模（百条级）不需要独立向量库服务：
- 真实模式：qwen text-embedding 向量化；向量缓存存本地文件（启动零大流量传输），
  首次计算后写入 knowledge/embeddings_cache.json；
- 模拟模式：字符 bigram Jaccard 相似度。
两种模式接口一致，便于答辩时说明可平滑升级为专业向量库（Milvus/Chroma）。
"""
import hashlib
import json
import logging
import re
from pathlib import Path

import numpy as np
from sqlalchemy.orm import Session

from ..models import Regulation
from ..agents.llm import client, llm_ready
from ..config_runtime import get_cfg

logger = logging.getLogger("zhuan.rag")

_cache: list[dict] = []
EMB_CACHE_FILE = Path(__file__).resolve().parent.parent / "knowledge" / "embeddings_cache.json"


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


def _content_sig(rows) -> str:
    h = hashlib.md5()
    for r in rows:
        h.update(f"{r.id}|{r.doc_name}|{r.clause_no}|{r.title}|{r.content}".encode("utf-8"))
    return h.hexdigest()


def refresh_cache(db: Session) -> str:
    """加载条款并就绪检索模式。向量来自本地缓存文件；缺失时实时计算并落盘。

    只查询轻量列（不读 embedding 大字段），避免远程库大流量传输卡启动。
    """
    global _cache
    rows = db.query(
        Regulation.id,
        Regulation.doc_name,
        Regulation.clause_no,
        Regulation.title,
        Regulation.content,
        Regulation.tags,
    ).all()
    _cache = []
    if not rows:
        return "keyword"

    mode = "keyword"
    vec_map: dict[int, list[float]] = {}
    if llm_ready():
        sig = _content_sig(rows)
        if EMB_CACHE_FILE.exists():
            try:
                data = json.loads(EMB_CACHE_FILE.read_text(encoding="utf-8"))
                if data.get("sig") == sig and set(map(int, data["vectors"].keys())) == {r.id for r in rows}:
                    vec_map = {int(k): v for k, v in data["vectors"].items()}
                    mode = "vector"
            except Exception as e:
                logger.warning("向量缓存文件读取失败，将重新计算：%s", e)
        if mode != "vector":
            vecs = embed_texts([f"{r.doc_name}{r.clause_no}{r.title}{r.content}" for r in rows])
            if vecs:
                vec_map = {r.id: v for r, v in zip(rows, vecs)}
                try:
                    EMB_CACHE_FILE.write_text(
                        json.dumps({"sig": sig, "vectors": {str(k): v for k, v in vec_map.items()}}),
                        encoding="utf-8",
                    )
                except Exception as e:
                    logger.warning("向量缓存写入失败（不影响运行）：%s", e)
                mode = "vector"

    for r in rows:
        vec = vec_map.get(r.id)
        _cache.append(
            {
                "id": r.id,
                "doc_name": r.doc_name,
                "clause_no": r.clause_no,
                "title": r.title,
                "content": r.content,
                "tags": r.tags or [],
                "vec": np.array(vec, dtype=np.float32) if vec else None,
                "grams": None if vec else _bigrams(f"{r.doc_name}{r.clause_no}{r.title}{r.content}"),
            }
        )
    logger.info("知识库缓存就绪：%d条，检索模式=%s", len(_cache), mode)
    return mode


def search(db: Session, query: str, k: int = 4) -> list[dict]:
    if not _cache:
        refresh_cache(db)
    if not _cache:
        return []

    q_grams = _bigrams(query)
    scored = []
    if _cache[0]["vec"] is not None:
        qv = embed_texts([query])
        if qv:
            q = np.array(qv[0], dtype=np.float32)
            for item in _cache:
                denom = float(np.linalg.norm(q) * np.linalg.norm(item["vec"])) or 1.0
                scored.append((float(np.dot(q, item["vec"]) / denom), item))
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
