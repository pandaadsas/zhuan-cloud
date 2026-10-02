"""安全知识库检索（Chroma 本地向量库版）。

条款规模（百条级）不需要独立向量库服务：
- 真实模式：qwen text-embedding 向量化，结合本地 BM25 补召回；向量存入 Chroma 本地持久化目录
  （knowledge/chroma_data），按条款内容哈希增量更新——只重算新增或变动的条款；
- 模拟模式：字符 bigram Jaccard 相似度，零 API 消耗。
两种模式接口一致，后续可平滑升级为独立向量服务（Chroma Server / Qdrant / Milvus）。
"""
import hashlib
import logging
import math
import re
from collections import Counter
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
        if score <= 0:  # 只剔除完全无重叠的，避免全文长条款被阈值误伤
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


def _clause_numbers(query: str) -> list[str]:
    # 三段编号，不把年份、四段版本号或小数的局部当作条款号。
    numbers = re.findall(r"(?<![A-Za-z\d.])(?:第)?(\d+\.\d+\.\d+)(?:条)?(?![\d.])", query)
    return list(dict.fromkeys(f"第{number}条" for number in numbers))


def _lexical_tokens(text: str) -> list[str]:
    """中文连续二字片段及完整英文/数字词；不引入分词依赖或特定条款词表。"""
    tokens = []
    for part in re.findall(r"[\u4e00-\u9fff]+|[a-z0-9]+(?:\.[0-9]+)*", text.lower()):
        if re.fullmatch(r"[\u4e00-\u9fff]+", part):
            tokens.extend(part[i:i + 2] for i in range(len(part) - 1))
        else:
            tokens.append(part)
    return tokens


def _search_lexical(query: str, k: int) -> list[dict]:
    """BM25 本地补召回；仅索引标题和正文，避免公共规范名干扰术语权重。"""
    terms = set(_lexical_tokens(query))
    if not terms or not _cache:
        return []
    documents = [Counter(_lexical_tokens(f"{r['title']} {r['content']}")) for r in _cache]
    lengths = [sum(d.values()) for d in documents]
    average = sum(lengths) / len(documents) or 1
    frequencies = {term: sum(term in d for d in documents) for term in terms}
    scored = []
    for item, counts, length in zip(_cache, documents, lengths):
        score = 0.0
        for term in terms:
            count = counts.get(term, 0)
            if count:
                df = frequencies[term]
                idf = math.log(1 + (len(documents) - df + 0.5) / (df + 0.5))
                score += idf * count * 2.2 / (count + 1.2 * (0.25 + 0.75 * length / average))
        if score > 0:
            scored.append((score, item))
    scored.sort(key=lambda pair: (-pair[0], pair[1]["id"]))
    return [{key: item[key] for key in ("doc_name", "clause_no", "title", "content", "tags")} | {"score": round(score, 4)}
            for score, item in scored[:k]]


def _merge_candidates(vector: list[dict], lexical: list[dict], k: int) -> list[dict]:
    """保留向量首位，引入关键词前两位，再以向量优先补齐、去重。

    确保仅出现在关键词通道的条款能进入小候选集；不把两种原始分数相加。
    score 改为两通道倒数排名之和，仅作诊断，非相似度/支持概率；最终顺序按通道配额。
    """
    def key(row):
        return row["doc_name"], row["clause_no"], row["content"]
    scores = {}
    for source in (vector, lexical):
        for rank, row in enumerate(source, 1):
            identity = key(row)
            scores[identity] = scores.get(identity, 0.0) + 1 / (60 + rank)
    merged, seen = [], set()
    for row in vector[:1] + lexical[:2] + vector[1:] + lexical[2:]:
        identity = key(row)
        if identity not in seen:
            merged.append(dict(row, score=round(scores[identity], 6)))
            seen.add(identity)
        if len(merged) >= k:
            break
    return merged


def search_with_mode(db: Session, query: str, k: int = 4) -> tuple[list[dict], str]:
    """内部评测接口；模式逐次返回，避免用启动模式推断实际检索路径。"""
    if not query.strip() or k <= 0:
        return [], "empty"
    if not _cache:
        refresh_cache(db)
    if not _cache:
        return [], "empty"
    numbers = _clause_numbers(query)
    if numbers:
        results = []
        for number in numbers:
            for item in sorted(_cache, key=lambda entry: entry["id"]):
                if item["clause_no"] == number:
                    results.append({
                        key: item[key]
                        for key in ("doc_name", "clause_no", "title", "content", "tags")
                    } | {"score": 1.0})
        return results[:k], "exact"
    try:
        results = _search_vector(query, max(10, k))
    except Exception as e:
        logger.warning("Chroma 检索失败，降级关键词检索：%s", e)
        results = []
    if results:
        lexical = _search_lexical(query, max(10, k))
        if lexical:
            return _merge_candidates(results, lexical, k), "hybrid"
        return results[:k], "vector"
    return _search_keyword(query, k), "keyword"


def search(db: Session, query: str, k: int = 4) -> list[dict]:
    results, mode = search_with_mode(db, query, k)
    if logger.isEnabledFor(logging.INFO):
        details = []
        for rank, item in enumerate(results, 1):
            details.append(
                f"候选 {rank}/{len(results)} | 《{item['doc_name']}》{item['clause_no']} "
                f"{item['title']} | score={item['score']}\n"
                f"正文：\n{item['content']}"
            )
        logger.info(
            "RAG 检索结果（核验前候选；hybrid score为融合诊断分，非相似度） query=%r mode=%s k=%d 命中=%d\n%s\n检索结果结束",
            query, mode, k, len(results), "\n\n".join(details) or "无候选条款",
        )
    return results
