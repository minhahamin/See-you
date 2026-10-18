"""parse_request, ask_clarification 단위 테스트."""
from datetime import date

from langchain_core.messages import HumanMessage

from agent.nodes.ask_clarification import build_question
from agent.nodes.parse_request import ParsedRequest, find_missing, merge_request, parse_request
from agent.state import TripRequest

TODAY = date(2026, 10, 18)


def test_merge_keeps_old_values_and_unions_preferences() -> None:
    """새로 파싱된 값이 없으면 이전 값을 유지하고 취향은 합친다."""
    old = TripRequest(days=3, companions="커플", preferences=["바다"])
    merged = merge_request(old, ParsedRequest(start_date="2026-11-14", preferences=["흑돼지", "바다"]), TODAY)
    assert (merged.days, merged.companions, merged.start_date) == (3, "커플", "2026-11-14")
    assert merged.preferences == ["바다", "흑돼지"]


def test_merge_rejects_past_and_malformed_dates() -> None:
    """과거 날짜나 잘못된 형식은 인정하지 않는다."""
    assert merge_request(None, ParsedRequest(start_date="2026-01-01"), TODAY).start_date is None
    assert merge_request(None, ParsedRequest(start_date="11월 14일"), TODAY).start_date is None


def test_find_missing_lists_required_fields() -> None:
    """필수 조건 중 빈 항목만 반환한다."""
    assert find_missing(TripRequest()) == ["start_date", "days", "companions"]
    assert find_missing(TripRequest(start_date="2026-11-14", days=2, companions="가족")) == []


def test_parse_request_node(fake_llm) -> None:
    """노드는 파싱 결과를 병합해 request와 missing_fields를 돌려준다."""
    fake_llm[ParsedRequest] = lambda msgs: ParsedRequest(days=2, companions="가족")
    out = parse_request({"messages": [HumanMessage("가족이랑 2박 3일")]})
    assert out["request"].companions == "가족"
    assert out["missing_fields"] == ["start_date"]


def test_build_question_mentions_each_missing_field() -> None:
    """되묻기 문장은 부족한 항목마다 한 줄씩 포함한다."""
    text = build_question(["days", "companions"])
    assert "며칠" in text and "누구와" in text and "언제" not in text
