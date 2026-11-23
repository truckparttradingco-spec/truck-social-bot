# Truck Part Auto Publisher (Cloudflare Workers)

Standalone Instagram Business publisher for Truck Part Trading. It does not use Metricool.

## Features in this first implementation

- Instagram OAuth login (Instagram Login)
- Encrypted long-lived access token storage in D1
- Cloudflare Cron Trigger checks three daily local-time slots
- Random media selection from the approved media archive
- Product-level no-repeat rule for the previous seven days
- Publishes one feed item (photo or Reel) and one Story per slot
- R2 media upload, D1 history, pause/resume and manual test controls

## Important setup requirements

1. Create a Meta app and add the Instagram product / Instagram Login.
2. Configure OAuth redirect URI exactly as:
   `https://YOUR-WORKER.workers.dev/oauth/callback`
3. Request these scopes:
   - `instagram_business_basic`
   - `instagram_business_content_publish`
4. For an app used only by its own app-role/tester accounts, complete the required app-role setup. Public use by other accounts may require Meta App Review / Advanced Access.
5. Create a Cloudflare D1 database named `truck-part-publisher` and apply `schema.sql`.
6. Create an R2 bucket named `truck-part-publisher-media`. Attach a public custom domain to the bucket and set `PUBLIC_MEDIA_BASE_URL` to that origin. Instagram must be able to fetch media over HTTPS.
7. Replace the placeholder `database_id` in `wrangler.toml`.

## Worker secrets

Set these with Wrangler (never commit them):

- `META_APP_ID`
- `META_APP_SECRET`
- `META_REDIRECT_URI`
- `ADMIN_KEY` (strong random password)
- `TOKEN_ENCRYPTION_KEY` (base64-encoded 32 random bytes)

Set `PUBLIC_MEDIA_BASE_URL` as a Worker variable or secret if required by your deployment policy.

## Deploy

Use the Cloudflare account that will host the Worker. The GitHub source is ready, but it is not deployed until these account-side resources and secrets are configured.

```bash
cd cloudflare-publisher
npx wrangler d1 create truck-part-publisher
# Copy the returned database_id into wrangler.toml
npx wrangler d1 execute truck-part-publisher --remote --file=schema.sql
npx wrangler r2 bucket create truck-part-publisher-media
# In Cloudflare R2, attach a public custom domain to this bucket.
# Then set the matching public origin:
npx wrangler secret put PUBLIC_MEDIA_BASE_URL
npx wrangler secret put META_APP_ID
npx wrangler secret put META_APP_SECRET
npx wrangler secret put META_REDIRECT_URI
npx wrangler secret put ADMIN_KEY
openssl rand -base64 32
# Use the output as TOKEN_ENCRYPTION_KEY:
npx wrangler secret put TOKEN_ENCRYPTION_KEY
npx wrangler deploy
```

## Meta app configuration

In Meta for Developers, create an app with the Instagram product / Instagram Login. Add the exact redirect URI from `META_REDIRECT_URI` to the app's valid OAuth redirect URIs. For this Worker it is `https://YOUR-WORKER.workers.dev/oauth/callback`. The app needs Instagram Business Login and the `instagram_business_basic` and `instagram_business_content_publish` permissions. Meta may require App Review / Advanced Access before accounts outside the app's roles can authorize it.

## Safe first launch

The database defaults to `enabled=false`. Connect Instagram, upload a small test image, verify the public media URL, then use **آزمایش انتشار همین حالا**. Only activate the schedule after a successful test.

## Scheduling

Default timezone is `Asia/Tehran` and slots are `10:00,14:00,17:00`. Cloudflare Cron runs in UTC; the Worker converts each invocation to the configured IANA timezone before matching a slot. Set `APP_TIMEZONE` and `POSTING_SLOTS` as Worker variables if you want different values.

## Current scope / known limitations

- One Instagram Business account per deployment.
- Each scheduled slot publishes a feed item and then a Story using the same product media.
- Initial media must be uploaded through the dashboard. A later adapter can import the website archive manifest from `truckparttrading.com`.
- The Worker does not generate product claims; the title and product code are supplied with each media item.
- Instagram API access, app review, token health, public media hosting and Cloudflare resource creation must be completed before live publishing.
