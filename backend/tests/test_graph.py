"""apply_feedback 단위 테스트와 그래프 전체 흐름(되묻기 → 생성 → 검증 루프 → 피드백) 테스트."""
import pytest
from langchain_core.messages import HumanMessage
from langgraph.types import Command

from agent import catalog
from agent.graph import build_graph, make_checkpointer, route_after_feedback, route_after_validate
from agent.nodes.apply_feedback import FeedbackAction, apply_feedback
from agent.nodes.build_itinerary import build_itinerary
from agent.nodes.parse_request import ParsedRequest
from agent.planning import LLMPlan, to_candidate
from agent.review_tools import ReviewAnalysis, fallback_summary
from agent.state import TripRequest
from tests.conftest import plan_from_prompt


def _full_state(days: int = 2) -> dict:
    """일정까지 만들어진 상태 (apply_feedback 입력용)."""
    cands = [to_candidate(pid, i) for i, pid in enumerate(sorted(catalog.places()))]
    state = {
        "request": TripRequest(start_date="2026-11-14", days=days, companions="커플"),
        "candidates": cands,
        "review_summaries": {c.id: fallback_summary(c) for c in cands},
        "weather": {},
    }
    state["itinerary"] = build_itinerary(state)["itinerary"]
    return state


def test_feedback_accept_and_rebuild(fake_llm, fake_search) -> None:
    """확정은 accepted, 조건 변경은 취향을 추가하고 재검색을 요청한다."""
    fake_llm[LLMPlan] = plan_from_prompt
    state = {**_full_state(), "feedback": "좋아요"}
    fake_llm[FeedbackAction] = lambda m: FeedbackAction(action="accept")
    assert apply_feedback(state)["accepted"] is True

    fake_llm[FeedbackAction] = lambda m: FeedbackAction(action="rebuild", constraint="흑돼지")
    fake_llm[ParsedRequest] = lambda m: ParsedRequest()  # 피드백에 조건 변경이 없으면 기존 조건을 그대로 둔다
    out = apply_feedback(state)
    assert out["rerun_search"] is True and "흑돼지" in out["request"].preferences
    assert out["feedback"] is None and out["retry_count"] == 0


def test_feedback_replace_visit_changes_only_that_block(fake_llm, fake_search) -> None:
    """방문 하나를 바꾸면 그 블록만 changed이고 나머지는 그대로다."""
    fake_llm[LLMPlan] = plan_from_prompt
    state = {**_full_state(), "feedback": "1일차 두 번째 카페로 바꿔줘"}
    before = state["itinerary"]
    target = before.days[0].visits[1]
    fake_llm[FeedbackAction] = lambda m: FeedbackAction(action="replace_visit", day=1, visit_index=2, constraint="조용한 곳")
    fake_llm[ReviewAnalysis] = lambda m: ReviewAnalysis(summaries=[])  # 요약이 비면 특성 기반 요약으로 채워진다

    out = apply_feedback(state)
    after = out["itinerary"]
    changed = [(d.day, v.place_id) for d in after.days for v in d.visits if v.changed]
    assert len(changed) == 1 and changed[0][0] == 1
    assert changed[0][1] != target.place_id
    assert catalog.places()[changed[0][1]].category == catalog.places()[target.place_id].category
    assert [v.place_id for v in after.days[1].visits] == [v.place_id for v in before.days[1].visits]  # 다른 일차는 그대로
    assert changed[0][1] in out["review_summaries"]
    assert "1일차 2번째 방문" in out["notice"] and "바꿨어요" in out["notice"]  # 무엇이 바뀌었는지 알려 준다


def test_feedback_replace_day_marks_new_places(fake_llm, fake_search) -> None:
    """일차 전체 재구성은 새로 들어온 장소만 changed로 표시한다."""
    fake_llm[LLMPlan] = plan_from_prompt
    state = {**_full_state(), "feedback": "2일차 다시 짜줘"}
    before_ids = {v.place_id for v in state["itinerary"].days[1].visits}
    fake_llm[FeedbackAction] = lambda m: FeedbackAction(action="replace_day", day=2, constraint="실내 위주")
    out = apply_feedback(state)
    day2 = out["itinerary"].days[1]
    assert all(v.changed == (v.place_id not in before_ids) for v in day2.visits)
    assert not any(v.changed for v in out["itinerary"].days[0].visits)
    assert out["notice"] == "2일차를 다시 짰어요."


def test_feedback_unknown_day_leaves_itinerary(fake_llm, fake_search) -> None:
    """없는 일차를 지정하면 일정을 그대로 두고 안내한다."""
    fake_llm[LLMPlan] = plan_from_prompt
    state = {**_full_state(), "feedback": "9일차 바꿔줘"}
    fake_llm[FeedbackAction] = lambda m: FeedbackAction(action="replace_day", day=9)
    out = apply_feedback(state)
    assert "itinerary" not in out and out["messages"]


def test_routing_functions(monkeypatch) -> None:
    """분기 함수: 검증 재시도 한도와 피드백 후 경로. 검증 실패 시 기본은 부분 수리, 설정하면 전체 재생성."""
    assert route_after_validate({"validation_issues": ["x"], "retry_count": 1}) == "repair_itinerary"
    monkeypatch.setenv("VALIDATION_LOOP", "regenerate")
    assert route_after_validate({"validation_issues": ["x"], "retry_count": 1}) == "build_itinerary"
    monkeypatch.delenv("VALIDATION_LOOP")
    assert route_after_validate({"validation_issues": ["x"], "retry_count": 2}) == "present_itinerary"
    assert route_after_validate({"validation_issues": [], "retry_count": 0}) == "present_itinerary"
    assert route_after_feedback({"accepted": True}) == "__end__"
    assert route_after_feedback({"rerun_search": True}) == "search_places"
    assert route_after_feedback({}) == "validate_itinerary"


def test_graph_full_flow(wired, fake_llm) -> None:
    """되묻기(interrupt) → 재개 → 일정 제시(interrupt) → 피드백 → 확정까지 한 스레드에서 이어진다."""
    graph = build_graph(make_checkpointer())
    cfg = {"configurable": {"thread_id": "t1"}}

    # 1) 조건이 부족하면 되묻는다
    out = graph.invoke({"messages": [HumanMessage("제주 2박 3일 가고 싶어요")]}, cfg)
    q = out["__interrupt__"][0].value
    assert q["type"] == "question" and set(q["missing_fields"]) == {"start_date", "companions"}

    # 2) 답하면 이어서 일정을 만들고, 검증 문제가 남아도 재시도 한도(2회) 뒤 제시한다
    out = graph.invoke(Command(resume="11월 14일에 커플로 가요"), cfg)
    shown = out["__interrupt__"][0].value
    assert shown["type"] == "itinerary" and len(shown["itinerary"]["days"]) == 2
    assert wired["build"] <= 3  # 최초 1회 + 재생성 최대 2회
    assert shown["itinerary"]["validation"]["total"] > 0

    # 3) 피드백으로 한 곳만 바꾸면 다시 제시된다
    fake_llm[FeedbackAction] = lambda m: FeedbackAction(action="replace_visit", day=1, visit_index=2, constraint="조용한 곳")
    out = graph.invoke(Command(resume="1일차 두 번째 장소 바꿔줘"), cfg)
    again = out["__interrupt__"][0].value
    flags = [v["changed"] for d in again["itinerary"]["days"] for v in d["visits"]]
    assert sum(flags) == 1
    assert "바꿨어요" in again["notice"]

    # 4) 확정하면 끝난다
    fake_llm[FeedbackAction] = lambda m: FeedbackAction(action="accept")
    out = graph.invoke(Command(resume="좋아요"), cfg)
    assert "__interrupt__" not in out and out["accepted"] is True


def test_graph_without_feedback_ends(wired) -> None:
    """조건이 충분하면 되묻지 않고, 빈 응답으로 재개하면 피드백 없이 끝난다."""
    graph = build_graph(make_checkpointer())
    cfg = {"configurable": {"thread_id": "t2"}}
    out = graph.invoke({"messages": [HumanMessage("11월에 커플로 2박 3일")]}, cfg)
    assert out["__interrupt__"][0].value["type"] == "itinerary"
    out = graph.invoke(Command(resume=""), cfg)
    assert "__interrupt__" not in out and not out.get("feedback")


def test_feedback_rebuild_applies_changed_date_days_and_budget(fake_llm, fake_search) -> None:
    """피드백으로 날짜·일수·예산이 바뀌면 조건에 반영하고 다시 검색한다. 지난 날짜는 무시한다."""
    fake_llm[LLMPlan] = plan_from_prompt
    state = {**_full_state(), "feedback": "12월 12일로 3일, 저렴하게 바꿔줘"}
    fake_llm[FeedbackAction] = lambda m: FeedbackAction(action="rebuild")
    fake_llm[ParsedRequest] = lambda m: ParsedRequest(start_date="2099-12-12", days=3, budget=1)

    out = apply_feedback(state)
    assert out["rerun_search"] is True
    assert (out["request"].start_date, out["request"].days, out["request"].budget) == ("2099-12-12", 3, 1)
    assert out["request"].companions == "커플"  # 말하지 않은 조건은 유지

    fake_llm[ParsedRequest] = lambda m: ParsedRequest(start_date="2020-01-01")
    assert apply_feedback(state)["request"].start_date == "2026-11-14"  # 이미 지난 날짜는 받아들이지 않는다


def test_feedback_rebuild_gives_parser_current_request_and_skips_empty_constraint(fake_llm, fake_search) -> None:
    """'하루 미뤄줘' 같은 상대 변경을 계산하도록 파서에 현재 조건을 주고, 취향이 아닌 변경은 취향에 넣지 않는다."""
    seen: list[str] = []

    def parse(messages: list) -> ParsedRequest:
        seen.append(messages[-1].content)
        return ParsedRequest(start_date="2099-12-13")

    fake_llm[LLMPlan] = plan_from_prompt
    fake_llm[FeedbackAction] = lambda m: FeedbackAction(action="rebuild")
    fake_llm[ParsedRequest] = parse
    state = {**_full_state(), "feedback": "출발을 하루 미뤄줘"}
    out = apply_feedback(state)
    assert "출발일 2026-11-14" in seen[0] and "하루 미뤄줘" in seen[0]
    assert out["request"].start_date == "2099-12-13"
    assert out["request"].preferences == state["request"].preferences


def test_feedback_unclear_keeps_itinerary_and_does_not_accept(fake_llm, fake_search) -> None:
    """의미 없는 피드백은 확정으로 보지 않고 일정을 그대로 둔 채 다시 묻는다."""
    fake_llm[LLMPlan] = plan_from_prompt
    fake_llm[FeedbackAction] = lambda m: FeedbackAction(action="unclear")
    out = apply_feedback({**_full_state(), "feedback": "ㅋㅋㅋㅋ"})
    assert not out.get("accepted") and "itinerary" not in out and not out.get("rerun_search")
    assert "바꾸고 싶으신지" in out["messages"][0].content


def test_feedback_input_includes_recent_conversation() -> None:
    """피드백 해석기는 직전 대화를 함께 받아 '다시 포함해' 같은 말을 해석할 수 있다."""
    from langchain_core.messages import AIMessage

    from agent.nodes.apply_feedback import render_feedback_input

    state = {"feedback": "흑돼지 다시 포함해", "messages": [HumanMessage("2일차 점심 흑돼지로"), AIMessage("바꿨어요."), HumanMessage("흑돼지 다시 포함해")]}
    text = render_feedback_input(state)
    assert "사용자: 2일차 점심 흑돼지로" in text and "에이전트: 바꿨어요." in text and text.endswith("이번 피드백: 흑돼지 다시 포함해")
    assert render_feedback_input({"feedback": "안녕", "messages": []}) == "안녕"


def test_replace_day_keeps_requested_place_and_leaves_other_days(fake_llm, fake_search, monkeypatch) -> None:
    """keep으로 지정한 장소는 그 일차 점심에 반드시 들어가고, 다른 일차는 바뀌지 않는다."""
    fake_llm[LLMPlan] = plan_from_prompt
    fake_llm[ReviewAnalysis] = lambda m: ReviewAnalysis(summaries=[])
    monkeypatch.setattr(
        "agent.nodes.apply_feedback.hybrid_search",
        lambda q, n=30, filters=None: [{"id": "x", "text": "", "meta": {"place_id": "404165"}}],  # 키워드 검색이 흑돼지 식당을 돌려준다
    )
    state = {**_full_state(), "feedback": "2일차 흑돼지 넣고 나머지는 가까운 곳으로"}
    before = state["itinerary"]
    fake_llm[FeedbackAction] = lambda m: FeedbackAction(action="replace_day", day=2, constraint="이동이 짧은 곳", keep=["흑돼지"])

    out = apply_feedback(state)
    day2 = out["itinerary"].days[1]
    hog = catalog.places()["404165"]  # 흑돼지 식당 (왕일번지식당)
    lunch = [v for v in day2.visits if v.place_id == hog.id]
    assert len(lunch) == 1 and lunch[0].slot == "lunch" and lunch[0].start < "13:30"
    assert [v.place_id for v in out["itinerary"].days[0].visits] == [v.place_id for v in before.days[0].visits]
    assert out["itinerary"].days[1].visits[-1].end <= "22:00"
