export class TTLCache {
  constructor() {
    this.map = new Map();
    this.inflight = new Map();
  }

  get(key) {
    const item = this.map.get(key);
    if (!item) return null;
    if (Date.now() > item.expiresAt) {
      this.map.delete(key);
      return null;
    }
    return item.value;
  }

  set(key, value, ttlSeconds) {
    this.map.set(key, { value, expiresAt: Date.now() + ttlSeconds * 1000 });
  }

  async getOrCreate(key, ttlSeconds, factory) {
    const hit = this.get(key);
    if (hit !== null) return { value: hit, cached: true };

    if (this.inflight.has(key)) {
      return { value: await this.inflight.get(key), cached: true };
    }

    const promise = (async () => {
      try {
        const value = await factory();
        this.set(key, value, ttlSeconds);
        return value;
      } finally {
        this.inflight.delete(key);
      }
    })();

    this.inflight.set(key, promise);
    return { value: await promise, cached: false };
  }
}

export const cache = new TTLCache();
