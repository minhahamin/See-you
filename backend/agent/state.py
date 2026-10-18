"""PlannerState와 노드 사이에서 주고받는 데이터 모델.

일정 모델(Visit, DayPlan, Itinerary)은 프론트 src/types/index.ts와 같은 구조로 유지한다.
"""
from typing import Annotated, Literal, TypedDict

from langgraph.graph.message import add_messages
from pydantic import BaseModel, Field

from models import Place

Companion = Literal["혼자", "커플", "친구", "가족"]
Slot = Literal["morning", "lunch", "afternoon", "cafe", "dinner", "stay"]
WeatherCondition = Literal["sunny", "cloudy", "rain"]

REQUIRED_FIELDS = ("start_date", "days", "companions")  # 이 값이 없으면 되묻는다


class TripRequest(BaseModel):
    """사용자 대화에서 파싱한 여행 조건."""

    region: str = "제주"
    start_date: str | None = None  # YYYY-MM-DD
    days: int | None = Field(default=None, ge=1, le=7)
    companions: Companion | None = None
    preferences: list[str] = Field(default_factory=list)
    budget: int | None = Field(default=None, ge=1, le=3)  # 1 저렴 ~ 3 여유


class Candidate(Place):
    """검색으로 찾은 후보 장소 (장소 정보 + 숨은 특성 일부)."""

    indoor: bool = False
    price_level: int = 2
    good_for: list[str] = Field(default_factory=list)
    not_good_for: list[str] = Field(default_factory=list)
    rank: int = 0  # 같은 분류 안의 검색 순위 (0이 가장 관련도 높음)


class ReviewSummary(BaseModel):
    """후보 장소의 후기 요약. 근거가 되는 후기 id를 함께 가진다."""

    place_id: str
    pros: list[str] = Field(default_factory=list)
    cons: list[str] = Field(default_factory=list)
    evidence_review_ids: list[str] = Field(default_factory=list)
    suitable: bool = True
    exclude_reason: str | None = None


class Weather(BaseModel):
    """하루 날씨."""

    condition: WeatherCondition
    temp_max: float
    temp_min: float


class Visit(BaseModel):
    """하루 일정 속 장소 방문 한 건."""

    place_id: str
    start: str  # HH:MM
    end: str  # HH:MM
    travel_minutes_from_prev: int = 0  # 하루 첫 방문은 0
    reason: str
    evidence_review_ids: list[str] = Field(default_factory=list)
    changed: bool = False  # 피드백으로 바뀐 블록
    slot: Slot | None = None  # 하루 중 역할 (일정 재배치용)


class DayPlan(BaseModel):
    """하루 일정."""

    day: int
    date: str  # YYYY-MM-DD
    weather: Weather | None = None  # 날씨 도구가 연동되기 전에는 None
    visits: list[Visit] = Field(default_factory=list)


class Validation(BaseModel):
    """검증 통과 항목 수 / 전체 항목 수."""

    passed: int = 0
    total: int = 0


class Itinerary(BaseModel):
    """여행 일정 전체."""

    title: str
    region: str
    companions: str
    days: list[DayPlan]
    validation: Validation = Field(default_factory=Validation)


class PlannerState(TypedDict, total=False):
    """LangGraph 상태. 노드는 이 값으로만 서로 데이터를 주고받는다."""

    messages: Annotated[list, add_messages]  # 대화 기록
    request: TripRequest | None  # 파싱된 조건
    missing_fields: list[str]  # 부족한 조건
    candidates: list[Candidate]  # 검색된 후보 장소
    review_summaries: dict[str, ReviewSummary]  # place_id → 후기 요약
    weather: dict[str, Weather]  # 날짜 → 날씨
    itinerary: Itinerary | None  # 일자별 일정
    validation_issues: list[str]
    feedback: str | None
    retry_count: int
    rerun_search: bool  # 피드백이 전체 재검색을 요구하는지
    accepted: bool  # 사용자가 일정을 확정했는지
    profile: dict | None  # 저장된 사용자 설정 {companion, preferences, budget}. 맞춤 일정의 기본 조건
    applied_settings: dict  # 설정에서 가져와 반영한 항목 {companions, budget, preferences}
