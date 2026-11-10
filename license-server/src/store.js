export function memoryStore() {
  const installs = new Map();
  const ents = [];
  return {
    async createInstall(id, now) {
      if (installs.has(id)) return false;
      installs.set(id, { install_id: id, created_at: now });
      return true;
    },
    async getInstall(id) {
      return installs.get(id) || null;
    },
    async listInstalls() {
      return [...installs.values()].map((row) => ({
        ...row,
        entitlements: ents.filter((e) => e.install_id === row.install_id).map((e) => ({ ...e })),
      }));
    },
    async entitlementsForInstall(id) {
      return ents.filter((e) => e.install_id === id).map((e) => ({ ...e }));
    },
    async findBySubscription(subId) {
      if (!subId) return [];
      return ents.filter((e) => e.stripe_subscription_id === subId).map((e) => ({ ...e }));
    },
    async upsertEntitlement(row) {
      const i = ents.findIndex((e) => e.install_id === row.install_id && e.product === row.product);
      if (i >= 0) {
        const prev = ents[i];
        ents[i] = {
          ...prev,
          ...row,
          stripe_customer_id: row.stripe_customer_id || prev.stripe_customer_id || null,
          stripe_subscription_id: row.stripe_subscription_id || prev.stripe_subscription_id || null,
          expires_at: row.expires_at === undefined ? prev.expires_at : row.expires_at,
        };
      } else {
        ents.push({
          stripe_customer_id: null,
          stripe_subscription_id: null,
          expires_at: null,
          ...row,
        });
      }
    },
  };
}

export function d1Store(db) {
  return {
    async createInstall(id, now) {
      const res = await db.prepare(
        "INSERT OR IGNORE INTO installs (install_id, created_at) VALUES (?, ?)",
      ).bind(id, now).run();
      return (res.meta?.changes || 0) > 0;
    },
    async getInstall(id) {
      return db.prepare("SELECT install_id, created_at FROM installs WHERE install_id = ?").bind(id).first();
    },
    async listInstalls() {
      const { results: rows } = await db.prepare(
        "SELECT install_id, created_at FROM installs ORDER BY created_at",
      ).all();
      const { results: entRows } = await db.prepare(
        "SELECT install_id, product, status, expires_at, stripe_customer_id, stripe_subscription_id, created_at, updated_at FROM entitlements",
      ).all();
      return (rows || []).map((row) => ({
        ...row,
        entitlements: (entRows || []).filter((e) => e.install_id === row.install_id),
      }));
    },
    async entitlementsForInstall(id) {
      const { results } = await db.prepare(
        "SELECT install_id, product, status, expires_at, stripe_customer_id, stripe_subscription_id, created_at, updated_at FROM entitlements WHERE install_id = ?",
      ).bind(id).all();
      return results || [];
    },
    async findBySubscription(subId) {
      if (!subId) return [];
      const { results } = await db.prepare(
        "SELECT install_id, product, status, expires_at, stripe_customer_id, stripe_subscription_id, created_at, updated_at FROM entitlements WHERE stripe_subscription_id = ?",
      ).bind(subId).all();
      return results || [];
    },
    async upsertEntitlement(row) {
      await db.prepare(
        `INSERT INTO entitlements (
           install_id, product, status, expires_at, stripe_customer_id, stripe_subscription_id, created_at, updated_at
         ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
         ON CONFLICT(install_id, product) DO UPDATE SET
           status = excluded.status,
           expires_at = excluded.expires_at,
           stripe_customer_id = COALESCE(excluded.stripe_customer_id, entitlements.stripe_customer_id),
           stripe_subscription_id = COALESCE(excluded.stripe_subscription_id, entitlements.stripe_subscription_id),
           updated_at = excluded.updated_at`,
      ).bind(
        row.install_id,
        row.product,
        row.status,
        row.expires_at ?? null,
        row.stripe_customer_id ?? null,
        row.stripe_subscription_id ?? null,
        row.created_at,
        row.updated_at,
      ).run();
    },
  };
}
