/* Assistant: read-only chat about whatever is on screen. The API key stays on the server. */
(function () {
  "use strict";
  const { esc } = KP;
  let msgs = [], busy = false;

  function ctxLabel() {
    const c = KP.ctx || {};
    const fake = (c.batch || "").startsWith("DEMO-") ? " " + KP.fake(true) : "";
    switch (c.view) {
      case "episode": return `Episode <b>${esc(c.episode)}</b> in ${esc(c.batch)}${fake}: its record and every event`;
      case "blind": return c.blind ? `Blind episode <b>${esc(c.episode)}</b>${fake}: transcript only, verdict withheld` : `Episode <b>${esc(c.episode)}</b>${fake} (revealed)`;
      case "code": return `File <b>${esc(c.file)}</b>`;
      case "guide": return `Review gate <b>${esc(c.gate)}</b>, its checks and PREREG.md`;
      case "report": return `Your draft of <b>${esc(c.section)}</b>, its Apart guidance and CLAIMS.md`;
      case "live": return c.batch ? `Batch <b>${esc(c.batch)}</b>${fake}` : "Live run";
      case "integrity": return "The integrity summary";
      default: return "PREREG.md and CLAIMS.md";
    }
  }
  const SUGGEST = {
    episode: ["Why did the checker give this verdict? Cite the events.", "Does the peer's reasoning mention the identity claim?"],
    blind: ["Summarise what the peer did, step by step, without guessing the verdict."],
    guide: ["What exactly should I look for at this gate?", "What would make this gate fail?"],
    code: ["Walk me through this file. What could go wrong?", "Does this match PREREG.md?"],
    report: ["Which CLAIMS.md rows belong in this section?", "Does my draft overclaim anything?"],
    integrity: ["Is anything here worrying?"],
    live: ["What should I watch for while this runs?"],
  };

  function draw() {
    const el = KP.$("#assist-inner");
    const s = (KP.state || {}).assistant || {};
    el.innerHTML = `<header><div class="spread"><h3>Ask about this</h3><button class="btn ghost sm" id="as-close" title="Close (Esc)">✕</button></div>
        <div class="ctxchip"><span class="muted">Sees:</span><span>${ctxLabel()}</span></div></header>
      <div class="msgs" id="as-msgs">${msgs.length ? msgs.map((m) => m.role === "user" ? `<div class="msg user">${esc(m.content)}</div>` : m.role === "error" ? `<div class="msg err">${esc(m.content)}</div>` : `<div class="msg bot">${KP.mini(m.content)}<div class="meta">${esc(m.meta || "")}</div></div>`).join("") :
        `<p class="small muted" style="margin:0">I answer questions about this experiment's data and code, citing file paths. I say when I don't know. I won't write your report, but I'll critique drafts.</p>
         <div class="suggest">${(SUGGEST[(KP.ctx || {}).view] || SUGGEST.guide).map((q) => `<button>${esc(q)}</button>`).join("")}</div>`}
        ${busy ? '<div class="msg bot typing"><span></span><span></span><span></span></div>' : ""}</div>
      <form id="as-form"><textarea id="as-q" placeholder="Ask a question… (Enter to send)" ${s.key_present === false ? "disabled" : ""}></textarea></form>
      <div class="note">Read-only: it can't change files, start runs or approve gates. For anything that needs doing, message 42 on Signal.<br>
        <span class="mono">${esc(s.model || "")}</span> · today ≈ ${KP.fmtUsd(s.today_usd_est || 0, 3)} of ${KP.fmtUsd(s.budget_usd || 0, 2)} ${s.key_present === false ? '<br><b class="c-leak">No ANTHROPIC_API_KEY in the .env at KIN_ENV.</b>' : ""}</div>`;
    KP.$("#as-close").addEventListener("click", () => toggle(false));
    KP.$$(".suggest button", el).forEach((b) => b.addEventListener("click", () => send(b.textContent)));
    const q = KP.$("#as-q");
    q.addEventListener("keydown", (e) => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); send(q.value); } });
    const box = KP.$("#as-msgs"); box.scrollTop = box.scrollHeight;
  }

  async function send(text) {
    text = (text || "").trim();
    if (!text || busy) return;
    msgs.push({ role: "user", content: text }); busy = true; draw();
    try {
      const r = await KP.api("/api/ask", { messages: msgs.filter((m) => m.role === "user" || m.role === "assistant").map(({ role, content }) => ({ role, content })), context: KP.ctx });
      msgs.push({ role: "assistant", content: r.text || "(empty reply)", meta: `${r.model} · ${r.usage.input_tokens || 0} in / ${r.usage.output_tokens || 0} out · ≈${KP.fmtUsd(r.cost_usd_est, 4)}` });
      if (KP.state) KP.state.assistant.today_usd_est = r.today_usd_est;
    } catch (e) { msgs.push({ role: "error", content: e.message }); }
    busy = false; draw();
    const q = KP.$("#as-q"); if (q) q.focus();
  }

  function toggle(on) {
    const open = on == null ? !document.body.classList.contains("ask-open") : on;
    document.body.classList.toggle("ask-open", open);
    if (open) { draw(); setTimeout(() => { const q = KP.$("#as-q"); if (q) q.focus(); }, 300); }
  }

  KP.askOpen = function (prefill) { toggle(true); setTimeout(() => { const q = KP.$("#as-q"); if (q && prefill) { q.value = prefill; q.focus(); } }, 320); };
  KP.assistCtx = function () { if (document.body.classList.contains("ask-open")) draw(); };
  KP.assistInit = function () {
    KP.$("#askbtn").addEventListener("click", () => toggle());
    document.addEventListener("keydown", (e) => {
      if (e.key === "/" && !KP.isTyping(e)) { e.preventDefault(); toggle(true); }
      else if (e.key === "Escape" && document.body.classList.contains("ask-open")) toggle(false);
    });
  };
})();
