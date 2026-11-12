import { CHECK_PRODUCTS, PRODUCTS } from "./prices.js";

const STORED_KEYS = [
  "install_id", "product", "status", "expires_at",
  "stripe_customer_id", "stripe_subscription_id", "created_at", "updated_at",
];

export function isoFromUnix(sec) {
  if (sec == null || sec === "") return null;
  const n = Number(sec);
  if (!Number.isFinite(n)) return null;
  return new Date(n * 1000).toISOString();
}

function productOf(meta) {
  const product = meta?.product;
  return PRODUCTS.includes(product) ? product : "";
}

function installOf(meta, fallback) {
  const id = meta?.install_id || fallback || "";
  return typeof id === "string" ? id : "";
}

export function covers(row, product, nowMs) {
  if (!row || row.status !== "active") return false;
  if (row.product !== product && row.product !== "both") return false;
  if (row.expires_at) {
    const exp = Date.parse(row.expires_at);
    if (Number.isFinite(exp) && exp <= nowMs) return false;
  }
  return true;
}

export function entitlementView(rows, product, nowMs) {
  const matching = (rows || []).filter((row) => covers(row, product, nowMs));
  if (!matching.length) return { active: false, expires: null };
  const dated = matching.map((row) => row.expires_at).filter(Boolean).sort();
  return { active: true, expires: dated[0] || null };
}

async function writeEntitlement(store, row) {
  const clean = {};
  for (const key of STORED_KEYS) clean[key] = row[key] ?? null;
  await store.upsertEntitlement(clean);
}

export async function applyStripeEvent(store, event, nowIso) {
  const type = event?.type;
  const obj = event?.data?.object || {};
  if (type === "checkout.session.completed") {
    const installId = installOf(obj.metadata, obj.client_reference_id);
    const product = productOf(obj.metadata);
    if (!installId || !product) return { applied: false, reason: "missing install or product" };
    await store.createInstall(installId, nowIso);
    await writeEntitlement(store, {
      install_id: installId,
      product,
      status: "active",
      expires_at: null,
      stripe_customer_id: obj.customer || null,
      stripe_subscription_id: obj.subscription || null,
      created_at: nowIso,
      updated_at: nowIso,
    });
    return { applied: true, install_id: installId, product, status: "active" };
  }
  if (type === "invoice.paid" || type === "invoice.payment_failed") {
    const meta = obj.subscription_details?.metadata || obj.parent?.subscription_details?.metadata || {};
    const subId = obj.subscription || obj.parent?.subscription_details?.subscription || null;
    const periodEnd = obj.lines?.data?.[0]?.period?.end;
    let installId = installOf(meta, "");
    let product = productOf(meta);
    if (!installId || !product) {
      const found = await store.findBySubscription(subId);
      if (found.length) {
        installId = found[0].install_id;
        product = found[0].product;
      }
    }
    if (!installId || !product) return { applied: false, reason: "missing install or product" };
    const status = type === "invoice.paid" ? "active" : "inactive";
    await store.createInstall(installId, nowIso);
    await writeEntitlement(store, {
      install_id: installId,
      product,
      status,
      expires_at: status === "active" ? isoFromUnix(periodEnd) : null,
      stripe_customer_id: obj.customer || null,
      stripe_subscription_id: subId,
      created_at: nowIso,
      updated_at: nowIso,
    });
    return { applied: true, install_id: installId, product, status };
  }
  if (type === "customer.subscription.deleted") {
    const subId = obj.id || null;
    let targets = [];
    const metaInstall = installOf(obj.metadata, "");
    const metaProduct = productOf(obj.metadata);
    if (metaInstall && metaProduct) targets = [{ install_id: metaInstall, product: metaProduct }];
    else targets = await store.findBySubscription(subId);
    if (!targets.length) return { applied: false, reason: "unknown subscription" };
    for (const row of targets) {
      await writeEntitlement(store, {
        install_id: row.install_id,
        product: row.product,
        status: "inactive",
        expires_at: row.expires_at ?? null,
        stripe_customer_id: obj.customer || row.stripe_customer_id || null,
        stripe_subscription_id: subId || row.stripe_subscription_id || null,
        created_at: row.created_at || nowIso,
        updated_at: nowIso,
      });
    }
    return { applied: true, status: "inactive" };
  }
  return { applied: false, reason: "ignored" };
}

export function isCheckProduct(product) {
  return CHECK_PRODUCTS.includes(product);
}
