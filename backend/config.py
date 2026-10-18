"""환경변수 로딩과 설정값."""
import logging
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

BASE_DIR = Path(__file__).resolve().parent
ROOT_DIR = BASE_DIR.parent


class Settings(BaseSettings):
    """환경변수 기반 설정. 키는 .env에서만 읽는다."""

    model_config = SettingsConfigDict(
        env_file=ROOT_DIR / ".env", env_file_encoding="utf-8", extra="ignore"
    )

    llm_provider: str = ""
    llm_model: str = ""
    embedding_model: str = ""
    llm_api_key: str = ""
    tour_api_key: str = ""
    kma_api_key: str = ""
    langsmith_api_key: str = ""
    langsmith_project: str = "travel-planner"

    data_dir: Path = BASE_DIR / "data"
    chroma_dir: Path = BASE_DIR / "chroma"
    eval_results_dir: Path = BASE_DIR / "eval" / "results"
    region: str = "제주"
    max_retry: int = 2


def get_settings() -> Settings:
    """설정 객체를 생성해 반환한다."""
    return Settings()


def setup_logging(level: int = logging.INFO) -> None:
    """프로젝트 공통 로깅 포맷을 설정한다."""
    logging.basicConfig(
        level=level, format="%(asctime)s %(levelname)s %(name)s: %(message)s"
    )
    # httpx는 요청 URL(쿼리의 서비스키 포함)을 INFO로 남기므로 WARNING 이상만 허용한다.
    for noisy in ("httpx", "httpcore"):
        logging.getLogger(noisy).setLevel(logging.WARNING)
