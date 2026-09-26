"""短信发送（阿里云短信服务 Dysmsapi RPC 签名实现，无额外依赖）。

配置见 .env：ALIYUN_SMS_ACCESS_KEY_ID / ALIYUN_SMS_ACCESS_KEY_SECRET /
ALIYUN_SMS_SIGN_NAME / ALIYUN_SMS_TEMPLATE_CODE（模板需含变量 ${code}）。
"""
import base64
import hashlib
import hmac
import logging
import urllib.parse
import uuid

import httpx

from ..config import settings

logger = logging.getLogger("zhuan.sms")

_ENDPOINT = "https://dysmsapi.aliyuncs.com/"


def sms_ready() -> bool:
    return bool(
        settings.aliyun_sms_access_key_id
        and settings.aliyun_sms_access_key_secret
        and settings.aliyun_sms_sign_name
        and settings.aliyun_sms_template_code
    )


def _percent_encode(s: str) -> str:
    return urllib.parse.quote(s, safe="-_.~")


def _sign(params: dict, secret: str) -> str:
    canonical = "&".join(
        f"{_percent_encode(k)}={_percent_encode(v)}" for k, v in sorted(params.items())
    )
    string_to_sign = "GET&%2F&" + _percent_encode(canonical)
    digest = hmac.new((secret + "&").encode(), string_to_sign.encode(), hashlib.sha1).digest()
    return base64.b64encode(digest).decode()


def send_code_sms(phone: str, code: str) -> None:
    if not sms_ready():
        raise RuntimeError("短信服务未配置")
    params = {
        "AccessKeyId": settings.aliyun_sms_access_key_id,
        "Action": "SendSms",
        "Format": "JSON",
        "PhoneNumbers": phone,
        "RegionId": "cn-hangzhou",
        "SignName": settings.aliyun_sms_sign_name,
        "SignatureMethod": "HMAC-SHA1",
        "SignatureNonce": uuid.uuid4().hex,
        "SignatureVersion": "1.0",
        "TemplateCode": settings.aliyun_sms_template_code,
        "TemplateParam": f'{{"code":"{code}"}}',
        "Timestamp": __import__("datetime").datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ"),
        "Version": "2017-05-25",
    }
    params["Signature"] = _sign(params, settings.aliyun_sms_access_key_secret)
    resp = httpx.get(_ENDPOINT, params=params, timeout=15)
    data = resp.json()
    if data.get("Code") != "OK":
        logger.warning("短信发送失败：%s", data)
        raise RuntimeError(f"短信发送失败：{data.get('Message', '未知错误')}")
    logger.info("验证码短信已发送至 %s", phone)
