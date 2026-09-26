import random
import re
from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ..auth import create_token, get_current_user, hash_password, verify_password
from ..database import get_db
from ..models import User, VerifyCode
from ..serializers import user_public
from ..services.mailer import send_code_email, smtp_ready
from ..services.sms import send_code_sms, sms_ready

router = APIRouter(prefix="/api/auth", tags=["auth"])

EMAIL_RE = re.compile(r"^[\w.+-]+@[\w-]+(\.[\w-]+)+$")
PHONE_RE = re.compile(r"^1[3-9]\d{9}$")
CODE_TTL_MINUTES = 10
SEND_INTERVAL_SECONDS = 60


class LoginIn(BaseModel):
    username: str
    password: str


class SendCodeIn(BaseModel):
    channel: str  # email / sms
    target: str


class RegisterIn(BaseModel):
    channel: str
    target: str
    code: str
    username: str
    password: str
    name: str = ""


@router.post("/login")
def login(payload: LoginIn, db: Session = Depends(get_db)):
    ident = payload.username.strip()
    user = (
        db.query(User)
        .filter((User.username == ident) | (User.email == ident.lower()))
        .first()
    )
    if not user or not verify_password(payload.password, user.password_hash):
        raise HTTPException(status_code=400, detail="账号或密码错误")
    return {"token": create_token(user.id), "user": user_public(user)}


@router.get("/me")
def me(user: User = Depends(get_current_user)):
    return user_public(user)


@router.post("/send-code")
def send_code(payload: SendCodeIn, db: Session = Depends(get_db)):
    channel, target = payload.channel.strip(), payload.target.strip()
    if channel == "email":
        if not EMAIL_RE.match(target):
            raise HTTPException(status_code=400, detail="邮箱格式不正确")
        target = target.lower()
        if not smtp_ready():
            raise HTTPException(status_code=503, detail="邮件服务暂未配置，请联系管理员或使用演示账号")
        sender = lambda: send_code_email(target, code)
    elif channel == "sms":
        if not PHONE_RE.match(target):
            raise HTTPException(status_code=400, detail="手机号格式不正确")
        if not sms_ready():
            raise HTTPException(status_code=503, detail="短信服务暂未开通，请使用邮箱注册")
        sender = lambda: send_code_sms(target, code)
    else:
        raise HTTPException(status_code=400, detail="不支持的验证方式")

    last = (
        db.query(VerifyCode)
        .filter(VerifyCode.channel == channel, VerifyCode.target == target)
        .order_by(VerifyCode.created_at.desc())
        .first()
    )
    if last and (datetime.now() - last.created_at).total_seconds() < SEND_INTERVAL_SECONDS:
        raise HTTPException(status_code=429, detail="发送过于频繁，请稍后再试")

    code = f"{random.randint(0, 999999):06d}"
    db.add(
        VerifyCode(
            target=target,
            channel=channel,
            code=code,
            expires_at=datetime.now() + timedelta(minutes=CODE_TTL_MINUTES),
        )
    )
    db.commit()
    sender()
    return {"ok": True, "expires_in": CODE_TTL_MINUTES * 60}


@router.post("/register")
def register(payload: RegisterIn, db: Session = Depends(get_db)):
    channel, target = payload.channel.strip(), payload.target.strip()
    username = payload.username.strip()
    if not re.match(r"^[A-Za-z0-9_]{3,30}$", username):
        raise HTTPException(status_code=400, detail="账号需为 3-30 位字母、数字或下划线")
    if len(payload.password) < 6:
        raise HTTPException(status_code=400, detail="密码至少 6 位")
    if channel == "email":
        if not EMAIL_RE.match(target):
            raise HTTPException(status_code=400, detail="邮箱格式不正确")
        target = target.lower()
    elif channel == "sms":
        if not PHONE_RE.match(target):
            raise HTTPException(status_code=400, detail="手机号格式不正确")
    else:
        raise HTTPException(status_code=400, detail="不支持的验证方式")

    record = (
        db.query(VerifyCode)
        .filter(
            VerifyCode.channel == channel,
            VerifyCode.target == target,
            VerifyCode.code == payload.code.strip(),
            VerifyCode.used.is_(False),
        )
        .order_by(VerifyCode.created_at.desc())
        .first()
    )
    if not record:
        raise HTTPException(status_code=400, detail="验证码错误")
    if record.expires_at < datetime.now():
        raise HTTPException(status_code=400, detail="验证码已过期，请重新获取")

    if db.query(User).filter(User.username == username).first():
        raise HTTPException(status_code=400, detail="该账号已被注册")
    if channel == "email" and db.query(User).filter(User.email == target).first():
        raise HTTPException(status_code=400, detail="该邮箱已注册，请直接登录")
    if channel == "sms" and db.query(User).filter(User.phone == target).first():
        raise HTTPException(status_code=400, detail="该手机号已注册，请直接登录")

    user = User(
        username=username,
        password_hash=hash_password(payload.password),
        name=payload.name.strip() or username,
        role="safety_officer",  # 注册用户默认安全员角色，正式环境由管理员分配
        email=target if channel == "email" else "",
        phone=target if channel == "sms" else "",
    )
    db.add(user)
    record.used = True
    db.commit()
    db.refresh(user)
    return {"token": create_token(user.id), "user": user_public(user)}
