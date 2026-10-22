/**
 * GREEN App — Field sheet ("fiche terrain") renderer.
 * Shared by the history page, the camera page and GREEN Map cell details.
 *
 *   el.innerHTML = Fiche.html(analysis, { compact: false });
 *
 * `analysis` is an /api/analysis/{id} payload (or an upload response
 * normalised by Fiche.fromUpload). Every value is escaped. Texts come from
 * the server in the request language, labels from I18n.
 */
const Fiche = {
  /** Upload/analyze response → the same shape as /api/analysis/{id}. */
  fromUpload(res) {
    const d = res.disease || {};
    return {
      id: res.analysis_id,
      detected_disease: d.detected_disease,
      plant_type: d.plant_type,
      confidence: d.confidence,
      severity: d.severity,
      image_path: res.image_path,
      thumb_path: res.thumb_path,
      fiche_terrain: res.fiche_terrain,
      created_at: new Date().toISOString(),
      duplicate: !!res.duplicate,
    };
  },

  html(a, opts = {}) {
    const f = a.fiche_terrain || {};
    const w = f.winner || {};
    const healthy = isHealthy(a);
    const level = alertLevel(a);
    const confPct = f.confidence != null ? f.confidence : Math.round((a.confidence || 0) * 1000) / 10;
    const low = f.low_confidence != null ? f.low_confidence : confPct < 70;
    const t = (k, p) => escapeHtml(I18n.t(k, p));
    const list = items => `<ul>${items.map(x => `<li>${escapeHtml(x)}</li>`).join('')}</ul>`;
    const section = (key, body) => `<div class="fiche-section"><div class="fiche-section-title">${t(key)}</div>${body}</div>`;

    let html = '';
    if (a.image_path && !opts.noImage) {
      html += `<img class="fiche-img" src="${escapeHtml(opts.compact ? (a.thumb_path || a.image_path) : a.image_path)}" alt="${t('fiche.image_alt')}" loading="lazy" />`;
    }
    if (a.duplicate) html += `<div class="fiche-note">${t('fiche.duplicate')}</div>`;

    html += `
      <div class="fiche-verdict">
        <div class="fiche-verdict-ico ${healthy ? 'healthy' : 'diseased'}" aria-hidden="true">${healthy ? Fiche.ICON_LEAF : Fiche.ICON_ALERT}</div>
        <div class="fiche-verdict-main">
          <div class="fiche-kicker">${t(healthy ? 'model.result.healthy' : (low ? 'model.result.uncertain' : 'common.ai.probable_disease'))}</div>
          <h4>${escapeHtml(analysisLabel(a))}</h4>
          <div class="fiche-sub">${escapeHtml(plantLabel(a.plant_type))}</div>
          <div class="fiche-conf" title="${t('common.ai.confidence')}">
            <div class="fiche-conf-track"><div class="fiche-conf-fill" style="width:${Math.max(0, Math.min(100, confPct))}%"></div></div>
            <span class="fiche-conf-pct">${escapeHtml(I18n.percent(confPct / 100))}</span>
          </div>
          ${healthy ? '' : `<span class="fiche-pill fiche-pill-${level}" title="${t('model.alert.help')}">${t('model.alert.title')} : ${escapeHtml(alertLabel(level))}</span>`}
        </div>
      </div>`;

    if (low) html += `<div class="fiche-warning">${t('common.ai.low_confidence')}</div>`;

    if (!opts.compact) {
      if (w.reference_name && !healthy) {
        html += section('fiche.reference', `<p class="fiche-text"><a href="/diseases?id=${encodeURIComponent(w.reference_id || '')}">${escapeHtml(w.reference_name)}</a>${w.scientific_name ? ` <em>(${escapeHtml(w.scientific_name)})</em>` : ''}</p>`);
      }
      if ((f.symptoms || []).length) html += section('fiche.symptoms', list(f.symptoms));
      if ((f.recommendations || []).length) html += section('fiche.recommendations', list(f.recommendations));
      const alternatives = (f.top3 || []).slice(1).filter(x => x && x.code);
      if (alternatives.length) {
        html += section('fiche.alternatives', `<ul>${alternatives.map(x =>
          `<li>${escapeHtml(classLabel(x.code))} — ${escapeHtml(I18n.percent((x.confidence || 0) / 100))}</li>`).join('')}</ul>`);
      }
    }

    html += `<p class="fiche-disclaimer">${escapeHtml(f.disclaimer || I18n.t('common.ai.disclaimer'))}</p>`;
    if (!opts.compact) {
      const meta = [
        `${t('fiche.source')} : ${escapeHtml(I18n.t(`fiche.sources.${a.source || 'upload'}`))}`,
        a.created_at ? escapeHtml(I18n.dateTime(a.created_at)) : '',
        a.latitude != null ? `${I18n.number(a.latitude, { maximumFractionDigits: 5 })}, ${I18n.number(a.longitude, { maximumFractionDigits: 5 })}` : '',
        a.id ? `#${escapeHtml(a.id)}` : '',
      ].filter(Boolean);
      html += `<div class="fiche-meta">${meta.map(m => `<span>${m}</span>`).join('')}</div>`;
      if (!healthy && a.id && opts.botLink !== false) {
        html += `<a class="btn btn-primary fiche-bot" href="/chatbot?analysis_id=${encodeURIComponent(a.id)}">${t('fiche.ask_bot')}</a>`;
      }
    }
    return `<div class="fiche-body">${html}</div>`;
  },

  ICON_LEAF: '<svg width="18" height="18" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24"><path d="M17 8C8 10 5.9 16.17 3.82 19.82A2 2 0 0 0 6 22c5.13 0 9-4.46 9-10V8"/><path d="M12 22s0-8-7-10"/></svg>',
  ICON_ALERT: '<svg width="18" height="18" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24"><path d="M10.29 3.86L1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z"/><line x1="12" y1="9" x2="12" y2="13"/><line x1="12" y1="17" x2="12.01" y2="17"/></svg>',
};
