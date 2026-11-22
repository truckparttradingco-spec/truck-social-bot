"""Interactive connection wizard (`python main.py setup`) and connection tester
(`python main.py test`).  Secrets are typed on the user's own machine and are
written to .env only."""
from __future__ import annotations

import getpass
import io
import os
from pathlib import Path

import requests
from PIL import Image

from .config import ROOT

ENV_PATH = ROOT / ".env"


# --------------------------------------------------------------------------
# .env helpers
# --------------------------------------------------------------------------
def save_env(values: dict[str, str], path: Path | None = None) -> None:
    path = path or ENV_PATH
    lines = path.read_text(encoding="utf-8").splitlines() if path.exists() else []
    if not lines and (ROOT / ".env.example").exists():
        lines = (ROOT / ".env.example").read_text(encoding="utf-8").splitlines()
    done = set()
    for i, line in enumerate(lines):
        key = line.split("=", 1)[0].strip()
        if key in values and "=" in line and not line.strip().startswith("#"):
            lines[i] = f"{key}={values[key]}"
            done.add(key)
    for k, v in values.items():
        if k not in done:
            lines.append(f"{k}={v}")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    for k, v in values.items():
        os.environ[k] = v
    try:
        path.chmod(0o600)
    except OSError:
        pass


def _ask(prompt: str, secret: bool = False, default: str = "") -> str:
    suffix = f" [{default}]" if default else ""
    val = (getpass.getpass if secret else input)(f"{prompt}{suffix}: ").strip()
    return val or default


def _yes(prompt: str, default: bool = True) -> bool:
    d = "Y/n" if default else "y/N"
    a = input(f"{prompt} ({d}): ").strip().lower()
    return default if not a else a in ("y", "yes", "ب", "بله")


def _err(r: requests.Response) -> str:
    try:
        j = r.json()
    except ValueError:
        return r.text[:200]
    e = j.get("error") or j
    return e.get("message", str(e)) if isinstance(e, dict) else str(e)


# --------------------------------------------------------------------------
# Telegram
# --------------------------------------------------------------------------
def tg_check(token: str, chat: str, send_test: bool = False) -> tuple[bool, str]:
    base = f"https://api.telegram.org/bot{token}"
    try:
        r = requests.get(f"{base}/getMe", timeout=30)
        j = r.json()
        if not j.get("ok"):
            return False, f"Bot token rejected: {j.get('description')}"
        bot = j["result"]
        r = requests.get(f"{base}/getChat", params={"chat_id": chat}, timeout=30).json()
        if not r.get("ok"):
            return False, f"Channel '{chat}' not found: {r.get('description')} (is the bot added to the channel?)"
        title = r["result"].get("title", chat)
        m = requests.get(f"{base}/getChatMember", params={"chat_id": chat, "user_id": bot["id"]}, timeout=30).json()
        status = m.get("result", {}).get("status") if m.get("ok") else None
        if status not in ("administrator", "creator"):
            return False, f"Bot @{bot['username']} found channel '{title}' but is not an admin there (status: {status})"
        if send_test:
            s = requests.post(f"{base}/sendMessage", data={"chat_id": chat, "text": "✅ Connection test from Truck Part Trading bot"}, timeout=30).json()
            if not s.get("ok"):
                return False, f"Cannot post: {s.get('description')} (give the bot 'Post messages' permission)"
        return True, f"@{bot['username']} is admin of '{title}'" + (" - test message sent" if send_test else "")
    except requests.RequestException as e:
        return False, f"Network error: {e}"


def setup_telegram() -> None:
    print("\n=== Telegram ===")
    print("1) In Telegram open @BotFather -> /newbot -> copy the token.")
    print("2) Add the bot to your channel as Administrator (permission: Post messages).")
    if not _yes("Set up Telegram now?"):
        return
    token = _ask("Bot token", secret=True, default=os.environ.get("TG_BOT_TOKEN", ""))
    chat = _ask("Channel username, e.g. @mychannel", default=os.environ.get("TG_CHAT_ID", ""))
    ok, msg = tg_check(token, chat, send_test=_yes("Send a visible test message to the channel?", False))
    print(("OK  " if ok else "FAIL ") + msg)
    if ok or _yes("Save anyway?", False):
        save_env({"TG_BOT_TOKEN": token, "TG_CHAT_ID": chat})


# --------------------------------------------------------------------------
# Meta (Facebook Page + Instagram)
# --------------------------------------------------------------------------
def meta_pages(user_token: str, version: str) -> list[dict]:
    r = requests.get(f"https://graph.facebook.com/{version}/me/accounts",
                     params={"fields": "id,name,access_token,instagram_business_account{id,username}",
                             "limit": 100, "access_token": user_token}, timeout=60)
    if r.status_code >= 400:
        raise RuntimeError(_err(r))
    return r.json().get("data", [])


def meta_exchange(app_id: str, secret: str, short_token: str, version: str) -> str:
    r = requests.get(f"https://graph.facebook.com/{version}/oauth/access_token",
                     params={"grant_type": "fb_exchange_token", "client_id": app_id,
                             "client_secret": secret, "fb_exchange_token": short_token}, timeout=60)
    if r.status_code >= 400:
        raise RuntimeError(_err(r))
    return r.json()["access_token"]


def setup_meta(version: str) -> None:
    print("\n=== Facebook Page + Instagram ===")
    print("Needs: a Facebook Page, an Instagram Business/Creator account linked to that Page, and a Meta app")
    print("(developers.facebook.com -> My Apps -> Create App -> type 'Business').")
    print("Then in Tools -> Graph API Explorer: pick your app, click 'Generate Access Token' with these permissions:")
    print("  pages_show_list, pages_read_engagement, pages_manage_posts,")
    print("  instagram_basic, instagram_content_publish, business_management")
    if not _yes("Set up Facebook/Instagram now?"):
        return
    app_id = _ask("App ID")
    secret = _ask("App Secret (Settings -> Basic)", secret=True)
    short = _ask("Token from Graph API Explorer", secret=True)
    try:
        long_token = meta_exchange(app_id, secret, short, version)
        pages = meta_pages(long_token, version)
    except (RuntimeError, requests.RequestException) as e:
        print("FAIL", e)
        return
    if not pages:
        print("FAIL no Page found for this token. Check the permissions above and that you are admin of the Page.")
        return
    print("\nPages you manage:")
    for i, p in enumerate(pages, 1):
        ig = p.get("instagram_business_account", {}).get("username")
        print(f"  {i}) {p['name']}   instagram: {('@' + ig) if ig else 'NOT LINKED'}")
    idx = int(_ask("Choose a number", default="1")) - 1
    page = pages[idx]
    values = {"FB_PAGE_ID": page["id"], "FB_PAGE_TOKEN": page["access_token"]}
    ig = page.get("instagram_business_account")
    if ig:
        values["IG_USER_ID"] = ig["id"]
        values["IG_ACCESS_TOKEN"] = page["access_token"]        # page token also publishes to the linked IG account
        print(f"Instagram @{ig.get('username')} found.")
    else:
        print("This Page has no linked Instagram Business account -> Instagram skipped. Link it in Instagram: "
              "Settings -> Account type -> Business, and Page settings -> Linked accounts.")
    save_env(values)
    print("Saved. (Page tokens made from a long-lived token do not expire.)")


# --------------------------------------------------------------------------
# Cloudinary (public URL for Instagram)
# --------------------------------------------------------------------------
def _tiny_jpeg() -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (64, 64), (255, 122, 26)).save(buf, "JPEG")
    return buf.getvalue()


def cloudinary_check(cloud: str, preset: str) -> tuple[bool, str]:
    try:
        r = requests.post(f"https://api.cloudinary.com/v1_1/{cloud}/image/upload",
                          data={"upload_preset": preset, "folder": "truck-part-trading"},
                          files={"file": ("test.jpg", _tiny_jpeg(), "image/jpeg")}, timeout=60)
        j = r.json()
        if r.status_code >= 400 or "secure_url" not in j:
            return False, j.get("error", {}).get("message", str(j))
        h = requests.head(j["secure_url"], timeout=30)
        return h.status_code == 200, f"upload OK, public URL returns HTTP {h.status_code}"
    except requests.RequestException as e:
        return False, f"Network error: {e}"


def setup_cloudinary() -> None:
    print("\n=== Image hosting for Instagram (Cloudinary, free) ===")
    print("Instagram downloads the image from a public link. Create an account at cloudinary.com, then:")
    print("Settings -> Upload -> Add upload preset -> Signing mode: UNSIGNED -> Save.")
    if not _yes("Set up Cloudinary now?"):
        return
    cloud = _ask("Cloud name (shown on the dashboard)", default=os.environ.get("CLOUDINARY_CLOUD_NAME", ""))
    preset = _ask("Upload preset name", default=os.environ.get("CLOUDINARY_UPLOAD_PRESET", ""))
    ok, msg = cloudinary_check(cloud, preset)
    print(("OK  " if ok else "FAIL ") + msg)
    if ok or _yes("Save anyway?", False):
        save_env({"CLOUDINARY_CLOUD_NAME": cloud, "CLOUDINARY_UPLOAD_PRESET": preset})


def run_wizard(cfg: dict) -> None:
    version = cfg.get("graph_api_version", "v23.0")
    print("Connection wizard - secrets are stored only in .env on this computer.")
    setup_telegram()
    setup_meta(version)
    if cfg["platforms"].get("instagram"):
        setup_cloudinary()
    print("\nDone. Verify everything with:  python main.py test")


# --------------------------------------------------------------------------
# Tester
# --------------------------------------------------------------------------
def run_test(cfg: dict, send_test: bool = False) -> bool:
    version = cfg.get("graph_api_version", "v23.0")
    env = os.environ
    all_ok = True

    def report(name: str, ok: bool, msg: str):
        nonlocal all_ok
        all_ok &= ok
        print(f"[{'OK' if ok else 'FAIL':4s}] {name:10s} {msg}")

    if cfg["platforms"].get("telegram"):
        if env.get("TG_BOT_TOKEN") and env.get("TG_CHAT_ID"):
            report("telegram", *tg_check(env["TG_BOT_TOKEN"], env["TG_CHAT_ID"], send_test))
        else:
            report("telegram", False, "TG_BOT_TOKEN / TG_CHAT_ID missing (run: python main.py setup)")
    if cfg["platforms"].get("facebook"):
        if env.get("FB_PAGE_ID") and env.get("FB_PAGE_TOKEN"):
            r = requests.get(f"https://graph.facebook.com/{version}/{env['FB_PAGE_ID']}",
                             params={"fields": "name", "access_token": env["FB_PAGE_TOKEN"]}, timeout=60)
            report("facebook", r.status_code < 400, f"Page '{r.json().get('name')}'" if r.status_code < 400 else _err(r))
        else:
            report("facebook", False, "FB_PAGE_ID / FB_PAGE_TOKEN missing")
    if cfg["platforms"].get("instagram"):
        if env.get("IG_USER_ID") and env.get("IG_ACCESS_TOKEN"):
            r = requests.get(f"https://graph.facebook.com/{version}/{env['IG_USER_ID']}",
                             params={"fields": "username,media_count", "access_token": env["IG_ACCESS_TOKEN"]}, timeout=60)
            report("instagram", r.status_code < 400,
                   f"@{r.json().get('username')} ({r.json().get('media_count')} posts)" if r.status_code < 400 else _err(r))
        else:
            report("instagram", False, "IG_USER_ID / IG_ACCESS_TOKEN missing")
        mode = cfg.get("hosting", {}).get("mode")
        if mode == "cloudinary":
            if env.get("CLOUDINARY_CLOUD_NAME") and env.get("CLOUDINARY_UPLOAD_PRESET"):
                report("hosting", *cloudinary_check(env["CLOUDINARY_CLOUD_NAME"], env["CLOUDINARY_UPLOAD_PRESET"]))
            else:
                report("hosting", False, "CLOUDINARY_CLOUD_NAME / CLOUDINARY_UPLOAD_PRESET missing")
        else:
            report("hosting", mode == "static" and bool(cfg["hosting"].get("public_base_url")), f"mode: {mode}")
    print("\nAll good - you can run:  python main.py post --dry-run  then  python main.py post" if all_ok
          else "\nFix the FAIL lines above (python main.py setup), then run this test again.")
    return all_ok
