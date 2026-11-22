from __future__ import annotations

import logging
import time
from pathlib import Path

import requests

log = logging.getLogger("tsb")


class PublishError(RuntimeError):
    pass


def _check(r: requests.Response, what: str) -> dict:
    try:
        j = r.json()
    except ValueError:
        raise PublishError(f"{what}: non-JSON response ({r.status_code}): {r.text[:200]}")
    if r.status_code >= 400 or (isinstance(j, dict) and ("error" in j or j.get("ok") is False)):
        raise PublishError(f"{what}: {j}")
    return j


class Instagram:
    name = "instagram"

    def __init__(self, env: dict, version: str):
        self.uid = env.get("IG_USER_ID")
        self.token = env.get("IG_ACCESS_TOKEN")
        if not self.uid or not self.token:
            raise PublishError("IG_USER_ID / IG_ACCESS_TOKEN missing")
        self.base = f"https://graph.facebook.com/{version}"

    def _post(self, path: str, **data) -> dict:
        r = requests.post(f"{self.base}/{path}", data={**data, "access_token": self.token}, timeout=90)
        return _check(r, f"instagram {path}")

    def _wait_ready(self, container_id: str, tries: int = 20) -> None:
        for _ in range(tries):
            r = requests.get(f"{self.base}/{container_id}",
                             params={"fields": "status_code", "access_token": self.token}, timeout=60)
            status = _check(r, "instagram status").get("status_code")
            if status == "FINISHED":
                return
            if status in ("ERROR", "EXPIRED"):
                raise PublishError(f"instagram container status {status}")
            time.sleep(3)
        raise PublishError("instagram container not ready in time")

    def _publish(self, **media) -> str:
        cid = self._post(f"{self.uid}/media", **media)["id"]
        self._wait_ready(cid)
        return self._post(f"{self.uid}/media_publish", creation_id=cid)["id"]

    def post_photo(self, image_url: str, caption: str) -> str:
        return self._publish(image_url=image_url, caption=caption)

    def post_story(self, image_url: str) -> str:
        return self._publish(image_url=image_url, media_type="STORIES")


class Facebook:
    name = "facebook"

    def __init__(self, env: dict, version: str):
        self.page = env.get("FB_PAGE_ID")
        self.token = env.get("FB_PAGE_TOKEN")
        if not self.page or not self.token:
            raise PublishError("FB_PAGE_ID / FB_PAGE_TOKEN missing")
        self.base = f"https://graph.facebook.com/{version}"

    def _upload(self, path: Path, **data) -> dict:
        with open(path, "rb") as f:
            r = requests.post(f"{self.base}/{self.page}/photos",
                              data={**data, "access_token": self.token},
                              files={"source": (path.name, f, "image/jpeg")}, timeout=120)
        return _check(r, "facebook photos")

    def post_photo(self, path: Path, caption: str) -> str:
        return self._upload(path, message=caption).get("post_id") or ""

    def post_story(self, path: Path) -> str:
        photo_id = self._upload(path, published="false")["id"]
        r = requests.post(f"{self.base}/{self.page}/photo_stories",
                          data={"photo_id": photo_id, "access_token": self.token}, timeout=90)
        return str(_check(r, "facebook photo_stories").get("post_id", photo_id))


class Telegram:
    name = "telegram"

    def __init__(self, env: dict):
        self.token = env.get("TG_BOT_TOKEN")
        self.chat = env.get("TG_CHAT_ID")
        if not self.token or not self.chat:
            raise PublishError("TG_BOT_TOKEN / TG_CHAT_ID missing")

    def post_photo(self, path: Path, caption_html: str) -> str:
        with open(path, "rb") as f:
            r = requests.post(f"https://api.telegram.org/bot{self.token}/sendPhoto",
                              data={"chat_id": self.chat, "caption": caption_html, "parse_mode": "HTML"},
                              files={"photo": (path.name, f, "image/jpeg")}, timeout=120)
        return str(_check(r, "telegram sendPhoto")["result"]["message_id"])
