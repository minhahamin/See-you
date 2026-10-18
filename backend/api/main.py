"""FastAPI 앱: 세션, 메시지(SSE 스트리밍), 장소 상세, 지표."""
import logging

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from langgraph.graph.state import CompiledStateGraph
from sse_starlette.sse import EventSourceResponse

from agent import catalog
from agent.graph import build_graph
from api.metrics import MetricsStore, load_experiments
from api.schemas import (
    ExperimentsResponse,
    MessageIn,
    PlaceDetail,
    RunsResponse,
    SessionCreated,
    SessionSummary,
    place_out,
    review_out,
)
from api.sessions import SessionManager
from config import get_settings, setup_logging

logger = logging.getLogger(__name__)


def create_app(graph: CompiledStateGraph | None = None, store: MetricsStore | None = None) -> FastAPI:
    """앱을 만든다. 테스트에서는 그래프와 지표 저장소를 주입한다."""
    setup_logging()
    settings = get_settings()
    app = FastAPI(title="여행 일정 플래너 API")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[o.strip() for o in settings.cors_origins.split(",") if o.strip()],
        allow_methods=["*"],
        allow_headers=["*"],
    )
    metrics = store if store is not None else MetricsStore(settings.runs_log_path)
    sessions = SessionManager(graph or build_graph(), metrics)

    @app.get("/api/health")
    def health() -> dict[str, str]:
        """헬스체크."""
        return {"status": "ok"}

    @app.post("/api/sessions", response_model=SessionCreated)
    def create_session() -> SessionCreated:
        """새 세션을 만든다."""
        return SessionCreated(session_id=sessions.create())

    @app.post("/api/sessions/{session_id}/messages")
    async def send_message(session_id: str, body: MessageIn) -> EventSourceResponse:
        """사용자 메시지를 보내고 진행 단계·결과를 SSE로 받는다."""
        if not sessions.exists(session_id):
            raise HTTPException(404, "세션을 찾을 수 없습니다.")
        if sessions.is_busy(session_id):
            raise HTTPException(409, "이전 메시지를 처리하는 중입니다.")
        return EventSourceResponse(sessions.stream_turn(session_id, body.text))

    @app.get("/api/sessions/{session_id}", response_model=SessionSummary)
    async def get_session(session_id: str) -> SessionSummary:
        """현재 대화와 일정 요약."""
        if not sessions.exists(session_id):
            raise HTTPException(404, "세션을 찾을 수 없습니다.")
        return await sessions.summary(session_id)

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

    return app


app = create_app()
