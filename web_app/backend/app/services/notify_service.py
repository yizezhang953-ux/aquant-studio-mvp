"""Push a short Markdown message to the user's phone: PushPlus, Server酱, or a group-bot webhook
(企业微信 / 钉钉 / 飞书, or any URL that accepts a JSON POST)."""
from __future__ import annotations

import json
import urllib.request
from typing import Any
from urllib.parse import urlencode, urlparse

CHANNELS = {
    "none": "不推送",
    "pushplus": "PushPlus（微信公众号）",
    "serverchan": "Server酱（微信）",
    "webhook": "群机器人 Webhook（企业微信 / 钉钉 / 飞书）",
}
TIMEOUT = 15


def _post(url: str, body: dict[str, Any], form: bool = False) -> dict[str, Any]:
    if form:
        data, content_type = urlencode(body).encode(), "application/x-www-form-urlencoded"
    else:
        data, content_type = json.dumps(body, ensure_ascii=False).encode(), "application/json; charset=utf-8"
    request = urllib.request.Request(url, data=data, headers={"Content-Type": content_type}, method="POST")
    with urllib.request.urlopen(request, timeout=TIMEOUT) as response:  # noqa: S310 (fixed or user-chosen https URL)
        text = response.read().decode("utf-8", "replace")
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return {"raw": text[:200]}


def build_request(channel: str, target: str, title: str, markdown: str) -> tuple[str, dict[str, Any], bool]:
    """(url, body, form-encoded?) for one channel; split out so it can be tested without the network."""
    target = target.strip()
    if channel == "pushplus":
        return "https://www.pushplus.plus/send", {"token": target, "title": title, "content": markdown, "template": "markdown"}, False
    if channel == "serverchan":
        return f"https://sctapi.ftqq.com/{target}.send", {"title": title, "desp": markdown}, True
    if channel == "webhook":
        parsed = urlparse(target)
        if parsed.scheme != "https":
            raise ValueError("Webhook 地址要以 https:// 开头")
        host = parsed.hostname or ""
        if host.endswith("qyapi.weixin.qq.com"):
            return target, {"msgtype": "markdown", "markdown": {"content": f"### {title}\n{markdown}"}}, False
        if host.endswith("dingtalk.com"):
            return target, {"msgtype": "markdown", "markdown": {"title": title, "text": f"### {title}\n{markdown}"}}, False
        if host.endswith("feishu.cn") or host.endswith("larksuite.com"):
            return target, {"msg_type": "text", "content": {"text": f"{title}\n{markdown}"}}, False
        return target, {"title": title, "text": markdown}, False
    raise ValueError(f"未知的推送方式 {channel}")


def _check(channel: str, reply: dict[str, Any]) -> None:
    """Each service answers HTTP 200 even when the token is wrong; read its own error code."""
    code = reply.get("code", reply.get("errcode", reply.get("StatusCode", 0)))
    ok_codes = {200} if channel == "pushplus" else {0}
    if code not in ok_codes and code is not None:
        message = reply.get("msg") or reply.get("message") or reply.get("errmsg") or reply.get("StatusMessage") or code
        raise ValueError(f"推送服务返回错误：{message}")


def send(channel: str, target: str, title: str, markdown: str) -> None:
    if channel == "none":
        return
    if not target.strip():
        raise ValueError("还没有填写推送的 token / 地址")
    url, body, form = build_request(channel, target, title, markdown)
    try:
        reply = _post(url, body, form)
    except OSError as exc:
        raise ValueError(f"连不上推送服务：{exc}") from exc
    _check(channel, reply)
