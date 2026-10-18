"""세션 관리와 그래프 실행 → SSE 이벤트 변환."""
import asyncio
import json
import logging
import time
import uuid
from typing import Any, AsyncIterator

from langchain_core.messages import AIMessage, HumanMessage
from langgraph.graph.state import CompiledStateGraph
from langgraph.types import Command
from pydantic import BaseModel

from api.metrics import MetricsStore, RunRecorder, add_node_call, classify_issue, new_record, run_cost_usd
from api.schemas import (
    ChatMessageOut,
    ErrorEvent,
    ItineraryEvent,
    QuestionEvent,
    SessionSummary,
    StepEvent,
    place_out,
)
from agent.state import Itinerary
from llm import is_daily_quota_error

logger = logging.getLogger(__name__)

NODE_LABELS = {
    "parse_request": "여행 조건 파악",
    "ask_clarification": "추가 정보 확인",
    "search_places": "장소·후기 검색",
    "analyze_reviews": "후기 분석",
    "check_weather": "날씨 확인",
    "build_itinerary": "일정 생성",
    "validate_itinerary": "일정 검증",
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
    return sse("itinerary", ItineraryEvent(itinerary=itinerary, places=[place_out(i) for i in ids], issues=payload["issues"]))


class SessionManager:
    """세션 id(= LangGraph thread_id)를 관리하고 메시지 한 턴을 스트리밍으로 실행한다."""

    def __init__(self, graph: CompiledStateGraph, store: MetricsStore) -> None:
        """그래프와 지표 저장소를 받는다."""
        self._graph = graph
        self._store = store
        self._sessions: set[str] = set()
        self._locks: dict[str, asyncio.Lock] = {}

    def create(self) -> str:
        """새 세션을 만든다."""
        sid = uuid.uuid4().hex
        self._sessions.add(sid)
        self._locks[sid] = asyncio.Lock()
        return sid

    def exists(self, sid: str) -> bool:
        """세션이 있는지."""
        return sid in self._sessions

    def is_busy(self, sid: str) -> bool:
        """이전 메시지를 아직 처리 중인지 (한 세션은 동시에 한 턴만 실행한다)."""
        return self._locks[sid].locked()

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

    async def stream_turn(self, sid: str, text: str) -> AsyncIterator[dict[str, str]]:
        """메시지 한 턴을 실행하며 step·question·itinerary·error·done 이벤트를 내보낸다."""
        async with self._locks[sid]:
            recorder = RunRecorder()
            record = new_record(sid, uuid.uuid4().hex[:8])
            started_at = time.perf_counter()
            task_start: dict[str, tuple[float, int]] = {}  # task id → (시작 시각, 시작 시점 토큰 누계)
            try:
                pending = await self._pending_interrupts(sid)
                graph_input: Any = Command(resume=text) if pending else {"messages": [HumanMessage(text)]}
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
                            yield interrupt_event(chunk["__interrupt__"][0].value)
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
            yield sse("done", {})

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
