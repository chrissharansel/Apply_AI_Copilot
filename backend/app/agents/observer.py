"""Reads the page. Pure DOM inspection; no LLM, no side effects except tagging elements with data-agent-id."""
import re

OBSERVE_JS = r"""
(frameIdx) => {
  const txt = s => (s || '').replace(/\s+/g, ' ').trim();
  const shown = el => { const r = el.getBoundingClientRect(); const s = getComputedStyle(el);
    return r.width > 0 && r.height > 0 && s.visibility !== 'hidden' && s.display !== 'none'; };
  window.__agN = window.__agN || 0;
  const tag = el => { let id = el.getAttribute('data-agent-id');
    if (!id) { id = `f${frameIdx}-${window.__agN++}`; el.setAttribute('data-agent-id', id); } return id; };
  const labelOf = el => {
    let t = '';
    if (el.labels && el.labels.length) t = txt(el.labels[0].innerText);
    if (!t && el.getAttribute('aria-label')) t = txt(el.getAttribute('aria-label'));
    if (!t && el.getAttribute('aria-labelledby'))
      t = el.getAttribute('aria-labelledby').split(' ').map(i => txt((document.getElementById(i) || {}).innerText)).join(' ').trim();
    if (!t) { const p = el.closest('[class*=field],[class*=question],[class*=form-group],[class*=form-row]');
      if (p) { const l = p.querySelector('label,legend,[class*=label]'); if (l) t = txt(l.innerText); } }
    if (!t) t = el.placeholder || el.name || '';
    return t.slice(0, 300);
  };
  const groupLabel = el => {
    const fs = el.closest('fieldset'); if (fs) { const l = fs.querySelector('legend'); if (l) return txt(l.innerText); }
    const g = el.closest('[role=radiogroup],[role=group]');
    if (g) { const lb = g.getAttribute('aria-label') || txt((document.getElementById(g.getAttribute('aria-labelledby') || '') || {}).innerText); if (lb) return lb; }
    const p = el.closest('[class*=field],[class*=question],[class*=form-group]');
    if (p) { const l = p.querySelector('legend,label,[class*=label]'); if (l) return txt(l.innerText); }
    return '';
  };
  const fields = [], groups = new Map();
  document.querySelectorAll('input, select, textarea').forEach(el => {
    if (el.closest('header, nav, footer, [role=search]')) return;
    const type = (el.getAttribute('type') || el.tagName).toLowerCase();
    if (['hidden','submit','button','image','reset','search'].includes(type) || el.disabled) return;
    const choice = type === 'radio' || type === 'checkbox';
    const vis = shown(el) || (choice && el.labels && [...el.labels].some(shown));
    if (type !== 'file' && !vis) return;
    const label = choice ? (labelOf(el) || el.value) : labelOf(el);
    const req = el.required || el.getAttribute('aria-required') === 'true' || /\*\s*$|\(required\)/i.test(label);
    const base = { id: tag(el), name: el.name || '', required: req, maxlength: el.maxLength > 0 ? el.maxLength : null, options: [], value: '' };
    if (type === 'password') { fields.push({ ...base, kind: 'password', label }); return; }
    if (el.tagName === 'SELECT') {
      const options = [...el.options].filter(o => o.value !== '' && !/^(select|choose|please select|--)/i.test(txt(o.text))).map(o => ({ id: o.value, label: txt(o.text) }));
      const sel = el.selectedOptions[0];
      fields.push({ ...base, kind: 'select', label, options, value: sel && el.value !== '' ? txt(sel.text) : '' }); return;
    }
    if (el.tagName === 'TEXTAREA') { fields.push({ ...base, kind: 'textarea', label, value: el.value }); return; }
    if (type === 'file') { fields.push({ ...base, kind: 'file', label }); return; }
    if (choice) {
      const gk = (el.name || base.id) + '|' + type;
      if (!groups.has(gk)) groups.set(gk, { type, items: [], q: groupLabel(el) });
      groups.get(gk).items.push({ el, label, id: base.id, req });
      return;
    }
    let kind = type === 'date' ? 'date' : type === 'number' ? 'number' : 'text';
    if (el.getAttribute('role') === 'combobox' || el.getAttribute('aria-haspopup') === 'listbox') kind = 'combobox';
    fields.push({ ...base, kind, label, value: el.value, inputType: type });
  });
  groups.forEach((g, gk) => {
    const first = g.items[0];
    if (g.type === 'checkbox' && g.items.length === 1)
      { fields.push({ id: first.id, kind: 'checkbox', label: first.label || g.q, required: first.req, options: [], value: first.el.checked ? 'checked' : '' }); return; }
    const kind = g.type === 'radio' ? 'radio' : 'checkbox_group';
    const checked = g.items.filter(i => i.el.checked).map(i => i.label);
    fields.push({ id: 'g-' + gk + '-' + frameIdx, kind, label: g.q || first.el.name || first.label, required: g.items.some(i => i.req),
      options: g.items.map(i => ({ id: i.id, label: i.label })), value: checked.join(', ') });
  });
  const buttons = [];
  document.querySelectorAll('button, input[type=submit], input[type=button], [role=button], a').forEach(b => {
    if (!shown(b) || b.closest('footer')) return;
    const text = txt(b.innerText || b.value || b.getAttribute('aria-label') || '');
    if (!text || text.length > 60) return;
    if (b.tagName === 'A' && !/apply|next|continue|submit/i.test(text)) return;
    buttons.push({ id: tag(b), text, disabled: !!b.disabled || b.getAttribute('aria-disabled') === 'true' });
  });
  const errors = [...document.querySelectorAll('[aria-invalid="true"], .error, .field-error, [class*="error-message"], [role=alert]')]
    .filter(shown).map(e => txt(e.innerText)).filter(Boolean).slice(0, 8);
  return { fields, buttons, errors };
}
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
    fields, buttons, errors = [], [], []
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
    return {"fields": fields, "buttons": buttons, "errors": errors, "url": page.url}


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
