const model = 'clavius-drive-directional-horizon-v1';

export async function loadDriveSource(name, signal) {
  const index = await fetch('/data/manifest.json', {signal});
  if (!index.ok) throw new Error('Drive source manifest unavailable');
  const record = (await index.json()).rover_drive.sources[name];
  const response = await fetch(record.url, {signal});
  if (!response.ok) throw new Error('Drive source unavailable');
  const bytes = await response.arrayBuffer();
  const digest = new Uint8Array(await crypto.subtle.digest('SHA-256', bytes));
  const actual = Array.from(digest, byte => byte.toString(16).padStart(2, '0')).join('');
  if (actual !== record.sha256) throw new Error('Drive source checksum mismatch');
  return JSON.parse(new TextDecoder().decode(bytes));
}

export function replaySunlight(catalog, context) {
  const site = catalog?.sites?.[context.site];
  if (!context.native || catalog?.model !== model || catalog.sample_interval_s !== 1 ||
      !site) return null;
  const trace = [site, ...Object.values(site.maneuvers ?? {})].find(
    entry => entry.replay_sha256 === context.replayHash
  );
  const second = Math.floor(context.elapsed);
  const series = trace?.samples?.[context.start];
  const sample = series?.[second];
  return sample ? {sample, series, elapsed: second, source: 'Packaged replay'} : null;
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
    let saved = replaySunlight(this.catalog, ctx);
    const live = this.liveSeries;
    if (!saved && ctx.native && live && live.site_id === ctx.site && live.start_utc === ctx.start &&
        live.replay_sha256 === ctx.replayHash) {
      const second = Math.floor(ctx.elapsed);
      saved = {sample:live.samples[second], series:live.samples, elapsed:second, source:'Live service'};
    }
    if (saved && usable(saved.sample)) {
      this.previous = ctx;
      this.publish(saved);
      return;
    }
    // The manual render quaternion is reused next frame. Bind the sampled attitude
    // to this request before it leaves the browser.
    this.requestLive(ctx.orientation ? {...ctx, orientation:ctx.orientation.clone()} : ctx);
  }

  async requestLive(ctx) {
    const request = new AbortController();
    this.pending = request;
    const params = new URLSearchParams({
      start_utc: ctx.start, elapsed_s: ctx.elapsed, east_m: ctx.east, north_m: ctx.north
    });
    const timeout = setTimeout(() => request.abort(), 10000);
    try {
      const base = '/api/v1/sites/' + encodeURIComponent(ctx.site);
      const path = ctx.native ? base + '/drive-replay-environment?' +
        new URLSearchParams({start_utc:ctx.start, replay_sha256:ctx.replayHash}) :
        base + '/drive-environment?' + params;
      const response = await this.fetcher(path, {signal: request.signal});
      if (!response.ok) throw new Error('Environment service unavailable');
      const result = await response.json();
      if (this.pending !== request) return;
      if (ctx.native) {
        if (result.site_id !== ctx.site || result.model !== model || result.start_utc !== ctx.start ||
            result.replay_sha256 !== ctx.replayHash || result.sample_interval_s !== 1 ||
            result.samples?.length !== 21 || !result.samples.every(usable)) throw new Error('Invalid traverse environment');
        this.liveSeries = result;
        // The cursor may have moved while computing the whole traverse.
        this.previous = null;
        return;
      }
      const sample = result.sample;
      if (result.site_id !== ctx.site || result.model !== model || result.elapsed_s !== ctx.elapsed ||
          !usable(sample) || sample.east_m !== ctx.east || sample.north_m !== ctx.north) {
        throw new Error('Incomplete environment sample');
      }
      if (this.pending !== request) return;
      this.previous = ctx;
      this.publish({sample, elapsed: result.elapsed_s, orientation: ctx.orientation, source: 'Live service'});
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
