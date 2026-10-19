"""조건 추출 노드: 대화에서 여행 조건을 구조화하고 부족한 항목을 찾는다."""
import logging
from datetime import date

from langchain_core.messages import HumanMessage, SystemMessage
from pydantic import BaseModel, Field

from agent.prompts import PARSE_REQUEST_SYSTEM
from agent.state import REQUIRED_FIELDS, Area, Companion, PlannerState, TripRequest
from llm import structured_call

logger = logging.getLogger(__name__)

SUPPORTED_REGION = "제주"


class ParsedRequest(BaseModel):
    """LLM이 대화에서 뽑은 조건. 없는 값은 None."""

    region: str | None = None
    area: Area | None = None
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


def normalize_region(value: str | None) -> str | None:
    """'제주도'·'제주 여행' 같은 표기를 '제주'로 통일한다. 다른 지역은 그대로 둔다."""
    if not value:
        return None
    return "제주" if "제주" in value else value.strip()


def merge_request(old: TripRequest | None, new: ParsedRequest, today: date) -> TripRequest:
    """이전 조건에 새로 파싱된 값을 덮어쓴다. 취향은 합집합."""
    base = old or TripRequest()
    prefs = list(dict.fromkeys([*base.preferences, *new.preferences]))
    return TripRequest(
        region=normalize_region(new.region) or base.region,
        area=new.area or base.area,
        start_date=_valid_future_date(new.start_date, today) or _valid_future_date(base.start_date, today),
        days=new.days or base.days,
        companions=new.companions or base.companions,
        preferences=prefs,
        budget=new.budget or base.budget,
    )


def apply_profile(request: TripRequest, profile: dict | None) -> tuple[TripRequest, dict]:
    """저장된 설정을 기본 조건으로 채운다. 이미 정해진 값(말로 지정했거나 이전 대화에서 정한 값)은 덮어쓰지 않는다.

    돌려주는 dict는 이번에 설정에서 채운 항목이다 (사용자에게 '설정을 반영했다'고 알리는 데 쓴다).
    """
    if not profile:
        return request, {}
    updates: dict = {}
    applied: dict = {}
    if request.companions is None and profile.get("companion"):
        updates["companions"] = applied["companions"] = profile["companion"]
    if request.budget is None and profile.get("budget"):
        updates["budget"] = applied["budget"] = profile["budget"]
    new_prefs = [p for p in profile.get("preferences") or [] if p not in request.preferences]
    if new_prefs:
        updates["preferences"] = [*request.preferences, *new_prefs]
        applied["preferences"] = new_prefs
    return request.model_copy(update=updates), applied


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
    # 제주만 지원한다: 다른 지역을 말하면 한 번 알리고(되묻기), 그 뒤에는 제주로 만든다
    unsupported = request.region if request.region != SUPPORTED_REGION else None
    request = request.model_copy(update={"region": SUPPORTED_REGION})
    request, applied = apply_profile(request, state.get("profile"))
    missing = find_missing(request)
    notify = bool(unsupported) and not state.get("region_notified")
    if notify:
        missing = ["region", *missing]
    logger.info("조건 파싱 완료, 부족한 항목: %s, 설정에서 반영: %s", missing, list(applied))
    return {
        "request": request,
        "missing_fields": missing,
        "unsupported_region": unsupported,
        "region_notified": bool(unsupported) or bool(state.get("region_notified")),
        "applied_settings": {**state.get("applied_settings", {}), **applied},
    }
