"""회원가입·로그인·로그아웃·계정 삭제와 설정 API, 그리고 요청에서 현재 사용자를 찾는 의존성."""
import logging
from typing import Iterator

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from sqlalchemy.orm import Session

from accounts import service
from accounts.db import session_scope
from accounts.ratelimit import AttemptLimiter
from accounts.tables import User
from api.schemas import DeleteAccountIn, LoginIn, MeOut, SettingsModel, SignupIn, UserOut

logger = logging.getLogger(__name__)

COOKIE_NAME = "seeyou_session"
LOGIN_FAIL_LIMIT, LOGIN_WINDOW_SEC = 10, 15 * 60  # 이메일당 15분에 10번까지
SIGNUP_LIMIT, SIGNUP_WINDOW_SEC = 20, 60 * 60  # 같은 IP에서 한 시간에 20번까지 (프록시 뒤라 보조 수단)
GENERIC_LOGIN_ERROR = "이메일 또는 비밀번호가 올바르지 않아요."

router = APIRouter(prefix="/api")


class Limiters:
    """로그인·가입 시도 제한기. 앱마다 하나씩 만들어 app.state에 둔다."""

    def __init__(self) -> None:
        """기본 한도로 두 제한기를 만든다."""
        self.login = AttemptLimiter(LOGIN_FAIL_LIMIT, LOGIN_WINDOW_SEC)
        self.signup = AttemptLimiter(SIGNUP_LIMIT, SIGNUP_WINDOW_SEC)


def get_db(request: Request) -> Iterator[Session]:
    """요청 단위 DB 세션 (정상 종료 시 커밋, 예외 시 롤백)."""
    yield from session_scope(request.app.state.db_factory)


def current_user(request: Request, db: Session = Depends(get_db)) -> User | None:
    """쿠키의 토큰으로 로그인한 사용자를 찾는다. 로그인하지 않았으면 None."""
    return service.user_for_token(db, request.cookies.get(COOKIE_NAME))


def require_user(user: User | None = Depends(current_user)) -> User:
    """로그인이 필요한 엔드포인트용. 아니면 401."""
    if user is None:
        raise HTTPException(401, "로그인이 필요해요.")
    return user


def client_ip(request: Request) -> str:
    """클라이언트 IP. 프록시 뒤에서는 X-Forwarded-For의 첫 값을 쓴다 (위조 가능하므로 보조 수단으로만 쓴다)."""
    forwarded = request.headers.get("x-forwarded-for", "")
    return forwarded.split(",")[0].strip() or (request.client.host if request.client else "unknown")


def user_out(user: User) -> UserOut:
    """응답용 사용자 정보."""
    return UserOut(id=str(user.id), email=user.email, display_name=user.display_name)


def _set_cookie(request: Request, response: Response, token: str) -> None:
    settings = request.app.state.settings
    response.set_cookie(
        COOKIE_NAME,
        token,
        max_age=settings.login_ttl_days * 86400,
        httponly=True,  # 자바스크립트가 읽지 못하게 해서 XSS로 토큰이 새는 것을 막는다
        samesite="lax",
        secure=settings.cookie_secure,
        path="/",
    )


def _retry_after(seconds: int) -> HTTPException:
    return HTTPException(429, f"시도가 너무 많아요. {seconds}초 뒤에 다시 해 주세요.", headers={"Retry-After": str(seconds)})


@router.post("/auth/signup", response_model=UserOut, status_code=201)
def signup(body: SignupIn, request: Request, response: Response, db: Session = Depends(get_db)) -> UserOut:
    """이메일·비밀번호로 가입하고 바로 로그인한다."""
    limiters: Limiters = request.app.state.limiters
    ip = client_ip(request)
    wait = limiters.signup.retry_after(ip)
    if wait:
        raise _retry_after(wait)
    limiters.signup.hit(ip)
    try:
        user = service.create_user(db, body.email, body.password, body.display_name)
    except service.EmailTaken:
        raise HTTPException(409, "이미 가입된 이메일이에요.") from None
    _set_cookie(request, response, service.start_login(db, user.id, request.app.state.settings.login_ttl_days))
    return user_out(user)


@router.post("/auth/login", response_model=UserOut)
def login(body: LoginIn, request: Request, response: Response, db: Session = Depends(get_db)) -> UserOut:
    """로그인한다. 이메일이 없든 비밀번호가 틀리든 같은 오류를 돌려준다 (가입 여부 노출 방지)."""
    limiters: Limiters = request.app.state.limiters
    key = service.normalize_email(body.email)
    wait = limiters.login.retry_after(key)
    if wait:
        raise _retry_after(wait)
    user = service.authenticate(db, body.email, body.password)
    if user is None:
        limiters.login.hit(key)
        raise HTTPException(401, GENERIC_LOGIN_ERROR)
    limiters.login.reset(key)
    _set_cookie(request, response, service.start_login(db, user.id, request.app.state.settings.login_ttl_days))
    return user_out(user)


@router.post("/auth/logout", status_code=204)
def logout(request: Request, response: Response, db: Session = Depends(get_db)) -> Response:
    """로그인 세션을 폐기하고 쿠키를 지운다. 로그인 상태가 아니어도 오류가 아니다."""
    service.end_login(db, request.cookies.get(COOKIE_NAME))
    response.delete_cookie(COOKIE_NAME, path="/")
    response.status_code = 204
    return response


@router.get("/auth/me", response_model=MeOut)
def me(user: User | None = Depends(current_user)) -> MeOut:
    """현재 로그인한 사용자. 게스트면 user가 null."""
    return MeOut(user=user_out(user) if user else None)


@router.post("/auth/delete-account", status_code=204)
async def delete_account(
    body: DeleteAccountIn, request: Request, response: Response, user: User = Depends(require_user), db: Session = Depends(get_db)
) -> Response:
    """비밀번호를 한 번 더 확인하고 계정과 모든 데이터(대화·설정·로그인 세션)를 지운다."""
    if service.authenticate(db, user.email, body.password) is None:
        raise HTTPException(403, "비밀번호가 맞지 않아요.")
    session_ids = service.delete_user(db, user.id)
    await request.app.state.sessions.purge_checkpoints(session_ids)
    response.delete_cookie(COOKIE_NAME, path="/")
    response.status_code = 204
    return response


@router.get("/settings", response_model=SettingsModel)
def read_settings(user: User = Depends(require_user), db: Session = Depends(get_db)) -> SettingsModel:
    """저장된 설정. 한 번도 저장하지 않았으면 빈 설정."""
    return SettingsModel(**(service.get_settings(db, user.id) or {}))


@router.put("/settings", response_model=SettingsModel)
def write_settings(body: SettingsModel, user: User = Depends(require_user), db: Session = Depends(get_db)) -> SettingsModel:
    """설정을 저장한다. 에이전트는 이 값을 일정의 기본 조건으로 쓴다."""
    saved = service.put_settings(db, user.id, body.companion, body.preferences, body.budget)
    return SettingsModel(**saved)
