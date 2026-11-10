import { createApp } from "./app.js";
import { prices } from "./prices.js";
import { d1Store } from "./store.js";

export default {
  async fetch(request, env) {
    const app = createApp({
      store: d1Store(env.DB),
      env,
      now: () => new Date(),
      catalog: prices,
    });
    return app.handle(request);
  },
};
