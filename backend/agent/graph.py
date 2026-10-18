"""LangGraph 조립. 분기 조건 함수는 이 파일에 모은다."""
from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.checkpoint.memory import MemorySaver
from langgraph.checkpoint.serde.jsonplus import JsonPlusSerializer
from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph

from agent.nodes.analyze_reviews import analyze_reviews
from agent.nodes.apply_feedback import apply_feedback
from agent.nodes.ask_clarification import ask_clarification
from agent.nodes.build_itinerary import build_itinerary
from agent.nodes.check_weather import check_weather
from agent.nodes.parse_request import parse_request
from agent.nodes.present_itinerary import present_itinerary
from agent.nodes.search_places import search_places
from agent.nodes.validate_itinerary import validate_itinerary
from agent.state import PlannerState
from config import get_settings


# 체크포인트에서 복원을 허용할 상태 모델 (그 외 타입은 차단한다)
STATE_MODELS = [
    ("agent.state", name)
    for name in ("TripRequest", "Candidate", "ReviewSummary", "Weather", "Visit", "DayPlan", "Validation", "Itinerary")
]


def make_checkpointer() -> MemorySaver:
    """상태 모델의 직렬화·복원을 명시적으로 허용한 인메모리 체크포인터. (배포 시 SQLite로 교체)"""
    return MemorySaver(serde=JsonPlusSerializer(allowed_msgpack_modules=STATE_MODELS))


def route_after_parse(state: PlannerState) -> str:
    """필수 조건이 비었으면 되묻고, 충분하면 검색으로 간다."""
    return "ask_clarification" if state.get("missing_fields") else "search_places"


def route_after_validate(state: PlannerState) -> str:
    """검증 문제가 있고 재시도 여유가 있으면 일정을 다시 만들고, 아니면 사용자에게 제시한다."""
    if state.get("validation_issues") and state.get("retry_count", 0) < get_settings().max_retry:
        return "build_itinerary"
    return "present_itinerary"


def route_after_present(state: PlannerState) -> str:
    """피드백이 있으면 반영하고, 없으면 끝낸다."""
    return "apply_feedback" if state.get("feedback") else END


def route_after_feedback(state: PlannerState) -> str:
    """확정이면 끝, 조건이 바뀌었으면 재검색, 부분 수정이면 검증으로 간다."""
    if state.get("accepted"):
        return END
    if state.get("rerun_search"):
        return "search_places"
    return "validate_itinerary"


def build_graph(checkpointer: BaseCheckpointSaver | None = None) -> CompiledStateGraph:
    """여행 플래너 그래프를 만든다. 사용자 대기(interrupt)에는 체크포인터가 필요하다."""
    graph = StateGraph(PlannerState)
    nodes = {
        "parse_request": parse_request,
        "ask_clarification": ask_clarification,
        "search_places": search_places,
        "analyze_reviews": analyze_reviews,
        "check_weather": check_weather,
        "build_itinerary": build_itinerary,
        "validate_itinerary": validate_itinerary,
        "present_itinerary": present_itinerary,
        "apply_feedback": apply_feedback,
    }
    for name, fn in nodes.items():
        graph.add_node(name, fn)

    graph.add_edge(START, "parse_request")
    graph.add_conditional_edges("parse_request", route_after_parse, ["ask_clarification", "search_places"])
    graph.add_edge("ask_clarification", "parse_request")
    graph.add_edge("search_places", "analyze_reviews")
    graph.add_edge("analyze_reviews", "check_weather")
    graph.add_edge("check_weather", "build_itinerary")
    graph.add_edge("build_itinerary", "validate_itinerary")
    graph.add_conditional_edges("validate_itinerary", route_after_validate, ["build_itinerary", "present_itinerary"])
    graph.add_conditional_edges("present_itinerary", route_after_present, ["apply_feedback", END])
    graph.add_conditional_edges("apply_feedback", route_after_feedback, ["search_places", "validate_itinerary", END])
    return graph.compile(checkpointer=checkpointer or make_checkpointer())
