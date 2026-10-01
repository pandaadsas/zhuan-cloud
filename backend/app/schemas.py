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
    images: list[str] = []  # 整改照片 URL 列表（提交复查时附带）


class ChatIn(BaseModel):
    message: str
    session_id: int | None = None  # 空 = 开启新会话，后端落库后经 done 事件返回 id


class WeeklyGenIn(BaseModel):
    offset: int = 0  # 0=本周，-1=上周


class ProjectIn(BaseModel):
    name: str
    location: str = ""
    total_area: str = ""
    scale_desc: str = ""
    current_stage: str = ""
    note: str = ""


class ZoneIn(BaseModel):
    name: str
    zone_type: str = ""
    floor_count: int = 0
    current_stage: str = ""
    subcontractor_id: int | None = None
    responsible_user_id: int | None = None


class SubcontractorIn(BaseModel):
    name: str
    scope: str = ""
    leader_name: str = ""
    leader_phone: str = ""
