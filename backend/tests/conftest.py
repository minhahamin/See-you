"""공용 테스트 도구: LLM·검색 호출을 가짜로 바꾸는 fixture와 일정 계획 생성 도우미."""
import re
from typing import Any, Callable

import pytest

from agent import catalog
from agent.planning import LLMDay, LLMPlan, LLMVisit

LLM_TARGETS = [
    "agent.nodes.parse_request.structured_call",
    "agent.review_tools.structured_call",
    "agent.planning.structured_call",
    "agent.nodes.apply_feedback.structured_call",
]
SEARCH_TARGETS = ["agent.nodes.search_places.hybrid_search", "agent.nodes.apply_feedback.hybrid_search"]


@pytest.fixture
def fake_llm(monkeypatch: pytest.MonkeyPatch) -> dict[type, Callable[[list], Any]]:
    """schema 클래스별 응답 함수를 등록하면 structured_call이 그 함수를 호출한다."""
    handlers: dict[type, Callable[[list], Any]] = {}

    def call(schema: type, messages: list, temperature: float = 0.0) -> Any:
        if schema not in handlers:
            raise AssertionError(f"등록되지 않은 LLM 호출: {schema.__name__}")
        return handlers[schema](messages)

    for target in LLM_TARGETS:
        monkeypatch.setattr(target, call)
    return handlers


@pytest.fixture
def fake_search(monkeypatch: pytest.MonkeyPatch) -> None:
    """임베딩 API 없이 쓰도록 hybrid_search를 분류 필터만 적용한 고정 순서 결과로 바꾼다."""

    def search(query: str, n: int = 30, filters: dict | None = None) -> list[dict]:
        category = (filters or {}).get("category")
        ids = sorted(p.id for p in catalog.places().values() if category in (None, p.category))
        return [{"id": f"place-{i}", "text": "", "meta": {"place_id": i}} for i in ids][:n]

    for target in SEARCH_TARGETS:
        monkeypatch.setattr(target, search)


def plan_from_prompt(messages: list) -> LLMPlan:
    """프롬프트에 담긴 후보 목록을 읽어 규칙에 맞는 일정 계획을 만든다 (테스트용 LLM 대역)."""
    user = messages[-1].content
    days = [int(d) for d in re.findall(r"(\d+)일차 날씨", user)]
    note = re.search(r"이미 쓰는 장소\((.*?)\)", messages[0].content)
    skip = {n.strip() for n in note.group(1).split(",")} if note else set()
    rows = []
    for line in user.splitlines():
        m = re.match(r"\[(\d+)\] (.*?) \| (\S+) \| .*후기id (.*)$", line)
        if m and m.group(2) not in skip:
            rows.append((m.group(1), m.group(3), [i.strip() for i in m.group(4).split(",") if i.strip() and i.strip() != "-"]))
    pools = {c: [r for r in rows if r[1] == c] for c in ("관광지", "음식점", "카페", "숙소")}

    def take(category: str) -> tuple[str, list[str]]:
        pid, _, ev = pools[category].pop(0)
        return pid, ev

    plan_days = []
    for i, day in enumerate(days):
        visits = []
        for slot, category in [("morning", "관광지"), ("lunch", "음식점"), ("afternoon", "관광지"), ("cafe", "카페")]:
            pid, ev = take(category)
            visits.append(LLMVisit(place_id=pid, slot=slot, reason="후기 근거 추천", evidence_review_ids=ev[:1]))
        if i < len(days) - 1:
            pid, ev = pools["숙소"][0][0], pools["숙소"][0][2]
            visits.append(LLMVisit(place_id=pid, slot="stay", reason="후기 근거 추천", evidence_review_ids=ev[:1]))
        plan_days.append(LLMDay(day=day, visits=visits))
    return LLMPlan(title="테스트 여행", days=plan_days)
