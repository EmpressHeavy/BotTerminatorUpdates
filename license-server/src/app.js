import { applyStripeEvent, entitlementView, isCheckProduct } from "./billing.js";
import { formatPrice, pricePayload, prices, PRODUCTS } from "./prices.js";
import { checkoutForm, hmacHex, priceEnvName, safeEqual, verifyStripeSignature } from "./stripe.js";

const ID_RE = /^[a-zA-Z0-9_-]{16,128}$/;

function json(data, status = 200) {
  return new Response(JSON.stringify(data), {
    status,
    headers: { "content-type": "application/json; charset=utf-8" },
  });
}

function html(body, status = 200, headers = {}) {
  return new Response(body, {
    status,
    headers: { "content-type": "text/html; charset=utf-8", ...headers },
  });
}

function esc(s) {
  return String(s ?? "").replace(/[&<>"']/g, (c) => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
  }[c]));
}

export function newInstallId() {
  const bytes = new Uint8Array(32);
  crypto.getRandomValues(bytes);
  return [...bytes].map((b) => b.toString(16).padStart(2, "0")).join("");
}

function baseUrl(request, env) {
  const configured = String(env.PUBLIC_BASE_URL || "").replace(/\/$/, "");
  if (configured) return configured;
  return new URL(request.url).origin;
}

function payUrl(base, installId, product) {
  const u = new URL("/pay", base.endsWith("/") ? base : `${base}/`);
  u.searchParams.set("install_id", installId);
  if (product) u.searchParams.set("product", product);
  return u.toString();
}

async function adminCookie(secret) {
  return hmacHex(secret, "bt-license-admin-v1");
}

function cookieValue(request, name) {
  const raw = request.headers.get("cookie") || "";
  for (const part of raw.split(";")) {
    const [k, ...rest] = part.trim().split("=");
    if (k === name) return rest.join("=");
  }
  return "";
}

async function isAdmin(request, env) {
  const secret = env.ADMIN_TOKEN || "";
  if (!secret) return false;
  const header = request.headers.get("authorization") || "";
  const bearer = header.toLowerCase().startsWith("bearer ") ? header.slice(7).trim() : "";
  if (bearer && safeEqual(bearer, secret)) return true;
  const cookie = cookieValue(request, "bt_admin");
  if (!cookie) return false;
  return safeEqual(cookie, await adminCookie(secret));
}

function chooserPage(base, installId, catalog) {
  const cards = PRODUCTS.map((product) => {
    const row = catalog.products[product];
    const href = payUrl(base, installId, product);
    return `<li><a href="${esc(href)}">${esc(row.label)}</a> — ${esc(formatPrice(product, catalog))}</li>`;
  }).join("");
  return `<!doctype html><meta charset="utf-8"><title>Subscribe</title>
<main><h1>Choose a subscription</h1><ul>${cards}</ul></main>`;
}

function adminPage(rows) {
  const body = rows.map((row) => {
    const ents = (row.entitlements || []).map((e) =>
      `<li>${esc(e.product)}: ${esc(e.status)} expires ${esc(e.expires_at || "none")} sub ${esc(e.stripe_subscription_id || "none")}</li>`,
    ).join("") || "<li>no entitlement</li>";
    const buttons = PRODUCTS.map((product) => `
      <form method="post" action="/admin/toggle">
        <input type="hidden" name="install_id" value="${esc(row.install_id)}">
        <input type="hidden" name="product" value="${esc(product)}">
        <button name="active" value="true" type="submit">Turn ${esc(product)} on</button>
        <button name="active" value="false" type="submit">Turn ${esc(product)} off</button>
      </form>`).join("");
    return `<section><h2><code>${esc(row.install_id)}</code></h2><ul>${ents}</ul>${buttons}</section>`;
  }).join("") || "<p>No installs yet.</p>";
  return `<!doctype html><meta charset="utf-8"><title>License admin</title><main><h1>Installs</h1>${body}</main>`;
}

function loginPage() {
  return `<!doctype html><meta charset="utf-8"><title>License admin</title>
<main><h1>Admin</h1>
<form method="post" action="/admin/login">
<label>Admin token <input name="token" type="password" autocomplete="current-password"></label>
<button type="submit">Continue</button>
</form></main>`;
}

export function createApp({ store, env, fetchImpl, now, catalog = prices }) {
  const clock = now || (() => new Date());
  const fetchFn = fetchImpl || globalThis.fetch.bind(globalThis);

  async function handle(request) {
    const url = new URL(request.url);
    const path = url.pathname.replace(/\/$/, "") || "/";
    if (request.method === "GET" && path === "/") {
      return json({
        ok: true,
        products: PRODUCTS.map((product) => ({ product, ...pricePayload(product, catalog) })),
      });
    }
    if (request.method === "POST" && path === "/register") {
      const id = newInstallId();
      await store.createInstall(id, clock().toISOString());
      return json({ install_id: id }, 201);
    }
    if (request.method === "POST" && path === "/check") {
      let body;
      try { body = await request.json(); } catch { return json({ error: "bad json" }, 400); }
      const installId = String(body.install_id || "");
      const product = String(body.product || "");
      if (!ID_RE.test(installId) || !isCheckProduct(product)) {
        return json({ error: "install_id and product bt|ff are required" }, 400);
      }
      const rows = await store.entitlementsForInstall(installId);
      const view = entitlementView(rows, product, clock().getTime());
      const base = baseUrl(request, env);
      return json({
        active: view.active,
        product,
        expires: view.expires,
        renew_url: payUrl(base, installId),
        price: pricePayload(product, catalog),
      });
    }
    if (request.method === "GET" && path === "/pay") {
      const installId = url.searchParams.get("install_id") || "";
      const product = url.searchParams.get("product") || "";
      if (!ID_RE.test(installId)) return html("<p>Missing install id.</p>", 400);
      const known = await store.getInstall(installId);
      if (!known) return html("<p>Unknown install. Register the bot first.</p>", 404);
      const base = baseUrl(request, env);
      if (!product) return html(chooserPage(base, installId, catalog));
      if (!PRODUCTS.includes(product)) return html("<p>Unknown product.</p>", 400);
      const priceId = env[priceEnvName(product)] || "";
      if (!env.STRIPE_SECRET_KEY || !priceId) {
        return html(`<p>Checkout is not configured. Create a Stripe Price for ${esc(formatPrice(product, catalog))} and set ${esc(priceEnvName(product))}.</p>`, 503);
      }
      const form = checkoutForm({
        priceId,
        installId,
        product,
        successUrl: `${base}/pay/done`,
        cancelUrl: `${base}/pay/cancel`,
      });
      const res = await fetchFn("https://api.stripe.com/v1/checkout/sessions", {
        method: "POST",
        headers: {
          authorization: `Bearer ${env.STRIPE_SECRET_KEY}`,
          "content-type": "application/x-www-form-urlencoded",
        },
        body: form,
      });
      const payload = await res.json().catch(() => ({}));
      if (!res.ok || !payload.url) return html("<p>Stripe did not return a checkout link.</p>", 502);
      return Response.redirect(payload.url, 303);
    }
    if (request.method === "GET" && path === "/pay/done") {
      return html("<p>Payment received. Return to Bot Terminator and try the scan again.</p>");
    }
    if (request.method === "GET" && path === "/pay/cancel") {
      return html("<p>Checkout canceled. The bot stays paused until a subscription is active.</p>");
    }
    if (request.method === "POST" && path === "/stripe/webhook") {
      const raw = await request.text();
      const ok = await verifyStripeSignature(
        raw,
        request.headers.get("stripe-signature"),
        env.STRIPE_WEBHOOK_SECRET || "",
        Math.floor(clock().getTime() / 1000),
      );
      if (!ok) return json({ error: "bad signature" }, 400);
      let event;
      try { event = JSON.parse(raw); } catch { return json({ error: "bad json" }, 400); }
      const result = await applyStripeEvent(store, event, clock().toISOString());
      return json({ received: true, ...result });
    }
    if (path === "/admin" || path.startsWith("/admin/")) {
      if (request.method === "GET" && path === "/admin") {
        if (!(await isAdmin(request, env))) return html(loginPage(), 401);
        return html(adminPage(await store.listInstalls()));
      }
      if (request.method === "POST" && path === "/admin/login") {
        const form = new URLSearchParams(await request.text());
        const token = form.get("token") || "";
        if (!env.ADMIN_TOKEN || !safeEqual(token, env.ADMIN_TOKEN)) return html(loginPage(), 401);
        const cookie = await adminCookie(env.ADMIN_TOKEN);
        return html(adminPage(await store.listInstalls()), 200, {
          "set-cookie": `bt_admin=${cookie}; HttpOnly; Secure; SameSite=Strict; Path=/admin; Max-Age=43200`,
        });
      }
      if (!(await isAdmin(request, env))) return json({ error: "unauthorized" }, 401);
      if (request.method === "GET" && path === "/admin/installs") {
        return json({ installs: await store.listInstalls() });
      }
      if (request.method === "POST" && path === "/admin/toggle") {
        const ctype = request.headers.get("content-type") || "";
        let installId = "";
        let product = "";
        let active = false;
        if (ctype.includes("application/json")) {
          const body = await request.json();
          installId = String(body.install_id || "");
          product = String(body.product || "");
          active = body.active === true || body.active === "true";
        } else {
          const form = new URLSearchParams(await request.text());
          installId = form.get("install_id") || "";
          product = form.get("product") || "";
          active = form.get("active") === "true";
        }
        if (!ID_RE.test(installId) || !PRODUCTS.includes(product)) return json({ error: "bad install or product" }, 400);
        const known = await store.getInstall(installId);
        if (!known) return json({ error: "unknown install" }, 404);
        const nowIso = clock().toISOString();
        const existing = (await store.entitlementsForInstall(installId)).find((e) => e.product === product);
        await store.upsertEntitlement({
          install_id: installId,
          product,
          status: active ? "active" : "inactive",
          expires_at: active ? (existing?.expires_at || null) : null,
          stripe_customer_id: existing?.stripe_customer_id || null,
          stripe_subscription_id: existing?.stripe_subscription_id || null,
          created_at: existing?.created_at || nowIso,
          updated_at: nowIso,
        });
        if (ctype.includes("application/json")) return json({ install_id: installId, product, active });
        return html(adminPage(await store.listInstalls()));
      }
    }
    return json({ error: "not found" }, 404);
  }

  return { handle };
}
