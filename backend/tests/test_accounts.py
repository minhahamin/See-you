"""계정(가입·로그인·로그아웃·삭제), 로그인 보안, 대화 소유권·기록, 설정, 맞춤화, 영속성 테스트. 실제 PostgreSQL을 쓴다."""
import asyncio
import uuid
from datetime import timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from accounts import security, service
from accounts.db import make_engine, make_session_factory
from accounts.ratelimit import AttemptLimiter
from accounts.tables import ChatSession, LoginSession, User, UserSettings, utcnow
from agent.graph import build_graph, make_checkpointer
from agent.nodes.parse_request import ParsedRequest, apply_profile, parse_request
from agent.state import TripRequest
from api.main import create_app
from api.metrics import MetricsStore
from config import get_settings
from tests.test_api import parse_sse

PASSWORD = "correct-horse-battery"


@pytest.fixture
def app(wired, tmp_path, db_url):
    """가짜 LLM·검색 + 실제 Postgres로 만든 앱."""
    cfg = get_settings().model_copy(update={"cookie_secure": False})
    return create_app(graph=build_graph(make_checkpointer()), store=MetricsStore(tmp_path / "r.jsonl"), database_url=db_url, settings=cfg)


@pytest.fixture
def client(app):
    """첫 번째 사용자(브라우저)."""
    with TestClient(app) as c:
        yield c


@pytest.fixture
def other(app, client):
    """같은 앱에 붙은 두 번째 브라우저 (쿠키 보관함이 따로다). client가 서버를 시작해 둔 뒤에 쓴다."""
    return TestClient(app)


@pytest.fixture
def db(db_url):
    """검증용 직접 DB 세션."""
    engine = make_engine(db_url)
    factory = make_session_factory(engine)
    session = factory()
    yield session
    session.close()
    engine.dispose()


def signup(c: TestClient, email: str = "Me@Example.com", password: str = PASSWORD, **extra):
    return c.post("/api/auth/signup", json={"email": email, "password": password, **extra})


def chat(c: TestClient, text_: str = "11월에 커플로 2박 3일", **extra) -> list[tuple[str, dict]]:
    """세션을 만들고 메시지를 보내 SSE 이벤트를 받는다. (session_id, events)"""
    sid = c.post("/api/sessions").json()["session_id"]
    r = c.post(f"/api/sessions/{sid}/messages", json={"text": text_, **extra})
    assert r.status_code == 200
    return sid, parse_sse(r.text)  # type: ignore[return-value]


# ---- 보안 부품 ----


def test_password_hash_is_argon2_and_verifies() -> None:
    """비밀번호는 Argon2id 해시로만 저장되고, 틀린 비밀번호·없는 사용자는 False다."""
    h = security.hash_password(PASSWORD)
    assert h.startswith("$argon2id$") and PASSWORD not in h
    assert security.verify_password(h, PASSWORD) is True
    assert security.verify_password(h, "wrong-password") is False
    assert security.verify_password(None, PASSWORD) is False  # 없는 사용자도 같은 비교를 거친 뒤 False


def test_token_digest_is_stable_and_not_the_token() -> None:
    """토큰은 매번 다르고, 저장용 해시는 같은 입력에 같으며 원문과 다르다."""
    a, b = security.new_token(), security.new_token()
    assert a != b and len(a) >= 40
    assert security.token_digest(a) == security.token_digest(a) != a


def test_limiter_blocks_after_limit_and_expires() -> None:
    """한도를 넘으면 막고, 시간이 지나면 풀리며, reset하면 비운다."""
    now = [0.0]
    lim = AttemptLimiter(3, 60, clock=lambda: now[0])
    for _ in range(3):
        assert lim.retry_after("k") == 0
        lim.hit("k")
    assert 0 < lim.retry_after("k") <= 61
    now[0] = 61
    assert lim.retry_after("k") == 0
    lim.hit("k"); lim.hit("k"); lim.hit("k")
    lim.reset("k")
    assert lim.retry_after("k") == 0


# ---- 가입·로그인·로그아웃 ----


def test_signup_sets_cookie_and_stores_only_hashes(client, db) -> None:
    """가입하면 로그인되고, 쿠키는 httpOnly이며, DB에는 해시만 저장된다."""
    r = signup(client, display_name="민하")
    assert r.status_code == 201 and r.json()["email"] == "me@example.com" and r.json()["display_name"] == "민하"
    assert "password" not in r.text
    cookie = r.headers["set-cookie"].lower()
    assert "seeyou_session=" in cookie and "httponly" in cookie and "samesite=lax" in cookie and "secure" not in cookie
    assert client.get("/api/auth/me").json()["user"]["email"] == "me@example.com"

    user = db.query(User).one()
    assert user.password_hash.startswith("$argon2id$") and PASSWORD not in user.password_hash
    token = client.cookies.get("seeyou_session")
    stored = db.query(LoginSession).one()
    assert token not in stored.token_hash and stored.token_hash == security.token_digest(token)


def test_secure_cookie_flag_follows_setting(wired, tmp_path, db_url) -> None:
    """운영(https)에서는 COOKIE_SECURE로 Secure 속성이 붙는다."""
    cfg = get_settings().model_copy(update={"cookie_secure": True})
    app = create_app(graph=build_graph(make_checkpointer()), store=MetricsStore(tmp_path / "r.jsonl"), database_url=db_url, settings=cfg)
    with TestClient(app) as c:
        assert "secure" in signup(c).headers["set-cookie"].lower()


def test_signup_validation_and_duplicates(client) -> None:
    """약한 비밀번호·잘못된 이메일은 422, 같은 이메일(대소문자 무관)은 409."""
    assert signup(client, password="short").status_code == 422
    assert signup(client, email="not-an-email").status_code == 422
    assert signup(client, email="a@example.com").status_code == 201
    assert signup(client, email="A@EXAMPLE.COM").status_code == 409


def test_login_logout_flow_and_generic_error(client, other) -> None:
    """로그인은 성공/실패가 구분되지만 실패 이유(이메일 없음·비밀번호 틀림)는 같은 문구다. 로그아웃하면 토큰이 폐기된다."""
    signup(client)
    old_token = client.cookies.get("seeyou_session")
    assert client.post("/api/auth/logout").status_code == 204
    assert client.get("/api/auth/me").json() == {"user": None}

    wrong = other.post("/api/auth/login", json={"email": "me@example.com", "password": "wrong-password"})
    unknown = other.post("/api/auth/login", json={"email": "nobody@example.com", "password": PASSWORD})
    assert wrong.status_code == unknown.status_code == 401 and wrong.json() == unknown.json()

    ok = other.post("/api/auth/login", json={"email": " ME@example.com ", "password": PASSWORD})
    assert ok.status_code == 200 and other.get("/api/auth/me").json()["user"]["email"] == "me@example.com"

    # 로그아웃으로 폐기된 예전 토큰은 다시 써도 인증되지 않는다
    client.cookies.set("seeyou_session", old_token)
    assert client.get("/api/auth/me").json() == {"user": None}


def test_login_is_rate_limited_per_email(app, client) -> None:
    """같은 이메일로 틀린 시도가 한도를 넘으면 429(Retry-After)이고, 맞는 비밀번호도 잠시 막힌다."""
    signup(client)
    client.post("/api/auth/logout")
    app.state.limiters.login = AttemptLimiter(3, 600)
    for _ in range(3):
        assert client.post("/api/auth/login", json={"email": "me@example.com", "password": "bad-password"}).status_code == 401
    blocked = client.post("/api/auth/login", json={"email": "me@example.com", "password": PASSWORD})
    assert blocked.status_code == 429 and int(blocked.headers["retry-after"]) > 0


def test_expired_login_is_rejected(client, db) -> None:
    """만료된 로그인 세션은 인증되지 않는다."""
    signup(client)
    row = db.query(LoginSession).one()
    row.expires_at = utcnow() - timedelta(minutes=1)
    db.commit()
    assert client.get("/api/auth/me").json() == {"user": None}


def test_cross_origin_writes_are_rejected(client) -> None:
    """다른 출처에서 온 상태 변경 요청은 403, 같은 출처나 Origin이 없는 요청은 통과한다."""
    body = {"email": "csrf@example.com", "password": PASSWORD}
    assert client.post("/api/auth/signup", json=body, headers={"Origin": "https://evil.example"}).status_code == 403
    assert client.post("/api/auth/signup", json=body, headers={"Origin": "http://testserver"}).status_code == 201
    assert client.post("/api/auth/login", json=body).status_code == 200  # Origin 헤더 없음 (서버 간 호출 등)


# ---- 대화 소유권·기록 ----


def test_guest_flow_still_works_and_is_not_listed(client) -> None:
    """로그인하지 않아도 대화할 수 있고, 게스트 대화는 '내 일정' 목록이 없다(401)."""
    sid, events = chat(client)
    assert any(e == "itinerary" for e, _ in events)
    assert client.get(f"/api/sessions/{sid}").status_code == 200
    assert client.get("/api/sessions").status_code == 401


def test_account_sessions_are_private_and_listed(client, other, db) -> None:
    """내 대화는 나만 열 수 있고(남에게는 404), 목록에는 일정 제목과 일수가 보인다."""
    signup(client)
    sid, events = chat(client)
    title = dict(events)["itinerary"]["itinerary"]["title"]

    items = client.get("/api/sessions").json()
    assert [i["session_id"] for i in items] == [sid]
    assert items[0]["title"] == title and items[0]["trip_days"] == 2

    assert other.get(f"/api/sessions/{sid}").status_code == 404  # 게스트도
    signup(other, email="b@example.com")
    assert other.get(f"/api/sessions/{sid}").status_code == 404  # 다른 계정도
    assert other.get("/api/sessions").json() == []
    assert other.post(f"/api/sessions/{sid}/messages", json={"text": "hi"}).status_code == 404
    assert other.delete(f"/api/sessions/{sid}").status_code == 404
    assert client.get(f"/api/sessions/{sid}").status_code == 200


def test_empty_sessions_are_hidden_and_delete_removes_state(client, db) -> None:
    """메시지를 보내지 않은 빈 세션은 목록에 안 나오고, 삭제하면 행과 대화 상태가 사라진다."""
    signup(client)
    client.post("/api/sessions")  # 빈 세션
    sid, _ = chat(client)
    assert [i["session_id"] for i in client.get("/api/sessions").json()] == [sid]
    assert client.delete(f"/api/sessions/{sid}").status_code == 204
    assert client.get("/api/sessions").json() == []
    assert client.get(f"/api/sessions/{sid}").status_code == 404
    assert db.query(ChatSession).filter_by(id=sid).count() == 0


def test_claim_moves_guest_session_into_account(client, other) -> None:
    """게스트로 하던 대화를 로그인 후 가져오면 목록에 나타나고, 남의 대화는 가져올 수 없다."""
    sid, _ = chat(client)
    signup(client)
    assert client.post(f"/api/sessions/{sid}/claim").status_code == 204
    assert [i["session_id"] for i in client.get("/api/sessions").json()] == [sid]

    signup(other, email="b@example.com")
    assert other.post(f"/api/sessions/{sid}/claim").status_code == 404  # 이미 다른 계정의 것
    assert other.post("/api/sessions/" + uuid.uuid4().hex + "/claim").status_code == 404


def test_purge_old_guest_sessions_keeps_account_sessions(db) -> None:
    """오래된 게스트 대화만 지우고, 계정에 속한 대화와 최근 게스트 대화는 남긴다."""
    user = service.create_user(db, "p@example.com", PASSWORD)
    old_guest, new_guest, mine = (service.create_chat_session(db, None), service.create_chat_session(db, None), service.create_chat_session(db, user.id))
    db.get(ChatSession, old_guest).updated_at = utcnow() - timedelta(days=30)
    db.get(ChatSession, mine).updated_at = utcnow() - timedelta(days=30)
    db.commit()
    assert service.purge_old_guest_sessions(db, older_than_days=14) == [old_guest]
    db.commit()
    assert {r.id for r in db.query(ChatSession)} == {new_guest, mine}


# ---- 설정 ----


def test_settings_require_login_validate_and_persist(client, other) -> None:
    """설정은 로그인해야 쓸 수 있고, 값 검증을 거쳐 계정별로 저장된다."""
    assert client.get("/api/settings").status_code == 401
    signup(client)
    assert client.get("/api/settings").json() == {"companion": None, "preferences": [], "budget": None}

    bad = [{"companion": "혼자서", "preferences": [], "budget": 2}, {"companion": "가족", "preferences": [], "budget": 5}, {"preferences": ["a"] * 11}, {"preferences": ["x" * 31]}]
    assert all(client.put("/api/settings", json=b).status_code == 422 for b in bad)

    saved = client.put("/api/settings", json={"companion": "가족", "preferences": [" 실내 ", "조용한 곳", "실내"], "budget": 3}).json()
    assert saved == {"companion": "가족", "preferences": ["실내", "조용한 곳"], "budget": 3}
    assert client.get("/api/settings").json() == saved

    signup(other, email="b@example.com")
    assert other.get("/api/settings").json()["companion"] is None  # 계정별로 분리


# ---- 맞춤 일정 ----


def test_apply_profile_fills_only_missing_values() -> None:
    """설정은 비어 있는 값만 채우고, 말로 지정한 값은 덮어쓰지 않는다. 취향은 합친다."""
    profile = {"companion": "가족", "preferences": ["실내", "조용한 곳"], "budget": 3}
    req, applied = apply_profile(TripRequest(preferences=["실내"]), profile)
    assert (req.companions, req.budget, req.preferences) == ("가족", 3, ["실내", "조용한 곳"])
    assert applied == {"companions": "가족", "budget": 3, "preferences": ["조용한 곳"]}

    req, applied = apply_profile(TripRequest(companions="커플", budget=1), profile)
    assert (req.companions, req.budget) == ("커플", 1) and "companions" not in applied and "budget" not in applied
    assert apply_profile(TripRequest(), None) == (TripRequest(), {})


def test_profile_removes_clarification_question(fake_llm) -> None:
    """설정에 동행이 있으면 동행을 다시 묻지 않는다."""
    from langchain_core.messages import HumanMessage

    fake_llm[ParsedRequest] = lambda m: ParsedRequest(days=2, start_date=(__import__("datetime").date.today() + timedelta(days=30)).isoformat())
    base = {"messages": [HumanMessage("제주 2박 3일")]}
    assert parse_request(base)["missing_fields"] == ["companions"]
    out = parse_request({**base, "profile": {"companion": "가족", "preferences": ["실내"], "budget": 2}})
    assert out["missing_fields"] == [] and out["request"].companions == "가족" and out["applied_settings"]["preferences"] == ["실내"]


def test_logged_in_settings_personalize_the_itinerary_event(client) -> None:
    """저장된 설정이 일정 요청에 반영되고, 어떤 항목을 반영했는지 이벤트로 알려 준다."""
    signup(client)
    client.put("/api/settings", json={"companion": "가족", "preferences": ["실내"], "budget": 2})
    sid, events = chat(client, "11월에 2박 3일 제주")  # 메시지에는 동행·예산이 없다
    payload = dict(events)["itinerary"]
    assert payload["applied_settings"] == {"companions": "가족", "budget": 2, "preferences": ["실내"]}
    assert payload["itinerary"]["companions"] == "가족"
    assert not any(e == "question" for e, _ in events)  # 동행을 다시 묻지 않는다


def test_guest_settings_in_request_body_are_used(client) -> None:
    """로그인하지 않은 사용자는 브라우저에 저장된 설정을 요청에 실어 보내 같은 맞춤화를 받는다."""
    _, events = chat(client, "11월에 2박 3일 제주", settings={"companion": "커플", "preferences": ["바다"], "budget": 3})
    assert dict(events)["itinerary"]["applied_settings"]["companions"] == "커플"


def test_logged_in_user_ignores_body_settings(client) -> None:
    """로그인했으면 서버에 저장된 설정이 기준이고, 요청에 실린 값은 무시한다."""
    signup(client)
    client.put("/api/settings", json={"companion": "가족", "preferences": [], "budget": None})
    _, events = chat(client, "11월에 2박 3일 제주", settings={"companion": "혼자", "preferences": [], "budget": 1})
    assert dict(events)["itinerary"]["applied_settings"]["companions"] == "가족"


# ---- 계정 삭제 ----


def test_delete_account_removes_everything(client, other, db) -> None:
    """비밀번호를 확인하고 계정을 지우면 대화·설정·로그인 세션이 모두 사라지고, 다른 사용자의 데이터는 남는다."""
    signup(client)
    client.put("/api/settings", json={"companion": "가족", "preferences": [], "budget": 1})
    sid, _ = chat(client)
    signup(other, email="b@example.com")
    other_sid, _ = chat(other)

    assert client.post("/api/auth/delete-account", json={"password": "wrong-password"}).status_code == 403
    assert client.post("/api/auth/delete-account", json={"password": PASSWORD}).status_code == 204

    assert client.get("/api/auth/me").json() == {"user": None}
    assert client.post("/api/auth/login", json={"email": "me@example.com", "password": PASSWORD}).status_code == 401
    assert db.query(User).filter_by(email="me@example.com").count() == 0
    assert db.query(UserSettings).count() == 0 and db.query(ChatSession).filter_by(id=sid).count() == 0
    assert db.query(LoginSession).count() == 1  # b의 것만 남는다
    assert other.get(f"/api/sessions/{other_sid}").status_code == 200


# ---- 영속성 (실제 Postgres 체크포인터) ----


def test_conversation_survives_a_server_restart(db_url, wired) -> None:
    """Postgres 체크포인터에 저장된 대화는 서버(앱 인스턴스)를 새로 띄운 뒤에도 그대로 복원된다."""
    from agent.checkpoint import open_postgres_checkpointer
    from api.sessions import SessionManager

    async def run() -> tuple[str, str]:
        factory = make_session_factory(make_engine(db_url))
        async with open_postgres_checkpointer(db_url) as saver:
            first = SessionManager(build_graph(saver), MetricsStore(), factory)
            sid = await first.create(None)
            events = [e async for e in first.stream_turn(sid, "11월에 커플로 2박 3일")]
            assert any(e["event"] == "itinerary" for e in events)
        # 앱을 닫았다가(= 재시작) 새로 연다
        async with open_postgres_checkpointer(db_url) as saver:
            second = SessionManager(build_graph(saver), MetricsStore(), factory)
            assert await second.accessible(sid, None)
            summary = await second.summary(sid)
            assert summary.itinerary is not None and summary.awaiting == "feedback" and summary.messages
            await second.delete(sid)  # 체크포인트까지 지워진다
            assert (await second.summary(sid)).itinerary is None
        return sid, summary.itinerary.title

    sid, title = asyncio.run(run())
    assert title
    with make_engine(db_url).connect() as conn:  # 대화 상태 테이블도 비워졌다
        assert conn.execute(text("select count(*) from checkpoints where thread_id = :t"), {"t": sid}).scalar() == 0
