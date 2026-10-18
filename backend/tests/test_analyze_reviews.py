"""analyze_reviews 단위 테스트."""
from agent import catalog
from agent.nodes.analyze_reviews import analyze_reviews
from agent.planning import to_candidate
from agent.review_tools import ReviewAnalysis, apply_exclusions, clean_summary
from agent.state import ReviewSummary, TripRequest


def _sights(n: int):
    ids = sorted(p.id for p in catalog.places().values() if p.category == "관광지")[:n]
    return [to_candidate(pid, i) for i, pid in enumerate(ids)]


def test_clean_summary_drops_invalid_review_ids() -> None:
    """존재하지 않거나 다른 장소의 후기 id는 근거에서 제거한다."""
    pid = _sights(1)[0].id
    real = sorted(catalog.review_ids(pid))[0]
    s = clean_summary(ReviewSummary(place_id=pid, evidence_review_ids=[real, "nope-01"]))
    assert s.evidence_review_ids == [real]


def test_node_excludes_unsuitable_and_fills_missing(fake_llm) -> None:
    """부적합 장소는 제외되고, LLM이 빠뜨린 장소는 특성 기반 요약으로 채워진다."""
    cands = _sights(6)
    bad, skipped = cands[0], cands[1]
    fake_llm[ReviewAnalysis] = lambda msgs: ReviewAnalysis(
        summaries=[
            ReviewSummary(place_id=c.id, pros=["좋음"], suitable=(c.id != bad.id), exclude_reason="가족과 맞지 않음")
            for c in cands
            if c.id != skipped.id
        ]
    )
    out = analyze_reviews({"request": TripRequest(days=1, companions="가족"), "candidates": cands})
    kept_ids = {c.id for c in out["candidates"]}
    assert bad.id not in kept_ids and skipped.id in kept_ids
    assert out["review_summaries"][skipped.id].evidence_review_ids  # 대체 요약에도 근거 후기 id가 있다


def test_exclusion_keeps_minimum_per_category() -> None:
    """제외로 최소 개수가 모자라면 순위 높은 순으로 되살린다."""
    cands = _sights(3)
    summaries = {c.id: ReviewSummary(place_id=c.id, suitable=False) for c in cands}
    kept = apply_exclusions(cands, summaries, days=1)  # 하루 최소 관광지 2곳
    assert len(kept) == 2
    assert [c.rank for c in kept] == [0, 1]
