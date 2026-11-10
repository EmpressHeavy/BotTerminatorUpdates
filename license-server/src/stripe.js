const enc = new TextEncoder();

export function hex(buf) {
  return [...new Uint8Array(buf)].map((b) => b.toString(16).padStart(2, "0")).join("");
}

export function safeEqual(a, b) {
  const ba = enc.encode(String(a));
  const bb = enc.encode(String(b));
  const len = Math.max(ba.length, bb.length);
  let diff = ba.length ^ bb.length;
  for (let i = 0; i < len; i++) diff |= (ba[i] || 0) ^ (bb[i] || 0);
  return diff === 0;
}

export async function hmacHex(secret, message) {
  const key = await crypto.subtle.importKey(
    "raw",
    enc.encode(secret),
    { name: "HMAC", hash: "SHA-256" },
    false,
    ["sign"],
  );
  return hex(await crypto.subtle.sign("HMAC", key, enc.encode(message)));
}

/** Stripe-Signature: t=unix,v1=hex. Rejects a missing, stale, or mismatched signature. */
export async function verifyStripeSignature(rawBody, header, secret, nowSec, toleranceSec = 300) {
  if (!rawBody && rawBody !== "") return false;
  if (!header || !secret) return false;
  const parts = String(header).split(",").map((p) => p.trim());
  const t = parts.find((p) => p.startsWith("t="))?.slice(2);
  const v1s = parts.filter((p) => p.startsWith("v1=")).map((p) => p.slice(3));
  if (!t || !/^\d+$/.test(t) || v1s.length === 0) return false;
  if (Math.abs(Number(nowSec) - Number(t)) > toleranceSec) return false;
  const expected = await hmacHex(secret, `${t}.${rawBody}`);
  return v1s.some((v) => safeEqual(v, expected));
}

export function checkoutForm({ priceId, installId, product, successUrl, cancelUrl }) {
  const body = new URLSearchParams();
  body.set("mode", "subscription");
  body.set("line_items[0][price]", priceId);
  body.set("line_items[0][quantity]", "1");
  body.set("client_reference_id", installId);
  body.set("metadata[install_id]", installId);
  body.set("metadata[product]", product);
  body.set("subscription_data[metadata][install_id]", installId);
  body.set("subscription_data[metadata][product]", product);
  body.set("success_url", successUrl);
  body.set("cancel_url", cancelUrl);
  return body;
}

export function priceEnvName(product) {
  return { bt: "STRIPE_PRICE_BT", ff: "STRIPE_PRICE_FF", both: "STRIPE_PRICE_BOTH" }[product] || "";
}
