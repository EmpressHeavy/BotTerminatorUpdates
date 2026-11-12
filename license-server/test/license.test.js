import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { test } from "node:test";
import { createApp } from "../src/app.js";
import { memoryStore } from "../src/store.js";
import { hmacHex } from "../src/stripe.js";
import { prices } from "../src/prices.js";

const SECRET = "whsec_test_secret";
const ADMIN = "admin-test-token";
const NOW = new Date("2026-11-10T12:00:00.000Z");

function app(store, fetchImpl, env = {}) {
  return createApp({
    store,
    env: {
      STRIPE_WEBHOOK_SECRET: SECRET,
      ADMIN_TOKEN: ADMIN,
      STRIPE_SECRET_KEY: "sk_test_fake",
      STRIPE_PRICE_BT: "price_bt_test",
      STRIPE_PRICE_FF: "price_ff_test",
      STRIPE_PRICE_BOTH: "price_both_test",
      PUBLIC_BASE_URL: "https://license.example",
      ...env,
    },
    fetchImpl,
    now: () => NOW,
    catalog: prices,
  });
}

async function signed(event, secret = SECRET, t = Math.floor(NOW.getTime() / 1000)) {
  const raw = JSON.stringify(event);
  const v1 = await hmacHex(secret, `${t}.${raw}`);
  return { raw, header: `t=${t},v1=${v1}` };
}

async function post(handler, path, body, headers = {}) {
  return handler.handle(new Request(`https://license.example${path}`, {
    method: "POST",
    headers: { "content-type": "application/json", ...headers },
    body: typeof body === "string" ? body : JSON.stringify(body),
  }));
}

test("prices live in config, not in the worker logic", () => {
  assert.equal(prices.products.bt.amount_cents, 449);
  assert.equal(prices.products.ff.amount_cents, 449);
  assert.equal(prices.products.both.amount_cents, 899);
  for (const file of ["src/app.js", "src/billing.js", "src/stripe.js", "src/index.js", "src/store.js"]) {
    const text = readFileSync(new URL(`../${file}`, import.meta.url), "utf8");
    for (const needle of ["449", "899", "4.49", "8.99"]) {
      assert.equal(text.includes(needle), false, `${file} contains ${needle}`);
    }
  }
});

test("register then check is inactive until Stripe says paid", async () => {
  const store = memoryStore();
  const handler = app(store);
  const created = await post(handler, "/register", {});
  assert.equal(created.status, 201);
  const { install_id: id } = await created.json();
  assert.match(id, /^[a-f0-9]{64}$/);
  const checked = await post(handler, "/check", { install_id: id, product: "bt" });
  const body = await checked.json();
  assert.equal(body.active, false);
  assert.equal(body.product, "bt");
  assert.equal(body.expires, null);
  assert.equal(body.price.amount_cents, prices.products.bt.amount_cents);
  assert.ok(body.renew_url.startsWith(`https://license.example/pay?install_id=${id}`));
});

test("stripe test events activate, renew, fail, and delete without storing a handle", async () => {
  const store = memoryStore();
  const handler = app(store);
  const id = "a".repeat(32);
  await store.createInstall(id, NOW.toISOString());
  const checkout = {
    id: "evt_checkout",
    type: "checkout.session.completed",
    data: { object: {
      client_reference_id: id,
      customer: "cus_test",
      subscription: "sub_test",
      metadata: { install_id: id, product: "bt", x_handle: "@should_not_store" },
    } },
  };
  let signedEvent = await signed(checkout);
  let res = await post(handler, "/stripe/webhook", signedEvent.raw, { "stripe-signature": signedEvent.header });
  assert.equal(res.status, 200);
  let check = await (await post(handler, "/check", { install_id: id, product: "bt" })).json();
  assert.equal(check.active, true);
  let ff = await (await post(handler, "/check", { install_id: id, product: "ff" })).json();
  assert.equal(ff.active, false);
  const listed = await store.listInstalls();
  assert.equal(JSON.stringify(listed).includes("@should_not_store"), false);
  assert.equal(JSON.stringify(listed).includes("x_handle"), false);

  const invoice = {
    id: "evt_invoice",
    type: "invoice.paid",
    data: { object: {
      customer: "cus_test",
      subscription: "sub_test",
      subscription_details: { metadata: { install_id: id, product: "bt" } },
      lines: { data: [{ period: { end: 1893456000 } }] },
    } },
  };
  signedEvent = await signed(invoice);
  res = await post(handler, "/stripe/webhook", signedEvent.raw, { "stripe-signature": signedEvent.header });
  assert.equal(res.status, 200);
  check = await (await post(handler, "/check", { install_id: id, product: "bt" })).json();
  assert.equal(check.expires, "2030-01-01T00:00:00.000Z");

  const failed = {
    id: "evt_fail",
    type: "invoice.payment_failed",
    data: { object: { customer: "cus_test", subscription: "sub_test" } },
  };
  signedEvent = await signed(failed);
  res = await post(handler, "/stripe/webhook", signedEvent.raw, { "stripe-signature": signedEvent.header });
  assert.equal(res.status, 200);
  check = await (await post(handler, "/check", { install_id: id, product: "bt" })).json();
  assert.equal(check.active, false);

  const again = { ...checkout, id: "evt_checkout_2" };
  signedEvent = await signed(again);
  await post(handler, "/stripe/webhook", signedEvent.raw, { "stripe-signature": signedEvent.header });
  const deleted = {
    id: "evt_del",
    type: "customer.subscription.deleted",
    data: { object: { id: "sub_test", customer: "cus_test", metadata: { install_id: id, product: "bt" } } },
  };
  signedEvent = await signed(deleted);
  res = await post(handler, "/stripe/webhook", signedEvent.raw, { "stripe-signature": signedEvent.header });
  assert.equal(res.status, 200);
  check = await (await post(handler, "/check", { install_id: id, product: "bt" })).json();
  assert.equal(check.active, false);
});

test("both subscription covers bt and ff", async () => {
  const store = memoryStore();
  const handler = app(store);
  const id = "b".repeat(32);
  const event = {
    type: "checkout.session.completed",
    data: { object: {
      client_reference_id: id,
      customer: "cus_both",
      subscription: "sub_both",
      metadata: { install_id: id, product: "both" },
    } },
  };
  const signedEvent = await signed(event);
  const res = await post(handler, "/stripe/webhook", signedEvent.raw, { "stripe-signature": signedEvent.header });
  assert.equal(res.status, 200);
  assert.equal((await (await post(handler, "/check", { install_id: id, product: "bt" })).json()).active, true);
  assert.equal((await (await post(handler, "/check", { install_id: id, product: "ff" })).json()).active, true);
});

test("webhook rejects a bad signature", async () => {
  const handler = app(memoryStore());
  const res = await post(handler, "/stripe/webhook", "{}", { "stripe-signature": "t=1,v1=nope" });
  assert.equal(res.status, 400);
});

test("checkout uses the price id and the install id, not a hard-coded amount", async () => {
  const store = memoryStore();
  const id = "c".repeat(32);
  await store.createInstall(id, NOW.toISOString());
  const calls = [];
  const fetchImpl = async (url, opts) => {
    calls.push({ url, body: opts.body.toString(), auth: opts.headers.authorization });
    return new Response(JSON.stringify({ url: "https://checkout.stripe.com/c/pay/cs_test_123" }), { status: 200 });
  };
  const handler = app(store, fetchImpl);
  const res = await handler.handle(new Request(`https://license.example/pay?install_id=${id}&product=ff`));
  assert.equal(res.status, 303);
  assert.equal(res.headers.get("location"), "https://checkout.stripe.com/c/pay/cs_test_123");
  assert.equal(calls.length, 1);
  assert.match(calls[0].body, /price_ff_test/);
  assert.match(calls[0].body, new RegExp(`client_reference_id=${id}`));
  assert.match(calls[0].body, /metadata%5Bproduct%5D=ff/);
  assert.equal(calls[0].body.includes("unit_amount"), false);
  assert.equal(calls[0].auth, "Bearer sk_test_fake");
});

test("admin token lists installs and toggles one off", async () => {
  const store = memoryStore();
  const handler = app(store);
  const id = "d".repeat(32);
  await store.createInstall(id, NOW.toISOString());
  await store.upsertEntitlement({
    install_id: id, product: "bt", status: "active", expires_at: null,
    stripe_customer_id: "cus_x", stripe_subscription_id: "sub_x",
    created_at: NOW.toISOString(), updated_at: NOW.toISOString(),
  });
  const denied = await handler.handle(new Request("https://license.example/admin/installs"));
  assert.equal(denied.status, 401);
  const off = await post(handler, "/admin/toggle", { install_id: id, product: "bt", active: false }, {
    authorization: `Bearer ${ADMIN}`,
  });
  assert.equal(off.status, 200);
  assert.equal((await (await post(handler, "/check", { install_id: id, product: "bt" })).json()).active, false);
  const on = await post(handler, "/admin/toggle", { install_id: id, product: "bt", active: true }, {
    authorization: `Bearer ${ADMIN}`,
  });
  assert.equal((await on.json()).active, true);
  const listed = await handler.handle(new Request("https://license.example/admin/installs", {
    headers: { authorization: `Bearer ${ADMIN}` },
  }));
  const body = await listed.json();
  assert.equal(body.installs[0].install_id, id);
  assert.equal(body.installs[0].entitlements[0].status, "active");
});
