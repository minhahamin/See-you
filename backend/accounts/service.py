"""계정·로그인·설정·대화 기록에 대한 DB 접근. 모두 동기 함수이며 호출하는 쪽이 세션(트랜잭션)을 관리한다."""
import uuid
from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import delete, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from accounts import security
from accounts.tables import ChatSession, LoginSession, User, UserSettings, utcnow

TITLE_MAX = 120


class EmailTaken(Exception):
    """이미 가입된 이메일."""


def normalize_email(email: str) -> str:
    """이메일을 비교·저장용으로 정규화한다 (앞뒤 공백 제거, 소문자)."""
    return email.strip().lower()


# ---- 계정 ----


def create_user(db: Session, email: str, password: str, display_name: str | None = None) -> User:
    """사용자를 만든다. 이미 있는 이메일이면 EmailTaken."""
    user = User(
        email=normalize_email(email),
        password_hash=security.hash_password(password),
        display_name=(display_name or "").strip() or None,
    )
    db.add(user)
    try:
        db.flush()
    except IntegrityError as exc:
        db.rollback()
        raise EmailTaken from exc
    return user


def authenticate(db: Session, email: str, password: str) -> User | None:
    """이메일·비밀번호가 맞으면 사용자, 아니면 None. 없는 이메일도 같은 시간이 걸린다."""
    user = db.scalar(select(User).where(User.email == normalize_email(email)))
    if not security.verify_password(user.password_hash if user else None, password) or user is None:
        return None
    if security.needs_rehash(user.password_hash):
        user.password_hash = security.hash_password(password)
    return user


def start_login(db: Session, user_id: uuid.UUID, ttl_days: int) -> str:
    """로그인 세션을 만들고 쿠키에 담을 토큰 원문을 돌려준다 (DB에는 해시만 저장)."""
    token = security.new_token()
    db.add(LoginSession(token_hash=security.token_digest(token), user_id=user_id, expires_at=utcnow() + timedelta(days=ttl_days)))
    db.flush()
    return token


def user_for_token(db: Session, token: str | None) -> User | None:
    """쿠키 토큰으로 로그인한 사용자를 찾는다. 만료됐으면 지우고 None."""
    if not token:
        return None
    row = db.get(LoginSession, security.token_digest(token))
    if row is None:
        return None
    if row.expires_at <= utcnow():
        db.delete(row)
        return None
    return db.get(User, row.user_id)


def end_login(db: Session, token: str | None) -> None:
    """이 토큰의 로그인 세션을 폐기한다 (로그아웃)."""
    if token:
        db.execute(delete(LoginSession).where(LoginSession.token_hash == security.token_digest(token)))


def delete_user(db: Session, user_id: uuid.UUID) -> list[str]:
    """계정과 모든 데이터를 지운다. 체크포인트를 따로 지울 수 있게 그 사용자의 대화 id를 돌려준다."""
    session_ids = list(db.scalars(select(ChatSession.id).where(ChatSession.user_id == user_id)))
    db.execute(delete(User).where(User.id == user_id))  # 로그인 세션·대화·설정은 FK cascade로 함께 지워진다
    return session_ids


# ---- 설정 ----


def settings_dict(row: UserSettings | None) -> dict[str, Any] | None:
    """설정 행을 API·에이전트가 쓰는 dict로. 없으면 None."""
    if row is None:
        return None
    return {"companion": row.companion, "preferences": list(row.preferences or []), "budget": row.budget}


def get_settings(db: Session, user_id: uuid.UUID) -> dict[str, Any] | None:
    """저장된 설정. 한 번도 저장하지 않았으면 None."""
    return settings_dict(db.get(UserSettings, user_id))


def put_settings(db: Session, user_id: uuid.UUID, companion: str | None, preferences: list[str], budget: int | None) -> dict[str, Any]:
    """설정을 저장(없으면 만들고 있으면 덮어쓴다)한다."""
    row = db.get(UserSettings, user_id)
    if row is None:
        row = UserSettings(user_id=user_id)
        db.add(row)
    row.companion, row.preferences, row.budget = companion, preferences, budget
    db.flush()
    return settings_dict(row)  # type: ignore[return-value]


# ---- 대화 기록 ----


def create_chat_session(db: Session, user_id: uuid.UUID | None) -> str:
    """대화 세션을 만든다. 로그인하지 않았으면 user_id는 None(게스트)."""
    sid = uuid.uuid4().hex
    db.add(ChatSession(id=sid, user_id=user_id))
    db.flush()
    return sid


def get_chat_session(db: Session, sid: str) -> ChatSession | None:
    """id로 대화 세션을 찾는다."""
    return db.get(ChatSession, sid)


def can_access(row: ChatSession, user_id: uuid.UUID | None) -> bool:
    """게스트 대화는 id를 아는 사람 누구나, 계정에 속한 대화는 그 소유자만 접근할 수 있다."""
    return row.user_id is None or row.user_id == user_id


def list_chat_sessions(db: Session, user_id: uuid.UUID) -> list[ChatSession]:
    """사용자의 대화 목록 (최근 수정 순)."""
    return list(db.scalars(select(ChatSession).where(ChatSession.user_id == user_id).order_by(ChatSession.updated_at.desc())))


def claim_chat_session(db: Session, sid: str, user_id: uuid.UUID) -> bool:
    """게스트 대화를 로그인한 계정으로 가져온다. 이미 내 것이면 True, 남의 것이면 False."""
    row = db.get(ChatSession, sid)
    if row is None:
        return False
    if row.user_id is None:
        row.user_id = user_id
        return True
    return row.user_id == user_id


def delete_chat_session(db: Session, sid: str) -> None:
    """대화 세션 행을 지운다 (체크포인트는 호출하는 쪽에서 따로 지운다)."""
    db.execute(delete(ChatSession).where(ChatSession.id == sid))


def update_chat_meta(db: Session, sid: str, title: str | None = None, trip_days: int | None = None, companions: str | None = None) -> None:
    """목록에 보여 줄 요약을 갱신하고 최근 수정 시각을 올린다. None인 값은 건드리지 않는다."""
    row = db.get(ChatSession, sid)
    if row is None:
        return
    if title:
        row.title = title.strip()[:TITLE_MAX]
    if trip_days is not None:
        row.trip_days = trip_days
    if companions:
        row.companions = companions
    row.updated_at = utcnow()


def purge_old_guest_sessions(db: Session, older_than_days: int, now: datetime | None = None) -> list[str]:
    """오래 방치된 게스트 대화를 지우고 그 id를 돌려준다 (체크포인트 정리용)."""
    cutoff = (now or utcnow()) - timedelta(days=older_than_days)
    ids = list(db.scalars(select(ChatSession.id).where(ChatSession.user_id.is_(None), ChatSession.updated_at < cutoff)))
    if ids:
        db.execute(delete(ChatSession).where(ChatSession.id.in_(ids)))
    return ids
