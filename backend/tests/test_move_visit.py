"""타임라인 드래그 이동(move_visit)과 apply_feedback의 이동 경로 테스트."""
import pytest

from agent import catalog
from agent.moving import MoveError, move_visit, parse_move
from agent.nodes.apply_feedback import apply_feedback
from agent.planning import LLMPlan, fmt_time, parse_time
from tests.conftest import plan_from_prompt
from tests.test_graph import _full_state


def _flat(itinerary) -> dict[int, list[str]]:
    """일차별 장소 id 순서."""
    return {d.day: [v.place_id for v in d.visits] for d in itinerary.days}


def test_parse_move_reads_the_drag_sentence() -> None:
    """프론트가 보내는 이동 문장에서 일차·순번·시각을 읽고, 다른 문장은 None."""
    assert parse_move("1일차 2번째 방문(성산일출봉)을 2일차 14:30로 옮겨줘") == (1, 2, 2, 14 * 60 + 30)
    assert parse_move("장소 이름이 (괄호)를 가져도 된다: 1일차 1번째 방문(카페 (본점))을 1일차 9:00로 옮겨줘") == (1, 1, 1, 540)
    assert parse_move("2일차 다시 짜줘") is None


def test_move_to_other_day_marks_only_moved_block(fake_llm, fake_search) -> None:
    """다른 일차로 옮기면 그 방문만 changed이고, 원래 일차에서는 빠지고 시간순으로 들어간다."""
    fake_llm[LLMPlan] = plan_from_prompt
    itinerary = _full_state()["itinerary"]
    moving = itinerary.days[0].visits[0].place_id

    out = move_visit(itinerary, 1, 1, 2, 17 * 60)
    assert moving not in _flat(out)[1] and moving in _flat(out)[2]
    assert [(d.day, v.place_id) for d in out.days for v in d.visits if v.changed] == [(2, moving)]
    for day in out.days:
        starts = [parse_time(v.start) for v in day.visits]
        assert starts == sorted(starts)
        assert day.visits[0].travel_minutes_from_prev == 0


def test_move_within_day_keeps_duration_and_pushes_overlaps(fake_llm, fake_search) -> None:
    """같은 일차 안에서 옮기면 머무는 시간은 그대로이고, 앞 방문과 겹치면 이동시간만큼 뒤로 밀린다."""
    fake_llm[LLMPlan] = plan_from_prompt
    itinerary = _full_state()["itinerary"]
    first, second = itinerary.days[0].visits[:2]
    duration = parse_time(second.end) - parse_time(second.start)

    out = move_visit(itinerary, 1, 2, 1, parse_time(first.start) + 30)  # 첫 방문 중간(09:30)에 끼워 넣는다
    visits = out.days[0].visits
    moved = next(v for v in visits if v.place_id == second.place_id)
    assert parse_time(moved.end) - parse_time(moved.start) == duration
    assert moved.start > first.end  # 첫 방문이 끝나고 이동시간을 거친 뒤로 밀렸다
    assert all(a.end <= b.start for a, b in zip(visits, visits[1:]))  # HH:MM 문자열 비교


def test_move_rejects_overflow_and_bad_targets(fake_llm, fake_search) -> None:
    """22시를 넘기거나 없는 일차·방문이면 MoveError이고, 입력 일정은 바뀌지 않는다."""
    fake_llm[LLMPlan] = plan_from_prompt
    itinerary = _full_state()["itinerary"]
    snapshot = itinerary.model_copy(deep=True)

    with pytest.raises(MoveError):
        move_visit(itinerary, 1, 1, 2, 21 * 60 + 45)
    with pytest.raises(MoveError):
        move_visit(itinerary, 1, 1, 9, 600)
    with pytest.raises(MoveError):
        move_visit(itinerary, 1, 99, 2, 600)
    assert itinerary == snapshot


def test_apply_feedback_handles_move_without_llm(fake_llm, fake_search) -> None:
    """이동 문장은 LLM(FeedbackAction) 호출 없이 처리되고, 재생성하지 않도록 재시도 횟수를 채운다."""
    fake_llm[LLMPlan] = plan_from_prompt  # FeedbackAction은 등록하지 않는다: 호출하면 테스트가 실패한다
    state = _full_state()
    target = catalog.places()[state["itinerary"].days[0].visits[0].place_id].name
    state["feedback"] = f"1일차 1번째 방문({target})을 2일차 {fmt_time(18 * 60)}로 옮겨줘"

    out = apply_feedback(state)
    assert out["feedback"] is None and out["retry_count"] > 0
    assert any(v.changed for v in out["itinerary"].days[1].visits)

    state["feedback"] = "1일차 1번째 방문(x)을 2일차 21:50로 옮겨줘"
    refused = apply_feedback(state)
    assert "itinerary" not in refused and refused["messages"]
