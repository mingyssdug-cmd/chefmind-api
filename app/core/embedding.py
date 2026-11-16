from openai import OpenAI

from app.core.config import settings

_client = OpenAI(
    api_key=settings.DASHSCOPE_API_KEY,
    base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
)


def embed_text(text: str) -> list[float]:
    """单条文本向量化"""
    resp = _client.embeddings.create(
        model=settings.EMBEDDING_MODEL,
        input=text,
        dimensions=settings.EMBEDDING_DIM,
    )
    return resp.data[0].embedding


def embed_batch(texts: list[str]) -> list[list[float]]:
    """批量向量化（text-embedding-v4 单次最多 10 条）"""
    if not texts:
        return []
    results = []
    for i in range(0, len(texts), 10):
        batch = texts[i:i + 10]
        resp = _client.embeddings.create(
            model=settings.EMBEDDING_MODEL,
            input=batch,
            dimensions=settings.EMBEDDING_DIM,
        )
        results.extend([d.embedding for d in resp.data])
    return results