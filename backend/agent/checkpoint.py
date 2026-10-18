"""대화 상태(LangGraph 체크포인트)를 PostgreSQL에 저장하는 체크포인터."""
import asyncio
import sys
from contextlib import asynccontextmanager
from typing import AsyncIterator

from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from langgraph.checkpoint.serde.jsonplus import JsonPlusSerializer
from psycopg.rows import dict_row
from psycopg_pool import AsyncConnectionPool

from accounts.db import conninfo
from agent.graph import STATE_MODELS

POOL_MAX_SIZE = 10


def ensure_selector_loop() -> None:
    """Windows 기본 이벤트 루프(Proactor)는 psycopg 비동기를 지원하지 않아 Selector 루프로 바꾼다. 리눅스(배포)에서는 아무 일도 안 한다."""
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())


def selector_loop_factory() -> asyncio.AbstractEventLoop:
    """uvicorn의 `--loop agent.checkpoint:selector_loop_factory`로 쓰는 루프 팩토리. Windows에서 uvicorn은 Proactor 루프를 직접 지정하므로 이렇게 바꿔야 한다."""
    return asyncio.SelectorEventLoop()


@asynccontextmanager
async def open_postgres_checkpointer(database_url: str) -> AsyncIterator[AsyncPostgresSaver]:
    """연결 풀 위에 체크포인터를 만들고 테이블을 준비한다. 블록을 나가면 풀을 닫는다.

    상태 모델(agent.state)만 복원을 허용한다 (그 외 타입은 차단).
    """
    pool = AsyncConnectionPool(
        conninfo(database_url),
        max_size=POOL_MAX_SIZE,
        kwargs={"autocommit": True, "prepare_threshold": 0, "row_factory": dict_row},  # AsyncPostgresSaver 요구 사항
        open=False,
    )
    await pool.open()
    try:
        saver = AsyncPostgresSaver(pool, serde=JsonPlusSerializer(allowed_msgpack_modules=STATE_MODELS))
        await saver.setup()
        yield saver
    finally:
        await pool.close()
