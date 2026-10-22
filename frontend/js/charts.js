/**
 * GREEN App — Shared data-visualisation palette and Chart.js defaults.
 *
 * Rules (validated with the dataviz validator, light and dark):
 *  - categorical colour follows the ENTITY (model class code), in a fixed
 *    order — never the rank in the current view, so filters never repaint;
 *  - magnitude = one sequential hue (blue), light → dark;
 *  - status colours (alert levels) are reserved and always shown with a label.
 */
const VIZ = (() => {
  const dark = () => document.documentElement.getAttribute('data-theme') === 'dark';

  // 8 validated categorical slots (light / dark steps of the same hues)
  const SLOTS_LIGHT = ['#2a78d6', '#eb6834', '#1baf7a', '#eda100', '#e87ba4', '#008300', '#6250d6', '#e34948'];
  const SLOTS_DARK  = ['#3987e5', '#d95926', '#199e70', '#c98500', '#d55181', '#008300', '#9085e9', '#e66767'];
  const OTHER = { light: '#8a8986', dark: '#9b9a95' };

  // Fixed class → slot mapping. A 9th class shares the neutral "other" colour.
  const CLASS_SLOT = {
    Corn_Streak: 0, Corn_Leaf_Blight: 1, Cassava_Mosaic: 2, Tomato_Blight_Leaf: 3,
    Tomato_Brown_Spots: 4, Corn_Brown_Spots: 5, Corn_Yellowing: 6, Corn_Mildew: 7,
  };
  const PLANT_SLOT = { Corn: 0, Cassava: 2, Tomato: 1 };

  // Sequential blue ramp (100 → 700)
  const SEQ = ['#cde2fb', '#b7d3f6', '#9ec5f4', '#86b6ef', '#6da7ec', '#5598e7', '#3987e5',
               '#2a78d6', '#256abf', '#1c5cab', '#184f95', '#104281', '#0d366b'];

  // Status palette (fixed, never themed)
  const STATUS = { none: '#0ca30c', low: '#fab219', medium: '#ec835a', high: '#d03b3b' };

  function slot(i) { return (dark() ? SLOTS_DARK : SLOTS_LIGHT)[i]; }

  return {
    disease(code) {
      const i = CLASS_SLOT[code];
      return i === undefined ? (dark() ? OTHER.dark : OTHER.light) : slot(i);
    },
    plant(code) {
      const i = PLANT_SLOT[code];
      return i === undefined ? (dark() ? OTHER.dark : OTHER.light) : slot(i);
    },
    slot,
    status(level) { return STATUS[level] || STATUS.none; },
    /** t in [0, 1] → sequential blue; t = 0 stays visible (step 150). */
    seq(t) {
      if (t === null || t === undefined || Number.isNaN(t)) return null;
      const i = 1 + Math.round(Math.max(0, Math.min(1, t)) * (SEQ.length - 2));
      return SEQ[i];
    },
    /** Readable text colour on a sequential cell. */
    seqText(t) { return t !== null && t > 0.55 ? '#ffffff' : '#0b0b0b'; },
    /** Bins for a 5-step sequential legend. */
    seqBins() { return [0.1, 0.3, 0.5, 0.7, 0.9].map(t => this.seq(t)); },
    theme() {
      const d = dark();
      return {
        grid: d ? '#2a2a28' : '#ecebe8',
        tick: d ? '#c3c2b7' : '#52514e',
        text: d ? '#f0efec' : '#0b0b0b',
        surface: d ? '#1a1a19' : '#fcfcfb',
        tooltipBg: d ? '#161b22' : '#ffffff',
        tooltipBorder: d ? '#30363d' : '#e5e7eb',
      };
    },
    /** Common Chart.js options: recessive grid, thin marks, localized numbers, tooltip. */
    baseOptions(extra = {}) {
      const t = this.theme();
      return Object.assign({
        responsive: true,
        maintainAspectRatio: false,
        locale: I18n.locale,
        animation: false,
        interaction: { mode: 'index', intersect: false },
        plugins: {
          legend: { labels: { color: t.tick, boxWidth: 12, boxHeight: 12, font: { family: 'Inter', size: 12 } } },
          tooltip: {
            backgroundColor: t.tooltipBg, borderColor: t.tooltipBorder, borderWidth: 1,
            titleColor: t.text, bodyColor: t.tick, padding: 10,
          },
        },
        scales: {
          x: { grid: { color: t.grid, drawTicks: false }, border: { display: false }, ticks: { color: t.tick, padding: 6 } },
          y: { grid: { color: t.grid, drawTicks: false }, border: { display: false }, ticks: { color: t.tick, padding: 6, precision: 0 },
               beginAtZero: true },
        },
      }, extra);
    },
  };
})();
