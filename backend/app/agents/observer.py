"""Reads the page. Pure DOM inspection; no LLM. Understands native controls, ARIA/custom React controls,
contenteditable editors, shadow DOM and iframes. Collects every signal a field offers (label, placeholder, aria,
name/id, autocomplete, hint text, section heading) so the analyzer can map it semantically."""
import re

OBSERVE_JS = r"""
(frameIdx) => {
  const txt = s => (s || '').replace(/\s+/g, ' ').trim();
  const shown = el => { const r = el.getBoundingClientRect(); const s = getComputedStyle(el);
    return r.width > 0 && r.height > 0 && s.visibility !== 'hidden' && s.display !== 'none'; };
  const deep = (sel, root = document) => { let out = [...root.querySelectorAll(sel)];
    root.querySelectorAll('*').forEach(e => { if (e.shadowRoot) out = out.concat(deep(sel, e.shadowRoot)); }); return out; };
  const hiddenTree = el => { for (let p = el.parentElement; p; p = p.parentElement) { const s = getComputedStyle(p); if (s.display === 'none' || s.visibility === 'hidden') return true; } return false; };
  const byId = id => (id ? document.getElementById(id) : null);
  window.__agN = window.__agN || 0;
  const tag = el => { let id = el.getAttribute('data-agent-id');
    if (!id) { id = `f${frameIdx}-${window.__agN++}`; el.setAttribute('data-agent-id', id); } return id; };
  const labelOf = el => {
    let t = '';
    if (el.labels && el.labels.length) t = txt(el.labels[0].innerText);
    if (!t && el.getAttribute('aria-label')) t = txt(el.getAttribute('aria-label'));
    if (!t && el.getAttribute('aria-labelledby'))
      t = el.getAttribute('aria-labelledby').split(' ').map(i => txt((byId(i) || {}).innerText)).join(' ').trim();
    if (!t) { const p = el.closest('[class*=field],[class*=question],[class*=form-group],[class*=form-row]');
      if (p) { const l = p.querySelector('label,legend,[class*=label]'); if (l && !l.contains(el)) t = txt(l.innerText); } }
    if (!t) t = el.getAttribute('placeholder') || el.getAttribute('name') || '';
    return t.slice(0, 300);
  };
  const groupLabel = el => {
    const fs = el.closest('fieldset'); if (fs) { const l = fs.querySelector('legend'); if (l) return txt(l.innerText); }
    const g = el.closest('[role=radiogroup],[role=group]');
    if (g) { const lb = g.getAttribute('aria-label') || txt((byId(g.getAttribute('aria-labelledby')) || {}).innerText); if (lb) return lb; }
    const p = el.closest('[class*=field],[class*=question],[class*=form-group]');
    if (p) { const l = p.querySelector('legend,label,[class*=label]'); if (l) return txt(l.innerText); }
    return '';
  };
  const hintOf = el => {
    const d = el.getAttribute('aria-describedby');
    if (d) { const t = d.split(' ').map(i => txt((byId(i) || {}).innerText)).join(' ').trim(); if (t) return t.slice(0, 200); }
    const p = el.closest('[class*=field],[class*=question],[class*=form-group],[class*=form-row]');
    if (p) { const h = p.querySelector('[class*=help],[class*=hint],[class*=description],small'); if (h && !h.contains(el)) return txt(h.innerText).slice(0, 200); }
    return '';
  };
  const sectionOf = el => { const s = el.closest('section,fieldset,[class*=section],[role=group]');
    if (s) { const h = s.querySelector('h1,h2,h3,h4,legend'); if (h && !h.contains(el)) return txt(h.innerText).slice(0, 80); } return ''; };
  const captured = new Set(), fields = [], groups = new Map();
  const mk = (el, kind, extra = {}) => {
    captured.add(el);
    const label = extra.label !== undefined ? extra.label : labelOf(el);
    const req = el.required || el.getAttribute('aria-required') === 'true' || /\*\s*$|\(required\)/i.test(label);
    return { id: tag(el), kind, label, name: el.getAttribute('name') || '', domid: el.id || '', placeholder: el.getAttribute('placeholder') || '',
      ariaLabel: el.getAttribute('aria-label') || '', autocomplete: el.getAttribute('autocomplete') || '', hint: hintOf(el), section: sectionOf(el),
      required: req, maxlength: el.maxLength > 0 ? el.maxLength : null, options: [], value: '', custom: 'native', multi: false, ...extra };
  };
  const skip = el => el.closest('header, nav, footer, [role=search]');

  deep('input, select, textarea').forEach(el => {
    if (skip(el)) return;
    const type = (el.getAttribute('type') || el.tagName).toLowerCase();
    if (['hidden','submit','button','image','reset','search'].includes(type) || el.disabled) return;
    const choice = type === 'radio' || type === 'checkbox';
    const vis = shown(el) || (choice && el.labels && [...el.labels].some(shown));
    if (type !== 'file' && !vis) return;
    if (type === 'file' && hiddenTree(el)) return;      // styled uploaders hide the input itself, but never its whole container
    if (type === 'password') { fields.push(mk(el, 'password')); return; }
    if (el.tagName === 'SELECT') {
      const options = [...el.options].filter(o => o.value !== '' && !/^(select|choose|please select|--)/i.test(txt(o.text))).map(o => ({ id: o.value, label: txt(o.text) }));
      const sel = [...el.selectedOptions].filter(o => o.value !== '');
      fields.push(mk(el, el.multiple ? 'multiselect' : 'select', { options, value: sel.map(o => txt(o.text)).join(', '), multi: el.multiple })); return;
    }
    if (el.tagName === 'TEXTAREA') { fields.push(mk(el, 'textarea', { value: el.value })); return; }
    if (type === 'file') { fields.push(mk(el, 'file')); return; }
    if (choice) {
      const gk = (el.name || tag(el)) + '|' + type;
      if (!groups.has(gk)) groups.set(gk, { type, items: [], q: groupLabel(el) });
      const l = labelOf(el) || el.value;
      groups.get(gk).items.push({ el, label: l, id: tag(el), req: el.required || /\*\s*$/.test(l) });
      captured.add(el); return;
    }
    const isCombo = el.getAttribute('role') === 'combobox' || el.getAttribute('aria-haspopup') === 'listbox' || el.getAttribute('aria-autocomplete') === 'list';
    fields.push(mk(el, type === 'date' ? 'date' : type === 'number' ? 'number' : isCombo ? 'combobox' : 'text',
      isCombo ? { value: el.value, custom: 'aria_combobox', multi: !!el.closest('[class*=multi],[class*=Multi]') } : { value: el.value, inputType: type }));
  });
  groups.forEach((g, gk) => {
    const first = g.items[0];
    if (g.type === 'checkbox' && g.items.length === 1) {
      const f = mk(first.el, 'checkbox', { label: first.label || g.q, value: first.el.checked ? 'checked' : '' }); f.required = first.req; fields.push(f); return; }
    const f = mk(first.el, g.type === 'radio' ? 'radio' : 'checkbox_group', { label: g.q || first.el.name || first.label,
      options: g.items.map(i => ({ id: i.id, label: i.label })), value: g.items.filter(i => i.el.checked).map(i => i.label).join(', '), multi: g.type !== 'radio' });
    f.id = 'g-' + gk + '-' + frameIdx; f.required = g.items.some(i => i.req); fields.push(f);
  });

  // custom (ARIA) controls: MUI/React-Select style dropdowns, button-based radios, switches
  deep('[role=combobox]:not(input):not(select), [aria-haspopup=listbox]:not(input):not(select)').forEach(el => {
    if (!shown(el) || skip(el) || captured.has(el) || el.querySelector('input,textarea,select') || el.closest('[role=listbox]')) return;
    const v = txt(el.innerText);
    fields.push(mk(el, 'combobox', { custom: 'aria_combobox', value: /^(select|choose|please|--)/i.test(v) ? '' : v,
      multi: !!(el.closest('[class*=multi],[class*=Multi]') || el.getAttribute('aria-multiselectable') === 'true') }));
  });
  deep('[role=radiogroup]').forEach(g => {
    const rs = [...g.querySelectorAll('[role=radio]')];
    if (!rs.length || !shown(g) || skip(g) || rs.some(r => r.matches('input'))) return;
    const lab = g.getAttribute('aria-label') || txt((byId(g.getAttribute('aria-labelledby')) || {}).innerText) || groupLabel(g);
    const f = mk(g, 'radio', { label: lab, custom: 'aria_radio', options: rs.map(r => ({ id: tag(r), label: txt(r.innerText) || r.getAttribute('aria-label') || '' })),
      value: rs.filter(r => r.getAttribute('aria-checked') === 'true').map(r => txt(r.innerText)).join(', ') });
    f.id = 'g-aria-' + f.id; fields.push(f);
  });
  deep('[role=checkbox]:not(input), [role=switch]:not(input)').forEach(el => {
    if (!shown(el) || skip(el) || el.closest('[role=listbox],[role=menu],[role=radiogroup]')) return;
    fields.push(mk(el, 'checkbox', { label: labelOf(el) || txt(el.innerText), custom: 'aria_checkbox', value: el.getAttribute('aria-checked') === 'true' ? 'checked' : '' }));
  });
  deep('[contenteditable=""], [contenteditable="true"]').forEach(el => {
    if (!shown(el) || skip(el) || captured.has(el) || (el.parentElement && el.parentElement.closest('[contenteditable=true]'))) return;
    if (el.getBoundingClientRect().height < 30 && el.getAttribute('role') !== 'textbox') return;
    fields.push(mk(el, 'richtext', { custom: 'contenteditable', value: txt(el.innerText) }));
  });

  const buttons = [];
  deep('button, input[type=submit], input[type=button], [role=button], a').forEach(b => {
    if (!shown(b) || b.closest('footer') || b.closest('[role=listbox],[role=menu]')) return;
    const text = txt(b.innerText || b.value || b.getAttribute('aria-label') || '');
    if (!text || text.length > 60) return;
    if (b.tagName === 'A' && !/apply|next|continue|submit|review|proceed/i.test(text)) return;
    buttons.push({ id: tag(b), text, disabled: !!b.disabled || b.getAttribute('aria-disabled') === 'true' });
  });
  const errors = [...document.querySelectorAll('[aria-invalid="true"], .error, .field-error, [class*="error-message"], [role=alert]')]
    .filter(shown).map(e => txt(e.innerText)).filter(Boolean).slice(0, 8);
  let stepper = null; const bt = (document.body ? document.body.innerText : '').slice(0, 5000);
  const m = bt.match(/step\s+(\d+)\s*(?:of|\/)\s*(\d+)/i) || bt.match(/\b(\d+)\s*(?:of|\/)\s*(\d+)\s*(?:steps?|pages?)/i);
  if (m && +m[2] > 1 && +m[2] < 30) stepper = { cur: +m[1], total: +m[2] };
  return { fields, buttons, errors, stepper };
}
"""

LIST_OPTIONS_JS = r"""
() => { const txt = s => (s || '').replace(/\s+/g, ' ').trim();
  const vis = e => { const r = e.getBoundingClientRect(); const s = getComputedStyle(e); return r.width > 0 && r.height > 0 && s.visibility !== 'hidden' && s.display !== 'none'; };
  let els = [...document.querySelectorAll('[role=option]')].filter(vis);
  if (!els.length) els = [...document.querySelectorAll('[class*=select__option],[class*=menu-item],[class*=MenuItem],ul[role=listbox] li,[role=listbox] > *')].filter(vis);
  return [...new Set(els.map(e => txt(e.innerText)).filter(Boolean))].slice(0, 120); }
"""

PICK_OPTION_JS = r"""
(label) => { const norm = s => (s || '').toLowerCase().replace(/[^a-z0-9 ]/g, ' ').replace(/\s+/g, ' ').trim();
  const vis = e => { const r = e.getBoundingClientRect(); const s = getComputedStyle(e); return r.width > 0 && r.height > 0 && s.visibility !== 'hidden' && s.display !== 'none'; };
  document.querySelectorAll('[data-agent-opt]').forEach(e => e.removeAttribute('data-agent-opt'));
  const c = [...document.querySelectorAll('[role=option],[role=menuitem],[class*=select__option],[class*=option],[class*=MenuItem],ul[role=listbox] li,[role=listbox] > *')].filter(vis);
  const w = norm(label);
  const hit = c.find(e => norm(e.innerText) === w) || c.find(e => norm(e.innerText).startsWith(w)) || c.find(e => w && norm(e.innerText).includes(w));
  if (hit) { hit.setAttribute('data-agent-opt', '1'); return norm(hit.innerText); }
  return null; }
"""

SHOWS_JS = r"""
(e, l) => { const n = s => (s || '').toLowerCase().replace(/[^a-z0-9 ]/g, ' ').replace(/\s+/g, ' ').trim(); const w = n(l);
  const root = e.closest('[class*=control],[class*=Control],[class*=select],[class*=Select],[class*=autocomplete],[class*=Autocomplete]') || e.parentElement || e;
  const parts = [e.value || '', e.tagName !== 'INPUT' ? e.innerText : ''];
  root.querySelectorAll('[class*=singleValue],[class*=SingleValue],[class*=multiValue],[class*=MultiValue],[class*=chip],[class*=Chip],[class*=selected-value],[class*=value-container]').forEach(x => parts.push(x.innerText));
  return parts.some(p => n(p).includes(w)); }
"""

BLOCKER_JS = r"""
() => {
  const t = (document.body ? document.body.innerText : '').slice(0, 4000).toLowerCase();
  const vis = e => { const r = e.getBoundingClientRect(); return r.width > 0 && r.height > 0; };
  const cap = [...document.querySelectorAll('.g-recaptcha,.h-captcha,.cf-turnstile,iframe[src*="recaptcha"],iframe[src*="hcaptcha"],iframe[src*="turnstile"]')]
    .filter(e => !e.closest('.grecaptcha-badge') && vis(e) && e.getBoundingClientRect().height >= 50);
  if (/access denied|you have been blocked|unusual traffic|request blocked|bot detected|automated access/.test(t) && t.length < 1500) return 'blocked';
  if (cap.length || /verify (that )?you are (a )?human|are you a robot|complete the captcha/.test(t)) return 'captcha';
  if ([...document.querySelectorAll('input[type=password]')].some(vis)) return 'login';
  if (/(verification|security|one-time|authentication) code|authenticator app|two-factor|2-step/.test(t) &&
      document.querySelectorAll('input[type=text],input[type=tel],input[type=number]').length <= 2) return 'mfa';
  return null;
}
"""

META_JS = r"""
() => { const m = n => (document.querySelector(`meta[property="${n}"],meta[name="${n}"]`) || {}).content || '';
  return { title: document.title, h1: (document.querySelector('h1') || {}).innerText || '', ogTitle: m('og:title'),
    ogSite: m('og:site_name'), text: (document.body ? document.body.innerText : '').replace(/\s+/g, ' ').slice(0, 6000) }; }
"""

SKIP_FRAMES = ("recaptcha", "hcaptcha", "doubleclick", "challenges.cloudflare", "googletagmanager")
CONFIRM_RE = re.compile(r"(thank you for (applying|your application)|application (has been |was )?(successfully )?(submitted|received|sent)|"
                        r"successfully (submitted|applied)|we(’|')?ve received your application|we have received your application)", re.I)


async def observe(page) -> dict:
    fields, buttons, errors, stepper = [], [], [], None
    for idx, frame in enumerate(page.frames):
        if any(x in (frame.url or "") for x in SKIP_FRAMES):
            continue
        try:
            d = await frame.evaluate(OBSERVE_JS, idx)
        except Exception:
            continue
        fields += d["fields"]
        buttons += d["buttons"]
        errors += d["errors"]
        stepper = stepper or d.get("stepper")
    return {"fields": fields, "buttons": buttons, "errors": errors, "stepper": stepper, "url": page.url}


async def detect_blocker(page) -> str | None:
    found = set()
    for frame in page.frames:
        if any(x in (frame.url or "") for x in ("recaptcha", "hcaptcha", "doubleclick")):
            continue
        try:
            r = await frame.evaluate(BLOCKER_JS)
        except Exception:
            continue
        if r:
            found.add(r)
    for k in ("blocked", "captcha", "login", "mfa"):
        if k in found:
            return k
    return None


async def detect_confirmation(page) -> str | None:
    for frame in page.frames:
        try:
            t = await frame.evaluate("() => (document.body ? document.body.innerText : '').replace(/\\s+/g,' ')")
        except Exception:
            continue
        if m := CONFIRM_RE.search(t):
            s = max(0, m.start() - 40)
            return t[s:m.end() + 120].strip()
    return None


async def page_meta(page) -> dict:
    try:
        return await page.evaluate(META_JS)
    except Exception:
        return {"title": "", "h1": "", "ogTitle": "", "ogSite": "", "text": ""}
