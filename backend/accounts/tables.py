"""계정·로그인 세션·대화 기록·설정 테이블."""
import uuid
from datetime import datetime, timezone

from sqlalchemy import DateTime, ForeignKey, Integer, SmallInteger, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from accounts.db import Base


def utcnow() -> datetime:
    """타임존이 있는 현재 시각(UTC)."""
    return datetime.now(timezone.utc)


class User(Base):
    """가입한 사용자. 비밀번호 원문은 저장하지 않고 Argon2id 해시만 둔다."""

    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    email: Mapped[str] = mapped_column(String(254), unique=True, index=True)  # 소문자로 정규화해 저장
    password_hash: Mapped[str] = mapped_column(Text)
    display_name: Mapped[str | None] = mapped_column(String(40), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class LoginSession(Base):
    """로그인 상태. 쿠키의 토큰은 해시(sha256)만 저장해서, DB가 유출돼도 토큰을 재사용할 수 없다."""

    __tablename__ = "login_sessions"

    token_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class ChatSession(Base):
    """대화 세션. user_id가 없으면 로그인하지 않은(게스트) 대화다. id는 LangGraph thread_id와 같다."""

    __tablename__ = "chat_sessions"

    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=True, index=True
    )
    title: Mapped[str | None] = mapped_column(String(120), nullable=True)
    trip_days: Mapped[int | None] = mapped_column(Integer, nullable=True)
    companions: Mapped[str | None] = mapped_column(String(10), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)


class UserSettings(Base):
    """사용자 설정: 에이전트가 일정을 맞춤으로 만들 때 쓰는 기본 조건."""

    __tablename__ = "user_settings"

    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    companion: Mapped[str | None] = mapped_column(String(10), nullable=True)
    preferences: Mapped[list[str]] = mapped_column(JSONB, default=list)
    budget: Mapped[int | None] = mapped_column(SmallInteger, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)
