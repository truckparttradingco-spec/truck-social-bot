PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS oauth_states (
  state TEXT PRIMARY KEY,
  created_at TEXT NOT NULL,
  expires_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS instagram_account (
  id INTEGER PRIMARY KEY CHECK (id = 1),
  ig_user_id TEXT NOT NULL,
  username TEXT,
  encrypted_token TEXT NOT NULL,
  token_expires_at TEXT,
  connected_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS settings (
  key TEXT PRIMARY KEY,
  value TEXT NOT NULL
);

INSERT OR IGNORE INTO settings(key, value) VALUES
  ('enabled', 'false'),
  ('timezone', 'Asia/Tehran'),
  ('slots', '10:00,14:00,17:00');

CREATE TABLE IF NOT EXISTS media (
  id TEXT PRIMARY KEY,
  product_id TEXT NOT NULL,
  title TEXT NOT NULL,
  media_type TEXT NOT NULL CHECK(media_type IN ('IMAGE','VIDEO')),
  media_url TEXT NOT NULL,
  enabled INTEGER NOT NULL DEFAULT 1,
  created_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_media_enabled ON media(enabled);

CREATE TABLE IF NOT EXISTS publish_log (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  slot_key TEXT NOT NULL,
  media_id TEXT NOT NULL,
  product_id TEXT NOT NULL,
  feed_media_id TEXT,
  story_media_id TEXT,
  feed_status TEXT NOT NULL,
  story_status TEXT NOT NULL,
  error TEXT,
  published_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_publish_product_date
  ON publish_log(product_id, published_at);

CREATE TABLE IF NOT EXISTS scheduled_slots (
  slot_key TEXT PRIMARY KEY,
  status TEXT NOT NULL,
  started_at TEXT NOT NULL,
  finished_at TEXT,
  note TEXT
);
