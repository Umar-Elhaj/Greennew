/**
 * GREEN App — Store-and-forward queue for images to analyse (IndexedDB).
 *
 * Every capture (device camera, rover frame, imported photo) is first saved
 * locally with its context, then sent to the API when the network allows.
 * This is what makes the rover workflow possible: while the device is on the
 * rover's Wi-Fi (no Internet) images pile up here, and they are sent as soon
 * as the connection comes back (`online` event + periodic retry).
 *
 *   await UploadQueue.add(blob, { source: 'camera', parcel_id, latitude, … });
 *   UploadQueue.on('uploaded', ({ item, response }) => …);
 *   UploadQueue.on('changed', counts => …);   // { pending, failed }
 *
 * Statuses: pending (to send) → sent (removed) | failed (rejected by the
 * server, e.g. not an image; kept until the user deletes it). Network errors
 * and 5xx keep the item pending with an exponential back-off.
 */
const UploadQueue = (() => {
  const DB_NAME = 'green-uploads';
  const STORE = 'queue';
  const MAX_SIDE = 1600;          // resized before storage: small, under proxy body limits
  const JPEG_QUALITY = 0.85;
  const RETRY_MS = 30000;

  let dbPromise = null;
  let processing = false;
  const listeners = {};

  function emit(type, detail) { (listeners[type] || []).forEach(fn => { try { fn(detail); } catch (e) { console.error(e); } }); }

  function open() {
    if (!dbPromise) {
      dbPromise = new Promise((resolve, reject) => {
        const req = indexedDB.open(DB_NAME, 1);
        req.onupgradeneeded = () => {
          const store = req.result.createObjectStore(STORE, { keyPath: 'id', autoIncrement: true });
          store.createIndex('status', 'status');
        };
        req.onsuccess = () => resolve(req.result);
        req.onerror = () => reject(req.error);
      });
    }
    return dbPromise;
  }

  async function tx(mode, fn) {
    const db = await open();
    return new Promise((resolve, reject) => {
      const t = db.transaction(STORE, mode);
      const result = fn(t.objectStore(STORE));
      t.oncomplete = () => resolve(result && result.result !== undefined ? result.result : result);
      t.onerror = () => reject(t.error);
      t.onabort = () => reject(t.error);
    });
  }

  /** Downscale + re-encode as JPEG (also strips most metadata). */
  async function shrink(blob) {
    try {
      const bitmap = await createImageBitmap(blob);
      const scale = Math.min(1, MAX_SIDE / Math.max(bitmap.width, bitmap.height));
      if (scale === 1 && blob.type === 'image/jpeg' && blob.size < 1.5e6) return blob;
      const canvas = document.createElement('canvas');
      canvas.width = Math.round(bitmap.width * scale);
      canvas.height = Math.round(bitmap.height * scale);
      canvas.getContext('2d').drawImage(bitmap, 0, 0, canvas.width, canvas.height);
      return await new Promise(res => canvas.toBlob(b => res(b || blob), 'image/jpeg', JPEG_QUALITY));
    } catch (_) {
      return blob;   // not decodable here: let the server decide
    }
  }

  async function all() {
    return tx('readonly', store => store.getAll());
  }

  async function counts() {
    const items = await all();
    return {
      pending: items.filter(i => i.status === 'pending').length,
      failed: items.filter(i => i.status === 'failed').length,
    };
  }

  async function notify() { emit('changed', await counts()); }

  async function put(item) { return tx('readwrite', store => store.put(item)); }

  async function remove(id) {
    await tx('readwrite', store => store.delete(id));
    await notify();
  }

  async function add(blob, meta = {}) {
    const item = {
      blob: await shrink(blob),
      meta: { ...meta, captured_at: meta.captured_at || new Date().toISOString() },
      status: 'pending',
      attempts: 0,
      next_try: 0,
      last_error: null,
      created: Date.now(),
    };
    item.id = await tx('readwrite', store => store.add(item));
    await notify();
    process();
    return item.id;
  }

  async function send(item) {
    const form = new FormData();
    form.append('file', item.blob, `capture-${item.id}.jpg`);
    for (const [k, v] of Object.entries(item.meta)) {
      if (v !== null && v !== undefined && v !== '') form.append(k, String(v));
    }
    const endpoint = item.meta.source === 'upload' ? 'upload' : 'analyzeFrame';
    return API.camera[endpoint](form);
  }

  async function process() {
    if (processing || !navigator.onLine) return;
    processing = true;
    try {
      for (;;) {
        const now = Date.now();
        const next = (await all())
          .filter(i => i.status === 'pending' && i.next_try <= now)
          .sort((a, b) => a.created - b.created)[0];
        if (!next) break;
        emit('sending', next);
        const { data, error, status } = await send(next);
        if (!error) {
          await tx('readwrite', store => store.delete(next.id));
          emit('uploaded', { item: next, response: data });
          await notify();
          continue;
        }
        next.attempts += 1;
        next.last_error = error;
        if (status === 0 || status >= 500 || status === 429) {
          // network or server trouble: keep it and try later
          next.next_try = Date.now() + Math.min(10 * 60000, 5000 * 2 ** next.attempts);
          await put(next);
          emit('retry', next);
          await notify();
          break;
        }
        // rejected for good (not an image, too large, parcel gone…)
        next.status = 'failed';
        await put(next);
        emit('failed', next);
        await notify();
      }
    } finally {
      processing = false;
    }
  }

  async function retryFailed() {
    for (const item of await all()) {
      if (item.status === 'failed' || item.next_try > Date.now()) {
        item.status = 'pending';
        item.next_try = 0;
        await put(item);
      }
    }
    await notify();
    process();
  }

  window.addEventListener('online', () => { emit('online'); process(); });
  window.addEventListener('offline', () => emit('offline'));
  setInterval(process, RETRY_MS);

  return {
    add, all, counts, remove, retryFailed, process,
    on(type, fn) { (listeners[type] = listeners[type] || []).push(fn); },
  };
})();
