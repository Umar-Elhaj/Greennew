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
 *
 * Record: { key, id, name, crop_type, sowing_date, description, geometry,
 *           area_ha, perimeter_m, region, latitude, longitude, updated_at,
 *           analyses_count, last_analysis_at, sync, error, draft, deleted }
 * sync: 'synced' | 'pending' | 'conflict' | 'error'
 *
 *   ParcelStore.on('changed', () => render(await ParcelStore.list()))
 */
const ParcelStore = (() => {
  const DB_NAME = 'green-parcels';
  const FIELDS = ['name', 'crop_type', 'sowing_date', 'description', 'geometry'];
  let dbPromise = null;
  let syncing = false;
  const listeners = {};

  const emit = (type, detail) => (listeners[type] || []).forEach(fn => { try { fn(detail); } catch (e) { console.error(e); } });

  function open() {
    if (!dbPromise) {
      dbPromise = new Promise((resolve, reject) => {
        const req = indexedDB.open(DB_NAME, 1);
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
      sync: 'synced', error: null, draft: previous && previous.draft ? previous.draft : null, deleted: false,
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
          if (prev && (prev.sync === 'pending' || prev.deleted)) continue;
          if (prev && prev.key !== (p.client_id || prev.key)) await del(prev.key);
          await put(fromServer(p, prev));
        }
        // synced records that no longer exist on the server were deleted elsewhere
        for (const r of local) {
          if (r.id && !seen.has(r.id) && r.sync !== 'pending') await del(r.key);
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
    if (syncing || !navigator.onLine) return;
    syncing = true;
    emit('syncing', true);
    try {
      const ops = (await getAll('ops')).sort((a, b) => a.seq - b.seq);
      for (const op of ops) {
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
        }

        if (!res.error) {
          const later = (await getAll('ops')).some(o => o.key === rec.key && o.seq > op.seq);
          const fresh = fromServer(res.data, rec);
          fresh.key = rec.key;
          if (later) fresh.sync = 'pending';
          if (op.type === 'create') {
            // updates queued before the id was known now have one
            for (const o of await getAll('ops')) {
              if (o.key === rec.key && o.type === 'update' && !o.base_updated_at) {
                o.base_updated_at = res.data.updated_at;
                await tx('ops', 'readwrite', s => s.put(o));
              }
            }
          }
          await put(fresh);
          await delOp(op.seq);
          emit('synced', fresh);
          continue;
        }
        if (res.status === 0 || res.status >= 500) break;            // network: retry later
        if (res.status === 409 && res.body && res.body.parcel) {      // the server wins
          const server = fromServer(res.body.parcel, rec);
          server.key = rec.key;
          server.draft = payload(rec);
          server.sync = 'conflict';
          server.error = res.error;
          await put(server);
          await delOp(op.seq);
          emit('conflict', server);
          continue;
        }
        rec.sync = 'error';
        rec.error = res.error;
        if (op.type === 'delete') rec.deleted = false;
        await put(rec);
        await delOp(op.seq);
        emit('error', rec);
      }
    } finally {
      syncing = false;
      emit('syncing', false);
      emit('changed');
    }
  }

  window.addEventListener('online', sync);
  setInterval(sync, 30000);

  return {
    list, create, update, remove, sync, discardDraft, applyDraft, pendingCount, get,
    on(type, fn) { (listeners[type] = listeners[type] || []).push(fn); },
  };
})();
