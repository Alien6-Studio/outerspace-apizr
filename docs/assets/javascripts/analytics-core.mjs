// Release prerequisite: disable automatic history/form/search/scroll/outbound/video/download
// and user-provided-data collection in GA. Embedded public forms are not isolated documents.
export const CONSENT_KEY = 'marketing-analytics-consent-v2';
export const CONSENT_KEYS = [CONSENT_KEY, 'marketing-analytics-consent-v1', 'attest:analytics-consent:v1'];
export const MEASUREMENT_VERSION = 'marketing_v2';
const LIFE = 180 * 86400000;
const SITES = ['alien6', 'apizr', 'attest', 'hanko', 'trunx', 'signal', 'ruleflow'];
// Verified portfolio bindings. An environment override cannot silently change the destination.
export const GTM_BINDINGS = Object.freeze({
  alien6: { measurementId: 'G-Y5K3ME6MSG', containerId: 'GTM-NCP7M8VG' },
  apizr: { measurementId: 'G-MX4P2Y5EG4', containerId: 'GTM-WWM6WV6H' },
  attest: { measurementId: 'G-3XEQ6E2NHX', containerId: 'GTM-P43B2L5B' },
  hanko: { measurementId: 'G-30PLNNQP00', containerId: 'GTM-WWFBX6H8' },
  trunx: { measurementId: 'G-J83K01YWWT', containerId: 'GTM-NHD9K3HX' },
  signal: { measurementId: 'G-ZKXC86GEL7', containerId: 'GTM-W48B97CZ' },
  ruleflow: { measurementId: 'G-YZKX7Y39XE', containerId: 'GTM-TN46HSGN' },
});
export const GTM_STATE_KEY = '__a6AudienceV2'; // gitleaks:allow -- Public browser property name.
const TYPES = ['home', 'article', 'documentation', 'product', 'feature', 'pricing', 'service', 'case_study', 'academy'];
const POSITIONS = ['header', 'hero', 'content', 'article_list', 'read_next', 'footer', 'navigation', 'pricing', 'resources'];
const CTA_KINDS = ['contact', 'signup', 'demo', 'documentation', 'download', 'external_product', 'repository', 'product'];
const id = value => typeof value === 'string' && /^[a-z][a-z0-9_-]{0,99}$/.test(value);
const clean = value => typeof value === 'string' && value.startsWith('/') && !value.includes('%') ? value.split(/[?#]/)[0] : '';
const keyPath = value => clean(value).replace(/\/$/, '') || '/';

/** One controller per document. Unknown paths and missing allowlists fail closed. */
export function createAnalytics({ measurementId, hostnames = [], production, siteId, publicPaths = [], consentKeys = [] }, browser) {
  const binding = GTM_BINDINGS[siteId];
  const enabled = Boolean(browser && production && binding?.measurementId === measurementId && hostnames.includes(browser.location.hostname));
  const legacyKeys = [...new Set([...CONSENT_KEYS.slice(1), ...consentKeys])].filter(key => key !== CONSENT_KEY);
  const optOut = 'marketing-analytics-optout-v2';
  const disabledKey = `ga-disable-${measurementId}`;
  const listeners = new Set();
  let choice = enabled ? 'unknown' : 'disabled';
  let started = false, initialized = false, loaded = false, gtmReady = false, script, channel, previousPath = '', pageReferrer = '', boundaryRequested = false;
  let epoch = Number(browser?.[GTM_STATE_KEY]?.epoch) || 0;
  let expiryTimer, expiryAt = 0;
  const path = () => clean(browser?.location.pathname);
  const publicPath = candidate => {
    const pathname = clean(candidate);
    const segments = pathname.split('/').filter(Boolean);
    const section = ['fr', 'en', 'de', 'es', 'it'].includes(segments[0]) ? segments[1] : segments[0];
    if (!pathname || /^(auth|login|logout|register|signup|signin|sign-in|callback|oauth|account|profile|dashboard|admin|contact|checkout|preview|api|reset-password|forgot-password)$/i.test(section || '')) return false;
    return publicPaths.some(pattern => {
      if (typeof pattern === 'string') return Boolean(clean(pattern)) && keyPath(pattern) === keyPath(pathname);
      if (pattern instanceof RegExp) { pattern.lastIndex = 0; return pattern.test(pathname); }
      return false;
    });
  };
  const documentPublic = enabled && publicPath(path());
  const notify = () => listeners.forEach(listener => listener());
  const parse = raw => {
    try {
      const saved = JSON.parse(raw);
      return ['granted', 'denied'].includes(saved?.choice) && Number.isFinite(saved.expires)
        && saved.expires > Date.now() && saved.expires <= Date.now() + LIFE + 86400000 ? saved : null;
    } catch { return null; }
  };
  const marker = expires => {
    try { browser.document.cookie = `${optOut}=${expires ? '1' : ''}; Max-Age=${expires ? Math.max(0, Math.floor((expires - Date.now()) / 1000)) : 0}; Path=/; SameSite=Lax${browser.location.protocol === 'https:' ? '; Secure' : ''}`; } catch { /* Reads fail closed. */ }
  };
  const read = changedKey => {
    try {
      if (browser.document.cookie.split(';').some(value => value.trim() === `${optOut}=1`)) return 'denied';
      if (legacyKeys.includes(changedKey)) {
        const legacy = parse(browser.localStorage.getItem(changedKey));
        if (legacy?.choice === 'denied') { marker(legacy.expires); return 'denied'; }
      }
      const raw = browser.localStorage.getItem(CONSENT_KEY);
      const saved = parse(raw);
      if (saved?.version === 2) {
        if (saved.choice === 'granted') browser.localStorage.setItem(CONSENT_KEY, raw);
        return saved.choice;
      }
      // Legacy grants did not cover the broader v2 event notice. Denials remain valid.
      for (const key of legacyKeys) if (parse(browser.localStorage.getItem(key))?.choice === 'denied') return 'denied';
    } catch { /* A readable but unwritable old grant must not replay. */ }
    return 'unknown';
  };
  const initialize = () => {
    if (initialized) return true;
    browser.dataLayer ||= [];
    if (typeof browser.dataLayer.push !== 'function') return false;
    initialized = true;
    return true;
  };
  const stop = () => {
    browser[disabledKey] = true;
    if (expiryTimer !== undefined) browser.clearTimeout?.(expiryTimer);
    expiryTimer = undefined; expiryAt = 0;
    if (gtmReady) epoch = Math.max(epoch, Number(browser[GTM_STATE_KEY]?.epoch) || 0) + 1;
    publishState(false);
    if (gtmReady) {
      gtmReady = false;
      // The custom template reads the current snapshot, not a queued historic grant.
      try { browser.dataLayer.push({ event: 'a6_consent_update' }); } catch { /* Immediate opt-out remains effective. */ }
      previousPath = ''; pageReferrer = '';
    }
  };
  const clearCookies = () => {
    try {
      const labels = browser.location.hostname.split('.');
      for (const value of browser.document.cookie.split(';')) {
        const name = value.trim().split('=')[0];
        if (!/^(_ga(?:_|$)|_gid$|_gat(?:_|$)|_gac_)/.test(name)) continue;
        const expired = `${name}=; Max-Age=0; Path=/; SameSite=Lax`;
        browser.document.cookie = expired;
        for (let index = 0; index < labels.length - 1; index++) browser.document.cookie = `${expired}; Domain=.${labels.slice(index).join('.')}`;
      }
    } catch { /* Preserve essential cookies. */ }
  };
  const requestFreshDocument = url => {
    stop();
    if (boundaryRequested) return;
    boundaryRequested = true;
    if (url) browser.location.assign(url); else browser.location.reload();
  };
  const fresh = () => {
    if (enabled && publicPath(path()) !== documentPublic) { requestFreshDocument(); return false; }
    if (!enabled || !SITES.includes(siteId) || !documentPublic || !publicPath(path()) || boundaryRequested) return false;
    if (read() !== 'granted') { syncConsent(); return false; }
    return choice === 'granted' && loaded && browser[disabledKey] !== true && publishState(true);
  };
  const safeReferrer = value => {
    try { const url = new URL(value); return ['http:', 'https:'].includes(url.protocol) ? url.origin : ''; } catch { return ''; }
  };

  /** Only public metadata is exposed to the internal GTM consent template. */
  function publishState(granted) {
    let expires = 0;
    if (granted) try {
      const saved = parse(browser.localStorage.getItem(CONSENT_KEY));
      if (saved?.version === 2 && saved.choice === 'granted' && read() === 'granted') expires = saved.expires;
    } catch { /* The GTM template must see denial if storage becomes unavailable. */ }
    const isPublic = documentPublic && publicPath(path()) && !boundaryRequested;
    let allowed = Boolean(expires && isPublic);
    const state = {
      version: 1, siteId, measurementId, containerId: binding?.containerId,
      epoch,
      granted: allowed, expires: allowed ? expires : 0, publicDocument: isPublic,
      hostname: browser.location.hostname, pathname: isPublic ? path() : '',
      page_location: isPublic ? browser.location.origin + path() : '',
      page_referrer: isPublic ? pageReferrer || safeReferrer(browser.document.referrer) : '',
    };
    browser[GTM_STATE_KEY] = state;
    // Replace the namespace so values from previous routes cannot merge into this context.
    if (typeof browser.dataLayer?.push === 'function') try {
      browser.dataLayer.push({ a6_audience: null });
      browser.dataLayer.push({ a6_audience: { ...state } });
    } catch {
      allowed = false;
      browser[GTM_STATE_KEY] = { ...state, granted: false, expires: 0 };
      browser[disabledKey] = true;
    }
    return allowed;
  }
  const send = (event, metadata, context) => {
    if (!fresh()) return false;
    try {
      const parameters = {
        ...metadata, site_id: siteId, site_language: ['fr', 'en', 'de', 'es', 'it'].includes(path().split('/')[1]) ? path().split('/')[1] : 'en',
        measurement_version: MEASUREMENT_VERSION,
        page_location: browser.location.origin + path(), page_referrer: context ?? pageReferrer,
      };
      browser.dataLayer.push({ a6_event: null });
      browser.dataLayer.push({ event: 'a6_measurement', a6_event: { name: event, epoch, parameters } });
      return true;
    } catch { return false; }
  };

  function armExpiry(expires) {
    if (typeof browser.setTimeout !== 'function' || expiryAt === expires && expiryTimer !== undefined) return;
    if (expiryTimer !== undefined) browser.clearTimeout?.(expiryTimer);
    expiryAt = expires;
    expiryTimer = browser.setTimeout(() => {
      expiryTimer = undefined; expiryAt = 0;
      syncConsent();
    }, Math.min(2147483647, Math.max(1, expires - Date.now())));
  }

  function trackPage(candidate = path()) {
    if (!enabled) return false;
    if (publicPath(path()) !== documentPublic) { requestFreshDocument(); return false; }
    const pathname = clean(candidate);
    if (!pathname || keyPath(pathname) !== keyPath(path()) || !fresh()) return false;
    if (previousPath && keyPath(previousPath) === keyPath(pathname)) return false;
    const referrer = previousPath ? browser.location.origin + previousPath : safeReferrer(browser.document.referrer);
    if (!send('page_view', {}, referrer)) return false;
    previousPath = pathname; pageReferrer = referrer;
    return true;
  }

  function load() {
    if (!documentPublic || !publicPath(path()) || read() !== 'granted' || !SITES.includes(siteId)) return;
    if (!initialize()) return;
    try {
    if (!gtmReady) epoch = Math.max(epoch, Number(browser[GTM_STATE_KEY]?.epoch) || 0) + 1;
    if (!publishState(true)) { stop(); return; }
    armExpiry(browser[GTM_STATE_KEY].expires);
    browser[disabledKey] = false;
    if (!loaded) {
      loaded = true;
      browser.dataLayer.push({ 'gtm.start': Date.now(), event: 'gtm.js' });
    }
    if (!gtmReady) {
      browser.dataLayer.push({ event: 'a6_consent_update' });
      browser.dataLayer.push({ event: 'a6_analytics_ready' });
      gtmReady = true;
    }
    if (!script) {
      const element = browser.document.createElement('script');
      element.id = `marketing-analytics-${siteId}`; element.async = true;
      element.src = `https://www.googletagmanager.com/gtm.js?id=${binding.containerId}`;
      element.onerror = () => { if (script === element) script = undefined; element.remove?.(); };
      script = element; browser.document.head.appendChild(element);
    }
    trackPage();
    } catch { stop(); }
  }

  function syncConsent(changedKey) {
    if (!enabled) return;
    if (publicPath(path()) !== documentPublic) { requestFreshDocument(); return; }
    const next = read(changedKey);
    if (next !== 'granted') { stop(); clearCookies(); }
    const changed = choice !== next; choice = next;
    if (next === 'granted') load();
    if (changed) notify();
  }

  function choose(value) {
    if (!enabled || !['granted', 'denied'].includes(value)) return;
    const expires = Date.now() + LIFE;
    marker(value === 'denied' ? expires : 0);
    const saved = JSON.stringify({ version: 2, choice: value, expires });
    try { browser.localStorage.setItem(CONSENT_KEY, saved); } catch {
      if (value === 'denied') try { browser.localStorage.removeItem(CONSENT_KEY); } catch { /* Refusal cookie takes precedence. */ }
    }
    if (value === 'denied') {
      stop(); clearCookies();
      try { channel?.postMessage({ event: 'audience-denied', expires }); } catch { /* Storage/focus/pageshow still synchronize. */ }
      // Already-open Attest/legacy tabs must see withdrawals, without authorizing their old grants.
      for (const key of legacyKeys) try { browser.localStorage.setItem(key, JSON.stringify({ choice: 'denied', expires })); } catch { /* Best effort compatibility. */ }
    } else {
      // A fresh explicit v2 grant supersedes old refusals without replaying old interactions.
      for (const key of legacyKeys) try { browser.localStorage.removeItem(key); } catch { /* v2 remains authoritative. */ }
    }
    syncConsent();
  }

  function trackInteraction(event, metadata = {}, element) {
    if (!['select_content', 'cta_open', 'content_engaged'].includes(event) || !fresh()) return false;
    if (!metadata || typeof metadata !== 'object' || Array.isArray(metadata)) return false;
    if (element?.closest?.('form,[data-analytics-private]') || browser.document.activeElement?.closest?.('form,[data-analytics-private]')) return false;
    const permitted = ['content_id', 'content_type', 'link_position', ...(event === 'cta_open' ? ['cta_id', 'cta_kind'] : []), ...(event === 'content_engaged' ? ['engagement_rule'] : [])];
    if (Object.keys(metadata).some(key => !permitted.includes(key)) || !id(metadata.content_id) || !TYPES.includes(metadata.content_type)) return false;
    if (event === 'content_engaged' ? metadata.engagement_rule !== '30s_50pct' || metadata.link_position !== undefined : !POSITIONS.includes(metadata.link_position)) return false;
    if (event === 'cta_open' && (!id(metadata.cta_id) || !CTA_KINDS.includes(metadata.cta_kind))) return false;
    trackPage();
    return send(event, metadata);
  }

  function capture(event) {
    if (event.defaultPrevented || (event.type === 'click' ? event.button !== 0 : event.button !== 1)) return;
    const source = event.target?.closest ? event.target : event.target?.parentElement;
    const target = source?.closest?.('a[href]') || source?.closest?.('button[data-analytics-event]');
    if (!target || target.hasAttribute('download')) return;
    let destination;
    if (target.href) {
      try { destination = new URL(target.href, browser.location.href); } catch { return; }
      if (!['https:', 'http:'].includes(destination.protocol)) return;
    } else if (event.type !== 'click' || target.dataset?.analyticsEvent !== 'cta_open') return;
    const data = target.dataset;
    if (data?.analyticsEvent && (data.analyticsEvent !== 'select_content' || destination?.origin === browser.location.origin && publicPath(destination.pathname))) {
      const metadata = { content_id: data.analyticsContentId, content_type: data.analyticsContentType, link_position: data.analyticsPosition };
      if (data.analyticsEvent === 'cta_open') Object.assign(metadata, { cta_id: data.analyticsCtaId, cta_kind: data.analyticsCtaKind });
      trackInteraction(data.analyticsEvent, metadata, target);
    }
    if (event.type !== 'click' || event.metaKey || event.ctrlKey || event.shiftKey || event.altKey || target.target && target.target !== '_self') return;
    if (destination?.origin === browser.location.origin && publicPath(destination.pathname) !== documentPublic) {
      event.preventDefault(); event.stopPropagation(); requestFreshDocument(destination.href);
    }
  }

  function start() {
    if (!enabled || started) return;
    started = true; browser[disabledKey] = true;
    publishState(false);
    if (documentPublic) initialize();
    browser.document.addEventListener('click', capture, true);
    browser.document.addEventListener('auxclick', capture, true);
    browser.addEventListener('storage', event => { if (event.key === null || CONSENT_KEYS.includes(event.key) || legacyKeys.includes(event.key)) syncConsent(event.key); });
    browser.addEventListener('focus', () => syncConsent());
    browser.addEventListener('pageshow', () => syncConsent());
    if (typeof browser.BroadcastChannel === 'function') try {
      channel = new browser.BroadcastChannel('marketing-audience-v2');
      channel.onmessage = event => {
        if (event.data?.event !== 'audience-denied') return;
        const expires = Number(event.data.expires);
        if (!Number.isFinite(expires) || expires <= Date.now() || expires > Date.now() + LIFE + 1000) return;
        marker(expires);
        try { browser.localStorage.setItem(CONSENT_KEY, JSON.stringify({ version: 2, choice: 'denied', expires })); } catch { /* Refusal marker and immediate opt-out still apply. */ }
        stop(); clearCookies(); choice = 'denied'; notify();
      };
    } catch { /* Some browser policies disallow channels; retain the other listeners. */ }
    syncConsent();
  }

  return { start, choose, syncConsent, trackPage, trackLead() {}, trackInteraction, subscribe(listener) { listeners.add(listener); return () => listeners.delete(listener); }, getSnapshot: () => choice };
}

/** Optional proxy: explicitly marked authored body only, bound to one route view. */
export function observeContentEngagement(controller, browser) {
  const route = keyPath(browser.location.pathname);
  const measured = new Set();
  let element, contentKey, activeMs = 0, depth = false, sent = false, away = false;
  let last = browser.performance.now(), active = false;
  const reset = () => { element = undefined; contentKey = ''; activeMs = 0; depth = false; sent = false; active = false; };
  const visible = () => !away && browser.document.visibilityState === 'visible' && browser.document.hasFocus()
    && !browser.document.activeElement?.closest?.('form,[data-analytics-private]');
  const tick = () => {
    const now = browser.performance.now(), elapsed = Math.max(0, Math.min(1000, now - last)); last = now;
    if (keyPath(browser.location.pathname) !== route || controller.getSnapshot() !== 'granted') { reset(); return; }
    const body = browser.document.querySelector('[data-analytics-body]');
    const data = body?.dataset;
    const nextKey = `${data?.analyticsContentId}:${data?.analyticsPath}`;
    if (!body || body.closest('form,[data-analytics-private]') || !id(data.analyticsContentId) || !TYPES.includes(data.analyticsContentType) || !data.analyticsPath || keyPath(data.analyticsPath) !== route) { reset(); return; }
    if (body !== element || nextKey !== contentKey) { reset(); element = body; contentKey = nextKey; sent = measured.has(nextKey); }
    else if (active) activeMs += elapsed;
    active = visible();
    if (!active) return;
    const bounds = body.getBoundingClientRect();
    if (bounds.height > 0 && (browser.innerHeight - bounds.top) / bounds.height >= 0.5) depth = true;
    if (!sent && activeMs >= 30000 && depth) {
      sent = controller.trackInteraction('content_engaged', { content_id: data.analyticsContentId, content_type: data.analyticsContentType, engagement_rule: '30s_50pct' }, body);
      if (sent) measured.add(nextKey);
    }
  };
  const hide = () => { tick(); away = true; active = false; };
  const show = () => { away = false; tick(); };
  const timer = browser.setInterval(tick, 1000);
  for (const type of ['scroll', 'resize', 'focus', 'blur']) browser.addEventListener(type, tick);
  browser.addEventListener('pagehide', hide); browser.addEventListener('pageshow', show);
  browser.document.addEventListener('visibilitychange', tick);
  browser.document.addEventListener('focusin', tick);
  browser.document.addEventListener('focusout', tick);
  tick();
  return () => {
    browser.clearInterval(timer);
    for (const type of ['scroll', 'resize', 'focus', 'blur']) browser.removeEventListener(type, tick);
    browser.removeEventListener('pagehide', hide); browser.removeEventListener('pageshow', show);
    browser.document.removeEventListener('visibilitychange', tick);
    browser.document.removeEventListener('focusin', tick);
    browser.document.removeEventListener('focusout', tick);
  };
}
