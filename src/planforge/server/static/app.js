/* واجهة المحرر — الحدّ الأدنى الصادق: تعرض الحالة وتُطبّق العمليات
   وتُظهر سبب الرفض. لا تخفي شيئًا: التعديل المرفوض يُعلن المخالفات التي
   كان سيُدخلها، فيعرف المهندس لماذا رُفض لا أنه رُفض فقط. */
'use strict';

const $ = (id) => document.getElementById(id);
let SID = null;
let STATE = null;
let STOREY = 0;

/* الرمز يُحفظ كوكي بـSameSite=Strict، فيُرسل مع كل طلب تلقائيًا بلا
   تخزينه في localStorage — الأخير يقرؤه أي سكربت في الصفحة. */
$('auth').onclick = async () => {
  const value = $('tok').value.trim();
  if (!value) return say('أدخل الرمز', 'e');
  document.cookie =
    `pf_token=${encodeURIComponent(value)}; path=/; SameSite=Strict`;
  try {
    await api('/api/health');
    $('authRow').style.display = 'none';
    say('تم الدخول', 'g');
  } catch (err) {
    say('رمز غير صحيح', 'e');
  }
};

const say = (text, cls) => {
  const box = $('msg');
  box.textContent = text || '';
  box.className = cls || '';
};

async function api(path, options) {
  const res = await fetch(path, options);
  const body = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(body.detail || `HTTP ${res.status}`);
  return body;
}

const post = (path, payload) =>
  api(path, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload || {}),
  });

/* ── العرض ── */

function renderStamp(a) {
  const box = $('stampBox');
  box.innerHTML =
    `<p class="stamp ${a.delivery_ready ? 'ready' : ''}">` +
    `${a.stamp}<br>${a.summary_ar}</p>`;
}

function renderPlan(state) {
  const stage = $('stage');
  stage.innerHTML = state.storeys
    .map(
      (s) =>
        `<h3>دور ${s.index} — ${s.gia_m2} م² صافٍ</h3>${s.svg}`
    )
    .join('');
  stage.querySelectorAll('[data-wall]').forEach((el) => {
    el.addEventListener('click', () => {
      say(`الجدار ${el.dataset.wall} — اختر خطه من القائمة لتحريكه`);
    });
  });
}

function renderSelectors(state) {
  const s = state.storeys.find((x) => x.index === STOREY) || state.storeys[0];
  if (!s) return;
  STOREY = s.index;
  $('lines').innerHTML = s.lines
    .map(
      (l) =>
        `<option value="${l.id}" data-coord="${l.coord}">` +
        `${l.id} · ${l.axis} @ ${l.coord} مم · ${l.rooms.join('/')}` +
        `</option>`
    )
    .join('');
  $('rooms').innerHTML = s.rooms
    .map(
      (r) =>
        `<option value="${r.id}" data-area="${r.area_m2}">` +
        `${r.id} · ${r.type} · ${r.area_m2} م²` +
        `${r.furnishable ? '' : ' ⚠ لا تُؤثَّث'}</option>`
    )
    .join('');
  syncInputs();
}

function syncInputs() {
  const line = $('lines').selectedOptions[0];
  if (line) $('coord').value = line.dataset.coord;
  const room = $('rooms').selectedOptions[0];
  if (room) $('area').value = room.dataset.area;
}

function renderStatus(state) {
  const f = state.features;
  const c = ['layout', 'drawing', 'fixtures'].reduce(
    (acc, k) => {
      acc.e += state.reports[k].counts.errors;
      acc.w += state.reports[k].counts.warnings;
      return acc;
    },
    { e: 0, w: 0 }
  );
  $('status').innerHTML =
    `<ul>` +
    `<li class="${state.ok ? 'g' : 'e'}">` +
    `${state.ok ? 'جائز' : `${c.e} مخالفة`} · ${c.w} تحذير</li>` +
    `<li>الدرجة ${state.rank}</li>` +
    `<li>الحركة ${(f.circulation_ratio * 100).toFixed(1)}%</li>` +
    `<li>خطأ المساحة ${(f.mean_area_error * 100).toFixed(1)}%</li>` +
    `<li>تكديس الرطب ${(f.wet_stack_ratio * 100).toFixed(0)}%</li>` +
    `<li>محاذاة إنشائية ` +
    `${(f.structural_alignment_ratio * 100).toFixed(0)}%</li>` +
    `<li>غرف لا تُؤثَّث ${f.unfurnishable_rooms}</li>` +
    `</ul>`;
}

function renderIssues(state) {
  const items = [];
  for (const key of ['layout', 'drawing', 'fixtures']) {
    for (const v of state.reports[key].errors) {
      items.push(
        `<li class="e"><code>${v.rule}</code> ${v.message}` +
          `${v.rooms.length ? ` (${v.rooms.join(', ')})` : ''}` +
          `${v.actual ? `<br><small>${v.actual} ← ${v.required}` +
            `</small>` : ''}</li>`
      );
    }
    for (const v of state.reports[key].warnings) {
      items.push(
        `<li class="w"><code>${v.rule}</code> ${v.message}</li>`
      );
    }
  }
  $('issues').innerHTML = items.length
    ? `<ul>${items.join('')}</ul>`
    : '<p class="g">لا مخالفات ولا تحذيرات.</p>';
}

function render(state) {
  STATE = state;
  renderStamp(state.assurance);
  renderPlan(state);
  renderSelectors(state);
  renderStatus(state);
  renderIssues(state);
  $('undo').disabled = !state.history.can_undo;
  $('redo').disabled = !state.history.can_redo;
}

/* ── العمليات ── */

async function sendOp(op) {
  try {
    const res = await post(`/api/session/${SID}/op`, op);
    if (res.ok) {
      render(res.state);
      say(res.message, 'g');
      return;
    }
    const why = res.introduced
      .map((v) => `${v.rule}: ${v.message}`)
      .join(' · ');
    say(`${res.message}${why ? ' — ' + why : ''}`, 'e');
  } catch (err) {
    say(err.message, 'e');
  }
}

$('open').onclick = async () => {
  try {
    const res = await post('/api/open', { path: $('path').value.trim() });
    SID = res.session;
    render(res.state);
    say('فُتح المشروع', 'g');
  } catch (err) {
    say(err.message, 'e');
  }
};

$('save').onclick = async () => {
  try {
    const res = await post(`/api/session/${SID}/save`, {
      path: $('path').value.trim() || undefined,
    });
    say(`حُفظ في ${res.path} (${res.operations} عملية)`, 'g');
  } catch (err) {
    say(err.message, 'e');
  }
};

const historyBtn = (kind) => async () => {
  try {
    const res = await post(`/api/session/${SID}/${kind}`);
    if (res.ok) render(res.state);
    say(res.message, res.ok ? 'g' : 'e');
  } catch (err) {
    say(err.message, 'e');
  }
};
$('undo').onclick = historyBtn('undo');
$('redo').onclick = historyBtn('redo');

$('moveWall').onclick = () =>
  sendOp({
    kind: 'move_wall',
    storey: STOREY,
    line: $('lines').value,
    coord_mm: parseInt($('coord').value, 10),
  });

$('resize').onclick = () =>
  sendOp({
    kind: 'resize_room',
    storey: STOREY,
    room: $('rooms').value,
    target_area_mm2: Math.round(parseFloat($('area').value) * 1e6),
  });

$('lines').onchange = syncInputs;
$('rooms').onchange = syncInputs;
