import { createAnalytics, observeContentEngagement, CONSENT_KEY } from './analytics-core.mjs';

const pathKey = value => value.replace(/\/$/, '') || '/';
const attributes = (event, content, position, cta) => ({
  analyticsEvent: event, analyticsContentId: content.content_id, analyticsContentType: content.content_type, analyticsPosition: position,
  ...(cta ? { analyticsCtaId: cta[0], analyticsCtaKind: cta[1] } : {}),
});
const HOME_CTAS = {
  '/getting-started/quickstart': ['home_quickstart', 'documentation'],
  '/getting-started/data-science': ['home_notebook_prediction', 'documentation'],
  '/getting-started/install': ['home_install', 'documentation'],
  '/academy': ['home_academy', 'documentation'],
};
const EXTERNAL_CTAS = {
  'github.com/alien6-studio/outerspace-apizr': ['apizr_repository', 'repository'],
  'pypi.org/project/outerspace-apizr': ['apizr_package', 'product'],
};

/** Preserve native Material choices/reload; legacy analytics grants do not grant v2. */
export function mountApizrAnalytics(browser, catalogue, measurementId, dependencies = {}) {
  if (browser.__apizrAudienceV2) return browser.__apizrAudienceV2;
  const entries = new Map(Object.entries(catalogue).map(([path, content]) => [pathKey(path), content]));
  const controller = (dependencies.createAnalytics || createAnalytics)({ measurementId, hostnames: ['apizr.outerspace.sh'], production: true, siteId: 'apizr', publicPaths: Object.keys(catalogue) }, browser);
  const observe = dependencies.observeContentEngagement || observeContentEngagement;
  let disposeEngagement = () => {}, observedPath, prompted = false, subscription, disposed = false, restored = false, previousNative, missingNative = false, choosing = false;
  const owned = new WeakMap();
  const nativeChoice = () => {
    try {
      const value = browser.__md_get?.('__consent');
      return value && typeof value === 'object' && !Array.isArray(value) && Object.values(value).every(item => typeof item === 'boolean') ? value : null;
    } catch { return null; }
  };
  // Inspect pending v2 state before start() can load it. Preserve existing refusal expiry.
  const pendingChoice = () => {
    try {
      if (browser.document.cookie.split(';').some(value => value.trim() === 'marketing-analytics-optout-v2=1')) return 'denied';
      const value = JSON.parse(browser.localStorage.getItem(CONSENT_KEY));
      return value?.version === 2 && ['granted', 'denied'].includes(value.choice) && Number.isFinite(value.expires)
        && value.expires > Date.now() && value.expires <= Date.now() + 181 * 86400000 ? value.choice : 'unknown';
    } catch { return 'unknown'; }
  };
  const reconcile = () => {
    const consent = nativeChoice(), native = consent ? consent.analytics === true : undefined;
    if (choosing) return consent;
    if (native === undefined && (!restored || previousNative !== undefined)) prompted = false;
    missingNative = native === undefined;
    const pending = pendingChoice();
    const revoke = native !== true && (controller.getSnapshot() === 'granted' || pending === 'granted')
      || !restored && native === false && pending !== 'denied';
    restored = true; previousNative = native;
    if (revoke) controller.choose('denied');
    return consent;
  };
  const materialKey = `${browser.__md_scope?.pathname || '/'}.__consent`;
  const consentForm = () => browser.document.forms.consent;
  const prompt = () => {
    if ((!missingNative && controller.getSnapshot() !== 'unknown') || prompted) return;
    const form = consentForm(), panel = browser.document.querySelector('[data-md-component="consent"]');
    if (!form || !panel) return;
    if (form.elements.analytics) form.elements.analytics.checked = false;
    panel.hidden = false; prompted = true;
  };
  const clearOwned = link => {
    const record = owned.get(link);
    if (!record) return;
    for (const [key, value] of Object.entries(record.applied)) if (link.dataset[key] === value) {
      if (record.previous[key] === undefined) delete link.dataset[key]; else link.dataset[key] = record.previous[key];
    }
    owned.delete(link);
  };
  const apply = (link, ...args) => {
    const applied = attributes(...args), previous = Object.fromEntries(Object.keys(applied).map(key => [key, link.dataset[key]]));
    Object.assign(link.dataset, applied); owned.set(link, { applied, previous });
  };
  const decorateLink = link => {
      clearOwned(link);
      const current = entries.get(pathKey(browser.location.pathname));
      if (!current || link.dataset.analyticsEvent || link.closest('form,[data-analytics-private],[data-md-component="search"],[data-md-component="consent"]') || link.hasAttribute('download')) return;
      let url; try { url = new URL(link.href, browser.location.href); } catch { return; }
      if (!['http:', 'https:'].includes(url.protocol)) return;
      const position = link.closest('.md-header') ? 'header' : link.closest('.md-footer') ? 'footer' : link.closest('.md-nav,.md-tabs') ? 'navigation' : 'content';
      if (url.origin === browser.location.origin) {
        const destination = entries.get(pathKey(url.pathname));
        if (!destination || pathKey(url.pathname) === pathKey(browser.location.pathname)) return;
        const cta = pathKey(browser.location.pathname) === '/' && link.matches('.md-button') && HOME_CTAS[pathKey(url.pathname)];
        apply(link, cta ? 'cta_open' : 'select_content', cta ? current : destination, cta ? 'hero' : position, cta);
      } else {
        const cta = EXTERNAL_CTAS[`${url.hostname}${url.pathname.replace(/\/$/, '')}`.toLowerCase()];
        if (cta) apply(link, 'cta_open', current, position, cta);
      }
  };
  const decorate = () => {
    for (const link of browser.document.querySelectorAll('a[href]')) decorateLink(link);
  };
  const engagement = {
    getSnapshot() { reconcile(); return controller.getSnapshot(); },
    trackInteraction(...args) { return reconcile()?.analytics === true && controller.trackInteraction(...args); },
  };
  const view = () => {
    if (disposed) return;
    reconcile();
    decorate(); controller.trackPage(browser.location.pathname);
    const path = pathKey(browser.location.pathname);
    if (path !== observedPath) {
      disposeEngagement(); observedPath = path;
      disposeEngagement = entries.has(path) ? observe(engagement, browser) : () => {};
    }
    prompt();
  };
  const restore = () => {
    const consent = reconcile();
    // A missing Material record requires a new native choice, even if a v2 record remains.
    if (consent?.analytics === true || consent) { controller.start(); controller.syncConsent(); }
    view();
  };
  const choose = event => {
    if (event.target !== consentForm() || !['submit', 'reset'].includes(event.type)) return;
    const granted = event.type === 'submit' && consentForm().elements.analytics?.checked === true;
    choosing = true; restored = true; previousNative = granted; missingNative = false;
    try { controller.choose(granted ? 'granted' : 'denied'); controller.start(); } finally { choosing = false; }
    // Native Material handler preserves the other categories, writes __consent and reloads.
  };
  const storage = event => {
    if (event.key === materialKey || event.key === CONSENT_KEY || event.key === null) restore();
  };
  const preflight = event => {
    const target = event.target?.closest?.('a[href]') || event.target?.parentElement?.closest?.('a[href]');
    if (target) { reconcile(); decorateLink(target); }
  };
  // Refresh only this target before the core's capture listener can emit an old annotation.
  browser.document.addEventListener('click', preflight, true);
  browser.document.addEventListener('auxclick', preflight, true);
  browser.document.addEventListener('submit', choose, true);
  browser.document.addEventListener('reset', choose, true);
  browser.addEventListener('storage', storage);
  browser.addEventListener('focus', restore);
  browser.addEventListener('pageshow', restore);
  const unsubscribe = controller.subscribe(view);
  restore();
  // Material publishes after replacing the page; never add a second history/view producer.
  if (browser.document$?.subscribe) subscription = browser.document$.subscribe(view);
  const result = { controller, dispose() {
    if (disposed) return; disposed = true; disposeEngagement(); unsubscribe(); subscription?.unsubscribe?.();
    browser.document.removeEventListener('submit', choose, true); browser.document.removeEventListener('reset', choose, true);
    browser.document.removeEventListener('click', preflight, true); browser.document.removeEventListener('auxclick', preflight, true);
    browser.removeEventListener('storage', storage); browser.removeEventListener('focus', restore); browser.removeEventListener('pageshow', restore);
  } };
  browser.__apizrAudienceV2 = result;
  return result;
}
