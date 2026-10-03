"""项目管理助手工具：项目 / 责任区域 / 分包单位的查询与增改删执行体。

仅项目经理可用（角色白名单声明在 chat_agent.Tool.roles）；
字段校验口径与 routers/projects.py 保持一致，另加重复名检查，
错误以 {"error": ...} 返回，由 LLM 转述给用户。
"""
import logging

from sqlalchemy import or_
from sqlalchemy.orm import Session

from ..models import Project, Subcontractor, User, WorkOrder, Zone

logger = logging.getLogger("zhuan.pm_tools")

_PROJECT_FIELDS = ("name", "location", "total_area", "scale_desc", "current_stage", "note")
_SUB_FIELDS = ("name", "scope", "leader_name", "leader_phone")


def _err(message: str) -> dict:
    return {"error": message}


def _int_arg(args: dict, key: str, default: int = 0) -> int:
    try:
        return int(args.get(key) or default)
    except (TypeError, ValueError):
        return default


def _project_line(db: Session, p: Project) -> str:
    zone_count = db.query(Zone).filter(Zone.project_id == p.id).count()
    sub_count = db.query(Subcontractor).filter(Subcontractor.project_id == p.id).count()
    return (
        f"- **#{p.id} {p.name}**｜地点：{p.location or '-'}｜规模：{p.scale_desc or '-'}｜"
        f"当前阶段：{p.current_stage or '-'}｜责任区域 {zone_count} 个｜分包 {sub_count} 家"
    )


def projects_markdown(db: Session) -> str:
    rows = db.query(Project).order_by(Project.id).all()
    if not rows:
        return "平台还没有任何项目。"
    lines = [f"**项目列表（共 {len(rows)} 个）**"]
    lines += [_project_line(db, p) for p in rows]
    return "\n".join(lines)


def zones_markdown(db: Session, project_id: int | None, project_name: str) -> str:
    query = db.query(Zone)
    if project_id is not None:
        query = query.filter(Zone.project_id == project_id)
    rows = query.order_by(Zone.id).all()
    if not rows:
        return f"「{project_name}」暂无责任区域，可以让我帮你新增。"
    lines = [f"**责任区域列表（{project_name}，共 {len(rows)} 个）**"]
    for z in rows:
        lines.append(
            f"- **#{z.id} {z.name}**（{z.zone_type or '未分类'}，{z.floor_count or '?'} 层）｜"
            f"阶段：{z.current_stage or '-'}｜分包：{z.subcontractor.name if z.subcontractor else '未指定'}｜"
            f"责任人：{z.responsible_user.name if z.responsible_user else '未指定'}"
        )
    return "\n".join(lines)


def subs_markdown(db: Session, project_id: int | None, project_name: str) -> str:
    query = db.query(Subcontractor)
    if project_id is not None:
        query = query.filter(Subcontractor.project_id == project_id)
    rows = query.order_by(Subcontractor.id).all()
    if not rows:
        return f"「{project_name}」暂无分包单位，可以让我帮你新增。"
    lines = [f"**分包单位列表（{project_name}，共 {len(rows)} 家）**"]
    for s in rows:
        lines.append(
            f"- **#{s.id} {s.name}**｜承包范围：{s.scope or '-'}｜"
            f"负责人：{s.leader_name or '-'}（{s.leader_phone or '-'}）"
        )
    return "\n".join(lines)


def responsible_users_markdown(db: Session, project_id: int | None, project_name: str) -> str:
    """分包负责人名单（供责任区域指派责任人时选用）。"""
    query = db.query(User).filter(User.role == "responsible")
    if project_id is not None:
        sub_ids = [s.id for s in db.query(Subcontractor.id).filter(Subcontractor.project_id == project_id)]
        query = query.filter(or_(User.subcontractor_id.in_(sub_ids), User.subcontractor_id.is_(None)))
    rows = query.order_by(User.id).all()
    if not rows:
        return f"「{project_name}」暂无分包负责人账号，指派责任人前请先在系统里创建。"
    lines = [f"**分包负责人名单（{project_name}，共 {len(rows)} 人）**"]
    for u in rows:
        sub = u.subcontractor.name if u.subcontractor_id and u.subcontractor else "未挂分包"
        lines.append(f"- **#{u.id} {u.name}**｜账号：{u.username}｜所属分包：{sub}" + (f"｜电话：{u.phone}" if u.phone else ""))
    return "\n".join(lines)


# ---------- 引用解析：分包 / 责任人支持传 id 或名称 ----------


def _resolve_sub(db: Session, project_id: int | None, args: dict) -> tuple[Subcontractor | None, str | None]:
    sub_id = args.get("subcontractor_id")
    name = str(args.get("subcontractor_name") or "").strip()
    if sub_id:
        sub = db.get(Subcontractor, _int_arg(args, "subcontractor_id"))
        if sub is None:
            return None, f"分包单位 #{sub_id} 不存在。"
        return sub, None
    if name:
        query = db.query(Subcontractor).filter(Subcontractor.name == name)
        if project_id is not None:
            query = query.filter(Subcontractor.project_id == project_id)
        sub = query.first()
        if sub is None:
            return None, f"未找到名称为「{name}」的分包单位，可先调用 list_subcontractors 确认。"
        return sub, None
    return None, None  # 未指定，允许留空


def _resolve_user(db: Session, args: dict) -> tuple[User | None, str | None]:
    uid = args.get("responsible_user_id")
    name = str(args.get("responsible_user_name") or "").strip()
    if uid:
        u = db.get(User, _int_arg(args, "responsible_user_id"))
        if u is None:
            return None, f"用户 #{uid} 不存在。"
        return u, None
    if name:
        users = db.query(User).filter(User.name == name).all()
        if not users:
            return None, f"未找到姓名为「{name}」的用户，可调用 list_responsible_users 查看名单。"
        if len(users) > 1:
            cands = "、".join(f"#{u.id} {u.name}（{u.role}）" for u in users)
            return None, f"存在多个同名用户：{cands}，请用 responsible_user_id 指定。"
        return users[0], None
    return None, None  # 未指定，允许留空


# ---------- 项目 ----------


def create_project(db: Session, user: User, args: dict):
    name = str(args.get("name") or "").strip()
    if not name:
        return _err("项目名称不能为空，请先向用户确认项目名称。"), []
    if db.query(Project).filter(Project.name == name).first():
        return _err(f"已存在同名项目「{name}」，请换一个名称或确认是否重复创建。"), []
    p = Project(name=name, **{k: str(args.get(k) or "") for k in _PROJECT_FIELDS if k != "name"})
    db.add(p)
    db.commit()
    db.refresh(p)
    logger.info("PM助手新增项目 user=%s project=#%s%s", user.name, p.id, p.name)
    return {"created": True, "project_id": p.id, "detail": _project_line(db, p)}, []


def update_project(db: Session, user: User, project: Project, args: dict):
    target = db.get(Project, _int_arg(args, "project_id")) if args.get("project_id") else project
    if target is None:
        return _err(f"项目 #{args.get('project_id')} 不存在，可调用 list_projects 确认。"), []
    changes = []
    for k in _PROJECT_FIELDS:
        v = args.get(k)
        if v is None or not str(v).strip():
            continue
        v = str(v).strip()
        if k == "name" and v != target.name and db.query(Project).filter(Project.name == v).first():
            return _err(f"已存在同名项目「{v}」，名称不可与其他项目重复。"), []
        old = getattr(target, k)
        if old != v:
            setattr(target, k, v)
            changes.append(f"{k}：{old or '空'} → {v}")
    if not changes:
        return _err("没有需要修改的字段，请确认要更新的内容后再调用。"), []
    db.commit()
    db.refresh(target)
    logger.info("PM助手编辑项目 user=%s project=#%s%s changes=%s", user.name, target.id, target.name, changes)
    return {"updated": True, "changes": changes, "detail": _project_line(db, target)}, []


# ---------- 责任区域 ----------


def _resolve_zone_project(db: Session, project: Project, args: dict) -> tuple[Project | None, str | None]:
    """区域归属项目：默认当前项目，可由 project_id 指定（用于跨项目管理）。"""
    pid = args.get("project_id")
    if pid and int(pid) != project.id:
        target = db.get(Project, _int_arg(args, "project_id"))
        if target is None:
            return None, f"项目 #{pid} 不存在。"
        return target, None
    return project, None


def _apply_zone_refs(db: Session, zone: Zone, project_id: int, args: dict) -> str | None:
    """按参数解析并写入分包/责任人引用；返回错误信息或 None。"""
    if "subcontractor_id" in args or "subcontractor_name" in args:
        sub, err = _resolve_sub(db, project_id, args)
        if err:
            return err
        zone.subcontractor_id = sub.id if sub else None
    if "responsible_user_id" in args or "responsible_user_name" in args:
        u, err = _resolve_user(db, args)
        if err:
            return err
        zone.responsible_user_id = u.id if u else None
    return None


def create_zone(db: Session, user: User, project: Project, args: dict):
    name = str(args.get("name") or "").strip()
    if not name:
        return _err("区域名称不能为空，请先向用户确认区域名称（如：3号楼）。"), []
    target_project, err = _resolve_zone_project(db, project, args)
    if err:
        return _err(err), []
    if db.query(Zone).filter(Zone.project_id == target_project.id, Zone.name == name).first():
        return _err(f"「{target_project.name}」已存在同名区域「{name}」。"), []
    zone = Zone(
        project_id=target_project.id,
        name=name,
        zone_type=str(args.get("zone_type") or ""),
        floor_count=_int_arg(args, "floor_count"),
        current_stage=str(args.get("current_stage") or ""),
    )
    if err := _apply_zone_refs(db, zone, target_project.id, args):
        db.rollback()
        return _err(err), []
    db.add(zone)
    db.commit()
    db.refresh(zone)
    logger.info("PM助手新增区域 user=%s project=%s zone=#%s%s", user.name, target_project.name, zone.id, zone.name)
    return {"created": True, "zone_id": zone.id, "project": target_project.name, "name": zone.name}, []


def update_zone(db: Session, user: User, project: Project, args: dict):
    zone = db.get(Zone, _int_arg(args, "zone_id"))
    if zone is None:
        return _err(f"责任区域 #{args.get('zone_id')} 不存在，可先调用 list_zones 确认。"), []
    changes = []
    for k in ("name", "zone_type", "current_stage"):
        v = args.get(k)
        if v is None or not str(v).strip():
            continue
        v = str(v).strip()
        if getattr(zone, k) != v:
            changes.append(f"{k}：{getattr(zone, k) or '空'} → {v}")
            setattr(zone, k, v)
    if "floor_count" in args and args.get("floor_count") is not None:
        n = _int_arg(args, "floor_count")
        if n != (zone.floor_count or 0):
            changes.append(f"floor_count：{zone.floor_count or 0} → {n}")
            zone.floor_count = n
    if err := _apply_zone_refs(db, zone, zone.project_id, args):
        db.rollback()
        return _err(err), []
    if not changes:
        return _err("没有需要修改的字段，请确认要更新的内容后再调用。"), []
    db.commit()
    logger.info("PM助手编辑区域 user=%s zone=#%s%s changes=%s", user.name, zone.id, zone.name, changes)
    return {"updated": True, "zone_id": zone.id, "name": zone.name, "changes": changes}, []


def delete_zone(db: Session, user: User, project: Project, args: dict):
    zone = db.get(Zone, _int_arg(args, "zone_id"))
    if zone is None:
        return _err(f"责任区域 #{args.get('zone_id')} 不存在，可先调用 list_zones 确认。"), []
    used = db.query(WorkOrder).filter(WorkOrder.zone_id == zone.id).count()
    if used:
        return _err(f"区域「{zone.name}」已关联 {used} 条工单，不能删除。建议改为编辑区域信息。"), []
    name = zone.name
    db.delete(zone)
    db.commit()
    logger.info("PM助手删除区域 user=%s zone=%s", user.name, name)
    return {"deleted": True, "zone_id": args.get("zone_id"), "name": name}, []


# ---------- 分包单位 ----------


def create_subcontractor(db: Session, user: User, project: Project, args: dict):
    name = str(args.get("name") or "").strip()
    if not name:
        return _err("分包单位名称不能为空，请先向用户确认。"), []
    target_project, err = _resolve_zone_project(db, project, args)
    if err:
        return _err(err), []
    if db.query(Subcontractor).filter(Subcontractor.project_id == target_project.id, Subcontractor.name == name).first():
        return _err(f"「{target_project.name}」已存在同名分包「{name}」。"), []
    sub = Subcontractor(
        project_id=target_project.id,
        name=name,
        **{k: str(args.get(k) or "") for k in _SUB_FIELDS if k != "name"},
    )
    db.add(sub)
    db.commit()
    db.refresh(sub)
    logger.info("PM助手新增分包 user=%s project=%s sub=#%s%s", user.name, target_project.name, sub.id, sub.name)
    return {"created": True, "subcontractor_id": sub.id, "project": target_project.name, "name": sub.name}, []


def update_subcontractor(db: Session, user: User, project: Project, args: dict):
    sub = db.get(Subcontractor, _int_arg(args, "subcontractor_id"))
    if sub is None:
        return _err(f"分包单位 #{args.get('subcontractor_id')} 不存在，可先调用 list_subcontractors 确认。"), []
    changes = []
    for k in _SUB_FIELDS:
        v = args.get(k)
        if v is None or not str(v).strip():
            continue
        v = str(v).strip()
        old = getattr(sub, k)
        if old != v:
            changes.append(f"{k}：{old or '空'} → {v}")
            setattr(sub, k, v)
    if not changes:
        return _err("没有需要修改的字段，请确认要更新的内容后再调用。"), []
    db.commit()
    logger.info("PM助手编辑分包 user=%s sub=#%s%s changes=%s", user.name, sub.id, sub.name, changes)
    return {"updated": True, "subcontractor_id": sub.id, "name": sub.name, "changes": changes}, []
