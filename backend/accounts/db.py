"""PostgreSQL 연결: 엔진, 세션 팩토리, 테이블 생성."""
import logging
from typing import Iterator

from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

logger = logging.getLogger(__name__)


class Base(DeclarativeBase):
    """모든 ORM 모델의 부모."""


def normalize_url(url: str) -> str:
    """Railway 등이 주는 postgres:// 형태를 SQLAlchemy(psycopg3) 형태로 바꾼다."""
    for prefix in ("postgres://", "postgresql://"):
        if url.startswith(prefix):
            return "postgresql+psycopg://" + url[len(prefix) :]
    return url


def conninfo(url: str) -> str:
    """psycopg(LangGraph 체크포인터)가 읽는 접속 문자열. 드라이버 접두사를 뗀다."""
    normalized = normalize_url(url)
    return "postgresql://" + normalized[len("postgresql+psycopg://") :]


def make_engine(url: str) -> Engine:
    """연결 풀이 있는 엔진을 만든다. 끊어진 연결은 쓰기 전에 확인한다."""
    if not url:
        raise RuntimeError(
            "DATABASE_URL이 비어 있습니다. 로컬에서는 `python -m scripts.dev_server`로 내장 Postgres와 서버를 함께 띄우세요."
        )
    return create_engine(normalize_url(url), pool_pre_ping=True, pool_size=5, max_overflow=5)


def init_db(engine: Engine) -> None:
    """테이블이 없으면 만든다. (스키마 변경이 생기면 마이그레이션 도구로 바꿔야 한다)"""
    from accounts import tables  # noqa: F401 - 모델을 Base에 등록하기 위해 가져온다

    Base.metadata.create_all(engine)


def make_session_factory(engine: Engine) -> sessionmaker[Session]:
    """요청 단위로 쓰는 세션 팩토리."""
    return sessionmaker(engine, expire_on_commit=False)


def session_scope(factory: sessionmaker[Session]) -> Iterator[Session]:
    """커밋/롤백을 보장하는 세션 컨텍스트 (제너레이터 기반)."""
    db = factory()
    try:
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()
