/* ============================================================
   GREEN App — Sign-in / register background slideshow
   Photos take turns behind the form: one fades in with a slow zoom,
   then gives way to the next. Purely decorative (aria-hidden).

   Bandwidth: only the first photo is loaded at start; each next one is
   fetched while the current one is on screen. Phones (portrait screens)
   get light portrait crops. With "data saver", a 2G connection or
   "reduce motion", the first photo stays still and nothing else loads.
   ============================================================ */
(function () {
  'use strict';

  const root = document.querySelector('.auth-bg');
  if (!root) return;

  const SLIDES = ['01-field', '02-farmer', '03-seedlings', '04-harvest', '05-nursery'];
  const SHOW_MS = 7000;   // time each photo stays fully visible
  const FADE_MS = 1600;   // must match the opacity transition in auth.css

  const portrait = window.matchMedia('(max-aspect-ratio: 1/1)').matches;
  const reduceMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
  const conn = navigator.connection || {};
  const lowData = conn.saveData === true || /(^|-)2g$/.test(conn.effectiveType || '');
  const animate = !reduceMotion && !lowData;

  const srcOf = (i) => `/assets/auth-bg/${SLIDES[i]}-${portrait ? 'portrait' : 'landscape'}.webp`;

  let current = null;   // <img> on screen
  let index = 0;
  let timer = null;
  let pending = null;   // next <img>, loading or ready

  function load(i) {
    const img = new Image();
    img.alt = '';
    img.decoding = 'async';
    img.className = 'auth-bg-img';
    img.src = srcOf(i);
    const ready = img.decode ? img.decode() : new Promise((ok, ko) => { img.onload = ok; img.onerror = ko; });
    return ready.then(() => img);
  }

  function show(img) {
    root.appendChild(img);
    if (!animate) img.classList.add('is-still');
    // next frame, so the fade-in transition runs
    requestAnimationFrame(() => requestAnimationFrame(() => img.classList.add('is-active')));
    const previous = current;
    current = img;
    if (previous) {
      previous.classList.remove('is-active');
      previous.classList.add('is-leaving');
      setTimeout(() => previous.remove(), FADE_MS + 100);
    }
  }

  function prepareNext() {
    const next = (index + 1) % SLIDES.length;
    pending = load(next).then((img) => ({ img, i: next })).catch(() => null);
  }

  function schedule() {
    clearTimeout(timer);
    timer = setTimeout(advance, SHOW_MS);
  }

  function advance() {
    if (document.hidden || !pending) return;   // resumed by visibilitychange
    const waiting = pending;
    pending = null;
    waiting.then((next) => {
      if (next) {
        index = next.i;
        show(next.img);
      } else {
        index = (index + 1) % SLIDES.length;   // photo failed to load: skip it
      }
      prepareNext();
      schedule();
    });
  }

  load(0).then((img) => {
    show(img);
    if (!animate) return;
    prepareNext();
    schedule();
  }).catch(() => { /* the dark green background stays: still a finished page */ });

  if (animate) {
    document.addEventListener('visibilitychange', () => {
      if (document.hidden) clearTimeout(timer);
      else if (current) schedule();
    });
  }
})();
