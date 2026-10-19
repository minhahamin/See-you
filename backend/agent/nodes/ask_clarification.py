"""되묻기 노드: 부족한 조건을 사용자에게 묻고 응답을 기다린다 (interrupt)."""
from langchain_core.messages import AIMessage, HumanMessage
from langgraph.types import interrupt

from agent.state import PlannerState

QUESTIONS = {
    "start_date": "여행은 언제 출발하나요? (예: 11월 14일)",
    "days": "며칠 일정인가요? (예: 2박 3일)",
    "companions": "누구와 함께 가나요? (혼자 / 커플 / 친구 / 가족)",
}


def build_question(missing: list[str], unsupported_region: str | None = None) -> str:
    """부족한 항목들을 하나의 질문 문장으로 묶는다. 지원하지 않는 지역을 말했으면 먼저 알린다."""
    lines = [f"- {QUESTIONS[f]}" for f in missing if f in QUESTIONS]
    header = "일정을 짜려면 몇 가지가 더 필요해요.\n"
    if "region" not in missing:
        return header + "\n".join(lines)
    notice = f"{unsupported_region or '그 지역'}은(는) 아직 지원하지 않고 제주 여행만 만들 수 있어요. 제주로 계속할게요."
    if not lines:
        return notice + " 괜찮으면 아무 말이나 보내 주세요 (예: 응, 제주로 해줘)."
    return notice + "\n" + header + "\n".join(lines)


def ask_clarification(state: PlannerState) -> dict:
    """질문을 사용자에게 보내고, 재개 값(사용자 답변)을 대화에 추가한다."""
    question = build_question(state["missing_fields"], state.get("unsupported_region"))
    answer = interrupt({"type": "question", "question": question, "missing_fields": state["missing_fields"]})
    return {"messages": [AIMessage(question), HumanMessage(str(answer))]}
