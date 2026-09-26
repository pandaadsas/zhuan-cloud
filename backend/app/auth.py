import hashlib
from typing import Callable

from fastapi import Depends, HTTPException, Security
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from itsdangerous import URLSafeTimedSerializer, BadSignature, SignatureExpired
from sqlalchemy.orm import Session

from .config import settings
from .database import get_db
from .models import User

_bearer = HTTPBearer(auto_error=False)
_ser = URLSafeTimedSerializer(settings.token_secret, salt="zhuan-auth")


def hash_password(pw: str) -> str:
    return hashlib.sha256(("zhuan$" + pw + "$cloud").encode("utf-8")).hexdigest()


def verify_password(pw: str, h: str) -> bool:
    return hash_password(pw) == h


def create_token(user_id: int) -> str:
    return _ser.dumps({"uid": user_id})


def get_current_user(
    cred: HTTPAuthorizationCredentials | None = Security(_bearer),
    db: Session = Depends(get_db),
) -> User:
    if cred is None:
        raise HTTPException(status_code=401, detail="未登录")
    try:
        data = _ser.loads(cred.credentials, max_age=settings.token_expire_minutes * 60)
    except (SignatureExpired, BadSignature):
        raise HTTPException(status_code=401, detail="登录已过期，请重新登录")
    user = db.get(User, data["uid"])
    if not user:
        raise HTTPException(status_code=401, detail="用户不存在")
    return user


def require_roles(*roles: str) -> Callable:
    def dep(user: User = Depends(get_current_user)) -> User:
        if user.role not in roles:
            raise HTTPException(status_code=403, detail="当前角色无权限执行该操作")
        return user

    return dep
