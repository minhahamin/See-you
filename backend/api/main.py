"""FastAPI 앱: 계정, 세션(기록), 메시지(SSE 스트리밍), 설정, 장소 상세, 지표."""
import logging
from contextlib import AsyncExitStack, asynccontextmanager
from typing import Any, AsyncIterator
from urllib.parse import urlparse

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from langgraph.graph.state import CompiledStateGraph
from sqlalchemy.orm import Session
from sse_starlette.sse import EventSourceResponse

from accounts import service
from accounts.db import init_db, make_engine, make_session_factory
from accounts.tables import User
from agent import catalog
from agent.checkpoint import ensure_selector_loop, open_postgres_checkpointer
from agent.graph import build_graph
from api import auth
from api.metrics import MetricsStore, load_experiments
from api.schemas import (
    ExperimentsResponse,
    MessageIn,
    PlaceDetail,
    RunsResponse,
    SessionCreated,
    SessionListItem,
    SessionSummary,
    place_out,
    review_out,
)
from api.sessions import SessionManager
from config import Settings, get_settings, setup_logging

logger = logging.getLogger(__name__)

ensure_selector_loop()  # Windows에서 psycopg 비동기를 쓰기 위한 설정 (리눅스에서는 아무 일도 안 한다)
UNSAFE_METHODS = {"POST", "PUT", "PATCH", "DELETE"}


def _trusted_origins(settings: Settings) -> set[str]:
    return {o.strip() for o in settings.cors_origins.split(",") if o.strip()}


def create_app(
    graph: CompiledStateGraph | None = None,
    store: MetricsStore | None = None,
    database_url: str | None = None,
    settings: Settings | None = None,
) -> FastAPI:
    """앱을 만든다. DB와 체크포인터는 서버가 시작될 때 연다 (lifespan).

    테스트에서는 그래프(체크포인터 대체)와 지표 저장소, DB 주소를 주입한다.
    """
    setup_logging()
    cfg = settings or get_settings()
    metrics = store if store is not None else MetricsStore(cfg.runs_log_path)
    db_url = database_url if database_url is not None else cfg.database_url

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        engine = make_engine(db_url)
        init_db(engine)
        app.state.db_factory = make_session_factory(engine)
        async with AsyncExitStack() as stack:
            compiled = graph
            if compiled is None:
                compiled = build_graph(await stack.enter_async_context(open_postgres_checkpointer(db_url)))
            app.state.sessions = SessionManager(compiled, metrics, app.state.db_factory)
            try:
                removed = await app.state.sessions.purge_old_guests(cfg.guest_session_ttl_days)
                if removed:
                    logger.info("오래된 게스트 대화 %d개를 정리했습니다", removed)
            except Exception as exc:  # noqa: BLE001 - 정리 실패가 서버 시작을 막으면 안 된다
                logger.error("게스트 대화 정리 실패: %s", type(exc).__name__)
            yield
        engine.dispose()

    app = FastAPI(title="여행 일정 플래너 API", lifespan=lifespan)
    app.state.settings = cfg
    app.state.limiters = auth.Limiters()
    trusted = _trusted_origins(cfg)

    app.add_middleware(CORSMiddleware, allow_origins=sorted(trusted), allow_methods=["*"], allow_headers=["*"])

    @app.middleware("http")
    async def reject_cross_origin_writes(request: Request, call_next: Any) -> Response:
        """상태를 바꾸는 요청은 같은 출처(또는 허용 목록)에서 온 것만 받는다 (CSRF 방어).

        Origin 헤더가 있고 요청 대상 호스트와 다르면 거절한다. 쿠키는 SameSite=Lax라 이것과 겹쳐서 막는다.
        """
        if request.method in UNSAFE_METHODS:
            origin = request.headers.get("origin")
            if origin and urlparse(origin).netloc != request.headers.get("host", "") and origin not in trusted:
                return JSONResponse({"detail": "허용되지 않은 출처의 요청이에요."}, status_code=403)
        return await call_next(request)

    app.include_router(auth.router)

    def sessions_of(request: Request) -> SessionManager:
        return request.app.state.sessions

    async def accessible_or_404(request: Request, sid: str, user: User | None) -> SessionManager:
        manager = sessions_of(request)
        if not await manager.accessible(sid, user.id if user else None):
            raise HTTPException(404, "세션을 찾을 수 없습니다.")  # 남의 대화도 같은 응답이라 존재 여부가 드러나지 않는다
        return manager

    @app.get("/api/health")
    def health() -> dict[str, str]:
        """헬스체크."""
        return {"status": "ok"}

    @app.post("/api/sessions", response_model=SessionCreated)
    async def create_session(request: Request, user: User | None = Depends(auth.current_user)) -> SessionCreated:
        """새 세션을 만든다. 로그인했으면 내 계정의 대화가 되고, 아니면 게스트 대화가 된다."""
        return SessionCreated(session_id=await sessions_of(request).create(user.id if user else None))

    @app.get("/api/sessions", response_model=list[SessionListItem])
    async def list_sessions(request: Request, user: User = Depends(auth.require_user)) -> list[SessionListItem]:
        """내 일정(대화) 목록. 최근 수정 순."""
        return await sessions_of(request).list_for(user.id)

    @app.post("/api/sessions/{session_id}/messages")
    async def send_message(
        session_id: str,
        body: MessageIn,
        request: Request,
        user: User | None = Depends(auth.current_user),
        db: Session = Depends(auth.get_db),
    ) -> EventSourceResponse:
        """사용자 메시지를 보내고 진행 단계·결과를 SSE로 받는다."""
        manager = await accessible_or_404(request, session_id, user)
        if manager.is_busy(session_id):
            raise HTTPException(409, "이전 메시지를 처리하는 중입니다.")
        # 로그인했으면 계정에 저장된 설정을, 아니면 브라우저가 보낸 설정을 에이전트의 기본 조건으로 쓴다
        if user:
            profile = service.get_settings(db, user.id)
        else:
            profile = body.settings.model_dump() if body.settings else None
        return EventSourceResponse(manager.stream_turn(session_id, body.text, profile))

    @app.get("/api/sessions/{session_id}", response_model=SessionSummary)
    async def get_session(session_id: str, request: Request, user: User | None = Depends(auth.current_user)) -> SessionSummary:
        """현재 대화와 일정 요약."""
        manager = await accessible_or_404(request, session_id, user)
        return await manager.summary(session_id)

    @app.delete("/api/sessions/{session_id}", status_code=204)
    async def delete_session(session_id: str, request: Request, user: User | None = Depends(auth.current_user)) -> Response:
        """대화와 저장된 상태를 지운다."""
        manager = await accessible_or_404(request, session_id, user)
        await manager.delete(session_id)
        return Response(status_code=204)

    @app.post("/api/sessions/{session_id}/claim", status_code=204)
    async def claim_session(session_id: str, request: Request, user: User = Depends(auth.require_user)) -> Response:
        """로그인 전에 하던 게스트 대화를 내 계정으로 가져온다."""
        if not await sessions_of(request).claim(session_id, user.id):
            raise HTTPException(404, "세션을 찾을 수 없습니다.")
        return Response(status_code=204)

    @app.get("/api/places/{place_id}", response_model=PlaceDetail)
    def get_place(place_id: str) -> PlaceDetail:
        """장소 상세와 후기."""
        if place_id not in catalog.places():
            raise HTTPException(404, "장소를 찾을 수 없습니다.")
        reviews = catalog.reviews_by_place().get(place_id, [])
        return PlaceDetail(place=place_out(place_id), reviews=[review_out(r) for r in reviews])

    @app.get("/api/metrics/experiments", response_model=ExperimentsResponse)
    def experiments() -> ExperimentsResponse:
        """버전별 평가 결과 (eval/results 기반)."""
        results, source = load_experiments()
        return ExperimentsResponse(experiments=results, source=source)

    @app.get("/api/metrics/runs", response_model=RunsResponse)
    def runs() -> RunsResponse:
        """노드별 지연·토큰, 요청당 응답시간·비용, 재생성 통계. 기록이 없으면 null."""
        return RunsResponse(
            nodes=metrics.node_metrics(),
            runs=metrics.run_metrics(),
            source="data/metrics/runs.jsonl" if metrics.node_metrics() else None,
        )

    # 배포에서는 빌드된 프론트(frontend/dist)를 같은 서버가 서빙한다. 개발 중(dist 없음)에는 건너뛴다.
    # API 라우트를 모두 등록한 뒤에 마운트해야 /api가 가려지지 않는다.
    if cfg.frontend_dist.is_dir():
        app.mount("/", StaticFiles(directory=cfg.frontend_dist, html=True), name="frontend")

    return app


app = create_app()
