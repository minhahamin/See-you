"""API 요청/응답 Pydantic 모델. 프론트 src/types/index.ts와 같은 구조로 유지한다 (한쪽을 바꾸면 같이 수정)."""
from typing import Literal

from pydantic import BaseModel, EmailStr, Field, field_validator

from agent import catalog
from agent.state import Itinerary, TripRequest

# 백엔드 분류명 → 프론트 Category 키
CATEGORY_KEY = {"관광지": "sight", "음식점": "food", "카페": "cafe", "숙소": "stay"}
REVIEW_DISCLAIMER = "후기는 합성 데이터입니다."


class PlaceOut(BaseModel):
    """프론트 Place."""

    id: str
    name: str
    category: Literal["sight", "food", "cafe", "stay", "activity"]
    address: str
    lat: float
    lng: float
    description: str
    thumbnail_url: str | None = None
    indoor: bool
    tags: list[str] = Field(default_factory=list)
    checklist: list[str] = Field(default_factory=list)


class ReviewOut(BaseModel):
    """프론트 Review."""

    review_id: str
    place_id: str
    text: str
    rating: int
    author_type: Literal["가족", "커플", "혼자", "친구"]
    season: str
    visit_time: str


class PlaceDetail(BaseModel):
    """GET /api/places/{id} 응답: 장소 + 후기."""

    place: PlaceOut
    reviews: list[ReviewOut]
    disclaimer: str = REVIEW_DISCLAIMER


class SessionCreated(BaseModel):
    """POST /api/sessions 응답."""

    session_id: str


Companion = Literal["혼자", "커플", "친구", "가족"]
MAX_PREFERENCES = 10
MAX_PREFERENCE_LEN = 30


class SettingsModel(BaseModel):
    """사용자 설정 (프론트 UserSettings). 에이전트가 일정을 맞춤으로 만들 때 기본 조건으로 쓴다."""

    companion: Companion | None = None
    preferences: list[str] = Field(default_factory=list, max_length=MAX_PREFERENCES)
    budget: int | None = Field(default=None, ge=1, le=3)

    @field_validator("preferences")
    @classmethod
    def clean_preferences(cls, values: list[str]) -> list[str]:
        """공백을 정리하고 빈 값·중복을 없앤다. 항목은 짧아야 한다."""
        cleaned = list(dict.fromkeys(v.strip() for v in values if v.strip()))
        if any(len(v) > MAX_PREFERENCE_LEN for v in cleaned):
            raise ValueError(f"취향은 {MAX_PREFERENCE_LEN}자 이하여야 합니다.")
        return cleaned


class MessageIn(BaseModel):
    """POST /api/sessions/{id}/messages 요청. 로그인하지 않은 사용자는 브라우저에 저장된 설정을 settings로 보낸다."""

    text: str = Field(min_length=1, max_length=2000)
    settings: SettingsModel | None = None


# ---- SSE 이벤트 payload ----


class StepEvent(BaseModel):
    """`step`: 노드 시작/완료. 프론트 AgentStep에 대응한다."""

    node: str
    label: str
    status: Literal["running", "done"]
    duration_ms: int | None = None
    tokens: int | None = None


class QuestionEvent(BaseModel):
    """`question`: 부족한 조건 되묻기."""

    question: str
    missing_fields: list[str]


class AppliedSettings(BaseModel):
    """이번 일정에 설정에서 가져와 반영한 항목 (사용자가 말로 직접 지정한 것은 제외)."""

    companions: str | None = None
    budget: int | None = None
    preferences: list[str] = Field(default_factory=list)


class ItineraryEvent(BaseModel):
    """`itinerary`: 일정 결과. places는 일정에 등장하는 장소의 프론트 Place 목록."""

    itinerary: Itinerary
    places: list[PlaceOut]
    issues: list[str]
    applied_settings: AppliedSettings = Field(default_factory=AppliedSettings)


class ErrorEvent(BaseModel):
    """`error`."""

    message: str


class ChatMessageOut(BaseModel):
    """프론트 ChatMessage."""

    id: str
    role: Literal["user", "assistant"]
    text: str


class SessionSummary(BaseModel):
    """GET /api/sessions/{id}: 현재 상태 요약."""

    session_id: str
    messages: list[ChatMessageOut]
    request: TripRequest | None = None
    itinerary: Itinerary | None = None
    places: list[PlaceOut] = Field(default_factory=list)
    awaiting: Literal["question", "feedback"] | None = None


# ---- 계정·기록 ----


class SignupIn(BaseModel):
    """회원가입 요청."""

    email: EmailStr
    password: str = Field(min_length=8, max_length=128)
    display_name: str | None = Field(default=None, max_length=40)


class LoginIn(BaseModel):
    """로그인 요청."""

    email: EmailStr
    password: str = Field(min_length=1, max_length=128)


class DeleteAccountIn(BaseModel):
    """계정 삭제 확인용 비밀번호."""

    password: str = Field(min_length=1, max_length=128)


class UserOut(BaseModel):
    """로그인한 사용자 정보. 비밀번호 해시는 절대 내보내지 않는다."""

    id: str
    email: str
    display_name: str | None = None


class MeOut(BaseModel):
    """GET /api/auth/me 응답. 로그인하지 않았으면 user가 null이다 (오류가 아니다)."""

    user: UserOut | None = None


class SessionListItem(BaseModel):
    """'내 일정' 목록의 한 줄."""

    session_id: str
    title: str | None = None
    trip_days: int | None = None
    companions: str | None = None
    created_at: str
    updated_at: str


# ---- 성능 지표 (프론트 MetricsSnapshot 구성 요소). null = 데이터 없음 ----


class ExperimentResult(BaseModel):
    """버전별 평가 결과 한 줄."""

    version: str
    description: str
    recall_at_5: float | None = None
    mrr: float | None = None
    faithfulness: float | None = None
    violation_rate: float | None = None


class ExperimentsResponse(BaseModel):
    """GET /api/metrics/experiments."""

    experiments: list[ExperimentResult]
    source: str | None = None


class NodeMetric(BaseModel):
    """노드별 평균 지연·토큰."""

    node: str
    avg_latency_ms: float | None = None
    avg_tokens: float | None = None


class RecentRun(BaseModel):
    """최근 요청 한 건. 단가가 설정되지 않으면 cost_usd는 null."""

    run_id: str
    response_sec: float
    cost_usd: float | None = None


class FailureReason(BaseModel):
    """검증 실패 사유와 횟수."""

    reason: str
    count: int


class RunMetrics(BaseModel):
    """요청 단위 집계."""

    avg_response_sec: float | None = None
    avg_cost_usd: float | None = None
    recent: list[RecentRun] = Field(default_factory=list)
    regen_rate: float | None = None
    top_failures: list[FailureReason] = Field(default_factory=list)


class RunsResponse(BaseModel):
    """GET /api/metrics/runs."""

    nodes: list[NodeMetric]
    runs: RunMetrics | None = None
    source: str | None = None


def place_out(place_id: str) -> PlaceOut:
    """장소 id로 프론트용 Place를 만든다. 태그와 체크리스트는 숨은 특성에서 규칙으로 만든다."""
    place, trait = catalog.places()[place_id], catalog.traits()[place_id]
    return PlaceOut(
        id=place.id,
        name=place.name,
        category=CATEGORY_KEY[place.category],
        address=place.address,
        lat=place.lat,
        lng=place.lng,
        description=place.description,
        thumbnail_url=place.image_url,
        indoor=trait.indoor,
        tags=["실내" if trait.indoor else "야외", *[f"{g} 추천" for g in trait.good_for]],
        checklist=list(trait.cons[:3]),
    )


def review_out(review) -> ReviewOut:  # noqa: ANN001
    """Review 모델을 프론트 Review로 바꾼다."""
    return ReviewOut(**review.model_dump(exclude={"created_at"}))
