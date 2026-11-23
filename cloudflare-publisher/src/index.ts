export interface Env {
  DB: D1Database;
  MEDIA: R2Bucket;
  META_APP_ID: string;
  META_APP_SECRET: string;
  META_REDIRECT_URI: string;
  ADMIN_KEY: string;
  TOKEN_ENCRYPTION_KEY: string;
  PUBLIC_MEDIA_BASE_URL: string;
  META_API_VERSION?: string;
  APP_TIMEZONE?: string;
  POSTING_SLOTS?: string;
}

type MediaRow = {
  id: string; product_id: string; title: string;
  media_type: "IMAGE" | "VIDEO"; media_url: string;
};

const json = (data: unknown, status = 200) =>
  new Response(JSON.stringify(data), { status, headers: { "content-type": "application/json; charset=utf-8" } });

const nowIso = () => new Date().toISOString();
const apiVersion = (env: Env) => env.META_API_VERSION || "v26.0";
const graphBase = (env: Env) => `https://graph.instagram.com/${apiVersion(env)}`;

function corsHeaders() {
  return { "access-control-allow-origin": "*", "access-control-allow-methods": "GET,POST,DELETE,OPTIONS", "access-control-allow-headers": "content-type,x-admin-key" };
}

async function encryptToken(token: string, secret: string): Promise<string> {
  const raw = Uint8Array.from(atob(secret), c => c.charCodeAt(0));
  if (raw.length !== 32) throw new Error("TOKEN_ENCRYPTION_KEY must be base64 for exactly 32 bytes");
  const key = await crypto.subtle.importKey("raw", raw, "AES-GCM", false, ["encrypt"]);
  const iv = crypto.getRandomValues(new Uint8Array(12));
  const ciphertext = await crypto.subtle.encrypt({ name: "AES-GCM", iv }, key, new TextEncoder().encode(token));
  const combined = new Uint8Array(iv.length + ciphertext.byteLength);
  combined.set(iv); combined.set(new Uint8Array(ciphertext), iv.length);
  return btoa(String.fromCharCode(...combined));
}

async function decryptToken(value: string, secret: string): Promise<string> {
  const raw = Uint8Array.from(atob(secret), c => c.charCodeAt(0));
  if (raw.length !== 32) throw new Error("TOKEN_ENCRYPTION_KEY must be base64 for exactly 32 bytes");
  const combined = Uint8Array.from(atob(value), c => c.charCodeAt(0));
  const key = await crypto.subtle.importKey("raw", raw, "AES-GCM", false, ["decrypt"]);
  const plain = await crypto.subtle.decrypt({ name: "AES-GCM", iv: combined.slice(0, 12) }, key, combined.slice(12));
  return new TextDecoder().decode(plain);
}

function isAdmin(req: Request, env: Env) {
  return !!env.ADMIN_KEY && req.headers.get("x-admin-key") === env.ADMIN_KEY;
}

async function adminRoute(req: Request, env: Env, url: URL): Promise<Response> {
  if (!isAdmin(req, env)) return json({ error: "unauthorized" }, 401);

  if (url.pathname === "/api/state" && req.method === "GET") {
    const account = await env.DB.prepare("SELECT ig_user_id, username, connected_at, token_expires_at FROM instagram_account WHERE id=1").first();
    const enabled = await env.DB.prepare("SELECT value FROM settings WHERE key='enabled'").first<{value:string}>();
    const media = await env.DB.prepare("SELECT id, product_id, title, media_type, media_url, enabled, created_at FROM media ORDER BY created_at DESC").all();
    const logs = await env.DB.prepare("SELECT product_id, feed_status, story_status, error, published_at FROM publish_log ORDER BY id DESC LIMIT 20").all();
    return json({ account, enabled: enabled?.value === "true", media: media.results, logs: logs.results });
  }

  if (url.pathname === "/api/settings" && req.method === "POST") {
    const body = await req.json() as { enabled?: boolean };
    await env.DB.prepare("INSERT INTO settings(key,value) VALUES('enabled',?) ON CONFLICT(key) DO UPDATE SET value=excluded.value")
      .bind(body.enabled ? "true" : "false").run();
    return json({ ok: true, enabled: !!body.enabled });
  }

  if (url.pathname === "/api/media" && req.method === "POST") {
    const body = await req.json() as { product_id?: string; title?: string; media_type?: string; media_url?: string };
    if (!body.product_id || !body.title || !body.media_url || !/^https:\/\//i.test(body.media_url)) return json({ error: "product_id, title and public https media_url are required" }, 400);
    if (body.media_type !== "IMAGE" && body.media_type !== "VIDEO") return json({ error: "media_type must be IMAGE or VIDEO" }, 400);
    const id = crypto.randomUUID();
    await env.DB.prepare("INSERT INTO media(id,product_id,title,media_type,media_url,created_at) VALUES(?,?,?,?,?,?)")
      .bind(id, body.product_id.trim(), body.title.trim(), body.media_type, body.media_url, nowIso()).run();
    return json({ ok: true, id });
  }

  if (url.pathname === "/api/upload" && req.method === "POST") {
    if (!env.PUBLIC_MEDIA_BASE_URL) return json({ error: "Set PUBLIC_MEDIA_BASE_URL to the public R2 custom domain first" }, 400);
    const form = await req.formData();
    const file = form.get("file");
    const productId = String(form.get("product_id") || "").trim();
    const title = String(form.get("title") || "").trim();
    if (!(file instanceof File) || !productId || !title) return json({ error: "file, product_id and title are required" }, 400);
    if (file.size > 100 * 1024 * 1024) return json({ error: "Maximum upload size is 100 MB" }, 413);
    const type = file.type.startsWith("image/") ? "IMAGE" : file.type.startsWith("video/") ? "VIDEO" : null;
    if (!type) return json({ error: "Only image and video files are supported" }, 400);
    const ext = (file.name.split(".").pop() || (type === "IMAGE" ? "jpg" : "mp4")).replace(/[^a-z0-9]/gi, "").toLowerCase();
    const key = `media/${crypto.randomUUID()}.${ext}`;
    await env.MEDIA.put(key, file.stream(), { httpMetadata: { contentType: file.type } });
    const mediaUrl = `${env.PUBLIC_MEDIA_BASE_URL.replace(/\/$/, "")}/${key}`;
    const id = crypto.randomUUID();
    await env.DB.prepare("INSERT INTO media(id,product_id,title,media_type,media_url,created_at) VALUES(?,?,?,?,?,?)")
      .bind(id, productId, title, type, mediaUrl, nowIso()).run();
    return json({ ok: true, id, media_url: mediaUrl });
  }

  if (url.pathname.startsWith("/api/media/") && req.method === "DELETE") {
    const id = url.pathname.split("/").pop();
    await env.DB.prepare("UPDATE media SET enabled=0 WHERE id=?").bind(id).run();
    return json({ ok: true });
  }

  if (url.pathname === "/api/run-now" && req.method === "POST") {
    const result = await runSlot(env, "manual-" + new Date().toISOString().replace(/[:.]/g, "-"), true);
    return json(result);
  }

  return json({ error: "not found" }, 404);
}

async function exchangeInstagramCode(code: string, env: Env) {
  const form = new FormData();
  form.set("client_id", env.META_APP_ID);
  form.set("client_secret", env.META_APP_SECRET);
  form.set("grant_type", "authorization_code");
  form.set("redirect_uri", env.META_REDIRECT_URI);
  form.set("code", code);
  const shortRes = await fetch("https://api.instagram.com/oauth/access_token", { method: "POST", body: form });
  const shortData = await shortRes.json() as any;
  if (!shortRes.ok || !shortData.access_token) throw new Error(shortData.error_message || "Instagram code exchange failed");

  const longUrl = new URL("https://graph.instagram.com/access_token");
  longUrl.searchParams.set("grant_type", "ig_exchange_token");
  longUrl.searchParams.set("client_secret", env.META_APP_SECRET);
  longUrl.searchParams.set("access_token", shortData.access_token);
  const longRes = await fetch(longUrl);
  const longData = await longRes.json() as any;
  if (!longRes.ok || !longData.access_token) throw new Error(longData.error?.message || "Long-lived token exchange failed");
  return { token: longData.access_token as string, expiresIn: Number(longData.expires_in || 5184000) };
}

async function oauthCallback(url: URL, env: Env): Promise<Response> {
  const error = url.searchParams.get("error");
  if (error) return new Response(`Instagram authorization failed: ${url.searchParams.get("error_description") || error}`, { status: 400 });
  const code = url.searchParams.get("code");
  const state = url.searchParams.get("state");
  if (!code || !state) return new Response("Missing OAuth code or state", { status: 400 });
  const saved = await env.DB.prepare("SELECT state FROM oauth_states WHERE state=? AND expires_at>?").bind(state, nowIso()).first();
  if (!saved) return new Response("Invalid or expired OAuth state. Return to the dashboard and connect again.", { status: 400 });
  await env.DB.prepare("DELETE FROM oauth_states WHERE state=?").bind(state).run();

  try {
    const { token, expiresIn } = await exchangeInstagramCode(code, env);
    const meUrl = new URL(`${graphBase(env)}/me`);
    meUrl.searchParams.set("fields", "user_id,username");
    meUrl.searchParams.set("access_token", token);
    const meRes = await fetch(meUrl);
    const me = await meRes.json() as any;
    if (!meRes.ok || !me.user_id) throw new Error(me.error?.message || "Could not read Instagram account identity");
    const encrypted = await encryptToken(token, env.TOKEN_ENCRYPTION_KEY);
    const expiry = new Date(Date.now() + expiresIn * 1000).toISOString();
    await env.DB.prepare(`INSERT INTO instagram_account(id,ig_user_id,username,encrypted_token,token_expires_at,connected_at)
      VALUES(1,?,?,?,?,?) ON CONFLICT(id) DO UPDATE SET ig_user_id=excluded.ig_user_id, username=excluded.username,
      encrypted_token=excluded.encrypted_token, token_expires_at=excluded.token_expires_at, connected_at=excluded.connected_at`)
      .bind(String(me.user_id), me.username || "", encrypted, expiry, nowIso()).run();
    return Response.redirect(new URL("/?connected=1", url.origin), 302);
  } catch (e) {
    return new Response(`Connection failed: ${(e as Error).message}`, { status: 502 });
  }
}

async function oauthStart(url: URL, env: Env): Promise<Response> {
  const state = crypto.randomUUID() + crypto.randomUUID();
  await env.DB.prepare("INSERT INTO oauth_states(state,created_at,expires_at) VALUES(?,?,?)")
    .bind(state, nowIso(), new Date(Date.now() + 10 * 60 * 1000).toISOString()).run();
  const auth = new URL("https://www.instagram.com/oauth/authorize");
  auth.searchParams.set("client_id", env.META_APP_ID);
  auth.searchParams.set("redirect_uri", env.META_REDIRECT_URI);
  auth.searchParams.set("response_type", "code");
  auth.searchParams.set("scope", "instagram_business_basic,instagram_business_content_publish");
  auth.searchParams.set("state", state);
  return Response.redirect(auth.toString(), 302);
}

async function graphPost(env: Env, path: string, values: Record<string, string>) {
  const form = new URLSearchParams(values);
  const response = await fetch(`${graphBase(env)}/${path}`, { method: "POST", headers: { "content-type": "application/x-www-form-urlencoded" }, body: form });
  const data = await response.json() as any;
  if (!response.ok || data.error) throw new Error(data.error?.message || `Instagram API error (${response.status})`);
  return data;
}

async function waitForContainer(env: Env, token: string, id: string) {
  for (let i = 0; i < 12; i++) {
    const u = new URL(`${graphBase(env)}/${id}`);
    u.searchParams.set("fields", "status_code,status");
    u.searchParams.set("access_token", token);
    const r = await fetch(u);
    const d = await r.json() as any;
    if (!r.ok) throw new Error(d.error?.message || "Container status check failed");
    if (d.status_code === "FINISHED") return;
    if (d.status_code === "ERROR" || d.status_code === "EXPIRED") throw new Error(d.status || "Instagram media processing failed");
    await new Promise(resolve => setTimeout(resolve, 2500));
  }
  throw new Error("Instagram media processing timed out");
}

async function publishOne(env: Env, igUserId: string, token: string, media: MediaRow, caption: string, story = false) {
  const values: Record<string, string> = { access_token: token };
  if (media.media_type === "IMAGE") values.image_url = media.media_url;
  else values.video_url = media.media_url;
  if (story) {
    values.media_type = "STORIES";
  } else if (media.media_type === "VIDEO") {
    values.media_type = "REELS";
    values.caption = caption;
    values.share_to_feed = "true";
  } else {
    values.caption = caption;
  }
  const container = await graphPost(env, `${igUserId}/media`, values);
  if (!container.id) throw new Error("Instagram did not return a media container ID");
  if (media.media_type === "VIDEO") await waitForContainer(env, token, container.id);
  const published = await graphPost(env, `${igUserId}/media_publish`, { creation_id: container.id, access_token: token });
  return String(published.id || "");
}

function captionFor(media: MediaRow) {
  return `🚛 ${media.title}\n\nTruck & Trailer Parts\nQuality parts for heavy-duty vehicles.\n\nProduct code: ${media.product_id}\n\nMore information: https://truckparttrading.com\n\n#TruckParts #TruckAndTrailer #HeavyDuty #Bearings #TruckPartTrading`;
}

function localParts(date: Date, timezone: string) {
  const parts = new Intl.DateTimeFormat("en-GB", { timeZone: timezone, year: "numeric", month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit", hourCycle: "h23" }).formatToParts(date);
  const v = Object.fromEntries(parts.map(p => [p.type, p.value]));
  return { date: `${v.year}-${v.month}-${v.day}`, time: `${v.hour}:${v.minute}` };
}

async function runSlot(env: Env, slotKey: string, force = false) {
  const enabled = await env.DB.prepare("SELECT value FROM settings WHERE key='enabled'").first<{value:string}>();
  if (!force && enabled?.value !== "true") return { skipped: true, reason: "Publishing is paused" };

  const account = await env.DB.prepare("SELECT ig_user_id, encrypted_token FROM instagram_account WHERE id=1").first<{ig_user_id:string;encrypted_token:string}>();
  if (!account) return { skipped: true, reason: "Instagram account is not connected" };

  const claimed = await env.DB.prepare("INSERT OR IGNORE INTO scheduled_slots(slot_key,status,started_at) VALUES(?,'running',?)")
    .bind(slotKey, nowIso()).run();
  if (!claimed.meta.changes) return { skipped: true, reason: "This slot was already processed" };

  let media: MediaRow | null = null;
  let feedId = "";
  let storyId = "";
  let feedStatus = "failed";
  let storyStatus = "failed";
  let error = "";
  try {
    const candidates = await env.DB.prepare(`SELECT m.id,m.product_id,m.title,m.media_type,m.media_url
      FROM media m WHERE m.enabled=1 AND NOT EXISTS (
        SELECT 1 FROM publish_log p WHERE p.product_id=m.product_id
        AND julianday(p.published_at) >= julianday('now','-7 days')
      )`).all<MediaRow>();
    const rows = candidates.results || [];
    if (!rows.length) throw new Error("No eligible media: add new products or wait until the 7-day repeat window expires");
    media = rows[Math.floor(Math.random() * rows.length)];
    const token = await decryptToken(account.encrypted_token, env.TOKEN_ENCRYPTION_KEY);
    const caption = captionFor(media);
    feedId = await publishOne(env, account.ig_user_id, token, media, caption, false);
    feedStatus = "published";
    storyId = await publishOne(env, account.ig_user_id, token, media, caption, true);
    storyStatus = "published";
  } catch (e) {
    error = (e as Error).message;
    if (feedStatus === "published") storyStatus = "failed";
  }
  if (media) {
    await env.DB.prepare(`INSERT INTO publish_log(slot_key,media_id,product_id,feed_media_id,story_media_id,feed_status,story_status,error,published_at)
      VALUES(?,?,?,?,?,?,?,?,?)`).bind(slotKey, media.id, media.product_id, feedId || null, storyId || null, feedStatus, storyStatus, error || null, nowIso()).run();
  }
  await env.DB.prepare("UPDATE scheduled_slots SET status=?,finished_at=?,note=? WHERE slot_key=?")
    .bind(feedStatus === "published" && storyStatus === "published" ? "published" : "failed", nowIso(), error || "ok", slotKey).run();
  return { ok: feedStatus === "published" && storyStatus === "published", product: media?.product_id, feedStatus, storyStatus, error: error || undefined };
}

async function scheduled(env: Env) {
  const tz = env.APP_TIMEZONE || "Asia/Tehran";
  const { date, time } = localParts(new Date(), tz);
  const configured = (env.POSTING_SLOTS || "10:00,14:00,17:00").split(",").map(s => s.trim());
  if (!configured.includes(time)) return;
  await runSlot(env, `${date}T${time}`);
}

export default {
  async fetch(req: Request, env: Env, ctx: ExecutionContext): Promise<Response> {
    const url = new URL(req.url);
    if (req.method === "OPTIONS") return new Response(null, { headers: corsHeaders() });
    try {
      if (url.pathname === "/oauth/start" && req.method === "GET") return await oauthStart(url, env);
      if (url.pathname === "/oauth/callback" && req.method === "GET") return await oauthCallback(url, env);
      if (url.pathname.startsWith("/api/")) {
        const response = await adminRoute(req, env, url);
        const headers = new Headers(response.headers);
        for (const [k,v] of Object.entries(corsHeaders())) headers.set(k,v);
        return new Response(response.body, { status: response.status, headers });
      }
      if (url.pathname === "/health") return json({ ok: true, service: "truck-part-auto-publisher" });
      return new Response(DASHBOARD, { headers: { "content-type": "text/html; charset=utf-8" } });
    } catch (e) {
      return json({ error: (e as Error).message || "internal error" }, 500);
    }
  },
  async scheduled(_controller: ScheduledController, env: Env, ctx: ExecutionContext) {
    ctx.waitUntil(scheduled(env));
  }
};

const DASHBOARD = `<!doctype html>
<html lang="fa" dir="rtl"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Truck Part Auto Publisher</title>
<style>
body{font-family:Tahoma,Arial,sans-serif;background:#101827;color:#eef2ff;margin:0;padding:24px}main{max-width:900px;margin:auto}
.card{background:#1d293b;border:1px solid #34445d;border-radius:14px;padding:18px;margin:14px 0}
button,input{font:inherit;border-radius:8px;padding:10px;border:1px solid #53657f}button{cursor:pointer;background:#2563eb;color:white;border:0;margin:4px}
input{background:#101827;color:white;width:100%;box-sizing:border-box;margin:5px 0}
small,.muted{color:#aab8cc}.ok{color:#4ade80}.bad{color:#fca5a5}
.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(220px,1fr));gap:10px}
.item{border-top:1px solid #34445d;padding:10px 0;overflow-wrap:anywhere}
</style></head><body><main>
<h1>Truck Part Auto Publisher</h1><p class="muted">پنل ساده انتشار خودکار اینستاگرام</p>
<section class="card"><h3>۱) کلید مدیریت</h3><input id="key" type="password" placeholder="ADMIN_KEY کلادفلر"><button onclick="loadState()">ورود به پنل</button>
<div id="account" class="muted">ابتدا کلید مدیریت را وارد کنید.</div></section>
<section class="card"><h3>۲) اتصال اینستاگرام</h3><p>اتصال رسمی و امن از طریق Meta OAuth</p><button onclick="connect()">اتصال با اینستاگرام</button></section>
<section class="card"><h3>۳) زمان‌بندی</h3><p>هر روز ساعت ۱۰:۰۰، ۱۴:۰۰ و ۱۷:۰۰ به وقت تنظیم‌شده</p><div id="status" class="muted">وضعیت نامشخص</div>
<button onclick="setEnabled(true)">فعال‌سازی انتشار</button><button onclick="setEnabled(false)" style="background:#9f3030">توقف انتشار</button><button onclick="runNow()">آزمایش انتشار همین حالا</button></section>
<section class="card"><h3>۴) افزودن عکس یا ویدئوی محصول</h3><div class="grid"><label>کد محصول<input id="product" placeholder="مثلاً 220149/10"></label><label>عنوان محصول<input id="title" placeholder="نام محصول و برند"></label></div>
<input id="file" type="file" accept="image/*,video/*"><button onclick="upload()">آپلود به آرشیو برنامه</button><p class="muted">فایل‌ها در R2 ذخیره می‌شوند. برای انتشار اینستاگرام باید آدرس عمومی R2 فعال باشد.</p></section>
<section class="card"><h3>آرشیو محتوا</h3><div id="media"></div></section>
<section class="card"><h3>گزارش آخرین انتشارها</h3><div id="logs"></div></section>
</main><script>
const $=id=>document.getElementById(id);
const key=()=>sessionStorage.getItem("adminKey")||"";
async function api(path,method="GET",body){const r=await fetch(path,{method,headers:{"x-admin-key":key(),...(body instanceof FormData?{}:{"content-type":"application/json"})},body:body?(body instanceof FormData?body:JSON.stringify(body)):undefined});const d=await r.json();if(!r.ok)throw Error(d.error||"خطا");return d}
function connect(){location.href="/oauth/start"}
async function loadState(){sessionStorage.setItem("adminKey",$("key").value||key());try{const d=await api("/api/state");$("account").innerHTML=d.account?"متصل: @"+d.account.username:"هنوز حسابی متصل نشده";$("status").innerHTML=d.enabled?'<b class="ok">انتشار خودکار فعال است</b>':'<b class="bad">انتشار متوقف است</b>'; $("media").innerHTML=(d.media||[]).map(m=>'<div class="item">'+m.title+' — '+m.product_id+' ('+m.media_type+') <button onclick="removeMedia(\''+m.id+'\')">حذف از صف</button></div>').join("")||"هنوز محتوایی اضافه نشده";$("logs").innerHTML=(d.logs||[]).map(x=>'<div class="item">'+x.product_id+' — پست: '+x.feed_status+' — استوری: '+x.story_status+' — '+x.published_at+(x.error?' — '+x.error:'')+'</div>').join("")||"سابقه‌ای وجود ندارد"}catch(e){$("account").textContent=e.message}}
async function setEnabled(v){try{await api("/api/settings","POST",{enabled:v});await loadState()}catch(e){alert(e.message)}}
async function upload(){try{const f=$("file").files[0];if(!f)throw Error("ابتدا فایل را انتخاب کنید");const data=new FormData();data.set("file",f);data.set("product_id",$("product").value);data.set("title",$("title").value);await api("/api/upload","POST",data);$("file").value="";await loadState();alert("فایل اضافه شد")}catch(e){alert(e.message)}}
async function removeMedia(id){try{await api("/api/media/"+id,"DELETE");await loadState()}catch(e){alert(e.message)}}
async function runNow(){if(!confirm("یک پست و استوری واقعی منتشر شود؟"))return;try{const r=await api("/api/run-now","POST",{});alert(JSON.stringify(r));await loadState()}catch(e){alert(e.message)}}
if(new URLSearchParams(location.search).has("connected"))history.replaceState({},"", "/");
</script></body></html>`;
