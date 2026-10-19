"""일정 제시 노드: 완성된 일정을 사용자에게 보여 주고 피드백을 기다린다 (interrupt)."""
from langchain_core.messages import HumanMessage
from langgraph.types import interrupt

from agent.state import PlannerState


def present_itinerary(state: PlannerState) -> dict:
    """일정과 남은 검증 문제를 전달하고, 사용자의 답을 피드백으로 기록한다. 빈 답이면 피드백 없음."""
    answer = interrupt(
        {
            "type": "itinerary",
            "itinerary": state["itinerary"].model_dump(),
            "issues": state.get("validation_issues", []),
            "applied_settings": state.get("applied_settings", {}),
            "notice": state.get("notice"),
        }
    )
    text = str(answer or "").strip()
    return {"feedback": text or None, "notice": None, "messages": [HumanMessage(text)] if text else []}
