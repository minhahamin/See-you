"""장소 특성 기반 합성 후기를 생성해 data/reviews.json을 만든다. (실제 리뷰 아님)"""
import json
import logging
import random
import time
from datetime import date, timedelta

from langchain_core.messages import HumanMessage, SystemMessage

from agent.prompts import REVIEWS_SYSTEM, REVIEWS_USER
from config import get_settings, setup_logging
from ingest.generate_traits import load_places
from llm import get_chat_model, is_daily_quota_error
from models import GeneratedReviews, Place, PlaceTraits, Review

logger = logging.getLogger(__name__)

MIN_REVIEWS, MAX_REVIEWS = 10, 20
MAX_ATTEMPTS = 4
BACKOFF_SEC = 15


def load_traits() -> dict[str, PlaceTraits]:
    """data/place_traits.json을 place_id 기준 딕셔너리로 읽는다."""
    path = get_settings().data_dir / "place_traits.json"
    return {t["place_id"]: PlaceTraits(**t) for t in json.loads(path.read_text(encoding="utf-8"))}


def generate_reviews_for(place: Place, traits: PlaceTraits, count: int) -> list[Review]:
    """장소 하나의 후기를 생성하고 id·작성일을 부여한다. 개수가 어긋나면 재시도한다."""
    llm = get_chat_model(temperature=0.9).with_structured_output(GeneratedReviews)
    messages = [
        SystemMessage(REVIEWS_SYSTEM.format(count=count)),
        HumanMessage(
            REVIEWS_USER.format(
                name=place.name,
                category=place.category,
                description=place.description,
                pros=", ".join(traits.pros),
                cons=", ".join(traits.cons),
                good_for=", ".join(traits.good_for),
                not_good_for=", ".join(traits.not_good_for),
                busy_times=", ".join(traits.busy_times),
                price_level=traits.price_level,
                indoor="실내" if traits.indoor else "야외",
            )
        ),
    ]
    for attempt in range(1, MAX_ATTEMPTS + 1):
        try:
            generated: GeneratedReviews = llm.invoke(messages)
            if not MIN_REVIEWS <= len(generated.reviews) <= MAX_REVIEWS:
                raise ValueError(f"후기 개수 {len(generated.reviews)}")
            break
        except Exception as exc:
            logger.warning("%s 생성 실패(%d/%d): %s", place.name, attempt, MAX_ATTEMPTS, type(exc).__name__)
            if attempt == MAX_ATTEMPTS or is_daily_quota_error(exc):
                raise
            time.sleep(BACKOFF_SEC * attempt)

    today = date.today()
    return [
        Review(
            review_id=f"{place.id}-{i + 1:02d}",
            place_id=place.id,
            created_at=(today - timedelta(days=random.randint(0, 730))).isoformat(),
            **g.model_dump(),
        )
        for i, g in enumerate(generated.reviews)
    ]


def main(limit: int | None = None) -> None:
    """후기를 생성해 저장한다. 이미 후기가 있는 장소는 건너뛴다."""
    setup_logging()
    settings = get_settings()
    out = settings.data_dir / "reviews.json"
    reviews: list[Review] = []
    if out.exists():
        reviews = [Review(**r) for r in json.loads(out.read_text(encoding="utf-8"))]
    done_ids = {r.place_id for r in reviews}

    traits = load_traits()
    places = [p for p in load_places() if p.id in traits][:limit]
    rng = random.Random(0)
    for place in places:
        if place.id in done_ids:
            continue
        reviews += generate_reviews_for(place, traits[place.id], rng.randint(MIN_REVIEWS, MAX_REVIEWS))
        out.write_text(
            json.dumps([r.model_dump() for r in reviews], ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        logger.info("%s 후기 저장 (누적 %d개)", place.name, len(reviews))


if __name__ == "__main__":
    main()
