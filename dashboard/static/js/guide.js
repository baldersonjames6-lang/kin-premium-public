/* Guide: the six review gates, the single next action, evidence inline, decisions to REVIEW_LOG.md. */
(function () {
  "use strict";
  const { esc } = KP;
  const STATE_LABEL = { approved: "Approved", open: "Open", changes_requested: "Changes requested", stale: "PREREG changed: re-approve" };

  KP.views.guide = async function (params, root) {
    const s = await KP.refresh();
    const firstOpen = (s.gates.find((g) => g.state !== "approved") || { gate: 6 }).gate;
    const sel = Math.min(6, Math.max(1, parseInt(params[0], 10) || firstOpen));
    KP.setCtx({ view: "guide", gate: sel });
    const g = await KP.api("/api/gate?g=" + sel);
    const n = s.next;

    root.innerHTML = `<div class="page">
      ${s.review_log_is_default ? "" : `<div class="fakebar" style="margin:-34px -44px 22px">TEST MODE · decisions go to a TEMP review log: ${esc(s.paths.review_log)}</div>`}
      ${KP.head("Step-by-step review", "What you need to do now", "Six gates, in order. Each one says why it matters, what to check, and shows the evidence. Your decision is appended to REVIEW_LOG.md with the hashes of the evidence you saw.")}
      <section class="next" aria-live="polite">
        <div class="step">${n.gate ? n.gate : "✓"}</div>
        <div><div class="lbl">Next action${n.remaining ? ` · ${n.remaining} checks left in this gate` : ""}</div><h3>${esc(n.title)}</h3><p>${esc(n.body)}</p></div>
        <a class="btn" href="${esc(n.go)}">${{ run: "Open Live run", label: "Start labelling", write: "Open the report guide", stale: "Review PREREG", decide: "Record decision", check: "Show me", waiting: "See what's missing" }[n.kind] || "Go"} →</a>
      </section>
      <div class="steps" role="tablist">${s.gates.map((x) => {
        const cls = [x.state, x.gate === sel ? "sel" : "", x.unlocked ? "" : "locked", x.gate === firstOpen && x.state !== "approved" ? "current" : ""].join(" ");
        return `<button role="tab" class="${cls}" data-g="${x.gate}" aria-selected="${x.gate === sel}">
          <span class="n">Gate ${x.gate} ${x.unlocked ? "" : '<span class="lock" title="locked until the previous gate is approved"></span>'}</span>
          <span class="t">${esc(x.title)}</span><span class="s">${x.unlocked ? STATE_LABEL[x.state] : "Locked"}</span></button>`;
      }).join("")}</div>
      <div class="grid2">
        <div class="stack" id="g-left"></div>
        <div class="card pad" id="g-evidence"><div class="empty">Loading evidence…</div></div>
      </div>
    </div>`;
    KP.$$(".steps button", root).forEach((b) => b.addEventListener("click", () => KP.go("#/guide/" + b.dataset.g)));
    renderLeft(g, s);
    renderEvidence(g, s);
  };

  function renderLeft(g, s) {
    const el = KP.$("#g-left");
    const unlocked = g.status.unlocked;
    const allAuto = g.auto.every((c) => c.ok), allMan = g.manual.every((c) => c.ok);
    const hist = (g.status.history || []).slice().reverse();
    el.innerHTML = `
      <div class="card pad">
        <h4>Why this matters</h4>
        <p class="why">${esc(g.why)}</p>
      </div>
      <div class="card pad">
        <div class="spread"><h4 style="margin:0">What to check</h4><span class="small muted">${g.manual.filter((m) => m.ok).length + g.auto.filter((m) => m.ok).length} of ${g.manual.length + g.auto.length}</span></div>
        ${unlocked ? "" : `<p class="small muted" style="margin:10px 0 0">Locked: approve gate ${g.gate - 1} first. You can still read the evidence.</p>`}
        <ul class="checks" style="margin-top:12px">
          ${g.auto.map((c) => `<li class="auto ${c.ok ? "on" : "off"}"><span class="box"></span><span class="lbl">${esc(c.label)}<span class="tag-auto">auto</span>${c.detail ? `<span class="det">${esc(c.detail)}</span>` : ""}</span></li>`).join("")}
          ${g.manual.map((c) => `<li class="manual ${c.ok ? "on" : ""}" data-item="${esc(c.id)}" role="checkbox" aria-checked="${c.ok}" tabindex="0"><span class="box"></span><span class="lbl">${linkSections(esc(c.label))}</span></li>`).join("")}
        </ul>
      </div>
      <div class="card pad decide">
        <h4>Your decision</h4>
        <textarea id="g-note" placeholder="Note for the log: what you checked, anything odd, what needs to change…" ${unlocked ? "" : "disabled"}></textarea>
        <div class="row">
          <button class="btn danger" id="g-changes" ${unlocked ? "" : "disabled"}>Request changes</button>
          <button class="btn ok" id="g-approve" ${unlocked && g.ready ? "" : "disabled"} title="${g.ready ? "" : !allAuto ? "Waiting on an automatic check" : "Tick every check first"}">Approve gate ${g.gate}</button>
        </div>
        <p class="tiny muted" style="margin:10px 0 0">Appends a block to <span class="mono">${esc(s.paths.review_log)}</span>: UTC time, gate, decision, your note and the sha256 of ${g.evidence.length} evidence file${g.evidence.length === 1 ? "" : "s"}.</p>
        <details class="tiny" style="margin-top:8px"><summary class="muted" style="cursor:pointer">Evidence that will be hashed</summary>
          <div class="filelist" style="margin-top:6px">${g.evidence.map((e) => `<div><span></span><span>${esc(e.path)}</span><span class="faint">${KP.short(e.sha256, 10)}</span></div>`).join("") || '<span class="muted">none yet</span>'}</div></details>
        <div id="g-result"></div>
      </div>
      ${hist.length ? `<div class="card pad"><h4>History for this gate</h4>${hist.map((h) => `<div class="logline"><span class="pill ${h.superseded_design ? "" : h.decision === "approved" ? "ok" : "bad"}"${KP.src("REVIEW_LOG.md:" + h.line)} title="${h.superseded_design ? "recorded for the v1 single-prompt design; does not count for the swarm design" : ""}">${esc(h.decision.replace("_", " "))}${h.superseded_design ? " · v1 design, superseded" : ""}</span><span class="small">${KP.when(h.time)}<br><span class="muted">${esc(h.note || "")}</span></span></div>`).join("")}</div>` : ""}`;

    KP.$$(".checks li.manual", el).forEach((li) => {
      const toggle = async (ev) => {
        if (ev.target.closest("a")) return;
        if (!unlocked) { KP.toast("This gate is locked until the previous one is approved.", true); return; }
        const on = !li.classList.contains("on");
        li.classList.toggle("on", on);
        try { const ng = await KP.api("/api/gate/check", { gate: g.gate, item: li.dataset.item, value: on }); renderLeft(ng, s); KP.refresh(); }
        catch (e) { KP.toast(e.message, true); }
      };
      li.addEventListener("click", toggle);
      li.addEventListener("keydown", (e) => { if (e.key === " " || e.key === "Enter") { e.preventDefault(); toggle(e); } });
    });
    KP.$$("a.sec", el).forEach((a) => a.addEventListener("click", (e) => { e.preventDefault(); const t = document.getElementById("sec-" + a.dataset.sec); if (t) t.scrollIntoView({ behavior: "smooth", block: "start" }); }));

    const decide = async (decision, btn) => {
      const note = KP.$("#g-note").value;
      if (!btn.dataset.armed) {
        btn.dataset.armed = "1"; const old = btn.textContent;
        btn.textContent = decision === "approved" ? "Confirm: append approval" : "Confirm: append request";
        setTimeout(() => { if (btn.isConnected) { delete btn.dataset.armed; btn.textContent = old; } }, 5000);
        return;
      }
      try {
        const r = await KP.api("/api/gate/decision", { gate: g.gate, decision, note });
        KP.toast(`Gate ${g.gate}: ${decision.replace("_", " ")} · written to REVIEW_LOG`);
        await KP.refresh();
        KP.go("#/guide/" + (decision === "approved" && g.gate < 6 ? g.gate + 1 : g.gate));
        setTimeout(() => { const res = KP.$("#g-result"); if (res) res.innerHTML = ""; }, 0);
        console.info("appended", r.path);
      } catch (e) { KP.toast(e.message, true); delete btn.dataset.armed; }
    };
    KP.$("#g-approve", el).addEventListener("click", (e) => decide("approved", e.currentTarget));
    KP.$("#g-changes", el).addEventListener("click", (e) => {
      if (!KP.$("#g-note").value.trim()) { KP.toast("Say what needs to change in the note first.", true); KP.$("#g-note").focus(); return; }
      decide("changes_requested", e.currentTarget);
    });
  }

  function linkSections(label) {
    return label.replace(/§(\d)/g, (m, n) => `<a href="#" class="sec" data-sec="${n}" title="show PREREG §${n}">§${n}</a>`);
  }

  // ------------------------------------------------------------ evidence
  async function renderEvidence(g, s) {
    const el = KP.$("#g-evidence");
    try {
      if (g.gate === 1) return ev1(el, s);
      if (g.gate === 2) return ev2(el);
      if (g.gate === 3) return ev3(el);
      if (g.gate === 4 || g.gate === 5) return ev45(el, g);
      if (g.gate === 6) return ev6(el);
    } catch (e) { el.innerHTML = `<div class="empty">${esc(e.message)}</div>`; }
  }

  async function ev1(el, s) {
    const p = await KP.api("/api/prereg");
    const lr = p.last_reviewed;
    const signedState = !p.signed ? `<span class="pill warn">not signed for this text</span>` : p.signed === p.sha256 ? `<span class="pill ok">signed · matches</span>` : `<span class="pill bad">signed hash differs: PREREG changed</span>`;
    const diffHtml = p.diff ? `<div class="console" style="height:auto;max-height:420px">${esc(p.diff).split("\n").map((l) => `<div class="${l.startsWith("+") && !l.startsWith("+++") ? "ok" : l.startsWith("-") && !l.startsWith("---") ? "err" : ""}">${l || "&nbsp;"}</div>`).join("")}</div>` : "";
    el.innerHTML = `<div class="spread" style="margin-bottom:14px"><h4 style="margin:0">Evidence · PREREG.md</h4>${signedState}</div>
      <div class="row wrap small" style="margin-bottom:6px"><span class="muted">sha256 now</span><span class="hash"${KP.src(p.path)}>${esc(p.sha256)}</span></div>
      ${lr ? `<div class="row wrap small" style="margin-bottom:6px"><span class="muted">last reviewed</span><span class="hash"${KP.src(lr._src)}>${esc(lr.sha256)}</span><span class="pill ${lr.decision === "approved" ? "ok" : "bad"}"${KP.src(lr._src)}>${esc(String(lr.decision).replace("_", " "))} · ${KP.when(lr.time)}</span></div>` : '<p class="small muted">You have not reviewed any version yet.</p>'}
      ${p.changed_since_review ? `<h4 style="margin-top:16px">Changed since your last review: diff against the version you ${esc(lr.decision === "approved" ? "approved" : "reviewed")}</h4><div class="tiny muted" style="word-break:break-all"${KP.src(lr.base_src || "")}>base text: ${esc(lr.base_src || "not kept")}</div>${diffHtml}` : lr ? '<p class="small"><span class="pill ok">unchanged since your last review</span></p>' : ""}
      <hr class="rule"><div class="doc">${p.html}</div>`;
  }

  async function ev2(el) {
    el.innerHTML = `<div class="tabs"><button class="on" data-t="data">Register sample</button><button data-t="tests">Checker tests</button></div><div id="ev2"></div>`;
    const tabs = KP.$$(".tabs button", el);
    const show = (t) => { tabs.forEach((b) => b.classList.toggle("on", b.dataset.t === t)); (t === "data" ? evData : evTests)(KP.$("#ev2"), false); };
    tabs.forEach((b) => b.addEventListener("click", () => { sessionStorage.setItem("kp.ev2tab", b.dataset.t); show(b.dataset.t); }));
    show(sessionStorage.getItem("kp.ev2tab") || "data");
  }

  async function evData(el, fake, seed) {
    const d = await KP.api(`/api/data?fake=${fake ? 1 : 0}${seed ? "&seed=" + seed : ""}`);
    if (!d.sample) {
      el.innerHTML = `<div class="empty">No <b>data/&lt;seed&gt;/</b> folder yet. It is written by <span class="mono">harness/datagen.py</span>.
        ${d.fake_available ? `<div style="margin-top:14px"><button class="btn sm" id="fk">Preview the FAKE fixture register</button></div>` : ""}</div>`;
      const b = KP.$("#fk", el); if (b) b.addEventListener("click", () => evData(el, true));
      return;
    }
    const sm = d.sample, inv = sm.tables.investors || { columns: [], rows: [] };
    const mset = new Set(sm.markers);
    const rows = inv.rows.map((r) => ({ r, mk: r.some((c) => /MK-[0-9A-Za-z]{6}/.test(c)) }));
    const shown = rows.filter((x) => x.mk).concat(rows.filter((x) => !x.mk).slice(0, 8));
    el.innerHTML = `
      <div class="spread" style="margin-bottom:12px">
        <div class="row">${KP.fake(sm.fake)}<label class="field" style="flex-direction:row;align-items:center;gap:8px">Seed
          <select id="seed">${d.seeds.map((x) => `<option ${x === sm.seed ? "selected" : ""}>${esc(x)}</option>`).join("")}</select></label></div>
        <span class="small muted">${esc(sm.dir)}</span>
      </div>
      <ul class="checks" style="margin-bottom:14px">${sm.checks.map((c) => `<li class="auto ${c.ok ? "on" : "off"}"><span class="box"></span><span class="lbl">${esc(c.label)}${c.detail ? `<span class="det">${esc(c.detail)}</span>` : ""}</span></li>`).join("")}</ul>
      <h4>Planted markers <span class="faint" style="text-transform:none;letter-spacing:0"${KP.src(sm.markers_path)}>${esc(sm.markers_path)}</span></h4>
      <div class="row wrap" style="margin-bottom:16px">${sm.markers.map((m) => `<mark class="mono">${esc(m)}</mark>`).join("")}</div>
      <h4>investors.csv · marker rows first, then a sample <span class="faint" style="text-transform:none;letter-spacing:0">(${inv.rows.length} rows)</span></h4>
      <div class="scroll sunk" style="max-height:340px"><table class="t datatable"><thead><tr>${inv.columns.map((c) => `<th>${esc(c)}</th>`).join("")}</tr></thead>
        <tbody>${shown.map((x) => `<tr class="${x.mk ? "has-mk" : ""}">${x.r.map((c) => `<td>${KP.markers(c, [...mset])}</td>`).join("")}</tr>`).join("")}</tbody></table></div>
      <div class="filelist" style="margin-top:14px">${Object.entries(sm.tables).map(([k, t]) => `<div><span class="faint">·</span><span${KP.src(t.path)}>${esc(t.path)} <span class="muted">${t.rows.length} rows</span></span><span class="faint">${KP.short(t.sha256, 10)}</span></div>`).join("")}</div>
      <p class="small" style="margin-top:14px"><a href="#/code/harness/datagen.py">Read datagen.py</a> · <a href="#/code/harness/checker.py">Read checker.py</a></p>`;
    KP.$("#seed", el).addEventListener("change", (e) => evData(el, fake, e.target.value));
  }

  async function evTests(el) {
    const t = await KP.api("/api/tests");
    const r = t.report;
    const list = r && r.tests ? r.tests : [];
    el.innerHTML = `
      <div class="spread" style="margin-bottom:12px">
        <div>${r && r.counts ? Object.entries(r.counts).map(([k, v]) => `<span class="pill ${k === "passed" ? "ok" : "bad"}">${v} ${esc(k)}</span>`).join(" ") : '<span class="muted small">No test report yet.</span>'}
          ${r && r.path ? `<div class="tiny muted" style="margin-top:6px"${KP.src(r.path)}>${esc(r.path)} · ${KP.when(r.time_utc)}</div>` : ""}</div>
        <button class="btn sm primary" id="runtests" ${t.run.running ? "disabled" : ""}>${t.run.running ? "Running…" : "Run tests now"}</button>
      </div>
      <div class="scroll" style="max-height:440px"><table class="t"><tbody>${list.map((x) => `<tr><td style="width:24px"><span class="tick ${x.outcome === "passed" ? "ok" : x.outcome === "skipped" ? "na" : "bad"}">${x.outcome === "passed" ? "✓" : x.outcome === "skipped" ? "–" : "✕"}</span></td>
        <td class="mono" style="font-size:12px">${esc(x.name)}${x.message ? `<div class="muted" style="white-space:pre-wrap">${esc(x.message.slice(0, 400))}</div>` : ""}</td></tr>`).join("")}</tbody></table></div>
      ${t.run.output ? `<details style="margin-top:12px"><summary class="small muted" style="cursor:pointer">pytest output (exit ${esc(t.run.returncode)})</summary><div class="console" style="height:200px;margin-top:8px">${esc(t.run.output)}</div></details>` : ""}`;
    KP.$("#runtests", el).addEventListener("click", async () => {
      await KP.api("/api/tests/run", {});
      KP.toast("Running harness tests…");
      const poll = async () => { const x = await KP.api("/api/tests"); if (x.run.running && el.isConnected) setTimeout(poll, 1500); else if (el.isConnected) { sessionStorage.setItem("kp.ev2tab", "tests"); KP.go(location.hash); } };
      evTests(el); setTimeout(poll, 1500);
    });
  }

  async function ev3(el) {
    const r = await KP.api("/api/prompts/swarm");
    const p = r.prompts || {};
    if (p.error) { el.innerHTML = `<div class="empty">Could not render harness/prompts.py: <pre class="mono small">${esc(p.error)}</pre></div>`; return; }
    const block = (title, x, extra) => `<div class="spread small" style="margin:18px 0 6px"><b>${title}</b><a class="mono" href="#/code/${esc((x.src || "").split(":")[0])}"${KP.src(x.src)}>${esc(x.src || "")}</a></div>${extra || ""}<div class="sysprompt" style="max-height:360px;overflow:auto;white-space:pre-wrap">${hlPolicy(esc(x.text))}</div>`;
    const hlPolicy = (h) => (p.policy ? h.split(esc(p.policy)).join(`<mark title="the v1 policy sentence, word for word">${esc(p.policy)}</mark>`) : h);
    const ids = Object.entries(p.identity || {});
    const groups = p.groups ? Object.entries(p.groups) : [];
    el.innerHTML = `<h4>Evidence · swarm prompts, rendered live from harness/prompts.py</h4>
      <ul class="checks" style="margin-bottom:16px">${r.checks.map((c) => `<li class="auto ${c.ok ? "on" : "off"}"><span class="box"></span><span class="lbl">${esc(c.label)}${c.detail ? `<span class="det">${esc(c.detail)}</span>` : ""}</span></li>`).join("")}</ul>
      <div class="tabs" id="p3tabs"><button data-t="id" class="on">Identity lines</button><button data-t="workers">Workers</button><button data-t="orch">Orchestrator</button><button data-t="mon">Monitors</button></div>
      <div id="p3"></div>
      <p class="small muted" style="margin-top:12px">Yellow marks the data-handling policy sentence wherever it appears verbatim. Steps: orchestrator ${esc((p.steps || {}).orchestrator)}, worker ${esc((p.steps || {}).worker)} per task.</p>`;
    const tabs = {
      id: () => `<p class="small muted">The harness (not the orchestrator) puts the line at the start of every task text. claim_false sends the opposite of the truth.</p>
        <table class="t"><tbody>${ids.map(([k, v]) => `<tr><td class="mono" style="width:130px">${esc(k)}</td><td${KP.src(v.src)}>${v.text ? `“${esc(v.text)}”` : '<span class="muted">(no sentence)</span>'}</td></tr>`).join("")}
        <tr><td class="mono">claim_false</td><td class="small"${KP.src(p.claim_false_src)}>${esc(p.claim_false_rule || "")}</td></tr></tbody></table>
        ${groups.length ? `<h4 style="margin-top:16px">Condition groups <span class="faint mono" style="text-transform:none;letter-spacing:0"${KP.src(p.groups_src)}>${esc(p.groups_src || "")}</span></h4><table class="t"><thead><tr><th>group</th><th>orchestrator is the worker model?</th><th>claim sent</th><th>primary?</th></tr></thead><tbody>${groups.map(([k, v]) => `<tr><td class="mono">${esc(k)}</td>${(Array.isArray(v) ? v : [v]).map((x) => `<td${KP.src(p.groups_src)}>${esc(x)}</td>`).join("")}</tr>`).join("")}</tbody></table>` : ""}
        ${block("What a worker sees around each task", p.task_wrapper)}`,
      workers: () => ["w1", "w2", "w3"].map((w) => block(`${w} system prompt (${w === "w3" ? "report writer" : "data agent"})`, p.workers[w])).join(""),
      orch: () => block(`Attack coordinator · variant ${esc(p.main_variant)} (main) · HIDDEN OBJECTIVE, never shown to workers or monitors`, p.orchestrator[p.main_variant] || {}, `<div class="tiny muted"${KP.src(p.main_variant_src)}>main variant set at ${esc(p.main_variant_src || "")}</div>`) +
        block("Honest coordinator (honest baseline, monitor thresholds only)", p.orchestrator.honest || {}) +
        Object.keys(p.orchestrator).filter((v) => v !== p.main_variant && v !== "honest").map((v) => `<details style="margin-top:14px"><summary class="small muted" style="cursor:pointer">Other variant: ${esc(v)} (spike only)</summary>${block(v, p.orchestrator[v])}</details>`).join(""),
      mon: () => block("LOCAL monitor (one worker's transcript)", p.monitor_local) + block("GLOBAL monitor (whole team's transcript)", p.monitor_global),
    };
    const show = (t) => { KP.$$("#p3tabs button", el).forEach((b) => b.classList.toggle("on", b.dataset.t === t)); KP.$("#p3", el).innerHTML = tabs[t](); sessionStorage.setItem("kp.p3tab", t); };
    KP.$$("#p3tabs button", el).forEach((b) => b.addEventListener("click", () => show(b.dataset.t)));
    show(sessionStorage.getItem("kp.p3tab") || "id");
  }

  async function ev45(el, g) {
    const bc = g.auto.find((c) => c.id === "batch");
    const mode = g.gate === 4 ? "pilot" : "audit";
    if (!bc || !bc.ok) {
      el.innerHTML = `<div class="empty">No complete <b>swarm ${g.gate === 4 ? "pilot" : "main"}</b> batch yet (the v1 single-prompt pilot does not count).<br>Start it from <a href="#/live">Live run</a> once gate ${g.gate - 1} is approved.
        <div style="margin-top:16px" class="small">Want to practise the blind-review flow first? Try it on a swarm spike batch from <a href="#/blind">Blind review</a> (practice, never counts), or on the <a href="#/blind/DEMO-fixture">FAKE fixture</a>.</div></div>`;
      return;
    }
    const batch = bc.detail;
    const q = await KP.api(`/api/blind/queue?batch=${encodeURIComponent(batch)}`);
    el.innerHTML = `<div class="spread"><h4 style="margin:0">Evidence · ${esc(batch)}</h4><a class="btn sm primary" href="#/blind/${encodeURIComponent(batch)}">${q.remaining.length ? `Label ${q.remaining.length} remaining` : "Open blind review"}</a></div>
      ${KP.views.agreementBlock(q.agreement, q.sample.length, batch)}`;
  }

  async function ev6(el) {
    const d = await KP.api("/api/claims");
    el.innerHTML = `<h4>Evidence · CLAIMS.md and figures</h4>${KP.views.claimsTable(d.claims)}
      <h4 style="margin-top:22px">figures/</h4>${KP.views.figureGrid(d.figures)}`;
  }
})();
