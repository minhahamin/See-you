"""analyze_reviews 단위 테스트."""
from agent import catalog
from agent.nodes.analyze_reviews import analyze_reviews
from agent.planning import to_candidate
from agent.review_tools import ReviewAnalysis, apply_exclusions, clean_summary, fallback_summary
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


def _place_with_mixed_ratings() -> tuple[str, str, str]:
    """4점 이상 후기와 2점 이하 후기가 모두 있는 장소의 (id, 좋은 후기 id, 나쁜 후기 id)."""
    for pid, reviews in catalog.reviews_by_place().items():
        good = next((r for r in reviews if r.rating >= 4), None)
        bad = next((r for r in reviews if r.rating <= 2), None)
        if good and bad:
            return pid, good.review_id, bad.review_id
    raise AssertionError("별점이 섞인 장소가 없다")


def test_clean_summary_puts_positive_reviews_first() -> None:
    """근거 후기는 별점 높은 것만 남긴다 (낮은 별점 후기가 추천 근거로 나오지 않게)."""
    pid, good, bad = _place_with_mixed_ratings()
    s = clean_summary(ReviewSummary(place_id=pid, evidence_review_ids=[bad, good]))
    assert s.evidence_review_ids == [good]


def test_fallback_summary_uses_best_review() -> None:
    """LLM이 빠뜨려 대체 요약을 쓸 때도 가장 낮은 별점 후기를 근거로 고르지 않는다."""
    pid, _, _ = _place_with_mixed_ratings()
    fallback = fallback_summary(to_candidate(pid, 0))
    ratings = {r.review_id: r.rating for r in catalog.reviews_by_place()[pid]}
    assert ratings[fallback.evidence_review_ids[0]] >= 4
