# 筑安云 ZhuAnCloud

> 工地安全隐患"上报 → 处置 → 闭环 → 复盘"AI协同平台
> **把案头交给AI，把安全留给现场。**

第一届"海之子杯"AI智能体大赛参赛作品。安全员通过**文字 / 语音 / 图片**上报隐患，
AI自动完成**信息抽取 → 知识库检索（规范条款）→ 风险定级 → 处置建议 → 责任人匹配 → 生成整改工单（人工审核）→ 派发 → 整改跟进（附整改照片）→ 超期预警 → 按风险等级汇总周报**。

支持**邮箱验证码注册登录**（手机号短信通道预留，接口已实现），新用户默认安全员角色。

背景项目：三河市保障性租赁住房项目（公开招标信息提炼，12栋一类高层住宅+10栋多层公共建筑，约14.75万㎡）。分包单位、人员、制度为演示用合理虚构，已在文档中标注。

## 技术栈

| 层 | 选型 | 说明 |
|---|---|---|
| Agent编排 | **LangGraph** 状态机 | 抽取→追问判定→检索→定级→匹配→工单草稿，节点可独立替换引擎 |
| 后端 | **FastAPI** + SQLAlchemy 2.0 | REST API，多层角色权限 |
| 前端 | **Vue3 + Element Plus + ECharts** | 四角色工作台、AI对话、数据看板 |
| 数据库 | **MySQL 8.4**（阿里云） | SQLite本地兜底开关，演示断网不翻车 |
| 知识库 | 规范条款 + 轻量向量检索 | 真实模式=通义text-embedding-v4余弦；模拟模式=bigram相似度 |
| 大模型 | 通义千问（DashScope兼容模式） | qwen-flash文本 / qwen-vl-plus图片 / qwen3-asr-flash语音 |

**双模式设计**：`MOCK_MODE=true`（默认）时全部AI能力走内置模拟引擎，**零API消耗**；
填入 `DASHSCOPE_API_KEY` 并将 `MOCK_MODE` 改为 `false` 即切换真实AI，前端横幅自动显示当前引擎。

## 快速启动（本地演示）

```bash
# 1. 后端（首次运行自动建表+灌入演示数据）
cd backend
python -m venv .venv                      # Python 3.12+
.venv\Scripts\activate
pip install -r requirements.txt -i https://mirrors.aliyun.com/pypi/simple/
# 编辑 .env：填数据库连接（可先用SQLite：把DB_HOST改成一个不可达地址即自动兜底）
python -m uvicorn app.main:app --port 8000

# 2. 前端（开发模式）
cd frontend
npm install --registry=https://registry.npmmirror.com
npm run dev        # http://localhost:5173

# 3. 或直接访问后端托管的构建产物 http://127.0.0.1:8000
```

Windows下双击 `scripts/start_all.bat` 一键启动（后端+前端开发服务）。

## 演示账号（密码均为 `zhuan@123`）

| 角色 | 账号 | 说明 |
|---|---|---|
| 安全员 张明 | `zhangmin` | 上报隐患、审核派单、复查闭环 |
| 安全总监 李强 | `liqiang` | 看板/周报；重大风险工单须由其复核 |
| 项目经理 王建国 | `wangjianguo` | 看板/周报 |
| 分包责任人（6人） | `zeren01`~`zeren06` | 接收工单、整改、提交复查 |

## 工单状态机

```
上报 → AI生成草稿 → [待审核] --安全员审核通过--> [已派发] --责任人--> [整改中]
                    |                              |                     |
                    驳回                     延期/超期预警           责任人提交
                    ↓                              ↓                     ↓
                 [已驳回]                      （催办）              [待复查] --安全员复查合格--> [已闭环]
                                                              |不合格退回→ 整改中
```

- **重大风险工单**须由安全总监（而非安全员）复核后派单；
- 超期工单在所有列表/看板自动标红预警；
- 每一步流转写入 `order_events`，全程可追溯。

## 知识库

`backend/knowledge/regulations.json`：49条精选条款（GB 55034-2022强制性规范、JGJ 80-2016高处作业、
JGJ 130-2011脚手架、GB 50720-2011消防、JGJ 46-2005临时用电、JGJ 196-2010塔吊、JGJ 215-2010升降机、
GB 50497-2019基坑监测、项目安全管理制度）。条款为要点精简演示版，正式使用以现行有效文本为准。

## 项目结构

```
zhuan-cloud/
├── backend/
│   ├── app/
│   │   ├── agents/        # LangGraph流水线、抽取/定级/匹配引擎、LLM抽象
│   │   ├── rag/           # 知识检索（向量/关键词双模式）
│   │   ├── routers/       # auth/meta/reports/orders/chat/stats/weekly/media
│   │   ├── services/      # 语音转写、图片识别、周报生成、Word导出
│   │   ├── models.py      # 9张表：users/subcontractors/zones/reports/work_orders/order_events/regulations/weekly_reports/projects
│   │   └── seed.py        # 幂等演示数据：项目/分包/人员/分区/条款/六周历史工单
│   └── knowledge/         # 规范条款知识库
├── frontend/              # Vue3 + Element Plus + ECharts
└── scripts/               # 一键启动脚本
```

## 安全提示

`.env` 含数据库口令，已在 `.gitignore` 排除，**严禁提交**。演示环境数据库请勿使用生产口令。
