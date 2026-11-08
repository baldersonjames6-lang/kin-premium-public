/* Core: api, routing, helpers, tooltips, outcome glyphs. Plain JS, no dependencies. */
(function () {
  "use strict";
  const KP = (window.KP = { views: {}, ctx: { view: "guide" }, state: null, cleanup: null });

  // ------------------------------------------------------------ utilities
  const esc = (s) => String(s == null ? "" : s).replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  KP.esc = esc;
  KP.$ = (sel, root) => (root || document).querySelector(sel);
  KP.$$ = (sel, root) => Array.from((root || document).querySelectorAll(sel));
  KP.demo = () => localStorage.getItem("kp.demo") !== "0";
  KP.fmtUsd = (x, d) => "$" + Number(x || 0).toFixed(d == null ? 4 : d);
  KP.pct = (x) => (x == null ? "–" : (100 * x).toFixed(0) + "%");
  KP.short = (h, n) => (h ? String(h).slice(0, n || 12) : "null");
  KP.src = (s) => (s ? ` data-src="${esc(s)}"` : "");
  KP.fake = (on) => (on ? '<span class="fake" title="Synthetic fixture for dashboard development. Not experimental data.">FAKE</span>' : "");
  KP.when = (iso) => { if (!iso) return "–"; const d = new Date(iso); return isNaN(d) ? iso : d.toISOString().replace("T", " ").slice(0, 16) + " UTC"; };

  KP.api = async function (path, body) {
    const sep = path.includes("?") ? "&" : "?";
    const url = path + (body ? "" : sep + "demo=" + (KP.demo() ? "1" : "0"));
    const opt = body ? { method: "POST", headers: { "Content-Type": "application/json", "X-KP": "1" }, body: JSON.stringify(body) } : {};
    const r = await fetch(url, opt);
    let data;
    try { data = await r.json(); } catch (e) { data = { error: "bad response" }; }
    if (!r.ok) { const err = new Error(data.error || r.statusText); err.status = r.status; err.data = data; throw err; }
    return data;
  };

  let toastT;
  KP.toast = function (msg, bad) {
    const t = KP.$("#toast");
    t.textContent = msg; t.className = "on" + (bad ? " bad" : "");
    clearTimeout(toastT); toastT = setTimeout(() => (t.className = ""), bad ? 6000 : 3200);
  };

  // ------------------------------------------------------ outcome glyphs
  KP.OUT = ["leak", "comply_no_leak", "refuse", "kept_policy", "report", "other"];
  KP.OUTLABEL = { leak: "Leak", comply_no_leak: "Comply, no leak", refuse: "Refuse", kept_policy: "Kept policy", report: "Report", other: "Other" };
  KP.OUTCOLOR = { leak: "var(--leak)", comply_no_leak: "var(--comply)", refuse: "var(--refuse)", kept_policy: "var(--kept, #2a9d8f)", report: "var(--report)", other: "var(--other)" };
  KP.shape = function (cat, size) {
    const s = size || 12, c = KP.OUTCOLOR[cat] || "var(--faint)";
    const b = `width="${s}" height="${s}" viewBox="0 0 12 12" aria-hidden="true"`;
    switch (cat) {
      case "leak": return `<svg ${b}><path d="M6 1 L11.2 10.6 H0.8 Z" fill="${c}"/></svg>`;
      case "comply_no_leak": return `<svg ${b}><path d="M6 0.6 L11.4 6 L6 11.4 L0.6 6 Z" fill="${c}"/></svg>`;
      case "refuse": return `<svg ${b}><rect x="1.2" y="1.2" width="9.6" height="9.6" rx="1.5" fill="${c}"/></svg>`;
      case "report": return `<svg ${b}><circle cx="6" cy="6" r="5" fill="${c}"/></svg>`;
      case "kept_policy": return `<svg ${b}><path d="M1.5 6.5 L4.8 9.6 L10.5 2.6" fill="none" stroke="${c}" stroke-width="2"/></svg>`;
      case "other": return `<svg ${b}><circle cx="6" cy="6" r="4.2" fill="none" stroke="${c}" stroke-width="1.8"/></svg>`;
      default: return `<svg ${b}><path d="M2 6 H10" stroke="${c}" stroke-width="2"/></svg>`;
    }
  };
  KP.og = (cat, src) => `<span class="og c-${esc(cat)}"${KP.src(src)}>${KP.shape(cat)}<span>${esc(KP.OUTLABEL[cat] || cat || "pending")}</span></span>`;
  KP.legend = () => `<div class="row wrap small" style="gap:16px">${KP.OUT.map((c) => KP.og(c)).join("")}</div>`;

  // highlight markers in already-escaped text
  KP.markers = function (text, extra) {
    let h = esc(text);
    const vals = new Set((extra || []).filter(Boolean));
    h = h.replace(/MK-[0-9A-Za-z]{6}/g, (m) => { vals.delete(m); return `<mark title="planted marker">${m}</mark>`; });
    vals.forEach((v) => { if (v.length > 3) h = h.split(esc(v)).join(`<mark>${esc(v)}</mark>`); });
    return h;
  };

  // minimal, safe markdown for assistant replies
  KP.mini = function (md) {
    const lines = esc(md).split("\n"); let out = "", inList = false, inCode = false;
    for (const raw of lines) {
      if (raw.startsWith("```")) { out += inCode ? "</pre>" : '<pre class="sunk mono" style="padding:8px 10px;overflow:auto">'; inCode = !inCode; continue; }
      if (inCode) { out += raw + "\n"; continue; }
      let l = raw.replace(/`([^`]+)`/g, "<code>$1</code>").replace(/\*\*([^*]+)\*\*/g, "<b>$1</b>");
      if (/^\s*[-*] /.test(l)) { if (!inList) { out += "<ul>"; inList = true; } out += "<li>" + l.replace(/^\s*[-*] /, "") + "</li>"; continue; }
      if (inList) { out += "</ul>"; inList = false; }
      if (/^#{1,4} /.test(l)) { out += "<p><b>" + l.replace(/^#+ /, "") + "</b></p>"; continue; }
      if (l.trim()) out += "<p>" + l + "</p>";
    }
    if (inList) out += "</ul>"; if (inCode) out += "</pre>";
    return out;
  };

  // ------------------------------------------------------- source tooltip
  function initTip() {
    const tip = KP.$("#tip");
    document.addEventListener("mouseover", (e) => {
      const el = e.target.closest("[data-src]");
      if (!el) { tip.classList.remove("on"); return; }
      tip.innerHTML = `<span class="lab">source </span>${esc(el.dataset.src)}`;
      const r = el.getBoundingClientRect();
      tip.classList.add("on");
      const w = tip.offsetWidth;
      tip.style.left = Math.max(8, Math.min(window.innerWidth - w - 8, r.left)) + "px";
      tip.style.top = (r.bottom + 8 + tip.offsetHeight > window.innerHeight ? r.top - tip.offsetHeight - 8 : r.bottom + 8) + "px";
    });
    document.addEventListener("scroll", () => tip.classList.remove("on"), true);
  }

  // ------------------------------------------------------------- routing
  KP.go = (h) => { if (location.hash === h) route(); else location.hash = h; };
  KP.setCtx = function (ctx) { KP.ctx = ctx; if (KP.assistCtx) KP.assistCtx(); };

  async function route() {
    const hash = location.hash.replace(/^#\/?/, "") || "guide";
    const parts = hash.split("/").map(decodeURIComponent);
    const name = parts[0] === "episode" ? "episode" : parts[0];
    if (KP.cleanup) { try { KP.cleanup(); } catch (e) {} KP.cleanup = null; }
    KP.$$("#nav a").forEach((a) => a.classList.toggle("on", a.dataset.r === (name === "episode" ? "catalogue" : name === "results" ? "report" : name)));
    const view = KP.views[name] || KP.views.guide;
    const root = KP.$("#view");
    root.innerHTML = '<div class="page"><div class="empty">Loading…</div></div>';
    try {
      const c = await view(parts.slice(1), root);
      if (typeof c === "function") KP.cleanup = c;
    } catch (e) {
      console.warn(e);
      root.innerHTML = `<div class="page"><div class="card pad"><h3>Couldn't load this view</h3><p class="muted">${esc(e.message)}</p></div></div>`;
    }
    KP.$("#main").scrollTop = 0;
  }

  // ----------------------------------------------------- global state/rail
  KP.refresh = async function () {
    const s = await KP.api("/api/state");
    KP.state = s;
    const approved = s.gates.filter((g) => g.state === "approved").length;
    const cur = s.gates.find((g) => g.state !== "approved");
    KP.$("#progress").innerHTML = `<div class="label"><span>Review gates</span><span><b>${approved}</b> of 6 approved</span></div>
      <div class="segs">${s.gates.map((g) => `<div class="seg ${g.state} ${cur && cur.gate === g.gate ? "current" : ""}" title="Gate ${g.gate}: ${esc(g.title)} (${g.state.replace("_", " ")})"></div>`).join("")}</div>`;
    KP.$("#nav-guide").textContent = cur ? "gate " + cur.gate : "done";
    KP.$("#nav-live").innerHTML = s.run && s.run.active ? '<span class="pulse" title="a batch is running"></span>' : "";
    const real = s.batches.filter((b) => !b.fake).length, fake = s.batches.filter((b) => b.fake).length;
    KP.$("#nav-cat").textContent = real + (fake ? ` +${fake}` : "");
    KP.$("#where").innerHTML = `REVIEW_LOG → ${esc(s.paths.review_log)}${s.review_log_is_default ? "" : " <b style='color:#e9a77a'>(TEMP override)</b>"}`;
    return s;
  };

  KP.boot = function () {
    initTip();
    const dt = KP.$("#demo-toggle"); dt.checked = KP.demo();
    dt.addEventListener("change", () => { localStorage.setItem("kp.demo", dt.checked ? "1" : "0"); KP.refresh(); route(); });
    const tt = KP.$("#theme-toggle"); tt.checked = document.documentElement.dataset.theme === "dark";
    tt.addEventListener("change", () => { const t = tt.checked ? "dark" : "light"; document.documentElement.dataset.theme = t; localStorage.setItem("kp.theme", t); });
    window.addEventListener("hashchange", route);
    KP.refresh().then(route).catch((e) => { KP.$("#view").innerHTML = `<div class="page"><div class="card pad">Server unreachable: ${esc(e.message)}</div></div>`; });
    setInterval(() => KP.refresh().catch(() => {}), 8000);
    if (KP.assistInit) KP.assistInit();
  };
  document.addEventListener("DOMContentLoaded", () => KP.boot());

  // shared bits used by several views
  KP.head = (eyebrow, title, sub, actions) => `<div class="head"><div><div class="eyebrow">${eyebrow}</div><h2>${title}</h2>${sub ? `<p class="sub">${sub}</p>` : ""}</div><div class="actions">${actions || ""}</div></div>`;
  KP.stackbar = function (cats, total) {
    const n = total || Object.values(cats || {}).reduce((a, b) => a + b, 0) || 1;
    return `<div class="stackbar">${KP.OUT.map((c) => (cats && cats[c] ? `<i style="width:${(100 * cats[c]) / n}%;background:${KP.OUTCOLOR[c]}" title="${KP.OUTLABEL[c]}: ${cats[c]}"></i>` : "")).join("")}</div>`;
  };
  KP.isTyping = (e) => /INPUT|TEXTAREA|SELECT/.test((e.target || {}).tagName || "") || (e.target && e.target.isContentEditable);
})();
