"""邮件发送（注册验证码）。配置见 .env：SMTP_HOST/SMTP_PORT/SMTP_USER/SMTP_PASS。

推荐 QQ 邮箱：设置 → 账户 → 开启 SMTP 服务 → 获取授权码（免费）。
SMTP_PORT=465 时使用 SSL，587 时使用 STARTTLS。
"""
import logging
import smtplib
from email.header import Header
from email.mime.text import MIMEText
from email.utils import formataddr

from ..config import settings

logger = logging.getLogger("zhuan.mailer")


def smtp_ready() -> bool:
    return bool(settings.smtp_host and settings.smtp_user and settings.smtp_pass)


def send_code_email(to: str, code: str) -> None:
    if not smtp_ready():
        raise RuntimeError("邮件服务未配置")
    subject = "筑安云注册验证码"
    text = (
        f"您好！\n\n您正在注册筑安云账号，验证码为：{code}\n\n"
        f"验证码 10 分钟内有效，请勿泄露给他人。如非本人操作，请忽略本邮件。\n\n—— 筑安云"
    )
    html = (
        f'<div style="font-family:Microsoft YaHei,sans-serif;max-width:520px;margin:0 auto">'
        f'<h2 style="color:#1d5bd8">筑安云</h2><p>您正在注册筑安云账号，验证码为：</p>'
        f'<p style="font-size:30px;font-weight:700;letter-spacing:8px;color:#1d5bd8">{code}</p>'
        f'<p style="color:#888">验证码 10 分钟内有效，请勿泄露给他人。如非本人操作，请忽略本邮件。</p></div>'
    )
    msg = MIMEText(html, "html", "utf-8")
    msg["Subject"] = Header(subject, "utf-8")
    msg["From"] = formataddr(("筑安云", settings.smtp_from or settings.smtp_user))
    msg["To"] = to

    port = settings.smtp_port
    if port == 465:
        server = smtplib.SMTP_SSL(settings.smtp_host, port, timeout=15)
    else:
        server = smtplib.SMTP(settings.smtp_host, port, timeout=15)
        server.starttls()
    try:
        server.login(settings.smtp_user, settings.smtp_pass)
        server.sendmail(settings.smtp_from or settings.smtp_user, [to], msg.as_string())
    finally:
        server.quit()
    logger.info("验证码邮件已发送至 %s", to)
