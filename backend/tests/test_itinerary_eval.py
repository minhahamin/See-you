"""일정 평가(v5)와 Faithfulness 판정 테스트. LLM은 가짜로 대체한다."""
from datetime import date, timedelta

from agent import catalog
from agent.nodes.parse_request import ParsedRequest
from agent.state import DayPlan, Itinerary, Validation, Visit
from eval import faithfulness as F
from eval import run_itinerary_eval as E
from tests.conftest import plan_from_prompt


def itinerary_with(place_ids: list[str]) -> Itinerary:
    """장소 id 목록으로 만든 하루짜리 일정 (추천 이유와 근거 후기 포함)."""
    visits = [
        Visit(place_id=pid, start=f"{9 + 2 * i:02d}:00", end=f"{10 + 2 * i:02d}:00", reason=f"이유 {i}", evidence_review_ids=sorted(catalog.review_ids(pid))[:1])
        for i, pid in enumerate(place_ids)
    ]
    return Itinerary(title="t", region="제주", companions="커플", days=[DayPlan(day=1, date="2026-12-01", visits=visits)], validation=Validation(passed=9, total=10))


def test_fixed_weather_follows_day_order() -> None:
    """일차 순서대로 고정 날씨를 돌려주고, 날짜가 더 많으면 나머지는 비운다."""
    forecast = E.fixed_weather(("rain", "sunny"))
    out = forecast(["2026-12-01", "2026-12-02", "2026-12-03"], "제주")
    assert [out[d].condition for d in ("2026-12-01", "2026-12-02")] == ["rain", "sunny"]
    assert "2026-12-03" not in out


def test_pass_metrics_counts_travel_and_visits() -> None:
    """이동시간·거리와 방문 수를 하루 평균으로 계산한다."""
    ids = list(catalog.places())[:3]
    it = itinerary_with(ids)
    it.days[0].visits[1].travel_minutes_from_prev = 30
    it.days[0].visits[2].travel_minutes_from_prev = 20
    m = E.pass_metrics(it, ["문제"])
    assert (m["passed"], m["total"], m["n_visits"]) == (9, 10, 3)
    assert m["avg_travel_min"] == 50 and m["avg_travel_km"] > 0 and m["issues"] == ["문제"]


def test_summarize_compares_first_pass_with_final() -> None:
    """루프 없음은 첫 pass, 루프 적용은 마지막 pass로 집계하고 오류 기록은 제외한다."""
    rec = lambda issues_first, issues_last, f0, f1, regen: {  # noqa: E731
        "id": "x", "regen_count": regen, "response_sec": 30.0, "tokens": 1000,
        "passes": [
            {"issues": ["a"] * issues_first, "passed": 10 - issues_first, "total": 10, "avg_travel_min": 100.0, "avg_travel_km": 50.0, "n_visits": 10, "faithfulness": f0},
            *([{"issues": ["a"] * issues_last, "passed": 10 - issues_last, "total": 10, "avg_travel_min": 80.0, "avg_travel_km": 40.0, "n_visits": 10, "faithfulness": f1}] if regen else []),
        ],
    }
    records = [rec(4, 1, 0.5, 0.75, 2), rec(0, 0, 1.0, 1.0, 0), {"id": "bad", "error": "x"}]
    s = E.summarize(records)
    assert s["no_loop"]["n"] == s["loop"]["n"] == 2
    assert s["no_loop"]["violation_itinerary_rate"] == 0.5 and s["loop"]["violation_itinerary_rate"] == 0.5
    assert s["no_loop"]["avg_violations"] == 2.0 and s["loop"]["avg_violations"] == 0.5
    assert s["no_loop"]["violation_check_rate"] == 4 / 20 and s["loop"]["violation_check_rate"] == 1 / 20
    assert s["no_loop"]["faithfulness"] == 0.75 and s["loop"]["faithfulness"] == 0.875
    assert s["loop"]["avg_regen"] == 1.0 and s["no_loop"]["avg_travel_min"] == 100.0 and s["loop"]["avg_travel_min"] == 90.0
    # 루프 비용은 루프 쪽에만 기록하고, 시나리오별 개선/동일/악화를 센다
    assert s["no_loop"]["avg_response_sec"] is None and s["loop"]["avg_response_sec"] == 30.0
    assert (s["loop"]["n_improved"], s["loop"]["n_same"], s["loop"]["n_worse"]) == (1, 1, 0)


def test_judge_scores_supported_share_and_counts_missing_as_unsupported(fake_llm) -> None:
    """뒷받침된 방문 비율이 점수이고, 판정이 빠진 방문은 뒷받침되지 않은 것으로 센다."""
    ids = list(catalog.places())[:4]
    fake_llm[F.Verdicts] = lambda msgs: F.Verdicts(
        verdicts=[F.Verdict(place_id=ids[0], supported=True), F.Verdict(place_id=ids[1], supported=False, unsupported_claim="주차 가능"), F.Verdict(place_id=ids[2], supported=True)]
    )  # ids[3]은 판정 누락
    score, verdicts = F.judge_itinerary(itinerary_with(ids))
    assert score == 0.5 and [v.supported for v in verdicts] == [True, False, True, False]
    assert verdicts[3].unsupported_claim == "판정 누락"


def test_judge_prompt_contains_reason_and_evidence(fake_llm) -> None:
    """판정 프롬프트에는 추천 이유와 근거 후기 본문이 들어간다."""
    seen: dict = {}

    def handler(msgs: list) -> F.Verdicts:
        seen["user"] = msgs[1].content
        return F.Verdicts()

    fake_llm[F.Verdicts] = handler
    pid = next(iter(catalog.reviews_by_place()))
    F.judge_itinerary(itinerary_with([pid]))
    review_text = catalog.reviews_by_place()[pid][0].text
    assert "추천 이유: 이유 0" in seen["user"] and review_text[:10] in seen["user"]


def test_judge_empty_itinerary_returns_none(fake_llm) -> None:
    """방문이 없으면 점수를 만들지 않는다 (LLM도 부르지 않는다)."""
    it = itinerary_with([])
    assert F.judge_itinerary(it) == (None, [])


def test_run_scenario_records_each_validation_pass(fake_llm, fake_search) -> None:
    """시나리오를 실행하면 검증 pass별 기록과 첫/최종 Faithfulness가 남고, 날씨는 고정값이 쓰인다."""
    from agent.review_tools import ReviewAnalysis

    today = date(2026, 10, 18)
    start = (today + timedelta(days=E.START_OFFSET_DAYS)).isoformat()
    fake_llm[ParsedRequest] = lambda m: ParsedRequest(days=2, companions="커플", start_date=start)
    fake_llm[ReviewAnalysis] = lambda m: ReviewAnalysis(summaries=[])
    seen_user: list[str] = []

    def plan(msgs: list):
        seen_user.append(msgs[-1].content)
        return plan_from_prompt(msgs)

    from agent.planning import LLMPlan

    fake_llm[LLMPlan] = plan
    fake_llm[F.Verdicts] = lambda msgs: F.Verdicts(verdicts=[F.Verdict(place_id=pid, supported=True) for pid in {l.split("]")[0][1:] for l in msgs[1].content.splitlines() if l.startswith("[")}])

    rec = E.run_scenario(E.Scenario("t", "{date}부터 커플끼리 제주 2일", ("rain", "sunny")), today)
    assert rec["id"] == "t" and rec["regen_count"] == len(rec["passes"]) - 1
    assert 1 <= len(rec["passes"]) <= 3  # 첫 생성 + 재생성 최대 2회
    assert rec["passes"][0]["faithfulness"] == 1.0 and rec["passes"][-1]["faithfulness"] == 1.0
    assert "1일차 날씨: rain" in seen_user[0] and "2일차 날씨: sunny" in seen_user[0]
