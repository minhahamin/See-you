"""장소별 숨은 특성을 LLM으로 생성해 data/place_traits.json을 만든다."""
import json
import logging
import time

from langchain_core.messages import HumanMessage, SystemMessage

from agent.prompts import TRAITS_SYSTEM, TRAITS_USER
from config import get_settings, setup_logging
from llm import get_chat_model
from models import GeneratedTraits, Place, PlaceTraits

logger = logging.getLogger(__name__)

MAX_ATTEMPTS = 4
BACKOFF_SEC = 15


def load_places() -> list[Place]:
    """data/places.json을 읽어 Place 목록으로 반환한다."""
    path = get_settings().data_dir / "places.json"
    return [Place(**p) for p in json.loads(path.read_text(encoding="utf-8"))]


def generate_traits_for(place: Place) -> PlaceTraits:
    """장소 하나의 특성을 생성한다. 호출 실패 시 백오프 후 재시도한다."""
    llm = get_chat_model(temperature=0.7).with_structured_output(GeneratedTraits)
    messages = [
        SystemMessage(TRAITS_SYSTEM),
        HumanMessage(
            TRAITS_USER.format(
                name=place.name,
                category=place.category,
                address=place.address,
                description=place.description,
                opening_hours=place.opening_hours or "정보 없음",
            )
        ),
    ]
    for attempt in range(1, MAX_ATTEMPTS + 1):
        try:
            generated: GeneratedTraits = llm.invoke(messages)
            return PlaceTraits(place_id=place.id, **generated.model_dump())
        except Exception as exc:
            logger.warning("%s 생성 실패(%d/%d): %s", place.name, attempt, MAX_ATTEMPTS, type(exc).__name__)
            if attempt == MAX_ATTEMPTS:
                raise
            time.sleep(BACKOFF_SEC * attempt)
    raise RuntimeError("unreachable")


def main(limit: int | None = None) -> None:
    """모든 장소의 특성을 생성한다. 이미 있는 장소는 건너뛰어 이어서 실행할 수 있다."""
    setup_logging()
    out = get_settings().data_dir / "place_traits.json"
    done: dict[str, PlaceTraits] = {}
    if out.exists():
        done = {t["place_id"]: PlaceTraits(**t) for t in json.loads(out.read_text(encoding="utf-8"))}

    places = load_places()[:limit]
    for place in places:
        if place.id in done:
            continue
        done[place.id] = generate_traits_for(place)
        out.write_text(
            json.dumps([t.model_dump() for t in done.values()], ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        logger.info("[%d/%d] %s 저장", len(done), len(places), place.name)


if __name__ == "__main__":
    main()
