import unittest

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.agents.chat_agent import _pending_action
from app.database import Base
from app.models import ChatMessage, ChatPendingAction, ChatSession, Project, User
from app.routers.chat import resolve_action
from app.schemas import ChatActionIn


class ChatActionProtocolTest(unittest.TestCase):
    def setUp(self):
        engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(engine)
        self.db = sessionmaker(bind=engine, expire_on_commit=False)()
        self.user = User(username="pm", password_hash="x", name="项目经理", role="project_manager")
        self.project = Project(name="当前项目")
        self.db.add_all([self.user, self.project])
        self.db.commit()

    def tearDown(self):
        self.db.close()

    def test_confirm_executes_once(self):
        artifact = _pending_action(
            self.db,
            self.user,
            self.project,
            "create_project",
            {"name": "确认后创建"},
        )
        self.db.flush()
        session = ChatSession(user_id=self.user.id, project_id=self.project.id, assistant="pm", title="测试")
        self.db.add(session)
        self.db.flush()
        message = ChatMessage(session_id=session.id, role="assistant", content="", artifacts=[artifact])
        self.db.add(message)
        self.db.flush()
        action = self.db.query(ChatPendingAction).filter(ChatPendingAction.token == artifact["data"]["token"]).one()
        action.message_id = message.id
        self.db.commit()

        result = resolve_action(
            artifact["data"]["token"],
            ChatActionIn(confirm=True),
            self.db,
            self.user,
            self.project,
        )

        self.assertTrue(result["ok"])
        self.assertEqual(result["artifact"]["data"]["status"], "completed")
        self.assertEqual(self.db.query(Project).filter(Project.name == "确认后创建").count(), 1)
        self.db.refresh(message)
        self.assertEqual(message.artifacts[0]["data"]["status"], "completed")

        with self.assertRaises(Exception):
            resolve_action(
                artifact["data"]["token"],
                ChatActionIn(confirm=True),
                self.db,
                self.user,
                self.project,
            )

    def test_cancel_does_not_execute(self):
        artifact = _pending_action(
            self.db,
            self.user,
            self.project,
            "create_project",
            {"name": "不应创建"},
        )
        self.db.commit()

        result = resolve_action(
            artifact["data"]["token"],
            ChatActionIn(confirm=False),
            self.db,
            self.user,
            self.project,
        )

        self.assertTrue(result["ok"])
        self.assertEqual(result["artifact"]["data"]["status"], "cancelled")
        self.assertEqual(self.db.query(Project).filter(Project.name == "不应创建").count(), 0)


if __name__ == "__main__":
    unittest.main()
