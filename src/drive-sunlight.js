const model = 'clavius-drive-directional-horizon-v1';

export async function loadSunlightCatalog(signal) {
  const index = await fetch('/data/manifest.json', {signal});
  if (!index.ok) throw new Error('Drive source manifest unavailable');
  const record = (await index.json()).rover_drive.sources.sunlight;
  const response = await fetch(record.url, {signal});
  if (!response.ok) throw new Error('Sunlight samples unavailable');
  const bytes = await response.arrayBuffer();
  const digest = new Uint8Array(await crypto.subtle.digest('SHA-256', bytes));
  const actual = Array.from(digest, byte => byte.toString(16).padStart(2, '0')).join('');
  if (actual !== record.sha256) throw new Error('Sunlight catalogue checksum mismatch');
  return JSON.parse(new TextDecoder().decode(bytes));
}

export function replaySunlight(catalog, context) {
  const site = catalog?.sites?.[context.site];
  if (!context.native || catalog?.model !== model || catalog.sample_interval_s !== 1 ||
      !site || site.replay_sha256 !== context.replayHash) return null;
  const second = Math.floor(context.elapsed);
  const sample = site.samples?.[context.start]?.[second];
  return sample ? {sample, elapsed: second, source: 'Packaged replay'} : null;
}

function usable(sample) {
  if (!sample || typeof sample.utc !== 'string') return false;
  const direction = sample.sun_site_enu;
  const values = [sample.east_m, sample.north_m, sample.sun_elevation_deg,
    sample.sun_horizon_deg, sample.disk_fraction];
  return Array.isArray(direction) && direction.length === 3 && direction.every(Number.isFinite) &&
    Math.abs(Math.hypot(...direction) - 1) < 1e-5 && values.every(Number.isFinite) &&
    sample.disk_fraction >= 0 && sample.disk_fraction <= 1 && typeof sample.earth_center_visible === 'boolean';
}

// A scrub, date change or site change invalidates any request still in flight.
export class DriveSunlight {
  constructor(publish, fetcher = (url, options) => fetch(url, options)) {
    this.publish = publish;
    this.fetcher = fetcher;
    this.retryAt = 0;
  }

  reset() {
    this.pending?.abort();
    this.pending = null;
    this.previous = null;
    this.retryAt = 0;
    this.publish(null);
  }

  update(ctx, now) {
    if (this.pending || now < this.retryAt) return;
    const old = this.previous;
    if (old && old.site === ctx.site && old.start === ctx.start && old.native === ctx.native &&
        ctx.elapsed >= old.elapsed && Math.floor(ctx.elapsed) === Math.floor(old.elapsed) &&
        Math.hypot(ctx.east - old.east, ctx.north - old.north) < 0.5) return;
    const saved = replaySunlight(this.catalog, ctx);
    if (saved && usable(saved.sample)) {
      this.previous = ctx;
      this.publish(saved);
      return;
    }
    this.requestLive(ctx);
  }

  async requestLive(ctx) {
    const request = new AbortController();
    this.pending = request;
    const params = new URLSearchParams({
      start_utc: ctx.start, elapsed_s: ctx.elapsed, east_m: ctx.east, north_m: ctx.north
    });
    const timeout = setTimeout(() => request.abort(), 10000);
    try {
      const path = '/api/v1/sites/' + encodeURIComponent(ctx.site) + '/drive-environment?' + params;
      const response = await this.fetcher(path, {signal: request.signal});
      if (!response.ok) throw new Error('Environment service unavailable');
      const result = await response.json();
      const sample = result.sample;
      if (result.site_id !== ctx.site || result.model !== model || result.elapsed_s !== ctx.elapsed ||
          !usable(sample) || sample.east_m !== ctx.east || sample.north_m !== ctx.north) {
        throw new Error('Incomplete environment sample');
      }
      if (this.pending !== request) return;
      this.previous = ctx;
      this.publish({sample, elapsed: result.elapsed_s, source: 'Live service'});
      this.retryAt = performance.now() + 200;
    } catch {
      if (this.pending !== request) return;
      this.previous = null;
      this.retryAt = performance.now() + 5000;
      this.publish({unavailable: true});
    } finally {
      clearTimeout(timeout);
      if (this.pending === request) this.pending = null;
    }
  }
}
