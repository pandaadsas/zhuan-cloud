"""演示数据初始化（幂等）：项目/分包/人员/责任分区/规范条款/六周历史工单。

背景项目：三河市保障性租赁住房项目（公开招标信息提炼，12栋一类高层住宅+10栋多层公共建筑，
总建筑面积约14.75万㎡）。分包单位、人员、制度均为演示用合理虚构，已在文档中标注。
"""
import json
import random
from datetime import datetime, timedelta
from pathlib import Path

from sqlalchemy.orm import Session

from .agents.assessor import IMMEDIATE_ACTIONS
from .auth import hash_password
from .models import OrderEvent, Project, Regulation, Report, Subcontractor, User, WorkOrder, Zone

KB_FILE = Path(__file__).resolve().parent.parent / "knowledge" / "regulations.json"
RISK_DEADLINE = {"重大": 1, "高": 2, "中": 3, "低": 7}

SCENARIOS = [
    ("3号楼", "12层", "东侧", "临边防护栏杆缺失，旁边有工人在进行二次结构作业", "高处作业-临边防护", "高"),
    ("5号楼", "1层", "大门口", "消防通道被钢管模板占用，无法通行", "消防安全-通道占用", "中"),
    ("2号楼", "6层", "楼梯间", "工人未戴安全帽搬运材料", "个人防护-安全帽", "中"),
    ("1号楼", "9层", "东南角", "动火作业未办理审批手续，无看火人", "动火作业", "高"),
    ("地下室区域", "", "配电房旁", "配电箱门未关闭，电缆私拉乱接", "临时用电", "中"),
    ("6号楼", "15层", "北侧", "电梯井洞口未覆盖防护盖板", "高处作业-洞口防护", "高"),
    ("塔吊作业区", "", "", "吊物下方有人员穿行，未设警戒", "起重吊装", "高"),
    ("3号楼", "3层", "西侧", "外脚手架剪刀撑缺失两道", "脚手架工程", "高"),
    ("公共区域及消防通道", "", "", "现场建筑垃圾未及时清运", "文明施工-垃圾清理", "低"),
    ("材料堆场", "", "", "钢筋材料未按平面布置图码放", "材料堆放", "低"),
    ("4号楼", "8层", "南侧", "作业人员高处作业未系挂安全带", "个人防护-安全带", "高"),
    ("地下室区域", "", "基坑东侧", "基坑边堆载超限，监测数据接近预警值", "基坑工程", "高"),
    ("1号楼", "10层", "", "施工升降机附墙架间距不符合说明书要求", "施工升降机", "高"),
    ("5号楼", "5层", "东侧", "楼内违规吸烟，发现烟头", "消防安全-违规吸烟", "中"),
    ("2号楼", "", "周边道路", "裸土未覆盖，道路扬尘大", "绿色施工-扬尘治理", "低"),
    ("生活区", "", "", "宿舍内使用大功率电器", "生活区管理", "低"),
    ("6号楼", "18层", "西侧", "模板支撑立杆间距过大，与方案不符", "模板支撑体系", "高"),
    ("4号楼", "2层", "大门口", "灭火器压力不足，未及时更换", "消防安全-设施缺失", "中"),
]


def run_if_empty(db: Session) -> bool:
    if db.query(User).count() > 0:
        return False
    _seed_all(db)
    return True


def _seed_all(db: Session):
    rng = random.Random(42)
    now = datetime.now()

    db.add(
        Project(
            name="三河市保障性租赁住房项目",
            location="河北省三河市",
            total_area="147,536.8㎡",
            scale_desc="12栋一类高层住宅及10栋多层公共建筑，总建筑面积约14.75万㎡",
            current_stage="主体结构 + 二次结构",
            note="演示背景项目：源自全国公共资源交易平台公开信息，承接单位与人员均为虚构。",
        )
    )

    subs = {
        "huayu": Subcontractor(name="华宇建筑劳务有限公司", scope="主体结构、二次结构、脚手架劳务作业（1-2号楼责任区）", leader_name="刘伟", leader_phone="13800000001"),
        "hengsheng": Subcontractor(name="恒盛建筑劳务有限公司", scope="主体结构、模板支撑劳务作业（3-6号楼责任区）", leader_name="赵强", leader_phone="13800000002"),
        "zhongan": Subcontractor(name="中安机电安装工程有限公司", scope="机电安装工程及现场临时用电维护", leader_name="陈志明", leader_phone="13800000003"),
        "guangsha": Subcontractor(name="广厦土方基础工程有限公司", scope="土方开挖与基坑支护工程", leader_name="孙立", leader_phone="13800000004"),
        "xinlong": Subcontractor(name="鑫隆起重设备有限公司", scope="塔式起重机及施工升降机安拆维保", leader_name="周海涛", leader_phone="13800000005"),
        "jiecheng": Subcontractor(name="洁诚环境工程有限公司", scope="现场文明施工、消防通道维护、垃圾清运、扬尘治理、生活区保洁", leader_name="吴刚", leader_phone="13800000006"),
    }
    db.add_all(subs.values())
    db.flush()

    pw = hash_password("zhuan@123")
    users = {
        "zhangmin": User(username="zhangmin", password_hash=pw, name="张明", role="safety_officer", phone="13900000001"),
        "liqiang": User(username="liqiang", password_hash=pw, name="李强", role="safety_supervisor", phone="13900000002"),
        "wangjianguo": User(username="wangjianguo", password_hash=pw, name="王建国", role="project_manager", phone="13900000003"),
        "zeren01": User(username="zeren01", password_hash=pw, name="刘伟", role="responsible", phone="13800000001", subcontractor_id=subs["huayu"].id),
        "zeren02": User(username="zeren02", password_hash=pw, name="赵强", role="responsible", phone="13800000002", subcontractor_id=subs["hengsheng"].id),
        "zeren03": User(username="zeren03", password_hash=pw, name="陈志明", role="responsible", phone="13800000003", subcontractor_id=subs["zhongan"].id),
        "zeren04": User(username="zeren04", password_hash=pw, name="孙立", role="responsible", phone="13800000004", subcontractor_id=subs["guangsha"].id),
        "zeren05": User(username="zeren05", password_hash=pw, name="周海涛", role="responsible", phone="13800000005", subcontractor_id=subs["xinlong"].id),
        "zeren06": User(username="zeren06", password_hash=pw, name="吴刚", role="responsible", phone="13800000006", subcontractor_id=subs["jiecheng"].id),
    }
    db.add_all(users.values())
    db.flush()

    zones = [
        Zone(name="1号楼", zone_type="高层住宅", floor_count=26, current_stage="主体结构", subcontractor_id=subs["huayu"].id, responsible_user_id=users["zeren01"].id),
        Zone(name="2号楼", zone_type="高层住宅", floor_count=26, current_stage="主体结构", subcontractor_id=subs["huayu"].id, responsible_user_id=users["zeren01"].id),
        Zone(name="3号楼", zone_type="高层住宅", floor_count=26, current_stage="主体结构", subcontractor_id=subs["hengsheng"].id, responsible_user_id=users["zeren02"].id),
        Zone(name="4号楼", zone_type="高层住宅", floor_count=26, current_stage="主体结构", subcontractor_id=subs["hengsheng"].id, responsible_user_id=users["zeren02"].id),
        Zone(name="5号楼", zone_type="高层住宅", floor_count=26, current_stage="二次结构", subcontractor_id=subs["hengsheng"].id, responsible_user_id=users["zeren02"].id),
        Zone(name="6号楼", zone_type="高层住宅", floor_count=26, current_stage="二次结构", subcontractor_id=subs["hengsheng"].id, responsible_user_id=users["zeren02"].id),
        Zone(name="地下室区域", zone_type="地下结构", floor_count=2, current_stage="基坑支护/底板", subcontractor_id=subs["guangsha"].id, responsible_user_id=users["zeren04"].id),
        Zone(name="塔吊作业区", zone_type="公共作业区", floor_count=0, current_stage="设备运行", subcontractor_id=subs["xinlong"].id, responsible_user_id=users["zeren05"].id),
        Zone(name="公共区域及消防通道", zone_type="公共区域", floor_count=0, current_stage="日常维护", subcontractor_id=subs["jiecheng"].id, responsible_user_id=users["zeren06"].id),
        Zone(name="材料堆场", zone_type="公共区域", floor_count=0, current_stage="材料管理", subcontractor_id=subs["huayu"].id, responsible_user_id=users["zeren01"].id),
        Zone(name="生活区", zone_type="临建设施", floor_count=0, current_stage="日常管理", subcontractor_id=subs["jiecheng"].id, responsible_user_id=users["zeren06"].id),
    ]
    db.add_all(zones)
    db.flush()

    kb = json.loads(KB_FILE.read_text(encoding="utf-8"))
    for item in kb["regulations"]:
        db.add(
            Regulation(
                doc_name=item["doc_name"],
                clause_no=item["clause_no"],
                title=item["title"],
                content=item["content"],
                tags=item["tags"],
            )
        )
    db.flush()

    # ---- 六周历史工单（状态分布贴近真实治理节奏，含少量超期与待审核） ----
    officer = users["zhangmin"]
    supervisor = users["liqiang"]
    zone_map = {z.name: z for z in zones}
    user_by_id = {u.id: u for u in users.values()}

    # (weeks_ago, [(final_status, count), ...])
    plans = {
        5: [("closed", 8)],
        4: [("closed", 6), ("rejected", 1)],
        3: [("closed", 5), ("recheck", 1), ("rectifying", 1)],
        2: [("closed", 3), ("recheck", 1), ("rectifying", 2), ("dispatched", 1)],
        1: [("closed", 2), ("recheck", 1), ("rectifying", 2), ("dispatched", 2), ("pending_review", 1)],
        0: [("pending_review", 2), ("dispatched", 2), ("rectifying", 2), ("recheck", 1), ("closed", 1)],
    }

    day_counter: dict[str, int] = {}

    def make_order(status: str, weeks_ago: int):
        building, floor, spot, desc, htype, risk = rng.choice(SCENARIOS)
        if weeks_ago == 0:
            max_days = max(now.weekday(), 1)
            created = now - timedelta(days=rng.randint(0, max_days), hours=rng.randint(1, 5), minutes=rng.randint(0, 50))
        else:
            created = now - timedelta(weeks=weeks_ago, days=rng.randint(0, 6), hours=rng.randint(1, 8), minutes=rng.randint(0, 59))
        day = created.strftime("%Y%m%d")
        day_counter[day] = day_counter.get(day, 0) + 1
        order_no = f"ZA-{day}-{day_counter[day]:03d}"

        zone = zone_map.get(building)
        resp_id = zone.responsible_user_id if zone else None
        resp_name = user_by_id[resp_id].name if resp_id else "未指定"
        deadline = created + timedelta(days=RISK_DEADLINE[risk])
        overdue = status in ("dispatched", "rectifying") and deadline < now

        input_type = rng.choices(["text", "voice", "image"], weights=[60, 25, 15])[0]
        loc_text = " ".join(x for x in (building, floor, spot) if x)
        report = Report(
            reporter_id=officer.id,
            input_type=input_type,
            raw_text=f"{loc_text}，{desc}。" if input_type == "text" else f"（{ {'voice': '语音', 'image': '图片'}[input_type] }上报）{loc_text}，{desc}。",
            processed=True,
            created_at=created,
        )
        db.add(report)
        db.flush()

        suggestion = (
            f"【立即措施】{IMMEDIATE_ACTIONS.get(htype, '立即核查现场情况，按项目安全制度组织整改')}。\n"
            f"【整改要求】按{risk}风险等级限期{RISK_DEADLINE[risk]}日内完成整改，期间设置警戒标识，完成后提交复查。\n"
            "【预防措施】纳入班前教育与日常巡查清单，举一反三排查同类隐患。"
        )

        closed_at = created + timedelta(days=rng.randint(1, 3), hours=rng.randint(1, 6)) if status == "closed" else None
        head = f"{building} {floor}".strip()
        order = WorkOrder(
            order_no=order_no,
            report_id=report.id,
            title=f"{head} {htype}隐患",
            building=building,
            floor=floor,
            spot=spot,
            zone_id=zone.id if zone else None,
            hazard_type=htype,
            description=desc,
            risk_level=risk,
            suggestion=suggestion,
            regulation_refs=[],
            source_type=input_type,
            responsible_user_id=resp_id,
            reviewer_id=officer.id if status != "pending_review" else None,
            deadline=deadline,
            status=status,
            overdue=overdue,
            rect_note="已组织班组按规范要求整改完成，现场已恢复。" if status in ("recheck", "closed") else "",
            dispatched_at=created + timedelta(hours=2) if status != "pending_review" else None,
            closed_at=closed_at,
            created_at=created,
            updated_at=closed_at or created,
        )
        db.add(order)
        db.flush()

        def ev(actor, action, detail, at):
            db.add(OrderEvent(order_id=order.id, actor=actor, action=action, detail=detail, created_at=at))

        ev("安全员 张明", "上报隐患", f"{'语音' if input_type == 'voice' else '拍照' if input_type == 'image' else '文字'}上报：{desc}", created)
        ev("筑安云AI", "生成工单草稿", f"信息抽取＋知识检索＋责任匹配完成（建议责任人：{resp_name}）", created + timedelta(minutes=1))
        if status in ("dispatched", "rectifying", "recheck", "closed"):
            ev("安全员 张明", "审核通过·派单", f"工单派发至 {resp_name}", created + timedelta(hours=2))
        if status in ("rectifying", "recheck", "closed"):
            ev(resp_name, "开始整改", "接收工单，组织班组整改", created + timedelta(hours=5))
        if status in ("recheck", "closed"):
            ev(resp_name, "提交复查", "整改完成，申请现场复查", created + timedelta(days=1))
        if status == "closed" and closed_at:
            ev("安全员 张明", "复查合格·闭环", "现场复查符合要求，工单闭环", closed_at)
        if status == "rejected":
            ev("安全员 张明", "驳回", "隐患描述信息不完整，需重新核实后再报", created + timedelta(hours=1))

    for weeks_ago, items in plans.items():
        for status, count in items:
            for _ in range(count):
                make_order(status, weeks_ago)

    db.commit()
