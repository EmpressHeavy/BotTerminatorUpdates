-- Install id, product, status, Stripe ids, timestamps. No X handles or profiles.
CREATE TABLE IF NOT EXISTS installs (
  install_id TEXT PRIMARY KEY,
  created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS entitlements (
  install_id TEXT NOT NULL,
  product TEXT NOT NULL,
  status TEXT NOT NULL,
  expires_at TEXT,
  stripe_customer_id TEXT,
  stripe_subscription_id TEXT,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  PRIMARY KEY (install_id, product)
);

CREATE INDEX IF NOT EXISTS entitlements_subscription
  ON entitlements (stripe_subscription_id);
