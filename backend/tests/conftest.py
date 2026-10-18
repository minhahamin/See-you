"""공용 테스트 도구: LLM·검색 호출을 가짜로 바꾸는 fixture와 일정 계획 생성 도우미."""
import re
from typing import Any, Callable

import pytest

from agent import catalog
from agent.nodes.parse_request import ParsedRequest
from agent.planning import LLMDay, LLMPlan, LLMVisit
from agent.review_tools import ReviewAnalysis

LLM_TARGETS = [
    "agent.nodes.parse_request.structured_call",
    "agent.review_tools.structured_call",
    "agent.planning.structured_call",
    "agent.nodes.apply_feedback.structured_call",
    "eval.faithfulness.structured_call",
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


@pytest.fixture
def wired(fake_llm, fake_search):
    """그래프 전체를 도는 데 필요한 LLM 대역을 등록한다."""
    calls = {"build": 0, "parse": 0}

    def parse(msgs: list) -> ParsedRequest:
        calls["parse"] += 1
        text = msgs[-1].content
        return ParsedRequest(
            days=2 if "2박" in text else None,
            companions="커플" if "커플" in text else None,
            start_date="2099-11-14" if "11월" in text else None,
        )

    def build(msgs: list) -> LLMPlan:
        calls["build"] += 1
        return plan_from_prompt(msgs)

    fake_llm[ParsedRequest] = parse
    fake_llm[ReviewAnalysis] = lambda m: ReviewAnalysis(summaries=[])
    fake_llm[LLMPlan] = build
    return calls


@pytest.fixture(autouse=True)
def no_real_weather_calls(monkeypatch: pytest.MonkeyPatch) -> None:
    """테스트가 기상청 API를 실제로 호출하지 않게 막는다. 날씨 테스트는 이 fixture를 덮어써서 쓴다."""
    from tools.weather import WeatherUnavailable

    def blocked(*args: Any, **kwargs: Any) -> Any:
        raise WeatherUnavailable("테스트에서는 외부 호출을 하지 않습니다")

    monkeypatch.setattr("tools.weather._fetch_items", blocked)


@pytest.fixture(autouse=True)
def no_real_llm_calls(monkeypatch: pytest.MonkeyPatch) -> None:
    """테스트가 실제 LLM을 호출하지 못하게 막는다. 가짜(fake_llm)를 등록하지 않은 호출은 여기서 실패한다."""

    def blocked(*args: Any, **kwargs: Any) -> Any:
        raise AssertionError("테스트에서 실제 LLM을 호출했습니다. fake_llm으로 대체하세요.")

    monkeypatch.setattr("llm.get_chat_model", blocked)



@pytest.fixture(scope="session")
def pg_url(tmp_path_factory: pytest.TempPathFactory):
    """테스트 전체에서 쓰는 실제 PostgreSQL (pgserver 내장). 세션이 끝나면 멈춘다."""
    import pgserver

    server = pgserver.get_server(tmp_path_factory.mktemp("pgdata"), cleanup_mode="stop")
    yield server.get_uri()
    server.cleanup()


@pytest.fixture
def db_url(pg_url: str) -> str:
    """테스트마다 계정·대화 테이블을 비운 DB 주소."""
    from sqlalchemy import text

    from accounts.db import init_db, make_engine

    engine = make_engine(pg_url)
    init_db(engine)
    with engine.begin() as conn:
        conn.execute(text("TRUNCATE users, login_sessions, chat_sessions, user_settings CASCADE"))
    engine.dispose()
    return pg_url
