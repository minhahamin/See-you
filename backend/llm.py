"""LLM·임베딩 생성 함수. 프로바이더는 환경변수로 교체한다."""
import logging

from langchain_core.embeddings import Embeddings
from langchain_core.language_models.chat_models import BaseChatModel

from config import get_settings

logger = logging.getLogger(__name__)

GEMINI_ALIASES = {"gemini", "google", "google_genai"}
OPENAI_ALIASES = {"openai"}


def _provider() -> str:
    """LLM_PROVIDER 값을 소문자로 정규화해 반환한다."""
    provider = get_settings().llm_provider.strip().lower()
    if not provider:
        raise ValueError("LLM_PROVIDER가 비어 있습니다. .env를 확인하세요.")
    return provider


def get_chat_model(temperature: float = 0.0) -> BaseChatModel:
    """설정된 프로바이더의 채팅 모델을 생성한다."""
    settings = get_settings()
    provider = _provider()
    if not settings.llm_model:
        raise ValueError("LLM_MODEL이 비어 있습니다. .env를 확인하세요.")

    if provider in GEMINI_ALIASES:
        from langchain_google_genai import ChatGoogleGenerativeAI

        return ChatGoogleGenerativeAI(
            model=settings.llm_model,
            google_api_key=settings.llm_api_key,
            temperature=temperature,
        )
    if provider in OPENAI_ALIASES:
        from langchain_openai import ChatOpenAI

        return ChatOpenAI(
            model=settings.llm_model,
            api_key=settings.llm_api_key,
            temperature=temperature,
        )
    raise ValueError(f"지원하지 않는 LLM_PROVIDER: {provider}")


def get_embeddings() -> Embeddings:
    """설정된 프로바이더의 임베딩 모델을 생성한다."""
    settings = get_settings()
    provider = _provider()
    if not settings.embedding_model:
        raise ValueError("EMBEDDING_MODEL이 비어 있습니다. .env를 확인하세요.")

    if provider in GEMINI_ALIASES:
        from langchain_google_genai import GoogleGenerativeAIEmbeddings

        return GoogleGenerativeAIEmbeddings(
            model=settings.embedding_model, google_api_key=settings.llm_api_key
        )
    if provider in OPENAI_ALIASES:
        from langchain_openai import OpenAIEmbeddings

        return OpenAIEmbeddings(
            model=settings.embedding_model, api_key=settings.llm_api_key
        )
    raise ValueError(f"지원하지 않는 LLM_PROVIDER: {provider}")
