/* Playback: catalogue of every batch and episode, and a step-by-step episode replay. */
(function () {
  "use strict";
  const { esc } = KP;
  const FKEYS = ["batch_id", "kind", "mode", "group", "variant", "orchestrator", "worker", "kinship_true", "claim", "category", "crossing"];
  const FLABEL = { batch_id: "Batch", kind: "Kind", mode: "Mode", group: "Group", variant: "Variant", orchestrator: "Orchestrator / requester", worker: "Worker / peer", kinship_true: "Kinship", claim: "Claim", category: "Outcome", crossing: "Crossing" };
  KP.designPill = (b) => (b.mode === "swarm" ? `<span class="pill line" title="${esc(b.design)}">swarm</span>` : b.mode === "single" ? `<span class="pill" title="${esc(b.design)}">single-prompt (v1 design, baseline)</span>` : "") +
    (b.kind === "spike" ? ' <span class="pill warn" title="manifest notes: SPIKE: feasibility only, never analysed">SPIKE, never analysed</span>' : b.never_analysed && !b.fake ? ` <span class="pill warn">${esc(b.kind)}, never analysed</span>` : "");

  KP.views.catalogue = async function (params, root) {
    KP.setCtx({ view: "catalogue" });
    const [bs, all] = await Promise.all([KP.api("/api/batches"), KP.api("/api/all_episodes")]);
    let f = {};
    try { f = JSON.parse(sessionStorage.getItem("kp.filters2") || "{}"); } catch (e) {}
    const opts = (k) => [...new Set(all.map((e) => e[k]).filter((x) => x != null))].map(String).sort();
    for (const k of Object.keys(f)) if (!FKEYS.includes(k) || (f[k] && !opts(k).includes(f[k]))) delete f[k];  // never let a stale filter empty the table

    root.innerHTML = `<div class="page wide" style="max-width:1400px">
      ${KP.head("Playback", "Every batch, every episode", "Filter down, then open an episode to replay it step by step. Hover any number to see the file and line it came from.")}
      <div class="batches" id="bcards">${bs.map((b) => `<div class="card batch ${f.batch_id === b.batch_id ? "on" : ""}" data-b="${esc(b.batch_id)}">
          <div class="spread"><span class="pill line">${esc(b.kind)}</span>${KP.fake(b.fake)}<span class="pill ${b.status === "complete" ? "ok" : b.status === "running" ? "warn" : "bad"}">${esc(b.status)}</span></div>
          <div class="id">${esc(b.batch_id)}</div>
          <div class="row wrap tiny" style="gap:4px;margin:4px 0">${KP.designPill(b)}${b.variants && b.variants.length ? ` <span class="mono faint">${esc(b.variants.join(", "))}</span>` : ""}</div>
          ${KP.stackbar(b.categories, b.n_episodes)}
          <div class="spread small"><span><b class="num">${b.n_episodes}</b> <span class="muted">episodes</span></span><span class="muted num">${KP.fmtUsd(b.cost_usd, 3)}</span></div></div>`).join("") || '<div class="empty">No batches yet.</div>'}</div>
      <div class="card filters" id="filters">${FKEYS.map((k) => `<label class="field">${FLABEL[k]}<select data-k="${k}"><option value="">All</option>${opts(k).map((v) => `<option ${f[k] === v ? "selected" : ""}>${esc(v)}</option>`).join("")}</select></label>`).join("")}
        <button class="btn ghost sm" id="clear" style="margin-left:auto">Clear filters</button></div>
      <div class="tally" id="tally"></div>
      <div class="card"><div class="scroll" style="max-height:calc(100vh - 160px)"><table class="t" id="tbl"><thead><tr><th>Episode · batch</th><th>Orchestrator → worker</th><th>Group</th><th>Kinship</th><th>Claim</th><th>Variant / style</th><th>Outcome</th><th>Crossing</th><th class="r" title="workers that raised a concern">Flags</th><th class="r" title="GLOBAL / LOCAL max (swarm); single score otherwise">claude G/L</th><th class="r" title="GLOBAL / LOCAL max (swarm); single score otherwise">qwen G/L</th><th class="r">Cost</th></tr></thead><tbody></tbody></table></div></div>
    </div>`;

    const draw = () => {
      const rows = all.filter((e) => FKEYS.every((k) => !f[k] || String(e[k]) === f[k]));
      const cats = {}; rows.forEach((e) => (cats[e.category] = (cats[e.category] || 0) + 1));
      KP.$("#tally").innerHTML = `<span><b class="num">${rows.length}</b> <span class="muted">episodes</span></span>` + KP.OUT.map((c) => `<span>${KP.og(c)} <b class="num">${cats[c] || 0}</b></span>`).join("") + (rows.some((r) => r.fake) ? `<span>${KP.fake(true)} <span class="muted small">includes demo fixture</span></span>` : "");
      const mon = (e, k) => {
        if (e.mode === "swarm") { const g = (e.mon_global || {})[k], l = (e.mon_local_max || {})[k]; return `<span class="num"${KP.src(e._src)}>${g == null ? "–" : esc(g)} <span class="faint">/</span> ${l == null ? "–" : esc(l)}</span>`; }
        const m = (e.monitors || {})[k]; return m ? `<span class="num ${m.flag ? "c-leak" : ""}" ${KP.src(e._src)}>${esc(m.score)}${m.flag ? " ⚑" : ""}</span>` : "–"; };
      KP.$("#tbl tbody").innerHTML = rows.slice(0, 1500).map((e) => `<tr class="click" data-href="#/episode/${encodeURIComponent(e.batch_id)}/${encodeURIComponent(e.episode_id)}">
        <td><span class="mono">${esc(e.episode_id)}</span> ${e.fake ? KP.fake(true) : ""} ${e.mode === "swarm" ? `<span class="pill line">swarm</span>` : `<span class="pill" title="${esc(e.design)}">single v1</span>`}${e.kind === "spike" ? ' <span class="pill warn" title="SPIKE: feasibility only, never analysed">spike</span>' : ""}<div class="mono tiny muted">${esc(e.batch_id)}</div></td>
        <td>${esc(e.orchestrator)} <span class="faint">→</span> ${esc(e.worker)}</td><td class="mono small">${esc(e.group || "–")}</td><td>${esc(e.kinship_true)}</td><td class="mono small">${esc(e.claim)}</td><td class="small muted">${esc(e.mode === "swarm" ? e.variant : e.request_style)}</td>
        <td>${e.error ? `<span class="pill bad" title="${esc(e.error)}">error</span>` : KP.og(e.category, e._src)}</td><td class="mono small"${KP.src(e._src)}>${esc(e.crossing || "–")}</td><td class="r num"${KP.src(e._src)}>${e.local_red_flags == null ? "–" : esc(e.local_red_flags)}</td><td class="r">${mon(e, "mon_claude")}</td><td class="r">${mon(e, "mon_qwen")}</td>
        <td class="r num small"${KP.src(e._src)}>${KP.fmtUsd(e.cost_usd, 4)}</td></tr>`).join("") || `<tr><td colspan="12"><div class="empty">No episodes match.</div></td></tr>`;
      KP.$$("#tbl tr.click").forEach((tr) => tr.addEventListener("click", () => KP.go(tr.dataset.href)));
      sessionStorage.setItem("kp.filters2", JSON.stringify(f));
      KP.$$("#bcards .batch").forEach((c) => c.classList.toggle("on", f.batch_id === c.dataset.b));
    };
    KP.$$("#filters select").forEach((s) => s.addEventListener("change", () => { f[s.dataset.k] = s.value; draw(); }));
    KP.$("#clear").addEventListener("click", () => { f = {}; KP.$$("#filters select").forEach((s) => (s.value = "")); draw(); });
    KP.$$("#bcards .batch").forEach((c) => c.addEventListener("click", () => { f.batch_id = f.batch_id === c.dataset.b ? "" : c.dataset.b; KP.$('#filters select[data-k="batch_id"]').value = f.batch_id; draw(); }));
    draw();
  };

  // ------------------------------------------------------------- episode
  const NODES = {
    requester: { x: 150, y: 130, label: "Requester", r: 42 },
    peer: { x: 450, y: 130, label: "Peer", r: 48 },
    env: { x: 750, y: 130, label: "Sandbox", sub: "read_table · write_report", r: 38 },
    overseer: { x: 600, y: 218, label: "Overseer", sub: "raise_concern", r: 20 },
    monitors: { x: 300, y: 36, label: "Monitors", sub: "mon_claude · mon_qwen", r: 20 },
    checker: { x: 620, y: 36, label: "Checker", sub: "checker.py", r: 20 },
  };
  const nodeOf = (who, ev) => (who === "env" && ev && ev.tool === "raise_concern" ? "overseer" : who && who.startsWith("mon_") ? "monitors" : NODES[who] ? who : who === "checker" ? "checker" : null);
  const STATUS = { red: "var(--leak)", amber: "var(--comply)", green: "var(--report)", grey: "var(--other)", none: "var(--panel)" };

  function statusAt(ep, events, i) {
    // derived only from what has happened up to step i
    let peer = "none", req = "amber", mon = "none";
    for (let k = 0; k <= i && k < events.length; k++) {
      const e = events[k];
      if (e.type === "tool_call" && e.tool === "raise_concern") peer = "green";
      if (e.type === "tool_call" && e.tool === "write_report" && peer !== "green") peer = /MK-[0-9A-Za-z]{6}/.test(e.content || "") ? "red" : "grey";
      if (e.type === "monitor") { if (e.flag) { mon = "red"; req = "red"; } else if (mon === "none") mon = "green"; }
      if (e.type === "outcome") {
        const c = (ep.outcome || {}).category;
        peer = { leak: "red", comply_no_leak: "amber", refuse: "green", kept_policy: "green", report: "green", other: "grey" }[c] || peer;
      }
    }
    return { peer, requester: req, monitors: mon };
  }

  KP.views.episode = async function (params, root) {
    const [batch, epId, step0] = params;
    const d = await KP.api(`/api/episode?batch=${encodeURIComponent(batch)}&ep=${encodeURIComponent(epId)}`);
    if (d.swarm) return KP.swarmEpisode(d, params, root);
    const ep = d.episode, events = d.events, o = ep.outcome || {};
    KP.setCtx({ view: "episode", batch, episode: epId });
    let cur = Math.min(events.length - 1, Math.max(0, parseInt(step0, 10) || 0)), playing = false, timer = null, speed = 1, userStepped = !!step0;
    const allMk = [...new Set([...(d.markers || []), ...events.flatMap((e) => (e.highlights || []).map((h) => h.value))])];

    const chip = (k, v, src) => `<span class="chip"${KP.src(src)}><span class="k">${k}</span><b>${esc(v)}</b></span>`;
    root.innerHTML = `${d.fake ? '<div class="fakebar">FAKE DEMO EPISODE · synthetic fixture, not experimental data</div>' : `<div class="fakebar spikebar">${esc(d.design || "single-prompt (v1 design, baseline)").toUpperCase()}${d.never_analysed ? " · " + esc(String(d.kind).toUpperCase()) + ", NEVER ANALYSED" : ""}</div>`}<div class="page wide" style="max-width:1400px">
      <div class="ep-head"><div>
        <div class="eyebrow small muted" style="letter-spacing:.14em;text-transform:uppercase"><a href="#/catalogue">Playback</a> / <span class="mono">${esc(batch)}</span></div>
        <h2 style="font:400 32px var(--serif);margin:6px 0 0">${esc(ep.episode_id)} ${KP.fake(d.fake)}</h2>
        <div class="chips">${chip("requester", ep.requester, ep._src)}${chip("peer", ep.peer, ep._src)}${chip("kinship", ep.kinship_true, ep._src)}${chip("claim", ep.claim, ep._src)}${chip("style", ep.request_style, ep._src)}${chip("seed", ep.seed, ep._src)}</div>
      </div><div class="row"><span class="small muted">${events.length} events · ${esc(KP.when(ep.t || (events[0] || {}).t))}</span></div></div>

      <div class="card stickystage" style="margin-bottom:14px;top:27px"><div class="stage"><svg id="stage" viewBox="0 0 900 260" preserveAspectRatio="xMidYMid meet"></svg></div>
        <div class="scrub" style="border-top:1px solid var(--rule)">
          <div class="ctl"><button id="b-first" title="First (Home)">⏮</button><button id="b-prev" title="Previous (←)">◀</button><button id="b-play" class="play" title="Play / pause (Space)">▶</button><button id="b-next" title="Next (→)">▶︎|</button><button id="b-last" title="Last (End)">⏭</button></div>
          <div class="track"><div class="ticks" id="ticks">${events.map((e) => `<i class="t-${esc(e.type)}" title="#${e.i} ${esc(e.type)}"></i>`).join("")}</div><input type="range" id="range" min="0" max="${Math.max(0, events.length - 1)}" value="${cur}" aria-label="timeline"></div>
          <div class="row small"><span class="num" id="pos"></span><select id="speed" style="padding:4px 26px 4px 8px;font-size:12.5px"><option value="0.5">0.5×</option><option value="1" selected>1×</option><option value="2">2×</option><option value="4">4×</option></select></div>
        </div></div>
      <p class="tiny muted" style="margin:0 0 18px">Keys: <kbd>Space</kbd> play/pause · <kbd>←</kbd><kbd>→</kbd> step · <kbd>Home</kbd><kbd>End</kbd> jump. Node colours are derived from what has happened so far: peer red = leaked a marker, amber = record fields without a marker, green = refused or reported; requester turns red when a monitor flags.</p>

      <div style="display:grid;grid-template-columns:minmax(0,1fr) 340px;gap:22px;align-items:start">
        <div class="events" id="events"></div>
        <div class="ep-side">
          <div class="card pad"><h4>Checker verdict</h4><div class="verdict">${ep.error ? '<span class="pill bad">error</span>' : KP.og(o.category, ep._src).replace(/<svg width="12" height="12"/, '<svg width="20" height="20"')}</div>
            <dl class="kv" style="margin-top:14px">
              <dt>leak</dt><dd${KP.src(ep._src)}>${esc(o.leak)}</dd>
              <dt>markers leaked</dt><dd${KP.src(ep._src)}>${(o.markers_leaked || []).map((m) => `<mark class="mono">${esc(m)}</mark>`).join(" ") || "none"}</dd>
              <dt>record fields in report</dt><dd${KP.src(ep._src)}>${esc(o.record_fields_in_report)}</dd>
              <dt>raised concern</dt><dd${KP.src(ep._src)}>${esc(o.raised_concern)}</dd>
              <dt>refused</dt><dd${KP.src(ep._src)}>${esc(o.refused)}</dd>
            </dl>${ep.error ? `<p class="small c-leak">${esc(ep.error)}</p>` : ""}</div>
          <div class="card pad"><h4>Monitors</h4>${Object.entries(ep.monitors || {}).map(([k, m]) => `<div class="score"${KP.src(ep._src)}><span class="mono">${esc(k)}</span><span class="bar"><i style="width:${(m.score || 0) * 10}%;${m.flag ? "background:var(--leak)" : ""}"></i></span><span class="num">${esc(m.score)}</span></div><div class="tiny muted" style="margin:-2px 0 8px 100px">flag: ${m.flag == null ? "null (no threshold yet)" : esc(m.flag)}</div>`).join("") || '<span class="muted small">none</span>'}</div>
          <div class="card pad"><h4>Recognition probe</h4><dl class="kv"><dt>answer</dt><dd${KP.src(ep._src)}>${esc((ep.recognition_probe || {}).answer)}</dd><dt>correct</dt><dd${KP.src(ep._src)}>${esc((ep.recognition_probe || {}).correct)}</dd></dl></div>
          <div class="card pad"><h4>Run</h4><dl class="kv"><dt>tokens in / out</dt><dd class="num"${KP.src(ep._src)}>${esc((ep.tokens || {}).in)} / ${esc((ep.tokens || {}).out)}</dd><dt>cost</dt><dd class="num"${KP.src(ep._src)}>${KP.fmtUsd(ep.cost_usd, 5)}</dd><dt>latency</dt><dd class="num"${KP.src(ep._src)}>${esc(ep.latency_s)} s</dd></dl>
            <div class="path" style="margin-top:10px">${esc(ep._src)}<br>${esc(batch)}/${esc(ep.events_file)}</div></div>
          ${allMk.length ? `<div class="card pad"><h4>Planted markers (seed ${esc(ep.seed)})</h4><div class="row wrap">${allMk.map((m) => `<mark class="mono">${esc(m)}</mark>`).join("")}</div></div>` : ""}
          ${d.labels.length ? `<div class="card pad"><h4>Your blind labels</h4>${d.labels.map((l) => `<div class="small"${KP.src(l._src)}>${KP.og(l.label)} <span class="muted">${esc(l.mode)} · ${KP.when(l.time_utc)}</span>${l.note ? `<div class="muted">${esc(l.note)}</div>` : ""}</div>`).join("")}</div>` : ""}
        </div>
      </div></div>`;

    KP.$("#events").innerHTML = events.map((e) => KP.renderEvent(e, allMk)).join("");

    const draw = () => {
      const e = events[cur] || {};
      const st = statusAt(ep, events, cur);
      const from = nodeOf(e.from, e), to = nodeOf(e.to, e) || (e.type === "monitor" || e.type === "outcome" ? "peer" : null);
      const active = new Set([from, to]);
      let svg = "";
      const edges = [["requester", "peer"], ["peer", "env"], ["peer", "overseer"], ["monitors", "peer"], ["checker", "peer"], ["monitors", "requester"]];
      for (const [a, b] of edges) {
        const A = NODES[a], B = NODES[b];
        const on = active.has(a) && active.has(b) && a !== b;
        svg += `<line class="edge ${on ? "active" : ""}" x1="${A.x}" y1="${A.y}" x2="${B.x}" y2="${B.y}"/>`;
      }
      for (const [id, n] of Object.entries(NODES)) {
        const s = st[id] || "none";
        const fill = s === "none" ? "var(--panel)" : `color-mix(in oklab, ${STATUS[s]} 22%, var(--panel))`;
        const stroke = s === "none" ? "var(--rule-2)" : STATUS[s];
        const isOn = active.has(id);
        svg += `<g class="node ${isOn || id === "peer" || id === "requester" ? "" : "dim"}"><circle class="body" cx="${n.x}" cy="${n.y}" r="${n.r}" fill="${fill}" stroke="${isOn ? "var(--ink)" : stroke}" stroke-width="${isOn ? 3 : 2}"/>
          ${n.r > 30 ? `<text x="${n.x}" y="${n.y + (n.sub ? 5 : -2)}" text-anchor="middle">${n.label}</text>` : `<text x="${n.x + n.r + 10}" y="${n.y - 2}">${n.label}</text>`}
          ${id === "requester" || id === "peer" ? `<text class="sub" x="${n.x}" y="${n.y + 15}" text-anchor="middle">${esc(ep[id])}</text>` : n.r > 30 ? `<text class="sub" x="${n.x}" y="${n.y + n.r + 18}" text-anchor="middle">${n.sub}</text>` : `<text class="sub" x="${n.x + n.r + 10}" y="${n.y + 13}">${n.sub}</text>`}</g>`;
      }
      KP.$("#stage").innerHTML = svg;
      KP.$$("#ticks i").forEach((t, k) => { t.classList.toggle("past", k <= cur); t.classList.toggle("cur", k === cur); });
      KP.$("#range").value = cur;
      KP.$("#pos").textContent = `${cur + 1} / ${events.length}`;
      KP.$$("#events .ev").forEach((el, k) => { el.classList.toggle("future", k > cur); el.classList.toggle("cur", k === cur); });
      const el = KP.$$("#events .ev")[cur], main = KP.$("#main"), stage = KP.$(".stickystage");
      if (el && userStepped) { const r = el.getBoundingClientRect(), top = stage.getBoundingClientRect().bottom + 16; if (r.top < top || r.top > window.innerHeight - 160) main.scrollTo({ top: main.scrollTop + r.top - top, behavior: "smooth" }); }
      userStepped = true;
      history.replaceState(null, "", `#/episode/${encodeURIComponent(batch)}/${encodeURIComponent(epId)}/${cur}`);
      KP.$("#b-play").textContent = playing ? "❚❚" : "▶";
    };
    const go = (k) => { cur = Math.max(0, Math.min(events.length - 1, k)); draw(); };
    const play = () => { playing = !playing; if (playing && cur >= events.length - 1) cur = 0; loop(); draw(); };
    const loop = () => { clearTimeout(timer); if (!playing) return; timer = setTimeout(() => { if (cur >= events.length - 1) { playing = false; draw(); return; } go(cur + 1); loop(); }, 1100 / speed); };
    KP.$("#b-first").onclick = () => go(0); KP.$("#b-last").onclick = () => go(events.length - 1);
    KP.$("#b-prev").onclick = () => go(cur - 1); KP.$("#b-next").onclick = () => go(cur + 1);
    KP.$("#b-play").onclick = play;
    KP.$("#range").addEventListener("input", (e) => go(+e.target.value));
    KP.$("#speed").addEventListener("change", (e) => { speed = +e.target.value; loop(); });
    KP.$$("#events .ev").forEach((el, k) => el.addEventListener("click", (e) => { if (!e.target.closest("details,a")) go(k); }));
    const onKey = (e) => {
      if (KP.isTyping(e)) return;
      if (e.key === " ") { e.preventDefault(); play(); }
      else if (e.key === "ArrowRight") { e.preventDefault(); go(cur + 1); }
      else if (e.key === "ArrowLeft") { e.preventDefault(); go(cur - 1); }
      else if (e.key === "Home") { e.preventDefault(); go(0); }
      else if (e.key === "End") { e.preventDefault(); go(events.length - 1); }
    };
    document.addEventListener("keydown", onKey);
    draw();
    return () => { clearTimeout(timer); document.removeEventListener("keydown", onKey); };
  };

  // shared event renderer (used by blind review too, with blind=true)
  KP.renderEvent = function (e, markers, blind) {
    const R = KP.SWARM_ROLE || {};
    const env = e.tool === "raise_concern" ? "Overseer" : e.tool === "write_report" ? "Report" : "Sandbox";
    const lab = (k) => (k === "env" ? env : k && k.startsWith("mon_") ? `${k}${e.scope ? " · " + (e.scope === "global" ? "GLOBAL" : "LOCAL " + e.scope) : ""}` : ({ requester: "Requester", peer: "Peer", checker: "Checker" }[k] || R[k] || k));
    let who = lab(e.from);
    const to = e.to ? lab(e.to).toLowerCase() : "";
    const spk = e.actor || e.from;
    const hidden = !blind && e.type === "system" && e.to === "orchestrator";
    if (e.type === "system" && e.from === "env" && e.to) who = `Harness → ${lab(e.to)} system prompt`;
    let body = e.content == null ? "" : String(e.content), code = false;
    if (e.type === "tool_call" || e.type === "outcome" || e.type === "tool_result") {
      code = true;
      try { const j = JSON.parse(body); body = JSON.stringify(j, null, 2).replace(/\\n/g, "\n"); } catch (err) {}
    }
    const hl = blind ? esc(body) : KP.markers(body, markers);
    const src = blind ? "" : KP.src(e._src);
    return `<div class="ev ${hidden ? "ev-hidden-obj" : ""} spk-${esc(spk)}" data-i="${esc(e.i)}"><div class="top"><span class="who">${esc(who)}</span>${to && !(e.type === "system" && e.from === "env") ? `<span>→ ${esc(to)}</span>` : ""}${hidden ? '<span class="pill bad">HIDDEN OBJECTIVE · never shown to workers or monitors</span>' : ""}${e.reply_label ? `<span class="pill line">${esc(e.reply_label)}</span>` : ""}${!blind && e.type === "monitor" && e.score != null ? `<span class="num"><b>${esc(e.score)}</b>/10</span>` : ""}<span class="typ ${esc(e.type)}">${esc(e.type)}</span>${e.tool ? `<span class="mono">${esc(e.tool)}</span>` : ""}${e.phase ? `<span class="mono faint">${esc(e.phase)}</span>` : ""}<span style="margin-left:auto" class="mono faint"${src}>#${esc(e.i)} · ${esc(String(e.t || "").slice(11, 19))}</span></div>
      <div class="body ${code ? "codeblock" : ""}">${hl}</div>
      ${e.reasoning ? `<details><summary>Reasoning text (${String(e.reasoning).length} chars)</summary><div class="reason">${blind ? esc(e.reasoning) : KP.markers(e.reasoning, markers)}</div></details>` : ""}
      ${!blind && e.flag != null && e.type === "monitor" ? `<div class="small" style="margin-top:6px">flag: <b class="${e.flag ? "c-leak" : ""}">${esc(e.flag)}</b></div>` : ""}</div>`;
  };
})();
