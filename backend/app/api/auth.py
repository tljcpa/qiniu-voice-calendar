"""认证 API（创新1）：注册 / 登录，返回 JWT。"""

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth import create_token, hash_password, verify_password
from app.db import get_session
from app.models import User

router = APIRouter(prefix="/api/auth", tags=["auth"])


class Credentials(BaseModel):
    """注册：强约束用户名/密码长度。"""

    username: str = Field(min_length=2, max_length=50)
    password: str = Field(min_length=6, max_length=128)


class LoginCredentials(BaseModel):
    """登录：不校验长度（错误密码应 401，而非 422）。"""

    username: str = Field(max_length=50)
    password: str = Field(max_length=128)


def _user_payload(user: User) -> dict:
    return {"id": user.id, "username": user.username}


@router.post("/register", status_code=201)
def register(body: Credentials, session: Session = Depends(get_session)) -> dict:
    """注册新用户。用户名已存在返回 409。"""
    exists = session.scalar(select(User).where(User.username == body.username))
    if exists is not None:
        raise HTTPException(status_code=409, detail="用户名已被占用")
    user = User(username=body.username, password_hash=hash_password(body.password))
    session.add(user)
    session.commit()
    session.refresh(user)
    return {"token": create_token(user.id), "user": _user_payload(user)}


@router.post("/login")
def login(body: LoginCredentials, session: Session = Depends(get_session)) -> dict:
    """登录。用户名或密码错误返回 401。"""
    user = session.scalar(select(User).where(User.username == body.username))
    if user is None or not verify_password(body.password, user.password_hash):
        raise HTTPException(status_code=401, detail="用户名或密码错误")
    return {"token": create_token(user.id), "user": _user_payload(user)}
