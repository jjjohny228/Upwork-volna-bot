from functools import lru_cache

from langchain_openai import OpenAIEmbeddings

from upwork_bot.config import get_settings


@lru_cache
def _get_embedder() -> OpenAIEmbeddings:
    settings = get_settings()
    return OpenAIEmbeddings(model="text-embedding-3-small", api_key=settings.openai_api_key)


async def embed_text(text: str) -> list[float]:
    embedder = _get_embedder()
    return await embedder.aembed_query(text)
