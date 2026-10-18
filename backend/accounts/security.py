"""비밀번호 해시와 로그인 토큰. 비밀번호 원문과 토큰 원문은 어디에도 저장하거나 기록하지 않는다."""
import hashlib
import secrets

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerifyMismatchError

_hasher = PasswordHasher()  # Argon2id, 라이브러리 기본 권장 파라미터
# 존재하지 않는 이메일로 로그인할 때도 같은 시간이 걸리도록 비교용 해시를 하나 만들어 둔다 (사용자 열거 방지)
_DUMMY_HASH = _hasher.hash("dummy-password-for-timing")


def hash_password(password: str) -> str:
    """비밀번호를 Argon2id로 해시한다."""
    return _hasher.hash(password)


def verify_password(password_hash: str | None, password: str) -> bool:
    """비밀번호를 검증한다. 해시가 없으면(없는 사용자) 비교용 해시로 같은 시간을 쓰고 False를 돌려준다."""
    try:
        _hasher.verify(password_hash or _DUMMY_HASH, password)
    except (VerifyMismatchError, InvalidHashError):
        return False
    return password_hash is not None


def needs_rehash(password_hash: str) -> bool:
    """해시 파라미터가 현재 권장값보다 약하면 True (로그인 성공 시 다시 저장한다)."""
    return _hasher.check_needs_rehash(password_hash)


def new_token() -> str:
    """추측할 수 없는 로그인 토큰 (256비트)."""
    return secrets.token_urlsafe(32)


def token_digest(token: str) -> str:
    """토큰의 sha256. DB에는 이 값만 저장한다."""
    return hashlib.sha256(token.encode("utf-8")).hexdigest()
