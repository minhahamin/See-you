"""환경변수 로딩과 설정값."""
import logging
from pathlib import Path
from typing import Literal

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
    # 토큰 단가(USD/1M 토큰). 비어 있으면 비용은 "데이터 없음"으로 둔다 (임의 값을 넣지 않는다).
    llm_price_in_per_1m: str = ""
    llm_price_out_per_1m: str = ""
    # 계정·대화 기록 저장소(PostgreSQL). 로컬에서는 `python -m scripts.dev_server`가 내장 Postgres를 띄워 준다.
    database_url: str = ""
    cookie_secure: bool = False  # https로 배포할 때 true (Secure 쿠키)
    login_ttl_days: int = 30  # 로그인 유지 기간
    guest_session_ttl_days: int = 14  # 로그인하지 않은 대화를 지우는 기준
    cors_origins: str = "http://localhost:5173,http://127.0.0.1:5173"
    reranker_model: str = "BAAI/bge-reranker-v2-m3"
    tour_api_key: str = ""
    kma_api_key: str = ""
    langsmith_api_key: str = ""
    langsmith_project: str = "travel-planner"

    data_dir: Path = BASE_DIR / "data"
    chroma_dir: Path = BASE_DIR / "chroma"
    eval_results_dir: Path = BASE_DIR / "eval" / "results"
    frontend_dist: Path = ROOT_DIR / "frontend" / "dist"  # 있으면 API 서버가 함께 서빙한다 (배포용)
    runs_log_path: Path = BASE_DIR / "data" / "metrics" / "runs.jsonl"
    region: str = "제주"
    max_retry: int = 2
    validation_loop: Literal["repair", "regenerate"] = "repair"  # 검증 실패 시 부분 수리(기본) 또는 전체 재생성(비교 실험용)


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
