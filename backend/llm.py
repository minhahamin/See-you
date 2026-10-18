"""LLM·임베딩 생성 함수. 프로바이더는 환경변수로 교체한다."""
import logging
import time
from typing import TypeVar

from langchain_core.embeddings import Embeddings
from langchain_core.language_models.chat_models import BaseChatModel
from pydantic import BaseModel

from config import get_settings

logger = logging.getLogger(__name__)

T = TypeVar("T", bound=BaseModel)
RETRY_ATTEMPTS = 3
RETRY_BACKOFF_SEC = 10

GEMINI_ALIASES = {"gemini", "google", "google_genai"}
OPENAI_ALIASES = {"openai"}


def _provider() -> str:
    """LLM_PROVIDER 값을 소문자로 정규화해 반환한다."""
    provider = get_settings().llm_provider.strip().lower()
    if not provider:
        raise ValueError("LLM_PROVIDER가 비어 있습니다. .env를 확인하세요.")
    return provider


def is_daily_quota_error(exc: Exception) -> bool:
    """일일 호출 한도 초과 오류인지 판별한다. 재시도해도 의미가 없다."""
    return "PerDay" in str(exc)


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


def structured_call(schema: type[T], messages: list, temperature: float = 0.0) -> T:
    """구조화 출력으로 LLM을 호출한다. 일시 오류는 재시도하고, 일일 한도 초과는 즉시 던진다."""
    model = get_chat_model(temperature=temperature).with_structured_output(schema)
    for attempt in range(1, RETRY_ATTEMPTS + 1):
        try:
            return model.invoke(messages)
        except Exception as exc:
            if attempt == RETRY_ATTEMPTS or is_daily_quota_error(exc):
                raise
            logger.warning("LLM 호출 실패(%d/%d): %s", attempt, RETRY_ATTEMPTS, type(exc).__name__)
            time.sleep(RETRY_BACKOFF_SEC * attempt)
    raise RuntimeError("unreachable")
