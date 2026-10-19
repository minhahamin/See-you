"""세션 관리(소유권·기록)와 그래프 실행 → SSE 이벤트 변환."""
import asyncio
import json
import logging
import time
import uuid
from typing import Any, AsyncIterator, Callable, TypeVar

from langchain_core.messages import AIMessage, HumanMessage
from langgraph.graph.state import CompiledStateGraph
from langgraph.types import Command
from pydantic import BaseModel
from sqlalchemy.orm import Session, sessionmaker

from accounts import service
from agent.state import Itinerary
from api.metrics import MetricsStore, RunRecorder, add_node_call, classify_issue, new_record, run_cost_usd
from api.schemas import (
    AppliedSettings,
    ChatMessageOut,
    ErrorEvent,
    ItineraryEvent,
    QuestionEvent,
    SessionListItem,
    SessionSummary,
    StepEvent,
    place_out,
)
from llm import is_daily_quota_error

logger = logging.getLogger(__name__)

T = TypeVar("T")
PROVISIONAL_TITLE_LEN = 30  # 일정이 나오기 전까지 목록에 보여 줄 제목 (첫 메시지 앞부분)

NODE_LABELS = {
    "parse_request": "여행 조건 파악",
    "ask_clarification": "추가 정보 확인",
    "search_places": "장소·후기 검색",
    "analyze_reviews": "후기 분석",
    "check_weather": "날씨 확인",
    "build_itinerary": "일정 생성",
    "validate_itinerary": "일정 검증",
    "repair_itinerary": "일정 부분 수리",
    "present_itinerary": "일정 제시",
    "apply_feedback": "피드백 반영",
}


def sse(event: str, payload: BaseModel | dict) -> dict[str, str]:
    """sse-starlette가 보낼 이벤트 dict."""
    data = payload.model_dump_json() if isinstance(payload, BaseModel) else json.dumps(payload, ensure_ascii=False)
    return {"event": event, "data": data}


def error_message(exc: Exception) -> str:
    """사용자에게 보여 줄 오류 문구. 내부 예외 내용은 노출하지 않는다."""
    if is_daily_quota_error(exc):
        return "LLM 일일 호출 한도에 도달했어요. 잠시 후 다시 시도해 주세요."
    return "일정을 만드는 중 오류가 발생했어요. 잠시 후 다시 시도해 주세요."


def interrupt_event(payload: dict[str, Any]) -> dict[str, str]:
    """interrupt 값(되묻기/일정 제시)을 SSE 이벤트로 바꾼다."""
    if payload["type"] == "question":
        return sse("question", QuestionEvent(question=payload["question"], missing_fields=payload["missing_fields"]))
    itinerary = Itinerary.model_validate(payload["itinerary"])
    ids = list(dict.fromkeys(v.place_id for d in itinerary.days for v in d.visits))
    return sse(
        "itinerary",
        ItineraryEvent(
            itinerary=itinerary,
            places=[place_out(i) for i in ids],
            issues=payload["issues"],
            applied_settings=AppliedSettings(**payload.get("applied_settings", {})),
            notice=payload.get("notice"),
        ),
    )


class SessionManager:
    """세션 id(= LangGraph thread_id)를 DB에서 관리하고 메시지 한 턴을 스트리밍으로 실행한다.

    계정에 속한 대화는 소유자만, 게스트 대화는 id를 아는 사람만 접근할 수 있다.
    """

    def __init__(self, graph: CompiledStateGraph, store: MetricsStore, db_factory: sessionmaker[Session]) -> None:
        """그래프, 지표 저장소, DB 세션 팩토리를 받는다."""
        self._graph = graph
        self._store = store
        self._db_factory = db_factory
        self._locks: dict[str, asyncio.Lock] = {}

    async def _db(self, fn: Callable[..., T], *args: Any, **kwargs: Any) -> T:
        """동기 DB 함수를 스레드에서 한 트랜잭션으로 실행한다 (이벤트 루프를 막지 않는다)."""

        def run() -> T:
            db = self._db_factory()
            try:
                result = fn(db, *args, **kwargs)
                db.commit()
                return result
            except Exception:
                db.rollback()
                raise
            finally:
                db.close()

        return await asyncio.to_thread(run)

    def _lock(self, sid: str) -> asyncio.Lock:
        return self._locks.setdefault(sid, asyncio.Lock())

    # ---- 생성·접근 ----

    async def create(self, user_id: uuid.UUID | None) -> str:
        """새 세션을 만든다. 로그인하지 않았으면 게스트 대화가 된다."""
        return await self._db(service.create_chat_session, user_id)

    async def accessible(self, sid: str, user_id: uuid.UUID | None) -> bool:
        """세션이 있고 이 사용자가 접근할 수 있는지. 남의 대화는 '없는 것'처럼 보이게 한다."""

        def check(db: Session) -> bool:
            row = service.get_chat_session(db, sid)
            return row is not None and service.can_access(row, user_id)

        return await self._db(check)

    def is_busy(self, sid: str) -> bool:
        """이전 메시지를 아직 처리 중인지 (한 세션은 동시에 한 턴만 실행한다)."""
        return self._lock(sid).locked()

    # ---- 기록 ----

    async def list_for(self, user_id: uuid.UUID) -> list[SessionListItem]:
        """'내 일정' 목록 (최근 수정 순). 대화 내용이 없는 빈 세션은 숨긴다."""

        def load(db: Session) -> list[SessionListItem]:
            return [
                SessionListItem(
                    session_id=r.id,
                    title=r.title,
                    trip_days=r.trip_days,
                    companions=r.companions,
                    created_at=r.created_at.isoformat(),
                    updated_at=r.updated_at.isoformat(),
                )
                for r in service.list_chat_sessions(db, user_id)
                if r.title
            ]

        return await self._db(load)

    async def claim(self, sid: str, user_id: uuid.UUID) -> bool:
        """게스트 대화를 내 계정으로 가져온다."""
        return await self._db(service.claim_chat_session, sid, user_id)

    async def delete(self, sid: str) -> None:
        """대화와 그 체크포인트를 지운다."""
        await self._db(service.delete_chat_session, sid)
        await self.purge_checkpoints([sid])

    async def purge_checkpoints(self, session_ids: list[str]) -> None:
        """대화 상태(체크포인트)를 지운다. 체크포인터가 삭제를 지원하지 않으면 건너뛴다."""
        saver = self._graph.checkpointer
        for sid in session_ids:
            self._locks.pop(sid, None)
            if hasattr(saver, "adelete_thread"):
                await saver.adelete_thread(sid)  # type: ignore[union-attr]

    async def purge_old_guests(self, older_than_days: int) -> int:
        """오래 방치된 게스트 대화를 지운다. 지운 개수를 돌려준다."""
        ids = await self._db(service.purge_old_guest_sessions, older_than_days)
        await self.purge_checkpoints(ids)
        return len(ids)

    # ---- 실행 ----

    @staticmethod
    def _config(sid: str, recorder: RunRecorder | None = None) -> dict[str, Any]:
        """LangGraph 실행 설정. thread_id가 곧 세션 id."""
        cfg: dict[str, Any] = {"configurable": {"thread_id": sid}}
        if recorder:
            cfg["callbacks"] = [recorder]
        return cfg

    async def _pending_interrupts(self, sid: str) -> list[Any]:
        """사용자 응답을 기다리는 interrupt 값 목록."""
        state = await self._graph.aget_state(self._config(sid))
        return [i.value for t in state.tasks for i in t.interrupts]

    async def stream_turn(self, sid: str, text: str, profile: dict | None = None) -> AsyncIterator[dict[str, str]]:
        """메시지 한 턴을 실행하며 step·question·itinerary·error·done 이벤트를 내보낸다.

        profile은 저장된 사용자 설정이다. 에이전트는 이를 일정의 기본 조건으로 쓴다.
        """
        async with self._lock(sid):
            recorder = RunRecorder()
            record = new_record(sid, uuid.uuid4().hex[:8])
            started_at = time.perf_counter()
            task_start: dict[str, tuple[float, int]] = {}  # task id → (시작 시각, 시작 시점 토큰 누계)
            meta: dict[str, Any] = {}  # 목록에 보여 줄 요약 (일정이 나오면 채운다)
            try:
                pending = await self._pending_interrupts(sid)
                graph_input: Any = Command(resume=text) if pending else {"messages": [HumanMessage(text)], "profile": profile}
                async for mode, chunk in self._graph.astream(
                    graph_input, self._config(sid, recorder), stream_mode=["tasks", "updates"]
                ):
                    if mode == "tasks":
                        node = chunk["name"]
                        if "result" not in chunk and "error" not in chunk:  # 노드 시작
                            task_start[chunk["id"]] = (time.perf_counter(), recorder.node_tokens(node))
                            yield sse("step", StepEvent(node=node, label=NODE_LABELS.get(node, node), status="running"))
                        else:  # 노드 종료
                            t0, tok0 = task_start.pop(chunk["id"], (time.perf_counter(), 0))
                            ms = (time.perf_counter() - t0) * 1000
                            tokens = recorder.node_tokens(node) - tok0
                            add_node_call(record, node, ms, 0, 0)  # 토큰은 종료 시 노드별 입출력으로 채운다
                            yield sse(
                                "step",
                                StepEvent(node=node, label=NODE_LABELS.get(node, node), status="done", duration_ms=round(ms), tokens=tokens or None),
                            )
                    elif mode == "updates":
                        if "__interrupt__" in chunk:
                            payload = chunk["__interrupt__"][0].value
                            if payload["type"] == "itinerary":
                                it = payload["itinerary"]
                                meta.update(title=it["title"], trip_days=len(it["days"]), companions=it.get("companions") or None)
                            yield interrupt_event(payload)
                        elif "validate_itinerary" in chunk:
                            issues = chunk["validate_itinerary"].get("validation_issues", [])
                            record["issue_kinds"] += [classify_issue(m) for m in issues]
            except Exception as exc:  # noqa: BLE001 - 어떤 실패든 스트림은 error+done으로 닫는다
                record["error"] = True
                logger.error("그래프 실행 실패: %s", type(exc).__name__)
                yield sse("error", ErrorEvent(message=error_message(exc)))
            finally:
                record["response_sec"] = time.perf_counter() - started_at
                tin, tout = sum(recorder.tokens_in.values()), sum(recorder.tokens_out.values())
                record["cost_usd"] = run_cost_usd(tin, tout) if (tin or tout) else None
                for node, n in record["nodes"].items():
                    n["tokens_in"], n["tokens_out"] = recorder.tokens_in[node], recorder.tokens_out[node]
                self._store.add(record)
                await self._save_meta(sid, text, meta)
            yield sse("done", {})

    async def _save_meta(self, sid: str, first_text: str, meta: dict[str, Any]) -> None:
        """목록용 제목·요약을 갱신한다. 일정이 아직 없으면 첫 메시지 앞부분을 임시 제목으로 쓴다."""

        def save(db: Session) -> None:
            row = service.get_chat_session(db, sid)
            if row is None:
                return
            title = meta.get("title") or (None if row.title else first_text[:PROVISIONAL_TITLE_LEN])
            service.update_chat_meta(db, sid, title=title, trip_days=meta.get("trip_days"), companions=meta.get("companions"))

        try:
            await self._db(save)
        except Exception as exc:  # noqa: BLE001 - 기록 갱신 실패가 응답을 망치지 않게 한다
            logger.error("대화 요약 저장 실패: %s", type(exc).__name__)

    async def summary(self, sid: str) -> SessionSummary:
        """현재 대화·조건·일정을 요약한다."""
        state = await self._graph.aget_state(self._config(sid))
        values = state.values or {}
        messages = [
            ChatMessageOut(id=m.id or f"m{i}", role="user" if isinstance(m, HumanMessage) else "assistant", text=str(m.content))
            for i, m in enumerate(values.get("messages", []))
            if isinstance(m, (HumanMessage, AIMessage))
        ]
        interrupts = [i.value for t in state.tasks for i in t.interrupts]
        awaiting = {"question": "question", "itinerary": "feedback"}.get(interrupts[0]["type"]) if interrupts else None
        itinerary = values.get("itinerary")
        ids = list(dict.fromkeys(v.place_id for d in itinerary.days for v in d.visits)) if itinerary else []
        return SessionSummary(
            session_id=sid,
            messages=messages,
            request=values.get("request"),
            itinerary=itinerary,
            places=[place_out(i) for i in ids],
            awaiting=awaiting,
        )
