"""후기 요약 공용 함수. analyze_reviews 노드와 apply_feedback 노드가 함께 쓴다."""
from langchain_core.messages import HumanMessage, SystemMessage
from pydantic import BaseModel, Field

from agent import catalog
from agent.prompts import ANALYZE_REVIEWS_SYSTEM
from agent.state import Candidate, ReviewSummary
from llm import structured_call
from models import Review

REVIEWS_PER_PLACE = 5
TEXT_LIMIT = 120
MIN_KEEP_PER_DAY = {"관광지": 2, "음식점": 1, "카페": 1}  # 제외하더라도 하루당 최소 확보할 수
MIN_KEEP_STAY = 1


class ReviewAnalysis(BaseModel):
    """LLM 출력: 후보 장소별 요약."""

    summaries: list[ReviewSummary] = Field(default_factory=list)


def sample_reviews(place_id: str) -> list[Review]:
    """요약에 쓸 후기를 고른다: 평점 낮은 것·중간·높은 것을 섞어 최대 5개."""
    reviews = sorted(catalog.reviews_by_place().get(place_id, []), key=lambda r: r.rating)
    if len(reviews) <= REVIEWS_PER_PLACE:
        return reviews
    picks = [reviews[0], reviews[1], reviews[len(reviews) // 2], reviews[-2], reviews[-1]]
    return list({r.review_id: r for r in picks}.values())  # 같은 후기가 겹치면 하나만


def render_candidate(c: Candidate) -> str:
    """후보 한 곳을 프롬프트용 텍스트로 만든다."""
    t = catalog.traits()[c.id]
    lines = [
        f"[{c.id}] {c.name} ({c.category}) | 장점 {', '.join(t.pros)} | 단점 {', '.join(t.cons)} "
        f"| 추천 {', '.join(t.good_for)} | 비추천 {', '.join(t.not_good_for)}"
    ]
    for r in sample_reviews(c.id):
        lines.append(f"  - ({r.review_id}, {r.author_type}, {r.rating}점) {r.text[:TEXT_LIMIT]}")
    return "\n".join(lines)


def fallback_summary(c: Candidate) -> ReviewSummary:
    """LLM이 빠뜨린 장소는 특성과 대표 후기 id로 요약을 대신한다."""
    t = catalog.traits()[c.id]
    ids = catalog.positive_first(c.id, [r.review_id for r in sample_reviews(c.id)])[:1]
    return ReviewSummary(place_id=c.id, pros=t.pros[:3], cons=t.cons[:3], evidence_review_ids=ids)


def clean_summary(s: ReviewSummary) -> ReviewSummary:
    """존재하지 않거나 다른 장소의 후기 id를 제거하고, 근거는 별점 높은 후기를 앞세운다."""
    valid = catalog.review_ids(s.place_id)
    ids = catalog.positive_first(s.place_id, [i for i in s.evidence_review_ids if i in valid])
    return s.model_copy(update={"evidence_review_ids": ids})


def summarize(candidates: list[Candidate], companions: str) -> dict[str, ReviewSummary]:
    """후보 전체를 한 번의 LLM 호출로 요약한다. 빠진 장소는 특성 기반 요약으로 채운다."""
    user = "\n".join(render_candidate(c) for c in candidates)
    result = structured_call(
        ReviewAnalysis,
        [SystemMessage(ANALYZE_REVIEWS_SYSTEM.format(companions=companions)), HumanMessage(user)],
    )
    ids = {c.id for c in candidates}
    by_id = {s.place_id: clean_summary(s) for s in result.summaries if s.place_id in ids}
    for c in candidates:
        by_id.setdefault(c.id, fallback_summary(c))
    return by_id


def apply_exclusions(
    candidates: list[Candidate], summaries: dict[str, ReviewSummary], days: int
) -> list[Candidate]:
    """부적합 장소를 제외하되, 분류별 최소 개수가 모자라면 순위 높은 순으로 되살린다."""
    kept: list[Candidate] = []
    for category in dict.fromkeys(c.category for c in candidates):
        group = sorted((c for c in candidates if c.category == category), key=lambda c: c.rank)
        ok = [c for c in group if summaries[c.id].suitable]
        minimum = MIN_KEEP_STAY if category == "숙소" else MIN_KEEP_PER_DAY[category] * days
        for c in group:
            if len(ok) >= min(minimum, len(group)):
                break
            if c not in ok:
                ok.append(c)
        kept.extend(ok)
    return kept
