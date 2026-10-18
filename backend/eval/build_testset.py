"""place_traits.json으로 질문-정답 쌍(평가셋)을 규칙 기반으로 만든다. LLM을 쓰지 않는다."""
import json
import logging
from typing import Any

from config import get_settings, setup_logging
from models import Place, PlaceTraits

logger = logging.getLogger(__name__)

MIN_RELEVANT, MAX_RELEVANT = 2, 12  # 정답이 너무 적거나 많은 질문은 지표가 왜곡되어 제외
COMPANION_PHRASE = {"가족": "가족과", "커플": "연인과", "친구": "친구들과", "혼자": "혼자서"}
CATEGORY_PHRASE = {"관광지": "가기 좋은 관광지", "음식점": "가기 좋은 음식점", "카페": "가기 좋은 카페", "숙소": "묵기 좋은 숙소"}


def load_pairs() -> list[tuple[Place, PlaceTraits]]:
    """장소와 특성을 짝지어 읽는다."""
    d = get_settings().data_dir
    places = [Place(**p) for p in json.loads((d / "places.json").read_text(encoding="utf-8"))]
    traits = {t["place_id"]: PlaceTraits(**t) for t in json.loads((d / "place_traits.json").read_text(encoding="utf-8"))}
    return [(p, traits[p.id]) for p in places]


def make_question(
    qid: str, qtype: str, text: str, pairs: list[tuple[Place, PlaceTraits]], cond: Any, filters: dict[str, Any]
) -> dict[str, Any] | None:
    """조건에 맞는 장소를 정답으로 하는 질문을 만든다. 정답 수가 범위를 벗어나면 None."""
    relevant = [p.id for p, t in pairs if cond(p, t)]
    if not MIN_RELEVANT <= len(relevant) <= MAX_RELEVANT:
        return None
    return {"id": qid, "type": qtype, "question": text, "relevant_place_ids": relevant, "filters": filters}


def build_testset() -> list[dict[str, Any]]:
    """특성 조합별 질문 목록을 만든다."""
    pairs = load_pairs()
    out: list[dict[str, Any] | None] = []

    for comp, comp_phrase in COMPANION_PHRASE.items():
        for cat, cat_phrase in CATEGORY_PHRASE.items():  # 동행 + 분류
            out.append(make_question(
                f"companion-{comp}-{cat}", "companion_category", f"{comp_phrase} {cat_phrase}", pairs,
                lambda p, t, c=comp, k=cat: p.category == k and c in t.good_for,
                {"author_type": comp, "category": cat},
            ))
        out.append(make_question(  # 동행 + 실내
            f"companion-{comp}-indoor", "companion_indoor", f"{comp_phrase} 가기 좋은 실내 장소", pairs,
            lambda p, t, c=comp: c in t.good_for and t.indoor, {"author_type": comp, "indoor": True},
        ))

    for cat in ("관광지", "카페"):  # 실내/야외 + 분류
        out.append(make_question(
            f"indoor-{cat}", "indoor_category", f"비 오는 날 가기 좋은 실내 {cat}", pairs,
            lambda p, t, k=cat: p.category == k and t.indoor, {"category": cat, "indoor": True},
        ))
        out.append(make_question(
            f"outdoor-{cat}", "outdoor_category", f"야외에서 즐기기 좋은 {cat}", pairs,
            lambda p, t, k=cat: p.category == k and not t.indoor, {"category": cat, "indoor": False},
        ))

    for cat in CATEGORY_PHRASE:  # 가격대 + 분류
        out.append(make_question(
            f"cheap-{cat}", "price", f"가격 부담 없는 {cat}", pairs,
            lambda p, t, k=cat: p.category == k and t.price_level == 1, {"category": cat},
        ))
        out.append(make_question(
            f"pricey-{cat}", "price", f"가격대가 높은 고급스러운 {cat}", pairs,
            lambda p, t, k=cat: p.category == k and t.price_level == 3, {"category": cat},
        ))

    return [q for q in out if q]


def main() -> None:
    """평가셋을 eval/testset.json에 저장한다."""
    setup_logging()
    testset = build_testset()
    path = get_settings().eval_results_dir.parent / "testset.json"
    path.write_text(json.dumps(testset, ensure_ascii=False, indent=2), encoding="utf-8")
    sizes = sorted(len(q["relevant_place_ids"]) for q in testset)
    logger.info("질문 %d개 저장: %s (정답 수 %d~%d)", len(testset), path, sizes[0], sizes[-1])
    for q in testset:
        logger.info("%-28s %-26s 정답 %d", q["id"], q["question"], len(q["relevant_place_ids"]))


if __name__ == "__main__":
    main()
