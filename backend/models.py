"""장소·특성·후기 데이터 모델 (data/*.json 스키마)."""
from typing import Literal

from pydantic import BaseModel, Field

Category = Literal["관광지", "음식점", "카페", "숙소"]
AuthorType = Literal["가족", "커플", "혼자", "친구"]


class Place(BaseModel):
    """TourAPI에서 가공한 장소 정보 (places.json)."""

    id: str
    name: str
    category: Category
    address: str
    lat: float
    lng: float
    description: str = ""
    opening_hours: str | None = None
    image_url: str | None = None  # TourAPI 대표 이미지 (프론트 썸네일용)


class PlaceTraits(BaseModel):
    """장소별 숨은 특성. 후기 생성과 평가 정답의 기준 (place_traits.json)."""

    place_id: str
    pros: list[str]
    cons: list[str]
    good_for: list[AuthorType]
    not_good_for: list[str]
    busy_times: list[str]
    price_level: int = Field(ge=1, le=3)
    indoor: bool


class GeneratedTraits(BaseModel):
    """LLM이 생성하는 특성 (place_id는 코드에서 부여, 구조화 출력용)."""

    pros: list[str]
    cons: list[str]
    good_for: list[AuthorType]
    not_good_for: list[str]
    busy_times: list[str]
    price_level: int = Field(ge=1, le=3)
    indoor: bool


class Review(BaseModel):
    """특성 기반 합성 후기 (reviews.json). 실제 리뷰가 아니다."""

    review_id: str
    place_id: str
    text: str
    rating: int = Field(ge=1, le=5)
    author_type: AuthorType
    season: Literal["봄", "여름", "가을", "겨울"]
    visit_time: str
    created_at: str


class GeneratedReview(BaseModel):
    """LLM이 생성하는 후기 본문 (id·날짜는 코드에서 부여)."""

    text: str
    rating: int = Field(ge=1, le=5)
    author_type: AuthorType
    season: Literal["봄", "여름", "가을", "겨울"]
    visit_time: str


class GeneratedReviews(BaseModel):
    """장소 하나에 대한 후기 묶음 (구조화 출력용)."""

    reviews: list[GeneratedReview]
