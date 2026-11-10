# License server testing

This branch is not an updater release. `VERSION` stays at v3.5.20, so existing Bot Terminator installs that follow `main` do not pull it. Do not merge until you have finished the test-mode steps below.

Prices are in `prices.json`, not in the Worker logic. Today that file is:

| Product | Stripe name | Amount |
|---|---|---|
| `bt` | Bot Terminator | $4.49 per month |
| `ff` | Follower Finder | $4.49 per month |
| `both` | Bot Terminator and Follower Finder | $8.99 per month |

If you change `prices.json`, create new Stripe Prices for those amounts. The Worker never sends an amount to Stripe. It sends the Price id you configure.

Nothing here was deployed, and no Stripe or Cloudflare resource was created for you.

## 1. Stripe test mode (no real charge)

In the Stripe Dashboard, turn **Test mode** on. The switch is in the upper right. Stay in test mode until section 4.

Create three products, each with one recurring monthly price, at the amounts in the table above. Copy each Price id (`price_...`). Test-mode and live-mode ids are different. Use the test-mode ids here.

Install the Stripe CLI if you want the webhook secret without a public URL yet. Otherwise add the webhook after the Worker is deployed (section 2) and use the signing secret from the Dashboard.

Test card, on Stripe's hosted checkout page only:

- Number `4242 4242 4242 4242`
- Any future expiry, any CVC, any postal code

That card does not move money. Do not use a real card while Test mode is on.

## 2. Deploy the Worker (free tier)

From this repo, on this branch:

```sh
cd license-server
npx wrangler login
npx wrangler d1 create bt-license
```

`d1 create` prints a `database_id`. Put that id in `wrangler.toml` where the placeholder `00000000-0000-0000-0000-000000000000` is. Do not put a Cloudflare account id in the file.

```sh
npx wrangler d1 execute bt-license --remote --file=schema.sql
npx wrangler secret put STRIPE_SECRET_KEY
npx wrangler secret put STRIPE_WEBHOOK_SECRET
npx wrangler secret put ADMIN_TOKEN
```

Use the test-mode secret key (`sk_test_...`) and the test-mode webhook signing secret (`whsec_...`). Pick a long random `ADMIN_TOKEN` and store it in a password manager. These three values are secrets. They are not written into `wrangler.toml`.

Price ids are not secrets. Edit `wrangler.toml`:

```toml
STRIPE_PRICE_BT = "price_..."
STRIPE_PRICE_FF = "price_..."
STRIPE_PRICE_BOTH = "price_..."
PUBLIC_BASE_URL = "https://bt-license.<your-subdomain>.workers.dev"
```

or set them in the dashboard after the first deploy. `PUBLIC_BASE_URL` is the origin only, with no path.

```sh
npx wrangler deploy
```

In Stripe test mode, add an endpoint:

`https://bt-license.<your-subdomain>.workers.dev/stripe/webhook`

Events: `checkout.session.completed`, `invoice.paid`, `invoice.payment_failed`, `customer.subscription.deleted`.

Put that endpoint's signing secret in `STRIPE_WEBHOOK_SECRET` if you did not already (test secret, not the live one).

Check the prices the Worker is serving:

```sh
curl https://bt-license.<your-subdomain>.workers.dev/
```

The JSON `amount_cents` values should match `prices.json` (449, 449, and 899).

## 3. Test clone, unlock, then stop

Use a **new** bot copy checked out from this branch, not an existing customer's install and not `main`.

In that copy, set `code/config/license.json`:

```json
{
  "product": "bt",
  "base_url": "https://bt-license.<your-subdomain>.workers.dev",
  "grace_hours": 72,
  "timeout_seconds": 10
}
```

From the `code/` directory:

```sh
python3 -m src.license_check register
python3 -m src.license_check require scan
```

The second command should exit 2 and print that the subscription isn't active, with a renew link. It does not delete local records. Register and check send `User-Agent: BotTerminator/<version>` (from `code/VERSION`). Cloudflare error 1010 blocks urllib's default agent on this Worker; curl was not blocked.

Open the renew link. Pick Bot Terminator ($4.49). Pay with the test card `4242...`. Return to the bot and run `require scan` again. It should print `subscription active`.

Stop it in either of these ways:

- Stripe test mode: cancel the subscription. The webhook marks the install inactive.
- Or toggle it yourself:

```sh
curl -H "Authorization: Bearer <ADMIN_TOKEN>" \
  -H "content-type: application/json" \
  -d '{"install_id":"<id from register>","product":"bt","active":false}' \
  https://bt-license.<your-subdomain>.workers.dev/admin/toggle
```

The admin page is `GET /admin`. It asks for the admin token, then lists installs and has on/off buttons.

Run `require scan` again. It should exit 2 and refuse. A scan, removal, or block in the bot hits the same check and stops with that sentence. X login stays on the bot. Records stay.

Canceling or toggling off stops the bot immediately. The 72 hour grace applies only when the Worker cannot be reached after it had previously answered `active: true`. Set `grace_hours` to `0` on the test clone if you also want to see an immediate refusal while the Worker is offline.

`both` ($8.99) makes both `bt` and `ff` checks active. `ff` alone is the Follower Finder price. This repo's bot sends `product: bt`.

Automated checks, with no network and Stripe's event shapes signed by a test secret:

```sh
cd license-server && node --test
cd code && python3 -m pytest -q tests/test_license_check.py
```

## 4. Switch to live mode (real card, real money)

Do this only after section 3 behaves the way you want.

1. Turn **Test mode** off in Stripe.
2. Create the same three products and monthly prices again, at $4.49, $4.49, and $8.99. Live Price ids are new. Put them in `wrangler.toml` (or the dashboard vars) in place of the test ids.
3. Add a live webhook endpoint to the same Worker URL and the same four events. Copy the **live** signing secret.
4. Replace the Worker secrets with the live values:

```sh
npx wrangler secret put STRIPE_SECRET_KEY       # sk_live_...
npx wrangler secret put STRIPE_WEBHOOK_SECRET   # live whsec_...
npx wrangler deploy
```

5. Register a fresh test install (or reuse the test clone's id) and open its renew link. Pay with your own card. The charge goes to your Stripe account, minus Stripe's fee. Then cancel it, or toggle the install off, and confirm `require scan` exits 2.

The test card `4242...` does not work in live mode. Do not put live secret keys in git.
