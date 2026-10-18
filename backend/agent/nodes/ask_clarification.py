"""되묻기 노드: 부족한 조건을 사용자에게 묻고 응답을 기다린다 (interrupt)."""
from langchain_core.messages import AIMessage, HumanMessage
from langgraph.types import interrupt

from agent.state import PlannerState

QUESTIONS = {
    "start_date": "여행은 언제 출발하나요? (예: 11월 14일)",
    "days": "며칠 일정인가요? (예: 2박 3일)",
    "companions": "누구와 함께 가나요? (혼자 / 커플 / 친구 / 가족)",
}


def build_question(missing: list[str]) -> str:
    """부족한 항목들을 하나의 질문 문장으로 묶는다."""
    return "일정을 짜려면 몇 가지가 더 필요해요.\n" + "\n".join(f"- {QUESTIONS[f]}" for f in missing)


def ask_clarification(state: PlannerState) -> dict:
    """질문을 사용자에게 보내고, 재개 값(사용자 답변)을 대화에 추가한다."""
    question = build_question(state["missing_fields"])
    answer = interrupt({"type": "question", "question": question, "missing_fields": state["missing_fields"]})
    return {"messages": [AIMessage(question), HumanMessage(str(answer))]}
