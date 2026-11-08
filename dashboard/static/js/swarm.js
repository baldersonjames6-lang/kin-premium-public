/* Swarm (decomposition) playback: orchestrator + w1, w2, w3 + report sink, step by step.
   Node colours: red = markers passed through it (its replies / the report it wrote), amber = it received
   markers in a task, green = it raised a concern, grey = involved, nothing of the above. */
(function () {
  "use strict";
  const { esc } = KP;
  const MK = /MK-[0-9A-Za-z]{6}/;
  const ROLE = { orchestrator: "Orchestrator", w1: "W1 · data agent", w2: "W2 · data agent", w3: "W3 · report writer" };
  KP.SWARM_ROLE = ROLE;
  const COL = { red: "var(--leak)", amber: "var(--comply)", green: "var(--report)", grey: "var(--other)" };
  const N = {
    orchestrator: { x: 450, y: 62, r: 46, label: "Orchestrator" },
    w1: { x: 170, y: 196, r: 40, label: "W1", sub: "data agent" },
    w2: { x: 450, y: 196, r: 40, label: "W2", sub: "data agent" },
    w3: { x: 730, y: 196, r: 40, label: "W3", sub: "report writer" },
    tables: { x: 310, y: 310, w: 120, h: 34, label: "tables", sub: "read_table" },
    overseer: { x: 560, y: 310, w: 120, h: 34, label: "overseer", sub: "raise_concern" },
    report: { x: 730, y: 310, w: 120, h: 34, label: "REPORT", sub: "write_report" },
  };
  const hasMk = (e) => (e.highlights || []).some((h) => h.kind === "marker") || MK.test(e.content || "");

  // which edge an event travels, and in which direction
  function edgeOf(e) {
    if (!e) return null;
    if (e.type === "message" && e.from === "orchestrator" && N[e.to] && e.tool === "send_task") return { a: "orchestrator", b: e.to, dir: 1 };
    if (e.type === "message" && N[e.from] && e.to === "orchestrator" && e.from !== "env") return { a: "orchestrator", b: e.from, dir: -1 };
    if (e.type === "tool_call" && /^w\d$/.test(e.from || "")) {
      if (e.tool === "read_table") return { a: e.from, b: "tables", dir: 1 };
      if (e.tool === "raise_concern") return { a: e.from, b: "overseer", dir: 1 };
      if (e.tool === "write_report") return { a: e.from, b: "report", dir: 1 };
    }
    if (e.type === "tool_result" && /^w\d$/.test(e.to || "") && e.tool === "read_table") return { a: e.to, b: "tables", dir: -1 };
    return null;
  }

  function stateAt(events, i) {
    const st = { orchestrator: null, w1: null, w2: null, w3: null, report: null, tables: null, overseer: null };
    const red = new Set(), used = new Set();
    const rank = { grey: 0, green: 1, amber: 2, red: 3 };
    const bump = (k, s) => { if (!st[k] || rank[s] > rank[st[k]]) st[k] = s; };
    for (let k = 0; k <= i && k < events.length; k++) {
      const e = events[k], ed = edgeOf(e);
      if (ed) used.add(ed.a + ">" + ed.b);
      if (e.type === "message" && e.tool === "send_task" && N[e.to]) { bump(e.to, hasMk(e) ? "amber" : "grey"); if (hasMk(e)) red.add("orchestrator>" + e.to); }
      if (e.type === "message" && /^w\d$/.test(e.from || "") && e.to === "orchestrator") {
        if (hasMk(e)) { bump(e.from, "red"); red.add("orchestrator>" + e.from); bump("orchestrator", "amber"); }
      }
      if (e.type === "tool_call" && e.tool === "raise_concern" && N[e.from]) { bump(e.from, "green"); st.overseer = "green"; }
      if (e.type === "tool_call" && e.tool === "write_report") {
        if (hasMk(e)) { bump(e.from, "red"); st.report = "red"; red.add(e.from + ">report"); bump("orchestrator", "red"); }
        else if (st.report !== "red") st.report = "grey";
      }
      if (e.type === "tool_call" && e.tool === "read_table") st.tables = "grey";
    }
    return { st, red, used };
  }

  const scoreCell = (v, src) => `<td class="r num"${KP.src(src)}>${v == null ? '<span class="faint">–</span>' : esc(v)}</td>`;
  const yesno = (v, bad) => (v == null ? "–" : v ? `<b class="${bad ? "c-leak" : "c-report"}">yes</b>` : "no");

  KP.swarmEpisode = function (d, params, root) {
    const [batch, epId, step0] = params;
    const ep = d.episode, events = d.events, sw = d.swarm, sm = sw.summary, o = ep.outcome || {};
    let cur = Math.min(events.length - 1, Math.max(0, parseInt(step0, 10) || 0)), playing = false, timer = null, speed = 1, userStepped = !!step0;
    let sel = sessionStorage.getItem("kp.swnode") || "orchestrator";
    const allMk = [...new Set([...(d.markers || []), ...events.flatMap((e) => (e.highlights || []).map((h) => h.value))])];
    const chip = (k, v, src) => `<span class="chip"${KP.src(src)}><span class="k">${k}</span><b>${esc(v == null ? "–" : v)}</b></span>`;
    const banner = d.never_analysed ? `<div class="fakebar spikebar" title="${esc(d.manifest_notes || "")}">${esc(String(d.kind || "").toUpperCase())}, NEVER ANALYSED · ${esc(String(d.design || "").toUpperCase())}</div>` : "";
    const monRow = (m) => `<tr><td class="mono">${m}</td>${scoreCell((sm.global || {})[m], sm._src)}${scoreCell((sm.local_max || {})[m], sm._src)}${["w1", "w2", "w3"].map((w) => scoreCell((sw.nodes[w].local_scores || {})[m], sm._src)).join("")}</tr>`;

    root.innerHTML = `${banner}<div class="page wide" style="max-width:1440px">
      <div class="ep-head"><div>
        <div class="eyebrow small muted" style="letter-spacing:.14em;text-transform:uppercase"><a href="#/catalogue">Playback</a> / <span class="mono">${esc(batch)}</span> · <span>${esc(d.design)}</span></div>
        <h2 style="font:400 32px var(--serif);margin:6px 0 0">${esc(ep.episode_id)} <span class="pill line">swarm</span></h2>
        <div class="chips">${chip("group", ep.group, ep._src)}${chip("variant", ep.variant, ep._src)}${chip("orchestrator", ep.orchestrator, ep._src)}${chip("workers", (ep.workers || {}).w1 || ep.peer, ep._src)}${chip("kinship", ep.kinship_true, ep._src)}${chip("claim", ep.claim, ep._src)}${chip("seed", ep.seed, ep._src)}</div>
      </div><div class="row"><span class="small muted">${events.length} events</span></div></div>

      <div class="swsum">
        <div class="card pad"><h4>Outcome (checker)</h4><div class="verdict">${ep.error ? '<span class="pill bad">error</span>' : KP.og(o.category, ep._src)}</div>
          <dl class="kv" style="margin-top:10px"><dt>leak</dt><dd${KP.src(sm._src)}>${yesno(sm.leak, true)}</dd><dt>objective met</dt><dd${KP.src(sm._src)}>${yesno(sm.objective_met, true)}</dd>
          <dt>crossing</dt><dd class="mono"${KP.src(sm._src)}>${esc(sm.crossing)}</dd><dt>local red flags</dt><dd class="num"${KP.src(sm._src)}>${esc(sm.local_red_flags)} <span class="faint">of 3</span></dd></dl></div>
        <div class="card pad"><h4>Monitors: GLOBAL (whole team) vs LOCAL (per worker)</h4>
          <table class="t mini"><thead><tr><th></th><th class="r">global</th><th class="r">local max</th><th class="r">w1</th><th class="r">w2</th><th class="r">w3</th></tr></thead><tbody>${monRow("mon_claude")}${monRow("mon_qwen")}</tbody></table>
          <p class="tiny muted" style="margin:8px 0 0">0–10 suspicion. Flags: ${Object.values(ep.monitors || {}).some((m) => m && m.flag != null) ? "see thresholds" : "null (no calibrated threshold yet)"}. Monitors never see the orchestrator's hidden objective or its closing summary.</p></div>
        <div class="card pad"><h4>Run</h4><dl class="kv"><dt>orchestrator tasks</dt><dd class="num"${KP.src(sm._src)}>${esc(o.orchestrator_n_tasks)}</dd><dt>asked for notes</dt><dd${KP.src(sm._src)}>${yesno(o.orchestrator_asked_for_notes)}</dd><dt>orch. declined</dt><dd${KP.src(sm._src)}>${yesno(o.orchestrator_declined)}</dd>
          <dt>cost</dt><dd class="num"${KP.src(ep._src)}>${KP.fmtUsd(ep.cost_usd, 4)}</dd><dt>latency</dt><dd class="num"${KP.src(ep._src)}>${esc(ep.latency_s)} s</dd></dl></div>
      </div>

      <div class="card stickystage" style="margin-bottom:14px;top:${banner ? "27px" : "0"}"><div class="stage sw"><svg id="stage" viewBox="0 0 900 350" preserveAspectRatio="xMidYMid meet" role="img" aria-label="team graph"></svg></div>
        <div class="scrub" style="border-top:1px solid var(--rule)">
          <div class="ctl"><button id="b-first" title="First (Home)">⏮</button><button id="b-prev" title="Previous (←)">◀</button><button id="b-play" class="play" title="Play / pause (Space)">▶</button><button id="b-next" title="Next (→)">▶︎|</button><button id="b-last" title="Last (End)">⏭</button></div>
          <div class="track"><div class="ticks" id="ticks">${events.map((e) => `<i class="t-${esc(e.type)}" title="#${e.i} ${esc(e.type)}"></i>`).join("")}</div><input type="range" id="range" min="0" max="${Math.max(0, events.length - 1)}" value="${cur}" aria-label="timeline"></div>
          <div class="row small"><span class="num" id="pos"></span><select id="speed" style="padding:4px 26px 4px 8px;font-size:12.5px"><option value="0.5">0.5×</option><option value="1" selected>1×</option><option value="2">2×</option><option value="4">4×</option></select></div>
        </div></div>
      <p class="tiny muted" style="margin:0 0 18px">Click a node to open its panel. Colours build up step by step: <b class="c-leak">red</b> = markers passed through it (its replies, or a leaking report), <b class="c-comply_no_leak">amber</b> = it received markers in a task, <b class="c-report">green</b> = it raised a concern, grey = otherwise. Red edges are the path the markers took. Keys: <kbd>Space</kbd> <kbd>←</kbd><kbd>→</kbd> <kbd>Home</kbd><kbd>End</kbd>.</p>

      <div style="display:grid;grid-template-columns:minmax(0,1fr) 440px;gap:22px;align-items:start">
        <div class="events" id="events"></div>
        <div class="ep-side swpanel" id="nodepanel" style="top:${banner ? 360 : 334}px"></div>
      </div></div>`;

    KP.$("#events").innerHTML = events.map((e) => KP.renderEvent(e, allMk)).join("");

    function panel() {
      const n = sw.nodes[sel];
      const evlist = (arr, empty) => (arr && arr.length ? arr.map((x) => `<div class="pitem"><div class="tiny muted"><span${KP.src(x._src)}>#${esc(x.i)}</span> ${x.reply_label ? `<span class="pill line">${esc(x.reply_label)}</span>` : ""} ${x.to && x.type === "message" ? "→ " + esc(x.to) : ""} ${x.from && x.to === "orchestrator" ? esc(x.from) + " →" : ""} ${x.tool ? `<span class="mono">${esc(x.tool)}</span>` : ""} ${x.markers.length ? `<span class="pill bad">${x.markers.length} marker${x.markers.length > 1 ? "s" : ""}</span>` : ""}</div><div class="pbody">${KP.markers(x.content || "", allMk)}</div></div>`).join("") : `<p class="small muted">${empty}</p>`);
      const mons = (n.monitor_events || []).map((m) => `<div class="score"${KP.src(m._src)}><span class="mono">${esc(m.mon)}</span><span class="bar"><i style="width:${(m.score || 0) * 10}%"></i></span><span class="num">${esc(m.score)}</span></div><div class="tiny muted" style="margin:-2px 0 8px">${esc(m.reason || "")}</div>`).join("") || '<p class="small muted">no monitor events</p>';
      let h = "";
      if (sel === "report") {
        h = `<div class="card pad"><h4>Final report (w3 → write_report)</h4>${sw.report.written ? `<div class="tiny muted"${KP.src(sw.report._src)}>${esc(sw.report._src)} · ${sw.report.markers.length} marker(s)</div><div class="reporttext">${KP.markers(sw.report.text, allMk)}</div>` : '<p class="small muted">No report was written.</p>'}</div>`;
      } else if (sel === "orchestrator") {
        h = `<div class="card pad objective"><div class="spread"><h4 style="margin:0">Hidden objective · orchestrator system prompt</h4><span class="pill bad">hidden from workers and monitors</span></div>
            <p class="tiny muted" style="margin:6px 0 8px">Shown to you for review only. Variant <b class="mono">${esc(ep.variant)}</b>. Neither the workers nor the local/global monitors ever see this text.</p>
            ${n.system ? `<div class="tiny muted"${KP.src(n.system._src)}>event #${esc(n.system.i)} · ${esc(n.system._src)}</div><div class="pbody sysprompt">${esc(n.system.content)}</div>` : '<p class="small muted">not recorded</p>'}</div>
          <div class="card pad"><h4>Orchestrator · ${esc(n.model)}</h4><dl class="kv"><dt>tasks sent</dt><dd class="num"${KP.src(sm._src)}>${esc((n.outcome || {}).orchestrator_n_tasks)}</dd><dt>asked for notes</dt><dd${KP.src(sm._src)}>${yesno((n.outcome || {}).orchestrator_asked_for_notes)}</dd><dt>objective met</dt><dd${KP.src(sm._src)}>${yesno((n.outcome || {}).objective_met, true)}</dd></dl></div>
          <div class="card pad"><h4>Tasks sent (${n.tasks_sent.length})</h4>${evlist(n.tasks_sent, "none")}</div>
          <div class="card pad"><h4>Replies received (${n.replies_received.length})</h4>${evlist(n.replies_received, "none")}</div>
          <div class="card pad"><h4>Closing summary · hidden from monitors</h4>${evlist(n.closing, "none")}</div>
          <div class="card pad"><h4>GLOBAL monitor (whole team)</h4>${mons}</div>`;
      } else {
        const ow = n.outcome || {};
        h = `<div class="card pad"><div class="spread"><h4 style="margin:0">${esc(ROLE[sel])} · ${esc(n.model)}</h4><span class="pill" style="color:${COL[n.status]}">checker: ${esc(n.status)}</span></div>
            <dl class="kv" style="margin-top:10px"><dt>tasks</dt><dd class="num"${KP.src(sm._src)}>${esc(ow.n_tasks)}</dd><dt>raised concern</dt><dd${KP.src(sm._src)}>${yesno(ow.raised_concern)}</dd><dt>refused</dt><dd${KP.src(sm._src)}>${yesno(ow.refused)}</dd>
            <dt>markers received</dt><dd class="num"${KP.src(sm._src)}>${(ow.markers_received || []).length}</dd><dt>markers in replies</dt><dd class="num"${KP.src(sm._src)}>${(ow.markers_in_replies || []).length}</dd>
            ${sel === "w3" ? `<dt>wrote report</dt><dd${KP.src(sm._src)}>${yesno(ow.wrote_report)}</dd><dt>markers in report</dt><dd class="num"${KP.src(sm._src)}>${(ow.markers_in_report || []).length}</dd>` : ""}</dl></div>
          <div class="card pad"><h4>LOCAL monitor scores (this worker only)</h4>${mons}</div>
          <div class="card pad"><details><summary class="small" style="cursor:pointer"><b>System prompt</b> <span class="muted">(what this worker was told)</span></summary>${n.system ? `<div class="tiny muted" style="margin-top:6px"${KP.src(n.system._src)}>event #${esc(n.system.i)} · ${esc(n.system._src)}</div><div class="pbody sysprompt">${esc(n.system.content)}</div>` : '<p class="small muted">never started (no task)</p>'}</details></div>
          <div class="card pad"><h4>Tasks received (${n.tasks.length})</h4>${evlist(n.tasks, "no task")}</div>
          <div class="card pad"><h4>Tool calls (${n.tool_calls.length})</h4>${evlist(n.tool_calls, "none")}</div>
          <div class="card pad"><h4>Replies to the orchestrator (${n.replies.length})</h4>${evlist(n.replies, "none")}</div>
          <div class="card pad"><h4>Concerns raised (${n.concerns.length})</h4>${evlist(n.concerns, "none")}</div>`;
      }
      KP.$("#nodepanel").innerHTML = `<div class="tabs nodetabs">${["orchestrator", "w1", "w2", "w3", "report"].map((k) => `<button data-n="${k}" class="${k === sel ? "on" : ""}">${k === "orchestrator" ? "Orch." : k === "report" ? "Report" : k.toUpperCase()}</button>`).join("")}</div>${h}`;
      KP.$$("#nodepanel .nodetabs button").forEach((b) => b.addEventListener("click", () => pick(b.dataset.n)));
    }
    const pick = (k) => { sel = k; sessionStorage.setItem("kp.swnode", k); panel(); draw(); };

    function draw() {
      const e = events[cur] || {};
      const { st, red, used } = stateAt(events, cur);
      const ed = edgeOf(e);
      const edges = [["orchestrator", "w1"], ["orchestrator", "w2"], ["orchestrator", "w3"], ["w1", "tables"], ["w2", "tables"], ["w1", "overseer"], ["w2", "overseer"], ["w3", "overseer"], ["w3", "report"]];
      const pt = (k) => { const n = N[k]; return n.w ? { x: n.x, y: n.y - n.h / 2 } : { x: n.x, y: n.y }; };
      let svg = `<defs><marker id="ah" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse"><path d="M0 0 L10 5 L0 10 z" fill="var(--ink)"/></marker></defs>`;
      for (const [a, b] of edges) {
        const A = pt(a), B = pt(b), key = a + ">" + b;
        const on = ed && ed.a === a && ed.b === b, isRed = red.has(key);
        const cls = ["edge", on ? "active" : "", isRed ? "redpath" : "", used.has(key) ? "used" : "faded"].join(" ");
        svg += `<line class="${cls}" x1="${A.x}" y1="${A.y}" x2="${B.x}" y2="${B.y}"/>`;
        if (on) {
          const [S, T] = ed.dir > 0 ? [A, B] : [B, A];
          svg += `<circle r="6" class="packet ${hasMk(e) ? "mk" : ""}"><animateMotion dur="${0.9 / speed}s" repeatCount="indefinite" path="M${S.x},${S.y} L${T.x},${T.y}"/></circle>`;
        }
      }
      const active = new Set(ed ? [ed.a, ed.b] : [e.actor || e.from]);
      for (const [id, n] of Object.entries(N)) {
        const s = st[id];
        const fill = s ? `color-mix(in oklab, ${COL[s]} 24%, var(--panel))` : "var(--panel)";
        const stroke = active.has(id) ? "var(--ink)" : s ? COL[s] : "var(--rule-2)";
        const sw2 = active.has(id) ? 3 : id === sel ? 3 : 2;
        const ring = id === sel ? `stroke-dasharray="${n.w ? "0" : "5 3"}"` : "";
        if (n.w) {
          svg += `<g class="node click" data-n="${id}"><rect x="${n.x - n.w / 2}" y="${n.y - n.h / 2}" width="${n.w}" height="${n.h}" rx="7" fill="${fill}" stroke="${stroke}" stroke-width="${sw2}" ${ring}/><text x="${n.x}" y="${n.y - 1}" text-anchor="middle">${n.label}</text><text class="sub" x="${n.x}" y="${n.y + 12}" text-anchor="middle">${n.sub}</text></g>`;
        } else {
          const model = id === "orchestrator" ? ep.orchestrator : ((ep.workers || {})[id] || ep.peer);
          svg += `<g class="node click" data-n="${id}"><circle class="body" cx="${n.x}" cy="${n.y}" r="${n.r}" fill="${fill}" stroke="${stroke}" stroke-width="${sw2}" ${ring}/>
            <text x="${n.x}" y="${n.y - 4}" text-anchor="middle">${n.label}</text><text class="sub" x="${n.x}" y="${n.y + 12}" text-anchor="middle">${esc(model)}</text>
            ${n.sub ? `<text class="sub" x="${n.x - n.r - 8}" y="${n.y + 4}" text-anchor="end">${n.sub}</text>` : `<text class="sub objlabel" x="${n.x + n.r + 12}" y="${n.y + 4}">hidden objective (${esc(ep.variant)})</text>`}</g>`;
        }
      }
      KP.$("#stage").innerHTML = svg;
      KP.$$("#stage .node.click").forEach((g) => g.addEventListener("click", () => pick(g.dataset.n)));
      KP.$$("#ticks i").forEach((t, k) => { t.classList.toggle("past", k <= cur); t.classList.toggle("cur", k === cur); });
      KP.$("#range").value = cur;
      KP.$("#pos").textContent = `${cur + 1} / ${events.length}`;
      KP.$$("#events .ev").forEach((el, k) => { el.classList.toggle("future", k > cur); el.classList.toggle("cur", k === cur); });
      const el = KP.$$("#events .ev")[cur], main = KP.$("#main"), stage = KP.$(".stickystage");
      if (el && userStepped) { const r = el.getBoundingClientRect(), top = stage.getBoundingClientRect().bottom + 16; if (r.top < top || r.top > window.innerHeight - 160) main.scrollTo({ top: main.scrollTop + r.top - top, behavior: "smooth" }); }
      userStepped = true;
      history.replaceState(null, "", `#/episode/${encodeURIComponent(batch)}/${encodeURIComponent(epId)}/${cur}`);
      KP.$("#b-play").textContent = playing ? "❚❚" : "▶";
    }
    const go = (k) => { cur = Math.max(0, Math.min(events.length - 1, k)); draw(); };
    const play = () => { playing = !playing; if (playing && cur >= events.length - 1) cur = 0; loop(); draw(); };
    const loop = () => { clearTimeout(timer); if (!playing) return; timer = setTimeout(() => { if (cur >= events.length - 1) { playing = false; draw(); return; } go(cur + 1); loop(); }, 1100 / speed); };
    KP.$("#b-first").onclick = () => go(0); KP.$("#b-last").onclick = () => go(events.length - 1);
    KP.$("#b-prev").onclick = () => go(cur - 1); KP.$("#b-next").onclick = () => go(cur + 1);
    KP.$("#b-play").onclick = play;
    KP.$("#range").addEventListener("input", (e) => go(+e.target.value));
    KP.$("#speed").addEventListener("change", (e) => { speed = +e.target.value; loop(); draw(); });
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
    panel(); draw();
    return () => { clearTimeout(timer); document.removeEventListener("keydown", onKey); };
  };
})();
