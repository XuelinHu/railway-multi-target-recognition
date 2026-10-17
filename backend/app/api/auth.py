from datetime import timedelta

from fastapi import APIRouter, Depends, HTTPException, Request, Response

from app.core.dependencies import get_store
from app.core.security import hash_password, hash_session_token, new_session_token, verify_password
from app.models.schemas import ApiResponse, AuthLoginRequest, AuthRegisterRequest, AuthUser, AuthUserRoleUpdateRequest, now_utc
from app.repositories.postgres_store import PostgresStore


router = APIRouter(prefix="/api/auth", tags=["auth"])
AUTH_COOKIE_NAME = "railway_session"
SESSION_MAX_AGE_SECONDS = 7 * 24 * 60 * 60


def resolve_user(request: Request, store: PostgresStore) -> AuthUser | None:
    token = request.cookies.get(AUTH_COOKIE_NAME, "")
    if not token:
        return None
    return store.get_user_by_auth_session(hash_session_token(token))


def require_user(request: Request, store: PostgresStore = Depends(get_store)) -> AuthUser:
    user = getattr(request.state, "current_user", None) or resolve_user(request, store)
    if user is None:
        raise HTTPException(status_code=401, detail="登录状态已失效，请重新登录")
    return user


def require_reviewer(current_user: AuthUser = Depends(require_user)) -> AuthUser:
    if current_user.role not in {"reviewer", "admin"}:
        raise HTTPException(status_code=403, detail="该操作需要审核员或管理员权限")
    return current_user


def require_admin(current_user: AuthUser = Depends(require_user)) -> AuthUser:
    if current_user.role != "admin":
        raise HTTPException(status_code=403, detail="该操作需要管理员权限")
    return current_user


@router.post("/register", response_model=ApiResponse)
def register(
    request: AuthRegisterRequest,
    response: Response,
    store: PostgresStore = Depends(get_store),
) -> ApiResponse:
    user = store.create_user(request.username, request.display_name, hash_password(request.password))
    if user is None:
        raise HTTPException(status_code=409, detail="该账号已存在")
    _start_session(response, user, store)
    return ApiResponse(data=_user_payload(user))


@router.post("/login", response_model=ApiResponse)
def login(
    request: AuthLoginRequest,
    response: Response,
    store: PostgresStore = Depends(get_store),
) -> ApiResponse:
    credentials = store.get_user_credentials(request.username)
    if credentials is None or not verify_password(request.password, credentials[1]) or not credentials[0].is_active:
        raise HTTPException(status_code=401, detail="账号或密码错误")
    user = credentials[0]
    _start_session(response, user, store)
    return ApiResponse(data=_user_payload(user))


@router.get("/me", response_model=ApiResponse)
def current_user(request: Request, store: PostgresStore = Depends(get_store)) -> ApiResponse:
    user = resolve_user(request, store)
    return ApiResponse(data=_user_payload(user) if user else None)


@router.post("/logout", response_model=ApiResponse)
def logout(request: Request, response: Response, store: PostgresStore = Depends(get_store)) -> ApiResponse:
    token = request.cookies.get(AUTH_COOKIE_NAME, "")
    if token:
        store.delete_auth_session(hash_session_token(token))
    response.delete_cookie(AUTH_COOKIE_NAME, path="/", httponly=True, samesite="lax")
    return ApiResponse(data={"loggedOut": True})


@router.get("/users", response_model=ApiResponse)
def list_users(
    store: PostgresStore = Depends(get_store),
    _: AuthUser = Depends(require_admin),
) -> ApiResponse:
    return ApiResponse(data=[_user_payload(user) for user in store.list_users()])


@router.put("/users/{user_id}/role", response_model=ApiResponse)
def update_user_role(
    user_id: str,
    request: AuthUserRoleUpdateRequest,
    store: PostgresStore = Depends(get_store),
    current_user: AuthUser = Depends(require_admin),
) -> ApiResponse:
    if user_id == current_user.user_id and request.role != "admin":
        raise HTTPException(status_code=400, detail="不能移除自己的管理员权限")
    user = store.update_user_role(user_id, request.role)
    if user is None:
        raise HTTPException(status_code=404, detail="用户不存在")
    return ApiResponse(data=_user_payload(user))


def _start_session(response: Response, user: AuthUser, store: PostgresStore) -> None:
    token = new_session_token()
    store.create_auth_session(
        hash_session_token(token),
        user.user_id,
        now_utc() + timedelta(seconds=SESSION_MAX_AGE_SECONDS),
    )
    response.set_cookie(
        AUTH_COOKIE_NAME,
        token,
        max_age=SESSION_MAX_AGE_SECONDS,
        httponly=True,
        samesite="lax",
        secure=False,
        path="/",
    )


def _user_payload(user: AuthUser) -> dict:
    return {
        "userId": user.user_id,
        "username": user.username,
        "displayName": user.display_name,
        "role": user.role,
    }
