"""Faithfulness(추천 이유의 근거 충실도)를 LLM으로 판정한다. RAGAS를 쓰지 않는 자체 구현이다.

각 방문의 추천 이유를 (장소 소개 + 특성 + 근거 후기)와 대조해 뒷받침되는지 판정하고,
Faithfulness = 뒷받침된 방문 수 / 전체 방문 수 로 계산한다. 일정 1건당 LLM 호출 1회.
한계: 생성에 쓴 모델과 같은 모델이 판정하므로 자기 평가 편향이 있을 수 있다.
"""
import logging

from langchain_core.messages import HumanMessage, SystemMessage
from pydantic import BaseModel, Field

from agent import catalog
from agent.prompts import FAITHFULNESS_JUDGE_SYSTEM
from agent.state import Itinerary
from llm import structured_call

logger = logging.getLogger(__name__)


class Verdict(BaseModel):
    """방문 하나에 대한 판정."""

    place_id: str
    supported: bool
    unsupported_claim: str | None = None


class Verdicts(BaseModel):
    """LLM 출력: 방문별 판정."""

    verdicts: list[Verdict] = Field(default_factory=list)


def render_visit(itinerary: Itinerary) -> tuple[str, list[str]]:
    """판정용 프롬프트 본문과 방문 place_id 목록(순서대로)을 만든다."""
    places, traits = catalog.places(), catalog.traits()
    reviews = {r.review_id: r for rs in catalog.reviews_by_place().values() for r in rs}
    blocks: list[str] = []
    order: list[str] = []
    for day in itinerary.days:
        for v in day.visits:
            p, t = places[v.place_id], traits[v.place_id]
            evidence = "\n".join(f"    - {reviews[i].text}" for i in v.evidence_review_ids if i in reviews) or "    (없음)"
            blocks.append(
                f"[{v.place_id}] {p.name}\n"
                f"  추천 이유: {v.reason}\n"
                f"  장소 소개: {p.description[:300]}\n"
                f"  특성: 장점 {', '.join(t.pros)} / 단점 {', '.join(t.cons)} / 실내 {t.indoor} / 가격대 {t.price_level}\n"
                f"  근거 후기:\n{evidence}"
            )
            order.append(v.place_id)
    return "\n\n".join(blocks), order


def judge_itinerary(itinerary: Itinerary) -> tuple[float | None, list[Verdict]]:
    """일정의 Faithfulness를 계산한다. 방문이 없으면 (None, [])."""
    body, order = render_visit(itinerary)
    if not order:
        return None, []
    result = structured_call(Verdicts, [SystemMessage(FAITHFULNESS_JUDGE_SYSTEM), HumanMessage(body)])
    by_id = {v.place_id: v for v in result.verdicts}
    # 판정이 빠진 방문은 '뒷받침되지 않음'으로 센다 (낙관적으로 부풀리지 않는다)
    verdicts = [by_id.get(pid, Verdict(place_id=pid, supported=False, unsupported_claim="판정 누락")) for pid in order]
    score = sum(v.supported for v in verdicts) / len(verdicts)
    return score, verdicts
