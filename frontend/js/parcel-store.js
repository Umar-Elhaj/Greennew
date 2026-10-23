/**
 * GREEN App — Parcels with offline support (IndexedDB).
 *
 * The server is the source of truth; this store keeps a copy so parcels can
 * be drawn and edited without network, plus an ordered queue of operations
 * replayed when the connection returns:
 *   create  → POST /api/parcels with client_id (replaying it is harmless)
 *   update  → PUT with base_updated_at; 409 = changed elsewhere: the server
 *             version replaces the local one, the local edit is kept as a
 *             draft (record.draft) and the record is flagged 'conflict'
 *   delete  → DELETE (or nothing if the parcel never reached the server)
 * After a successful create/update, the later updates of the same parcel
 * are rebased on the new server version (they were made on top of it).
 * Network errors, 5xx, 429 and 401 keep the queue as it is; any other
 * rejection flags the record 'error' (retry() queues it again, discard()
 * drops the local change).
 * One database per account (green-parcels-u<id>): a shared device never
 * shows nor sends the parcels of another account.
 *
 * Record: { key, id, name, crop_type, sowing_date, description, geometry,
 *           area_ha, perimeter_m, region, latitude, longitude, updated_at,
 *           analyses_count, last_analysis_at, sync, error, draft, deleted }
 * sync: 'synced' | 'pending' | 'conflict' | 'error'
 *
 *   ParcelStore.on('changed', () => render(await ParcelStore.list()))
 */
const ParcelStore = (() => {
  const DB_PREFIX = 'green-parcels-u';
  const FIELDS = ['name', 'crop_type', 'sowing_date', 'description', 'geometry'];
  let dbPromise = null;
  let dbUser = null;
  let syncing = false;
  const listeners = {};

  const emit = (type, detail) => (listeners[type] || []).forEach(fn => { try { fn(detail); } catch (e) { console.error(e); } });

  const userId = () => { const u = Auth.getUser(); return u && u.id ? String(u.id) : null; };

  function open() {
    const uid = userId();
    if (!uid) return Promise.reject(new Error('not signed in'));
    if (dbUser !== uid) { dbPromise = null; dbUser = uid; }
    if (!dbPromise) {
      dbPromise = new Promise((resolve, reject) => {
        const req = indexedDB.open(DB_PREFIX + uid, 1);
        req.onupgradeneeded = () => {
          req.result.createObjectStore('parcels', { keyPath: 'key' });
          req.result.createObjectStore('ops', { keyPath: 'seq', autoIncrement: true });
        };
        req.onsuccess = () => resolve(req.result);
        req.onerror = () => reject(req.error);
      });
    }
    return dbPromise;
  }

  async function tx(stores, mode, fn) {
    const db = await open();
    return new Promise((resolve, reject) => {
      const t = db.transaction(stores, mode);
      const out = fn(...[].concat(stores).map(s => t.objectStore(s)));
      t.oncomplete = () => resolve(out && out.result !== undefined ? out.result : out);
      t.onerror = () => reject(t.error);
    });
  }

  const getAll = store => tx(store, 'readonly', s => s.getAll());
  const get = key => tx('parcels', 'readonly', s => s.get(key));
  const put = rec => tx('parcels', 'readwrite', s => s.put(rec));
  const del = key => tx('parcels', 'readwrite', s => s.delete(key));
  const addOp = op => tx('ops', 'readwrite', s => s.add(op));
  const delOp = seq => tx('ops', 'readwrite', s => s.delete(seq));

  function uuid() {
    if (crypto.randomUUID) return crypto.randomUUID();
    return 'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx'.replace(/[xy]/g, c => {
      const r = Math.random() * 16 | 0;
      return (c === 'x' ? r : (r & 0x3 | 0x8)).toString(16);
    });
  }

  function fromServer(p, previous) {
    return {
      key: p.client_id || (previous && previous.key) || `server-${p.id}`,
      id: p.id,
      name: p.name, crop_type: p.crop_type, sowing_date: p.sowing_date, description: p.description,
      geometry: p.geometry, area_ha: p.area_ha, perimeter_m: p.perimeter_m, region: p.region,
      latitude: p.latitude, longitude: p.longitude, updated_at: p.updated_at,
      analyses_count: p.analyses_count ?? (previous && previous.analyses_count) ?? 0,
      last_analysis_at: p.last_analysis_at ?? (previous && previous.last_analysis_at) ?? null,
      // a conflict stays flagged (with its draft) until the user chooses
      sync: previous && previous.sync === 'conflict' ? 'conflict' : 'synced',
      error: previous && previous.sync === 'conflict' ? previous.error : null,
      draft: previous && previous.draft ? previous.draft : null, deleted: false,
    };
  }

  /** Local records (deleted ones hidden), refreshed from the server when online unless refresh=false. */
  async function list(refresh = true) {
    if (refresh && navigator.onLine) {
      const { data, error } = await API.parcels.list();
      if (!error && Array.isArray(data)) {
        const local = await getAll('parcels');
        const byId = new Map(local.filter(r => r.id).map(r => [r.id, r]));
        const seen = new Set();
        for (const p of data) {
          const prev = byId.get(p.id) || local.find(r => r.key === p.client_id);
          seen.add(p.id);
          // local changes waiting to be sent win until they are replayed
          if (prev && (prev.sync === 'pending' || prev.sync === 'error' || prev.deleted)) continue;
          if (prev && prev.key !== (p.client_id || prev.key)) await del(prev.key);
          await put(fromServer(p, prev));
        }
        // synced records that no longer exist on the server were deleted elsewhere
        for (const r of local) {
          if (r.id && !seen.has(r.id) && r.sync !== 'pending' && r.sync !== 'error') await del(r.key);
        }
      }
    }
    return (await getAll('parcels')).filter(r => !r.deleted)
      .sort((a, b) => (b.updated_at || '').localeCompare(a.updated_at || ''));
  }

  async function create(fields) {
    const rec = { key: uuid(), id: null, ...pick(fields), sync: 'pending', error: null, draft: null, deleted: false,
                  updated_at: new Date().toISOString(), analyses_count: 0, last_analysis_at: null,
                  area_ha: fields.area_ha ?? null, perimeter_m: fields.perimeter_m ?? null, region: null };
    await put(rec);
    await addOp({ type: 'create', key: rec.key });
    emit('changed');
    sync();
    return rec;
  }

  async function update(key, fields) {
    const rec = await get(key);
    if (!rec) return null;
    const base = rec.updated_at;
    Object.assign(rec, pick(fields), { sync: 'pending', error: null });
    if (fields.area_ha !== undefined) rec.area_ha = fields.area_ha;
    if (fields.perimeter_m !== undefined) rec.perimeter_m = fields.perimeter_m;
    await put(rec);
    await addOp({ type: 'update', key, base_updated_at: rec.id ? base : null });
    emit('changed');
    sync();
    return rec;
  }

  async function remove(key) {
    const rec = await get(key);
    if (!rec) return;
    rec.deleted = true;
    rec.sync = 'pending';
    await put(rec);
    await addOp({ type: 'delete', key });
    emit('changed');
    sync();
  }

  /** Keep the server version (after a conflict): drop the local draft. */
  async function discardDraft(key) {
    const rec = await get(key);
    if (!rec) return;
    rec.draft = null;
    rec.sync = 'synced';
    await put(rec);
    emit('changed');
  }

  /** Send a record flagged 'error' again (create if it never reached the server). */
  async function retry(key) {
    const rec = await get(key);
    if (!rec || rec.sync !== 'error') return;
    rec.sync = 'pending';
    rec.error = null;
    await put(rec);
    await addOp(rec.id ? { type: 'update', key, base_updated_at: rec.updated_at } : { type: 'create', key });
    emit('changed');
    sync();
  }

  /** Drop the local change of a record flagged 'error' (the server version comes back on refresh). */
  async function discard(key) {
    const rec = await get(key);
    if (!rec) return;
    if (!rec.id) { await del(key); } else { rec.sync = 'synced'; rec.error = null; await put(rec); }
    emit('changed');
    await list();
    emit('changed');
  }

  /** Re-apply the local draft on top of the server version. */
  async function applyDraft(key) {
    const rec = await get(key);
    if (!rec || !rec.draft) return;
    const draft = rec.draft;
    rec.draft = null;
    await put(rec);
    return update(key, draft);
  }

  function pick(fields) {
    const out = {};
    FIELDS.forEach(f => { if (fields[f] !== undefined) out[f] = fields[f]; });
    return out;
  }

  function payload(rec) {
    const p = {};
    FIELDS.forEach(f => { p[f] = rec[f] === '' ? null : rec[f]; });
    if (!p.sowing_date) delete p.sowing_date;
    return p;
  }

  async function pendingCount() {
    return (await getAll('ops')).length;
  }

  async function sync() {
    if (syncing || !navigator.onLine || !userId()) return;
    syncing = true;
    emit('syncing', true);
    try {
      const seqs = (await getAll('ops')).map(o => o.seq).sort((a, b) => a - b);
      const dropAll = async key => { for (const o of await getAll('ops')) if (o.key === key) await delOp(o.seq); };
      for (const seq of seqs) {
        if (userId() !== dbUser) break;                               // signed out / other account
        // read again: an earlier step may have rebased or dropped it
        const op = await tx('ops', 'readonly', s => s.get(seq));
        if (!op) continue;
        const rec = await get(op.key);
        if (!rec) { await delOp(op.seq); continue; }
        let res;
        if (op.type === 'create') {
          if (rec.id) { await delOp(op.seq); continue; }
          res = await API.parcels.create({ ...payload(rec), client_id: rec.key });
        } else if (op.type === 'update') {
          if (!rec.id) { await delOp(op.seq); continue; }   // the create still pending carries the data
          res = await API.parcels.update(rec.id, { ...payload(rec), base_updated_at: op.base_updated_at || undefined });
        } else {
          if (rec.id) res = await API.parcels.delete(rec.id);
          if (!res || !res.error || res.status === 404) { await del(rec.key); await delOp(op.seq); continue; }
          if (keepQueued(res.status)) break;
        }

        if (!res.error) {
          const later = (await getAll('ops')).some(o => o.key === rec.key && o.seq > op.seq);
          const fresh = fromServer(res.data, rec);
          fresh.key = rec.key;
          if (later) fresh.sync = 'pending';
          // later updates of this parcel were made on top of this version
          for (const o of await getAll('ops')) {
            if (o.key === rec.key && o.type === 'update' && o.seq > op.seq) {
              o.base_updated_at = res.data.updated_at;
              await tx('ops', 'readwrite', s => s.put(o));
            }
          }
          await put(fresh);
          await delOp(op.seq);
          emit('synced', fresh);
          continue;
        }
        if (keepQueued(res.status)) break;                            // retry later
        if (res.status === 409 && res.body && res.body.parcel) {      // the server wins
          const server = fromServer(res.body.parcel, rec);
          server.key = rec.key;
          server.draft = payload(rec);
          server.sync = 'conflict';
          server.error = res.error;
          await put(server);
          await dropAll(rec.key);      // the draft already holds every later local edit
          emit('conflict', server);
          continue;
        }
        // rejected (validation…): the record keeps the local values, flagged
        // 'error'; its other queued operations are dropped with this one
        rec.sync = 'error';
        rec.error = res.error;
        if (op.type === 'delete') rec.deleted = false;
        await put(rec);
        await dropAll(rec.key);
        emit('error', rec);
      }
    } finally {
      syncing = false;
      emit('syncing', false);
      emit('changed');
    }
  }

  // network, server trouble, rate limit, expired session (the API layer sends the user to sign in)
  function keepQueued(status) { return status === 0 || status >= 500 || status === 429 || status === 401; }

  window.addEventListener('online', sync);
  setInterval(sync, 30000);

  return {
    list, create, update, remove, sync, discardDraft, applyDraft, retry, discard, pendingCount, get,
    on(type, fn) { (listeners[type] = listeners[type] || []).push(fn); },
  };
})();
