"""조건 추출 노드: 대화에서 여행 조건을 구조화하고 부족한 항목을 찾는다."""
import logging
from datetime import date

from langchain_core.messages import HumanMessage, SystemMessage
from pydantic import BaseModel, Field

from agent.prompts import PARSE_REQUEST_SYSTEM
from agent.state import REQUIRED_FIELDS, Companion, PlannerState, TripRequest
from llm import structured_call

logger = logging.getLogger(__name__)


class ParsedRequest(BaseModel):
    """LLM이 대화에서 뽑은 조건. 없는 값은 None."""

    region: str | None = None
    start_date: str | None = None
    days: int | None = Field(default=None, ge=1, le=7)
    companions: Companion | None = None
    preferences: list[str] = Field(default_factory=list)
    budget: int | None = Field(default=None, ge=1, le=3)


def _valid_future_date(value: str | None, today: date) -> str | None:
    """YYYY-MM-DD 형식이고 오늘 이후인 날짜만 인정한다."""
    if not value:
        return None
    try:
        parsed = date.fromisoformat(value)
    except ValueError:
        return None
    return value if parsed >= today else None


def merge_request(old: TripRequest | None, new: ParsedRequest, today: date) -> TripRequest:
    """이전 조건에 새로 파싱된 값을 덮어쓴다. 취향은 합집합."""
    base = old or TripRequest()
    prefs = list(dict.fromkeys([*base.preferences, *new.preferences]))
    return TripRequest(
        region=new.region or base.region,
        start_date=_valid_future_date(new.start_date, today) or _valid_future_date(base.start_date, today),
        days=new.days or base.days,
        companions=new.companions or base.companions,
        preferences=prefs,
        budget=new.budget or base.budget,
    )


def find_missing(request: TripRequest) -> list[str]:
    """필수 조건 중 비어 있는 항목."""
    return [f for f in REQUIRED_FIELDS if getattr(request, f) in (None, "")]


def parse_request(state: PlannerState) -> dict:
    """사용자 발화 전체를 읽어 TripRequest를 갱신하고 missing_fields를 계산한다."""
    today = date.today()
    user_text = "\n".join(m.content for m in state.get("messages", []) if m.type == "human")
    parsed = structured_call(
        ParsedRequest,
        [SystemMessage(PARSE_REQUEST_SYSTEM.format(today=today.isoformat())), HumanMessage(user_text)],
    )
    request = merge_request(state.get("request"), parsed, today)
    missing = find_missing(request)
    logger.info("조건 파싱 완료, 부족한 항목: %s", missing)
    return {"request": request, "missing_fields": missing}
