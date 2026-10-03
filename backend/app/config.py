from pathlib import Path

from pydantic_settings import BaseSettings

BASE_DIR = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    # 数据库：阿里云 MySQL（答辩演示主库）；连不上时自动回退本地 SQLite
    db_host: str = "127.0.0.1"
    db_port: int = 3306
    db_user: str = "root"
    db_password: str = ""
    db_name: str = "csu"

    # AI 模式：True=内置模拟引擎(零API消耗) False=调用通义千问真实模型
    mock_mode: bool = True
    dashscope_api_key: str = ""
    qwen_text_model: str = "qwen-flash"
    qwen_vl_model: str = "qwen-vl-plus"
    qwen_embed_model: str = "text-embedding-v4"
    qwen_asr_model: str = "qwen3-asr-flash"
    # 通过真实模式依据核验验收后开启，可用环境变量回退。
    rag_evidence_check_enabled: bool = False

    token_secret: str = "zhuan-cloud-demo-secret-2026"
    token_expire_minutes: int = 4320  # 3天

    # 注册验证码：邮件 SMTP（推荐 QQ/163 邮箱授权码）
    smtp_host: str = ""
    smtp_port: int = 465
    smtp_user: str = ""
    smtp_pass: str = ""
    smtp_from: str = ""
    # 短信验证码（阿里云短信服务，可选）
    aliyun_sms_access_key_id: str = ""
    aliyun_sms_access_key_secret: str = ""
    aliyun_sms_sign_name: str = ""
    aliyun_sms_template_code: str = ""

    upload_dir: Path = BASE_DIR / "uploads"
    frontend_dist: Path = BASE_DIR.parent / "frontend" / "dist"

    class Config:
        env_file = BASE_DIR / ".env"
        env_file_encoding = "utf-8"


settings = Settings()
settings.upload_dir.mkdir(parents=True, exist_ok=True)
