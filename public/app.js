/* ═══════════════════════════════════════════════════════════
   Seri Putra Homestay — front-end
   No build step, no dependencies. Runs straight from the file.
   ═══════════════════════════════════════════════════════════ */

(() => {
'use strict';

const $  = (sel, root = document) => root.querySelector(sel);
const $$ = (sel, root = document) => [...root.querySelectorAll(sel)];

/* ── photos ───────────────────────────────────────────────── */

const PHOTOS = [
  { slug: 'living-mirror-lounge', cat: 'living',    span: 'wide', cap: 'Main lounge with feature mirror wall and smart TV' },
  { slug: 'bedroom-queen-1',      cat: 'bedrooms',  span: '',     cap: 'Queen bedroom 1 — upholstered headboard, blackout blinds' },
  { slug: 'bathroom-shower',      cat: 'bathrooms', span: 'tall', cap: 'Shower room — rain shower with instant water heater' },
  { slug: 'living-wide',          cat: 'living',    span: '',     cap: 'Open-plan living area looking through to the dining room' },
  { slug: 'bedroom-queen-2',      cat: 'bedrooms',  span: '',     cap: 'Queen bedroom 2 — tufted headboard, fresh towels provided' },
  { slug: 'living-classic-sofa',  cat: 'living',    span: 'wide', cap: 'Classic carved sofa set in the front sitting room' },
  { slug: 'bedroom-queen-3',      cat: 'bedrooms',  span: '',     cap: 'Queen bedroom 3 — headboard storage and its own air-cond' },
  { slug: 'bathroom-toilet',      cat: 'bathrooms', span: 'tall', cap: 'Second bathroom — toilet with hand bidet' },
  { slug: 'living-tv',            cat: 'living',    span: '',     cap: 'Smart TV lounge with ceiling fan and air-conditioning' },
  { slug: 'dining',               cat: 'living',    span: '',     cap: 'Dining table for six, with fridge and kitchen access' },
  { slug: 'bedroom-single',       cat: 'bedrooms',  span: '',     cap: 'Single bedroom — ideal for a child or a solo guest' },
  { slug: 'living-seating-nook',  cat: 'living',    span: '',     cap: 'Seating nook beside the staircase' },
];

/* ── config ───────────────────────────────────────────────── */

/* Defaults keep the page fully usable when it is opened as a plain file with
   no backend behind it — the calendar still prices dates correctly, it just
   cannot know what is already booked. */
const FALLBACK = {
  name: 'Seri Putra Homestay',
  address: '35, Jalan Megah 10, Taman Megah, 83000 Batu Pahat, Johor',
  maps_query: '35 Jalan Megah 10, Taman Megah, 83000 Batu Pahat, Johor',
  phone_primary: '+60 11-1241 2110',
  phone_secondary: '+60 12-730 4478',
  whatsapp: '601112412110',
  instagram: 'https://www.instagram.com/reel/DLUBPx7ICDl/?hl=en',
  instagram_label: 'Watch our reel',
  facebook: 'https://www.facebook.com/watch/?v=24293846236874579',
  facebook_label: 'Watch our video',
  currency: 'RM',
  base_rate: 250, weekend_rate: 300, holiday_rate: 350,
  deposit: 100, max_guests: 12, min_nights: 1,
  check_in_time: '3:00 PM', check_out_time: '12:00 PM',
  booking_window_days: 365,
  today: toISO(new Date()),
};

let CFG = { ...FALLBACK };
let RATES = {};      // 'YYYY-MM-DD' -> { rate, kind, label }
let BLOCKED = {};    // 'YYYY-MM-DD' -> reason
let LIVE = false;    // did we reach the backend?

/* ── date helpers (all local, no UTC drift) ───────────────── */

function toISO(d) {
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`;
}
function fromISO(s) {
  const [y, m, d] = s.split('-').map(Number);
  return new Date(y, m - 1, d);
}
function addDays(d, n) { const c = new Date(d); c.setDate(c.getDate() + n); return c; }
function startOfMonth(d) { return new Date(d.getFullYear(), d.getMonth(), 1); }
function nightsBetween(a, b) { return Math.round((fromISO(b) - fromISO(a)) / 86400000); }

const MONTHS = ['January','February','March','April','May','June',
                'July','August','September','October','November','December'];
const MONTHS_SHORT = ['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec'];
const DOW = ['Mon','Tue','Wed','Thu','Fri','Sat','Sun'];

function prettyDate(iso) {
  const d = fromISO(iso);
  return `${DOW[(d.getDay() + 6) % 7]}, ${d.getDate()} ${MONTHS_SHORT[d.getMonth()]}`;
}
function money(n) { return `${CFG.currency}${n}`; }

/* Pull a readable handle out of a profile URL. Post, reel and video URLs have
   no handle in them, so return '' and let the caller use its own label. */
const NOT_A_PROFILE = new Set(['reel', 'reels', 'p', 'tv', 'watch', 'video',
                               'videos', 'posts', 'share', 'story', 'stories']);
function socialLabel(url, prefix) {
  try {
    const parts = new URL(url).pathname.split('/').filter(Boolean);
    if (!parts.length || NOT_A_PROFILE.has(parts[0].toLowerCase())) return '';
    return prefix + parts[0];
  } catch {
    return '';
  }
}

/* Client-side mirror of pricing.py, used only until /api/availability lands
   (and as the whole story when the page is opened without a backend). */
function localRate(iso) {
  const d = fromISO(iso);
  const dow = d.getDay();                       // 0 Sun … 6 Sat
  if (dow === 5 || dow === 6) return { rate: CFG.weekend_rate, kind: 'weekend', label: '' };
  return { rate: CFG.base_rate, kind: 'base', label: '' };
}
function rateFor(iso) { return RATES[iso] || localRate(iso); }

/* ═══════════════════════ gallery ═══════════════════════ */

function buildGallery() {
  const grid = $('#galleryGrid');
  grid.innerHTML = PHOTOS.map((p, i) => `
    <button class="shot ${p.span ? 'shot--' + p.span : ''}" data-cat="${p.cat}" data-i="${i}"
            type="button" aria-label="View: ${p.cap.replace(/"/g, '&quot;')}">
      <picture>
        <source srcset="/images/full/${p.slug}.avif" type="image/avif" media="(min-width: 900px)">
        <img src="/images/thumb/${p.slug}.jpg" alt="${p.cap.replace(/"/g, '&quot;')}"
             loading="${i < 4 ? 'eager' : 'lazy'}" decoding="async">
      </picture>
      <span class="shot__cap">${p.cap}</span>
    </button>`).join('');
}

function wireFilters() {
  $$('.filter').forEach(btn => {
    btn.addEventListener('click', () => {
      $$('.filter').forEach(b => {
        b.classList.toggle('is-active', b === btn);
        b.setAttribute('aria-selected', b === btn);
      });
      const want = btn.dataset.filter;
      $$('.shot').forEach(shot => {
        shot.hidden = want !== 'all' && shot.dataset.cat !== want;
      });
    });
  });
}

/* ═══════════════════════ lightbox ═══════════════════════ */

const lb = {
  el: null, img: null, cap: null, count: null, index: 0, list: [], lastFocus: null,
};

function initLightbox() {
  lb.el = $('#lightbox');
  lb.img = $('#lbImg');
  lb.cap = $('#lbCap');
  lb.count = $('#lbCount');

  $('#galleryGrid').addEventListener('click', e => {
    const shot = e.target.closest('.shot');
    if (shot) openLightbox(Number(shot.dataset.i));
  });

  $('#lbClose').addEventListener('click', closeLightbox);
  $('#lbPrev').addEventListener('click', () => stepLightbox(-1));
  $('#lbNext').addEventListener('click', () => stepLightbox(1));
  lb.el.addEventListener('click', e => { if (e.target === lb.el) closeLightbox(); });

  document.addEventListener('keydown', e => {
    if (lb.el.hidden) return;
    if (e.key === 'Escape') closeLightbox();
    if (e.key === 'ArrowLeft') stepLightbox(-1);
    if (e.key === 'ArrowRight') stepLightbox(1);
  });

  // swipe on touch
  let x0 = null;
  lb.el.addEventListener('touchstart', e => { x0 = e.changedTouches[0].clientX; }, { passive: true });
  lb.el.addEventListener('touchend', e => {
    if (x0 === null) return;
    const dx = e.changedTouches[0].clientX - x0;
    if (Math.abs(dx) > 55) stepLightbox(dx < 0 ? 1 : -1);
    x0 = null;
  }, { passive: true });
}

function openLightbox(i) {
  lb.list = $$('.shot').filter(s => !s.hidden).map(s => Number(s.dataset.i));
  lb.index = Math.max(0, lb.list.indexOf(i));
  lb.lastFocus = document.activeElement;
  lb.el.hidden = false;
  document.body.style.overflow = 'hidden';
  paintLightbox();
  $('#lbClose').focus();
}

function closeLightbox() {
  lb.el.hidden = true;
  document.body.style.overflow = '';
  if (lb.lastFocus) lb.lastFocus.focus();
}

function stepLightbox(dir) {
  lb.index = (lb.index + dir + lb.list.length) % lb.list.length;
  paintLightbox();
}

function paintLightbox() {
  const p = PHOTOS[lb.list[lb.index]];
  lb.img.src = `/images/full/${p.slug}.jpg`;
  lb.img.alt = p.cap;
  lb.cap.textContent = p.cap;
  lb.count.textContent = `${lb.index + 1} / ${lb.list.length}`;
}

/* ═══════════════════════ calendar ═══════════════════════ */

const cal = { cursor: startOfMonth(new Date()), checkIn: null, checkOut: null };

function monthsShown() { return window.innerWidth < 1040 && window.innerWidth >= 780 ? 2
                              : window.innerWidth < 780 ? 1 : 2; }

function renderCalendar() {
  const host = $('#calMonths');
  const count = monthsShown();
  host.innerHTML = '';

  for (let m = 0; m < count; m++) {
    const first = new Date(cal.cursor.getFullYear(), cal.cursor.getMonth() + m, 1);
    host.appendChild(renderMonth(first));
  }

  const last = new Date(cal.cursor.getFullYear(), cal.cursor.getMonth() + count - 1, 1);
  $('#calTitle').textContent = count === 1
    ? `${MONTHS[cal.cursor.getMonth()]} ${cal.cursor.getFullYear()}`
    : `${MONTHS_SHORT[cal.cursor.getMonth()]} – ${MONTHS_SHORT[last.getMonth()]} ${last.getFullYear()}`;

  const today = fromISO(CFG.today);
  $('#calPrev').disabled = cal.cursor <= startOfMonth(today);
  const maxMonth = startOfMonth(addDays(today, CFG.booking_window_days));
  $('#calNext').disabled = new Date(cal.cursor.getFullYear(), cal.cursor.getMonth() + count, 1) > maxMonth;
}

function renderMonth(first) {
  const wrap = document.createElement('div');
  wrap.className = 'month';

  const daysInMonth = new Date(first.getFullYear(), first.getMonth() + 1, 0).getDate();
  const lead = (first.getDay() + 6) % 7;                 // Monday-first grid
  const today = fromISO(CFG.today);
  const maxDate = addDays(today, CFG.booking_window_days);

  let cells = '';
  for (let i = 0; i < lead; i++) cells += '<div class="day day--pad"></div>';

  for (let d = 1; d <= daysInMonth; d++) {
    const date = new Date(first.getFullYear(), first.getMonth(), d);
    const iso = toISO(date);
    const { rate, kind, label } = rateFor(iso);

    const isPast = date < today;
    const isFar = date > maxDate;
    const blockedReason = BLOCKED[iso];
    const disabled = isPast || isFar || !!blockedReason;

    const classes = ['day', `day--${kind}`];
    if (blockedReason) classes.push('day--blocked');
    if (iso === CFG.today) classes.push('day--today');
    if (iso === cal.checkIn) classes.push('day--in');
    if (iso === cal.checkOut) classes.push('day--out');
    if (cal.checkIn && cal.checkOut && iso > cal.checkIn && iso < cal.checkOut) classes.push('day--mid');

    const title = blockedReason ? 'Not available'
                : label ? `${label} — ${money(rate)}`
                : `${money(rate)} per night`;

    cells += `<button type="button" class="${classes.join(' ')}" data-iso="${iso}"
                 ${disabled ? 'disabled' : ''} title="${title}"
                 aria-label="${prettyDate(iso)}, ${blockedReason ? 'not available' : money(rate)}">
                <span class="day__n">${d}</span>
                ${disabled && !blockedReason ? '' : `<span class="day__p">${rate}</span>`}
              </button>`;
  }

  wrap.innerHTML = `
    <p class="month__name">${MONTHS[first.getMonth()]} ${first.getFullYear()}</p>
    <div class="month__dows">${DOW.map(d => `<span>${d[0]}</span>`).join('')}</div>
    <div class="month__grid">${cells}</div>`;
  return wrap;
}

/* A stay is only valid if every night inside it is free. */
function rangeIsClear(fromIso, toIso) {
  let d = fromISO(fromIso);
  const end = fromISO(toIso);
  while (d < end) {
    if (BLOCKED[toISO(d)]) return false;
    d = addDays(d, 1);
  }
  return true;
}

function pickDate(iso) {
  if (!cal.checkIn || cal.checkOut || iso <= cal.checkIn) {
    cal.checkIn = iso;
    cal.checkOut = null;
  } else if (!rangeIsClear(cal.checkIn, iso)) {
    // There is a booked night between the two picks — restart from here.
    cal.checkIn = iso;
    cal.checkOut = null;
    flashError('Those dates run through a night that is already booked. Start again from here.');
  } else if (nightsBetween(cal.checkIn, iso) < CFG.min_nights) {
    flashError(`Minimum stay is ${CFG.min_nights} night${CFG.min_nights > 1 ? 's' : ''}.`);
  } else {
    cal.checkOut = iso;
  }
  renderCalendar();
  renderQuote();
}

function wireCalendar() {
  $('#calMonths').addEventListener('click', e => {
    const day = e.target.closest('.day');
    if (day && !day.disabled && day.dataset.iso) pickDate(day.dataset.iso);
  });

  $('#calPrev').addEventListener('click', () => {
    cal.cursor = new Date(cal.cursor.getFullYear(), cal.cursor.getMonth() - 1, 1);
    renderCalendar();
  });
  $('#calNext').addEventListener('click', () => {
    cal.cursor = new Date(cal.cursor.getFullYear(), cal.cursor.getMonth() + 1, 1);
    renderCalendar();
  });
  $('#clearDates').addEventListener('click', () => {
    cal.checkIn = cal.checkOut = null;
    renderCalendar();
    renderQuote();
  });

  let lastCount = monthsShown();
  window.addEventListener('resize', () => {
    if (monthsShown() !== lastCount) { lastCount = monthsShown(); renderCalendar(); }
  });
}

/* ═══════════════════════ quote ═══════════════════════ */

function renderQuote() {
  const legIn = $('#legIn').querySelector('strong');
  const legOut = $('#legOut').querySelector('strong');

  legIn.textContent = cal.checkIn ? prettyDate(cal.checkIn) : 'Select a date';
  legOut.textContent = cal.checkOut ? prettyDate(cal.checkOut) : '—';

  const ready = !!(cal.checkIn && cal.checkOut);
  $('#quoteEmpty').hidden = ready;
  $('#quoteBody').hidden = !ready;
  $('#submitBtn').disabled = !ready;

  if (!ready) return;

  const lines = [];
  let total = 0;
  let d = fromISO(cal.checkIn);
  const end = fromISO(cal.checkOut);
  while (d < end) {
    const iso = toISO(d);
    const { rate, kind, label } = rateFor(iso);
    total += rate;
    const tag = kind === 'holiday' ? `<span class="tag tag--holiday">${label || 'Holiday'}</span>`
              : kind === 'weekend' ? '<span class="tag tag--weekend">Weekend</span>'
              : '';
    lines.push(`<li><span>${prettyDate(iso)}${tag}</span><b>${money(rate)}</b></li>`);
    d = addDays(d, 1);
  }

  $('#quoteLines').innerHTML = lines.join('');
  $('#quoteTotal').textContent = money(total);
  $('#quoteDeposit').textContent = money(CFG.deposit);
  $('#quoteBalance').textContent = money(total - CFG.deposit);
}

/* ═══════════════════════ form ═══════════════════════ */

function flashError(msg) {
  const box = $('#formError');
  box.textContent = msg;
  box.hidden = false;
  box.scrollIntoView({ block: 'nearest', behavior: 'smooth' });
  clearTimeout(flashError.t);
  flashError.t = setTimeout(() => { box.hidden = true; }, 6000);
}

function wireForm() {
  const guests = $('#f-guests');
  guests.innerHTML = Array.from({ length: CFG.max_guests }, (_, i) =>
    `<option value="${i + 1}"${i + 1 === 4 ? ' selected' : ''}>${i + 1} guest${i ? 's' : ''}</option>`
  ).join('');

  $('#bookingForm').addEventListener('submit', async e => {
    e.preventDefault();
    $('#formError').hidden = true;
    $$('.field').forEach(f => f.classList.remove('is-bad'));

    if (!cal.checkIn || !cal.checkOut) {
      return flashError('Please choose your check-in and check-out dates first.');
    }

    const form = e.target;
    const data = {
      check_in: cal.checkIn,
      check_out: cal.checkOut,
      guests: Number(form.guests.value),
      name: form.name.value.trim(),
      phone: form.phone.value.trim(),
      email: form.email.value.trim(),
      ic: form.ic.value.trim(),
      city: form.city.value.trim(),
      purpose: form.purpose.value,
      notes: form.notes.value.trim(),
      website: form.website.value,
    };

    if (data.name.length < 2) {
      $('#f-name').closest('.field').classList.add('is-bad');
      return flashError('Please tell us your full name.');
    }
    if (data.phone.replace(/\D/g, '').length < 8) {
      $('#f-phone').closest('.field').classList.add('is-bad');
      return flashError('Please enter a phone number we can reach you on.');
    }

    const btn = $('#submitBtn');
    btn.disabled = true;
    btn.textContent = 'Sending…';

    try {
      const res = await fetch('/api/bookings', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(data),
      });
      const body = await res.json();

      if (!res.ok) {
        if (res.status === 409) await loadAvailability();
        throw new Error(body.error || body.detail || 'Something went wrong.');
      }

      showSuccess(body, data);
      form.reset();
      cal.checkIn = cal.checkOut = null;
      renderCalendar();
      renderQuote();
      await loadAvailability();
    } catch (err) {
      flashError(err.message + ' You can also WhatsApp us directly — we reply fast.');
    } finally {
      btn.disabled = false;
      btn.textContent = 'Request booking';
    }
  });
}

function showSuccess(body, data) {
  $('#successRef').textContent = body.reference;
  $('#successBody').innerHTML =
    `<strong>${prettyDate(body.check_in)}</strong> to <strong>${prettyDate(body.check_out)}</strong> · ` +
    `${body.nights} night${body.nights > 1 ? 's' : ''} · ${money(body.total)} total.<br>` +
    `Deposit of ${money(body.deposit)} confirms it.`;
  $('#successWa').href = body.whatsapp_url ||
    `https://wa.me/${CFG.whatsapp}?text=${encodeURIComponent(
      `Hi ${CFG.name}, I just submitted booking ${body.reference}.`)}`;
  $('#successModal').hidden = false;
  document.body.style.overflow = 'hidden';
}

function wireSuccessModal() {
  const close = () => {
    $('#successModal').hidden = true;
    document.body.style.overflow = '';
  };
  $('#successClose').addEventListener('click', close);
  $('#successModal').addEventListener('click', e => {
    if (e.target === $('#successModal')) close();
  });
  document.addEventListener('keydown', e => {
    if (e.key === 'Escape' && !$('#successModal').hidden) close();
  });
}

/* ═══════════════════════ data loading ═══════════════════════ */

async function loadConfig() {
  try {
    const res = await fetch('/api/config');
    if (!res.ok) throw new Error();
    CFG = { ...FALLBACK, ...await res.json() };
    LIVE = true;
  } catch {
    CFG = { ...FALLBACK, today: toISO(new Date()) };
    LIVE = false;
  }
  applyConfig();
}

async function loadAvailability() {
  if (!LIVE) return;
  try {
    const start = toISO(new Date());
    const end = toISO(addDays(new Date(), CFG.booking_window_days));
    const res = await fetch(`/api/availability?start=${start}&end=${end}`);
    if (!res.ok) throw new Error();
    const data = await res.json();
    RATES = data.rates || {};
    BLOCKED = data.blocked || {};
    CFG.today = data.today || CFG.today;
  } catch {
    /* Keep whatever we have; the calendar still prices correctly. */
  }
  renderCalendar();
  renderQuote();
}

function applyConfig() {
  const wa = `https://wa.me/${CFG.whatsapp}?text=${encodeURIComponent(
    `Hi ${CFG.name}, I'd like to ask about a stay.`)}`;

  $$('[data-wa-link]').forEach(a => { a.href = wa; a.target = '_blank'; a.rel = 'noopener'; });
  $$('[data-phone-primary]').forEach(el => el.textContent = CFG.phone_primary);
  $$('[data-phone-secondary]').forEach(el => el.textContent = CFG.phone_secondary);
  $$('[data-base-rate]').forEach(el => el.textContent = money(CFG.base_rate));
  $$('[data-rate-base]').forEach(el => el.textContent = money(CFG.base_rate));
  $$('[data-rate-weekend]').forEach(el => el.textContent = money(CFG.weekend_rate));
  $$('[data-rate-holiday]').forEach(el => el.textContent = money(CFG.holiday_rate));
  $$('[data-deposit]').forEach(el => el.textContent = money(CFG.deposit));
  $$('[data-max-guests]').forEach(el => el.textContent = CFG.max_guests);
  $$('[data-min-nights]').forEach(el => el.textContent = CFG.min_nights);
  $$('[data-check-in-time]').forEach(el => el.textContent = CFG.check_in_time);
  $$('[data-check-out-time]').forEach(el => el.textContent = CFG.check_out_time);

  $('#igLink').href = CFG.instagram;
  $('#igHandle').textContent = CFG.instagram_label || socialLabel(CFG.instagram, '@');
  $('#fbLink').href = CFG.facebook;
  $('#fbHandle').textContent = CFG.facebook_label || socialLabel(CFG.facebook, '');
  $('#callLink').href = 'tel:' + CFG.phone_secondary.replace(/[^\d+]/g, '');

  const q = encodeURIComponent(CFG.maps_query);
  $('#mapsLink').href = `https://www.google.com/maps/search/?api=1&query=${q}`;
  $('#mapFrame').src = `https://maps.google.com/maps?q=${q}&z=16&output=embed`;

  $('#year').textContent = new Date().getFullYear();
}

/* ═══════════════════════ chrome ═══════════════════════ */

function wireNav() {
  const nav = $('#nav');
  const burger = $('#burger');
  const menu = $('#mobilemenu');

  const onScroll = () => nav.classList.toggle('is-stuck', window.scrollY > 40);
  onScroll();
  window.addEventListener('scroll', onScroll, { passive: true });

  burger.addEventListener('click', () => {
    const open = burger.getAttribute('aria-expanded') === 'true';
    burger.setAttribute('aria-expanded', String(!open));
    menu.hidden = open;
    nav.classList.toggle('is-open', !open);
  });

  $$('#mobilemenu a').forEach(a => a.addEventListener('click', () => {
    burger.setAttribute('aria-expanded', 'false');
    menu.hidden = true;
    nav.classList.remove('is-open');
  }));
}

/* ═══════════════════════ boot ═══════════════════════ */

async function init() {
  buildGallery();
  wireFilters();
  initLightbox();
  wireNav();
  wireCalendar();
  wireSuccessModal();

  await loadConfig();
  wireForm();
  renderCalendar();
  renderQuote();
  await loadAvailability();
}

if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', init);
} else {
  init();
}

})();
