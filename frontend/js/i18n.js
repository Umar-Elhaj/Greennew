/**
 * GREEN App — i18n (French / English)
 *
 * Loaded synchronously in <head>, right after /js/translations.js, so the
 * language is known before the first paint:
 *   <script src="/js/translations.js"></script>
 *   <script src="/js/i18n.js"></script>
 *
 * Markup:
 *   data-i18n="key"               textContent
 *   data-i18n-html="key"          innerHTML (dictionary content only, never user data)
 *   data-i18n-placeholder="key"   placeholder
 *   data-i18n-title="key"         title
 *   data-i18n-aria-label="key"    aria-label
 *   data-i18n-alt="key"           alt
 *   data-i18n-params='{"n": 3}'   values for {{n}} (and plural selection with "count")
 *
 * JS:
 *   I18n.t('common.items', { count: 12 })     → key_one / key_other via Intl.PluralRules
 *   I18n.number(1234.5), I18n.date(iso), I18n.money(25000)  (fr-CM / en-CM, XAF)
 *   window.addEventListener('languageChanged', redraw)
 *
 * Initial language: saved choice, else the browser language (fr / en), else fr.
 */
(function () {
  const STORAGE_KEY = 'green_lang';
  const LEGACY_KEY = 'green_language';
  const SUPPORTED = ['fr', 'en'];
  const DICT = window.GREEN_I18N_DICT || { fr: {}, en: {} };

  function storageGet(k) { try { return localStorage.getItem(k); } catch (_) { return null; } }
  function storageSet(k, v) { try { localStorage.setItem(k, v); } catch (_) { /* private mode */ } }

  function initialLang() {
    let saved = storageGet(STORAGE_KEY) || storageGet(LEGACY_KEY);
    if (SUPPORTED.includes(saved)) return saved;
    const nav = ((navigator.languages && navigator.languages[0]) || navigator.language || '').toLowerCase();
    if (nav.startsWith('en')) return 'en';
    return 'fr';
  }

  function lookup(lang, key) {
    let v = DICT[lang];
    for (const part of key.split('.')) {
      if (v && typeof v === 'object' && part in v) v = v[part];
      else return undefined;
    }
    return typeof v === 'string' ? v : undefined;
  }

  const warned = new Set();

  const I18n = {
    lang: initialLang(),

    get locale() { return this.lang === 'fr' ? 'fr-CM' : 'en-CM'; },

    /** Translate `key`; `params` fills {{name}}; `params.count` selects key_one / key_other. */
    t(key, params) {
      params = params || {};
      let candidates = [key];
      if (typeof params.count === 'number') {
        const cat = new Intl.PluralRules(this.locale).select(params.count);
        candidates = [`${key}_${cat}`, `${key}_other`, key];
      }
      let value;
      for (const lang of [this.lang, this.lang === 'fr' ? 'en' : 'fr']) {
        for (const k of candidates) {
          value = lookup(lang, k);
          if (value !== undefined) break;
        }
        if (value !== undefined) break;
      }
      if (value === undefined) {
        if (!warned.has(key)) { warned.add(key); console.warn(`[i18n] missing key: ${key}`); }
        return key;
      }
      return value.replace(/\{\{\s*(\w+)\s*\}\}/g, (m, name) => {
        if (!(name in params)) return m;
        const v = params[name];
        return typeof v === 'number' ? this.number(v) : String(v);
      });
    },

    /** True when the key exists (used for optional server codes). */
    has(key) { return lookup(this.lang, key) !== undefined; },

    /** Translate every data-i18n* attribute under `root`. */
    apply(root) {
      root = root || document;
      const params = (el) => {
        const raw = el.getAttribute('data-i18n-params');
        if (!raw) return undefined;
        try { return JSON.parse(raw); } catch (_) { return undefined; }
      };
      root.querySelectorAll('[data-i18n]').forEach((el) => {
        el.textContent = this.t(el.getAttribute('data-i18n'), params(el));
      });
      root.querySelectorAll('[data-i18n-html]').forEach((el) => {
        el.innerHTML = this.t(el.getAttribute('data-i18n-html'), params(el));
      });
      const attrs = { placeholder: 'placeholder', title: 'title', 'aria-label': 'aria-label', alt: 'alt' };
      for (const [suffix, attr] of Object.entries(attrs)) {
        root.querySelectorAll(`[data-i18n-${suffix}]`).forEach((el) => {
          el.setAttribute(attr, this.t(el.getAttribute(`data-i18n-${suffix}`), params(el)));
        });
      }
    },

    setLanguage(lang) {
      if (!SUPPORTED.includes(lang)) return;
      const changed = lang !== this.lang;
      this.lang = lang;
      storageSet(STORAGE_KEY, lang);
      document.documentElement.lang = lang;
      this.apply();
      if (changed) window.dispatchEvent(new CustomEvent('languageChanged', { detail: { lang } }));
    },

    // ---- Formatting (Intl) ---------------------------------
    number(n, opts) {
      if (n === null || n === undefined || Number.isNaN(Number(n))) return '—';
      return new Intl.NumberFormat(this.locale, opts).format(n);
    },
    percent(ratio, digits) {
      return this.number(ratio, { style: 'percent', maximumFractionDigits: digits === undefined ? 0 : digits });
    },
    money(n) {
      return this.number(n, { style: 'currency', currency: 'XAF', maximumFractionDigits: 0 });
    },
    date(d, opts) {
      if (!d) return '—';
      const date = d instanceof Date ? d : new Date(d);
      if (Number.isNaN(date.getTime())) return '—';
      return new Intl.DateTimeFormat(this.locale, opts || { year: 'numeric', month: 'long', day: 'numeric' }).format(date);
    },
    dateTime(d) {
      return this.date(d, { year: 'numeric', month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' });
    },
    /** "3 days ago" / "il y a 3 jours" */
    relative(d) {
      const date = d instanceof Date ? d : new Date(d);
      const secs = (date.getTime() - Date.now()) / 1000;
      const rtf = new Intl.RelativeTimeFormat(this.locale, { numeric: 'auto' });
      const steps = [[60, 'second'], [60, 'minute'], [24, 'hour'], [7, 'day'], [4.345, 'week'], [12, 'month'], [Infinity, 'year']];
      let v = secs;
      for (const [size, unit] of steps) {
        if (Math.abs(v) < size) return rtf.format(Math.round(v), unit);
        v /= size;
      }
      return this.date(date);
    },
  };

  window.I18n = window.i18n = I18n;
  document.documentElement.lang = I18n.lang;
  storageSet(STORAGE_KEY, I18n.lang);

  // Hide the page until it is translated (no flash of the other language).
  // The safety timeout keeps the page usable if a script fails.
  document.documentElement.classList.add('i18n-pending');
  const style = document.createElement('style');
  style.textContent = 'html.i18n-pending body{visibility:hidden}';
  document.head.appendChild(style);
  const reveal = () => document.documentElement.classList.remove('i18n-pending');
  setTimeout(reveal, 1500);

  document.addEventListener('DOMContentLoaded', () => {
    I18n.apply();
    reveal();
  });
})();
