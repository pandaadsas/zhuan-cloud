from pydantic import BaseModel


class LoginIn(BaseModel):
    username: str
    password: str


class ReportIn(BaseModel):
    text: str
    input_type: str = "text"  # text / voice / image


class ActionIn(BaseModel):
    action: str
    note: str = ""
    responsible_user_id: int | None = None


class ChatIn(BaseModel):
    message: str


class WeeklyGenIn(BaseModel):
    offset: int = 0  # 0=本周，-1=上周
