from __future__ import annotations

import asyncio
import hashlib
import json
import logging
from datetime import datetime, timezone
from typing import AsyncGenerator

from fastapi import (
    Depends,
    FastAPI,
    File,
    HTTPException,
    Request,
    Response,
    UploadFile,
    status,
)
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel, Field

from .ai import (
    INTENT_CODING_TASK,
    INTENT_DEBUGGING,
    AdaptiveModelOptimizer,
    TIER_STANDARD,
    generate_ai_response,
)
from .config import Settings, load_settings
from .db import ensure_database
from .middleware import InMemoryRateLimiter, RequestContextMiddleware
from .moderation import is_aggressive_context, soft_moderate
from .notifier import send_exception_report


# =====================================================
# APP INIT
# =====================================================

app = FastAPI(
    title="Ghost AI 👻",
    version="1.0.0",
)

settings: Settings = load_settings()

# =====================================================
# CORS (frontend gọi được)
# =====================================================

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.add_middleware(RequestContextMiddleware)


# =====================================================
# STARTUP EVENT
# =====================================================

@app.on_event("startup")
async def startup_event():
    logging.info("Starting Ghost AI...")
    await ensure_database()
    logging.info("Database ready ✅")


# =====================================================
# RAILWAY HEALTH CHECK (QUAN TRỌNG NHẤT)
# =====================================================

@app.get("/")
async def root():
    return {
        "name": "Ghost AI",
        "status": "online",
        "time": datetime.now(timezone.utc).isoformat(),
    }


@app.get("/health")
async def health():
    return {"ok": True}


# =====================================================
# GLOBAL ERROR HANDLER
# =====================================================

@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    logging.exception("Unhandled exception")

    try:
        await send_exception_report(str(exc))
    except Exception:
        pass

    return JSONResponse(
        status_code=500,
        content={"error": "Internal Server Error"},
    )


# =====================================================
# SIMPLE CHAT TEST ENDPOINT
# =====================================================

class ChatRequest(BaseModel):
    message: str = Field(min_length=1)


@app.post("/chat")
async def chat(req: ChatRequest):

    moderated = soft_moderate(req.message)

    response = await generate_ai_response(
        message=moderated,
        tier=TIER_STANDARD,
        intent=INTENT_CODING_TASK,
    )

    return {"reply": response}

    create_session,
    create_user,
    get_session,
    get_user_by_email,
    get_user_by_id,
    is_login_blocked,
    register_failed_login,
    revoke_all_user_sessions,
    revoke_session,
    rotate_refresh_jti,
    save_routing_log,
    save_message,
    update_session_activity,
)
from .security import (
    AuthError,
    anonymize_identifier,
    build_tokens,
    decode_access_token,
    decode_refresh_token,
    hash_password,
    hash_refresh_jti,
    now_ts,
    verify_password,
)


class ApiError(Exception):
    def __init__(self, status_code: int, message: str):
        self.status_code = status_code
        self.message = message
        super().__init__(message)


class RegisterRequest(BaseModel):
    email: str = Field(min_length=5, max_length=255)
    password: str = Field(min_length=10, max_length=128)


class LoginRequest(BaseModel):
    email: str = Field(min_length=5, max_length=255)
    password: str = Field(min_length=1, max_length=128)


class RefreshRequest(BaseModel):
    refresh_token: str | None = None


class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=4000)
    image_context: dict | None = None


class AuthContext(BaseModel):
    user_id: int
    email: str
    session_id: str


settings: Settings = load_settings()
ensure_database(settings.db_path)

app = FastAPI(title=settings.app_name)
app.add_middleware(RequestContextMiddleware, limiter=InMemoryRateLimiter())
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["*"],
)

LOGGER = logging.getLogger("ghost")
AMO = AdaptiveModelOptimizer()


def _error_response(status_code: int, message: str) -> JSONResponse:
    return JSONResponse(status_code=status_code, content={"error": True, "message": message})


def _normalize_email(email: str) -> str:
    return email.strip().lower()


def _password_is_strong(password: str) -> bool:
    has_upper = any(ch.isupper() for ch in password)
    has_lower = any(ch.islower() for ch in password)
    has_digit = any(ch.isdigit() for ch in password)
    return len(password) >= 10 and has_upper and has_lower and has_digit


def _cookie_common() -> dict:
    common = {
        "httponly": True,
        "secure": settings.cookie_secure,
        "samesite": "lax",
        "path": "/",
    }
    if settings.cookie_domain:
        common["domain"] = settings.cookie_domain
    return common


def _set_auth_cookies(response: Response, access_token: str, refresh_token: str) -> None:
    common = _cookie_common()
    response.set_cookie("access_token", access_token, max_age=settings.access_ttl_minutes * 60, **common)
    response.set_cookie("refresh_token", refresh_token, max_age=settings.refresh_ttl_days * 86400, **common)


def _clear_auth_cookies(response: Response) -> None:
    common = _cookie_common()
    response.delete_cookie("access_token", **common)
    response.delete_cookie("refresh_token", **common)


def _auth_error_response(message: str, status_code: int = 401) -> JSONResponse:
    response = _error_response(status_code, message)
    _clear_auth_cookies(response)
    return response


def _extract_token(request: Request, token_type: str) -> str | None:
    if token_type == "access":
        auth_header = request.headers.get("authorization", "")
        if auth_header.lower().startswith("bearer "):
            return auth_header.split(" ", 1)[1].strip()
        return request.cookies.get("access_token")

    refresh_header = request.headers.get("x-refresh-token")
    if refresh_header:
        return refresh_header.strip()
    return request.cookies.get("refresh_token")


def _session_expired(last_active: int) -> bool:
    return now_ts() - last_active > settings.session_inactivity_minutes * 60


async def _safe_bug_report(request: Request, error_message: str) -> None:
    report = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "endpoint": request.url.path,
        "error_message": error_message,
        "session_id": anonymize_identifier(request.cookies.get("refresh_token") or request.cookies.get("access_token")),
    }
    try:
        await send_exception_report(settings, report)
    except Exception:
        return


async def _load_auth_context(request: Request) -> AuthContext:
    token = _extract_token(request, "access")
    if not token:
        raise ApiError(401, "Missing access token")

    try:
        payload = decode_access_token(settings, token)
    except AuthError as exc:
        raise ApiError(401, "Invalid access token") from exc

    try:
        user_id = int(payload.get("sub", "0"))
    except ValueError as exc:
        raise ApiError(401, "Invalid access token") from exc

    session_id = str(payload.get("sid", "")).strip()
    if not session_id:
        raise ApiError(401, "Invalid session")

    session = get_session(settings.db_path, session_id)
    if not session or session.revoked:
        raise ApiError(401, "Session revoked")

    if _session_expired(session.last_active):
        revoke_session(settings.db_path, session_id)
        raise ApiError(401, "Session expired")

    user = get_user_by_id(settings.db_path, user_id)
    if not user:
        revoke_session(settings.db_path, session_id)
        raise ApiError(401, "User not found")

    update_session_activity(settings.db_path, session_id)
    return AuthContext(user_id=user.id, email=user.email, session_id=session_id)


def _login_attempt_key(client_ip: str, email: str) -> str:
    return hashlib.sha256(f"{client_ip}:{email}".encode("utf-8")).hexdigest()


def _sse(event: str, data: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=True)}\n\n"


@app.exception_handler(ApiError)
async def handle_api_error(_: Request, exc: ApiError):
    return _error_response(exc.status_code, exc.message)


@app.exception_handler(HTTPException)
async def handle_http_exception(_: Request, exc: HTTPException):
    return _error_response(exc.status_code, str(exc.detail))


@app.exception_handler(RequestValidationError)
async def handle_validation_error(_: Request, __: RequestValidationError):
    return _error_response(422, "Invalid request payload")


@app.exception_handler(Exception)
async def handle_unhandled_exception(request: Request, exc: Exception):
    asyncio.create_task(_safe_bug_report(request, str(exc)))
    return _error_response(500, "Internal server error")


@app.get("/health")
async def health() -> dict:
    try:
        return {"status": "ok", "service": "ghost"}
    except Exception:
        raise


@app.post("/auth/register")
async def register(payload: RegisterRequest, request: Request, response: Response):
    try:
        email = _normalize_email(payload.email)
        if not _password_is_strong(payload.password):
            raise ApiError(400, "Password must include upper/lower/digit and be at least 10 characters")

        existing = get_user_by_email(settings.db_path, email)
        if existing:
            raise ApiError(409, "Email already exists")

        user = create_user(settings.db_path, email, hash_password(payload.password))
        bundle = build_tokens(settings, user_id=user.id)

        create_session(
            settings.db_path,
            session_id=bundle.session_id,
            user_id=user.id,
            refresh_jti_hash=hash_refresh_jti(bundle.refresh_jti),
            ip_address=getattr(request.state, "client_ip", "unknown"),
            user_agent=request.headers.get("user-agent", "unknown"),
        )

        _set_auth_cookies(response, bundle.access_token, bundle.refresh_token)
        return {"error": False, "user": {"id": user.id, "email": user.email}}
    except ApiError:
        raise
    except Exception:
        raise


@app.post("/auth/login")
async def login(payload: LoginRequest, request: Request, response: Response):
    try:
        email = _normalize_email(payload.email)
        key = _login_attempt_key(getattr(request.state, "client_ip", "unknown"), email)

        blocked, retry_after = is_login_blocked(settings.db_path, key)
        if blocked:
            raise ApiError(429, f"Too many attempts. Retry in {retry_after}s")

        user = get_user_by_email(settings.db_path, email)
        if not user or not verify_password(payload.password, user.password_hash):
            retry_after = register_failed_login(settings.db_path, key)
            if retry_after > 0:
                raise ApiError(429, f"Too many attempts. Retry in {retry_after}s")
            raise ApiError(401, "Invalid credentials")

        clear_login_attempts(settings.db_path, key)

        bundle = build_tokens(settings, user_id=user.id)
        create_session(
            settings.db_path,
            session_id=bundle.session_id,
            user_id=user.id,
            refresh_jti_hash=hash_refresh_jti(bundle.refresh_jti),
            ip_address=getattr(request.state, "client_ip", "unknown"),
            user_agent=request.headers.get("user-agent", "unknown"),
        )

        _set_auth_cookies(response, bundle.access_token, bundle.refresh_token)
        return {"error": False, "user": {"id": user.id, "email": user.email}}
    except ApiError:
        raise
    except Exception:
        raise


@app.post("/auth/refresh")
async def refresh(payload: RefreshRequest, request: Request, response: Response):
    try:
        token = payload.refresh_token or _extract_token(request, "refresh")
        if not token:
            raise ApiError(401, "Missing refresh token")

        try:
            decoded = decode_refresh_token(settings, token)
        except AuthError as exc:
            raise ApiError(401, "Invalid refresh token") from exc

        session_id = str(decoded.get("sid", "")).strip()
        incoming_jti = str(decoded.get("jti", "")).strip()
        if not session_id or not incoming_jti:
            raise ApiError(401, "Malformed refresh token")

        session = get_session(settings.db_path, session_id)
        if not session or session.revoked:
            return _auth_error_response("Session revoked")

        if _session_expired(session.last_active):
            revoke_session(settings.db_path, session_id)
            return _auth_error_response("Session expired")

        incoming_hash = hash_refresh_jti(incoming_jti)
        if incoming_hash != session.refresh_jti_hash:
            revoke_all_user_sessions(settings.db_path, session.user_id)
            return _auth_error_response("Compromised session detected")

        bundle = build_tokens(settings, user_id=session.user_id, session_id=session_id)
        rotate_refresh_jti(settings.db_path, session_id, hash_refresh_jti(bundle.refresh_jti))
        _set_auth_cookies(response, bundle.access_token, bundle.refresh_token)
        return {"error": False, "message": "Session refreshed"}
    except ApiError:
        raise
    except Exception:
        raise


@app.post("/auth/logout")
async def logout(request: Request, response: Response):
    try:
        token = _extract_token(request, "access")
        if token:
            try:
                payload = decode_access_token(settings, token)
                sid = str(payload.get("sid", "")).strip()
                if sid:
                    revoke_session(settings.db_path, sid)
            except AuthError:
                pass
        _clear_auth_cookies(response)
        return {"error": False, "message": "Logged out"}
    except Exception:
        raise


@app.get("/auth/me")
async def me(auth: AuthContext = Depends(_load_auth_context)):
    try:
        return {"error": False, "user": {"id": auth.user_id, "email": auth.email}}
    except Exception:
        raise


@app.post("/chat/image")
async def upload_image(
    request: Request,
    file: UploadFile = File(...),
    auth: AuthContext = Depends(_load_auth_context),
):
    try:
        content_type = (file.content_type or "").lower()
        if not content_type.startswith("image/"):
            raise ApiError(400, "Only image uploads are supported")

        total_bytes = 0
        hasher = hashlib.sha256()
        while True:
            chunk = await file.read(1024 * 128)
            if not chunk:
                break
            total_bytes += len(chunk)
            if total_bytes > settings.max_upload_bytes:
                raise ApiError(413, "Image exceeds size limit")
            hasher.update(chunk)

        save_message(settings.db_path, auth.user_id, auth.session_id, "user", f"[image] {file.filename} ({total_bytes} bytes)")
        request.state.last_user_message = f"[image] {file.filename}"

        return {
            "error": False,
            "filename": file.filename,
            "mime": content_type,
            "size_bytes": total_bytes,
            "sha256": hasher.hexdigest(),
            "analysis": "Image received. Analysis mode enabled.",
            "show_image_tools": True,
        }
    except ApiError:
        raise
    except Exception:
        raise


@app.post("/chat/stream")
async def chat_stream(request: Request, payload: ChatRequest, auth: AuthContext = Depends(_load_auth_context)):
    try:
        message = payload.message.strip()
        request.state.last_user_message = message
        save_message(settings.db_path, auth.user_id, auth.session_id, "user", message)

        async def event_stream() -> AsyncGenerator[str, None]:
            route = AMO.route(message=message, has_image=bool(payload.image_context))
            debug_mode = route.intent in {INTENT_DEBUGGING, INTENT_CODING_TASK}

            yield _sse("meta", {"debug_mode": debug_mode, "show_image_tools": bool(payload.image_context)})

            try:
                envelope = await asyncio.wait_for(
                    generate_ai_response(
                        message=message,
                        image_context=payload.image_context,
                        optimizer=AMO,
                        route=route,
                    ),
                    timeout=settings.ai_timeout_seconds,
                )
                ai_text = envelope.text
                response_ms = envelope.response_ms
                fallback_used = envelope.fallback_used
            except asyncio.TimeoutError:
                route = AMO.failsafe_decision(message=message, reason="provider_timeout")
                ai_text = "Ghost fallback: response timed out. Please retry."
                response_ms = settings.ai_timeout_seconds * 1000
                fallback_used = True
            except Exception:
                route = AMO.failsafe_decision(message=message, reason="provider_failure")
                ai_text = "Ghost fallback: provider unavailable. Please retry."
                response_ms = 0.0
                fallback_used = True

            save_routing_log(
                settings.db_path,
                user_id=auth.user_id,
                session_id=auth.session_id,
                intent=route.intent,
                model_tier=route.model_tier if route.model_tier else TIER_STANDARD,
                message_length=route.message_length,
                decision_ms=route.decision_ms,
                response_ms=response_ms,
                fallback_used=fallback_used,
                downgraded=route.downgraded,
                reason=route.reason,
            )

            moderated = soft_moderate(ai_text, is_aggressive_context(message))
            save_message(settings.db_path, auth.user_id, auth.session_id, "assistant", moderated.original_text)

            for word in moderated.display_text.split(" "):
                yield _sse("chunk", {"text": f"{word} "})
                await asyncio.sleep(0.02)

            yield _sse(
                "done",
                {
                    "moderated": moderated.moderated,
                    "masked_text": moderated.display_text,
                    "raw_text": moderated.original_text if moderated.moderated else None,
                },
            )

        headers = {
            "Cache-Control": "no-cache, no-transform",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        }
        return StreamingResponse(event_stream(), media_type="text/event-stream", headers=headers)
    except ApiError:
        raise
    except Exception:
        raise
