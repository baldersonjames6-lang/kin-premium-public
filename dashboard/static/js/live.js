/* Live run: start a batch through harness/run_batch.py, watch the 4×4 grid fill, stop with SIGINT. */
(function () {
  "use strict";
  const { esc } = KP;
  const ORDER = ["qwen27", "qwen9", "dsv41", "haiku"];
  const KINDS = { swarm: [["smoke", "Smoke"], ["spike", "Spike"], ["pilot", "Pilot"], ["main", "Main"], ["demo", "FAKE demo"]],
                  single: [["smoke", "Smoke"], ["demo", "FAKE demo"]] };

  function family(id) { id = String(id || "").toLowerCase(); return id.includes("claude") ? "anthropic" : id.split("/")[0]; }
  function kin(models, r, p) { if (r === p) return "identical"; if (!models[r] || !models[p]) return "unknown"; return family(models[r]) === family(models[p]) ? "sibling" : "different"; }

  KP.views.live = async function (params, root) {
    let batch = params[0] || null, since = 0, kind = localStorage.getItem("kp.kind") || "smoke", timer = null, eps = [];
    let mode = localStorage.getItem("kp.runmode") || "swarm", variant = localStorage.getItem("kp.variant") || null;
    let first = await KP.api("/api/live" + (batch ? "?batch=" + encodeURIComponent(batch) : ""));
    if (!batch) {
      batch = first.run.batch_id || null;
      if (!batch) {
        const bs = KP.state.batches; const running = bs.find((b) => b.status === "running");
        batch = (running || bs.find((b) => !b.fake) || bs[0] || {}).batch_id || null;
      }
      if (batch) first = await KP.api("/api/live?batch=" + encodeURIComponent(batch));
    }
    KP.setCtx({ view: "live", batch });

    root.innerHTML = `<div class="page wide" style="max-width:1400px">
      <div id="lv-fake"></div>
      ${KP.head("Live run", "Run a batch and watch it fill", "Batches start through <span class='mono'>harness/run_batch.py</span>, which applies its own REVIEW_LOG check. Pilot and main unlock after gate 1. Stop sends SIGINT; the harness closes the batch and writes SHA256SUMS.")}
      <div class="card pad" style="margin-bottom:22px">
        <div class="spread wrap" style="align-items:flex-end;flex-wrap:wrap;gap:18px">
          <div class="row wrap" style="gap:18px;align-items:flex-end">
            <div class="field" role="group" aria-label="Mode">Mode<div class="seg-ctl" id="modes"></div></div>
            <div class="field" role="group" aria-label="Kind">Kind<div class="seg-ctl" id="kinds"></div></div>
            <label class="field" id="varf">Variant<select id="variant" style="width:130px"></select></label>
            <label class="field">Episodes (optional)<input type="number" id="n" min="1" max="720" style="width:120px" placeholder="full plan"></label>
            <label class="field" id="capf">Max cost (USD)<input type="number" id="cap" step="0.5" min="0.1" style="width:120px"></label>
          </div>
          <div class="row"><button class="btn primary" id="start">Start batch</button><button class="btn danger solid hidden" id="stop">Stop (SIGINT)</button></div>
        </div>
        <p class="small muted" id="why" style="margin:12px 0 0"></p>
      </div>
      <div class="spread" style="margin-bottom:14px">
        <div class="row"><h3 style="margin:0">Watching</h3><select id="watch"></select><span id="lv-status"></span></div>
        ${KP.legend()}
      </div>
      <div style="display:grid;grid-template-columns:minmax(0,1fr) 360px;gap:22px;align-items:start">
        <div class="card pad"><div class="livegrid" id="grid"></div>
          <p class="tiny muted" style="margin:14px 0 0" id="gridnote"></p></div>
        <div class="stack">
          <div class="card pad"><h4>Spend</h4><div class="bignum num" id="cost">–</div><div class="meter" id="meter" style="margin:12px 0 8px"><i style="width:0"></i></div><div class="small muted" id="costsub"></div></div>
          <div class="card pad"><h4>Progress</h4><div class="spread"><div class="bignum num" id="prog">–</div><div id="tally" class="small" style="text-align:right"></div></div><div style="margin-top:12px" id="stack"></div></div>
          <div class="card pad"><h4>Latest episodes</h4><div class="feed" id="feed"></div></div>
        </div>
      </div>
      <div class="card pad" style="margin-top:22px"><div class="spread"><h4 style="margin:0">Harness output</h4><span class="tiny muted mono" id="cmd"></span></div><div class="console" id="console" style="margin-top:12px">No batch started from this dashboard yet.</div></div>
    </div>`;

    // controls
    let caps = {};
    let kindsKey = "", lastLive = first;
    const allowedOf = (live, k) => (k === "demo" ? live.allowed.demo : mode === "swarm" ? live.allowed[k] : live.allowed_single[k]);
    const whyOf = (live, k) => (k === "demo" ? "" : (mode === "swarm" ? live.why : live.why_single)[k] || "");
    const drawKinds = (live) => {
      lastLive = live;
      const key = JSON.stringify([live.allowed, live.why, live.allowed_single, live.run.active, kind, mode, variant, live.gate4, live.plan]);
      if (key === kindsKey) return; kindsKey = key;
      caps = live.caps || {};
      if (!KINDS[mode].some(([k]) => k === kind)) kind = "smoke";
      variant = variant || live.default_variant;
      KP.$("#modes").innerHTML = [["swarm", "Swarm"], ["single", "Single-prompt (v1)"]].map(([m, l]) => `<button data-m="${m}" class="${m === mode ? "on" : ""}" title="${m === "swarm" ? "decomposition: 1 orchestrator + 3 workers (current design)" : "v1 single-prompt design, kept as a baseline: smoke only"}">${l}</button>`).join("");
      KP.$$("#modes button").forEach((b) => b.addEventListener("click", () => { mode = b.dataset.m; localStorage.setItem("kp.runmode", mode); delete KP.$("#cap").dataset.touched; kindsKey = ""; drawKinds(lastLive); }));
      KP.$("#kinds").innerHTML = KINDS[mode].map(([k, l]) => { const ok = allowedOf(live, k); return `<button data-k="${k}" class="${k === kind ? "on" : ""}" ${ok ? "" : "disabled"} title="${esc(whyOf(live, k))}">${ok ? "" : '<span class="lock"></span>'}${l}</button>`; }).join("");
      KP.$$("#kinds button").forEach((b) => b.addEventListener("click", () => { kind = b.dataset.k; localStorage.setItem("kp.kind", kind); delete KP.$("#cap").dataset.touched; kindsKey = ""; drawKinds(lastLive); }));
      const showVar = mode === "swarm" && (kind === "smoke" || kind === "spike");
      KP.$("#varf").classList.toggle("hidden", !showVar);
      KP.$("#variant").innerHTML = (live.variants || []).map((v) => `<option ${v === variant ? "selected" : ""}>${esc(v)}</option>`).join("");
      KP.$("#capf").classList.toggle("hidden", kind === "demo");
      if (!KP.$("#cap").dataset.touched) KP.$("#cap").value = caps[mode + ":" + kind] || "";
      const pl = live.plan || {}, sz = (pl[mode] || {})[kind];
      const size = sz == null ? "size unknown (run_batch --dry-run failed: " + esc(JSON.stringify(pl.errors || {})) + ")" : `<b${KP.src(pl._src)}>${sz} episodes planned</b>`;
      const groups = (g) => (g ? " Groups: " + Object.entries(g).map(([k, v]) => `${esc(k)} ${v}`).join(", ") + "." : "");
      const msgs = mode === "swarm" ? {
        smoke: `Swarm smoke: harness check, never analysed. ${size}; use Episodes to run just a few.`,
        spike: `Swarm spike: feasibility only, ungated, manifest says "SPIKE: feasibility only, never analysed". ${size}.`,
        pilot: `Swarm pilot (PREREG v2 §8): ${size} = ${pl.swarm_pilot_attack ?? "?"} attack + ${pl.swarm_pilot_honest ?? "?"} honest. The attack episodes are what you label blind at gate 4.${groups((pl.groups || {}).pilot)}`,
        main: `Swarm main (PREREG v2 §7): ${size}.${groups((pl.groups || {}).main)} ` + (live.gate4 !== "approved" ? "Note: the plan expects gate 4 (pilot review) to be approved first." : ""),
        demo: "FAKE demo: writes a synthetic batch under dashboard/dev_fixtures/runs/ with no model calls, so you can see how a run looks.",
      } : {
        smoke: `Single-prompt (v1 design, baseline) smoke: ${size}. Pilot and main now run only in swarm mode.`,
        demo: "FAKE demo: writes a synthetic batch under dashboard/dev_fixtures/runs/ with no model calls.",
      };
      const ok = allowedOf(live, kind);
      const sizes = mode === "swarm" && pl.swarm ? `<div class="tiny muted" style="margin-top:6px"${KP.src(pl._src)}>Planned sizes (from run_batch.py --dry-run): ${["smoke", "spike", "pilot", "main"].map((k) => `${k} <b>${pl.swarm[k] ?? "?"}</b>${k === "pilot" ? ` (${pl.swarm_pilot_attack ?? "?"} attack + ${pl.swarm_pilot_honest ?? "?"} honest)` : ""}`).join(" · ")}</div>` : "";
      KP.$("#why").innerHTML = (ok ? "" : `<b style="color:var(--bad)">Locked: ${esc(whyOf(live, kind))}.</b> `) + (msgs[kind] || "") + (live.run_batch_exists || kind === "demo" ? "" : " <b>harness/run_batch.py is not there yet.</b>") + sizes;
      KP.$("#start").disabled = !ok || live.run.active;
      KP.$("#start").textContent = kind === "demo" ? "Start FAKE demo" : `Start ${mode} ${kind} batch`;
    };
    KP.$("#variant").addEventListener("change", (e) => { variant = e.target.value; localStorage.setItem("kp.variant", variant); });
    KP.$("#cap").addEventListener("input", (e) => (e.target.dataset.touched = "1"));
    drawKinds(first);

    KP.$("#start").addEventListener("click", async (e) => {
      const b = e.currentTarget;
      const label = kind === "demo" ? "Start FAKE demo" : `Start ${mode} ${kind} batch`;
      if (kind !== "demo" && !b.dataset.armed) {
        const cap = KP.$("#cap").value || caps[mode + ":" + kind];
        b.dataset.armed = "1"; b.textContent = `Confirm: real ${mode} ${kind} run, cap $${cap}`;
        setTimeout(() => { if (b.dataset.armed) { delete b.dataset.armed; b.textContent = label; } }, 6000); return;
      }
      try {
        const n = KP.$("#n").value, cap = KP.$("#cap").value;
        const r = await KP.api("/api/run/start", { kind, mode, variant: mode === "swarm" && (kind === "smoke" || kind === "spike") ? variant : null, n: n ? +n : null, max_cost_usd: cap ? +cap : null });
        KP.toast(`Started ${kind} batch (pid ${r.pid})`);
        batch = null; since = 0; eps = []; follow = true; drawGrid({}); KP.refresh();
      } catch (err) { KP.toast(err.message, true); }
      delete b.dataset.armed; b.textContent = label;
    });
    KP.$("#stop").addEventListener("click", async () => { try { await KP.api("/api/run/stop", {}); KP.toast("SIGINT sent: the harness will close the batch"); } catch (e) { KP.toast(e.message, true); } });

    // batch picker
    const watch = KP.$("#watch");
    watch.innerHTML = KP.state.batches.map((b) => `<option value="${esc(b.batch_id)}" ${b.batch_id === batch ? "selected" : ""}>${b.fake ? "FAKE · " : ""}${esc(b.batch_id)} · ${esc(b.status)}</option>`).join("") || "<option>no batches yet</option>";
    watch.addEventListener("change", () => KP.go("#/live/" + encodeURIComponent(watch.value)));
    let follow = !params[0];

    // Single-prompt: requester x peer over the manifest's models. Swarm: workers (rows) x orchestrators (cols),
    // taken from the episodes seen so far plus the planned main/pilot grid; unknown model keys are just added.
    let gridMode = "single", gridKey = "";
    function drawGrid(models, swarmAxes) {
      const m = Object.keys(models || {}).length ? models : { qwen27: "Qwen/a", qwen9: "Qwen/b", dsv41: "deepseek-ai/c", haiku: "claude" };
      let h;
      if (swarmAxes) {
        gridMode = "swarm";
        const [rows, cols] = swarmAxes;
        KP.$("#grid").style.gridTemplateColumns = `110px repeat(${cols.length}, minmax(70px, 1fr))`;
        h = `<div class="corner">worker ↓<br>orchestrator →</div>` + cols.map((o) => `<div class="hdr">${esc(o)}</div>`).join("");
        for (const w of rows) {
          h += `<div class="rh">${esc(w)}</div>`;
          for (const o of cols) { const k = o === w ? "identical" : kin(m, o, w); h += `<div class="cell ${k}" id="c-${esc(o)}-${esc(w)}"><span class="kin">${k}</span><div class="dots"></div></div>`; }
        }
      } else {
        gridMode = "single";
        KP.$("#grid").style.gridTemplateColumns = "";
        const keys = Object.keys(models || {}).length ? ORDER.filter((k) => k in models).concat(Object.keys(models).filter((k) => !ORDER.includes(k))) : ORDER;
        h = `<div class="corner">requester ↓<br>peer →</div>` + keys.map((p) => `<div class="hdr">${esc(p)}</div>`).join("");
        for (const r of keys) {
          h += `<div class="rh">${esc(r)}</div>`;
          for (const p of keys) { const k = kin(m, r, p); h += `<div class="cell ${k}" id="c-${r}-${p}"><span class="kin">${k}</span><div class="dots"></div></div>`; }
        }
      }
      KP.$("#grid").innerHTML = h;
      KP.$("#gridnote").textContent = swarmAxes ? "Rows are the worker model (all three workers), columns the orchestrator. Tinted cells are true kin (dark: identical). Click a dot to replay it." : "Rows are the requester, columns the peer. Tinted cells are true kin (dark: identical, light: same-family sibling). A ring marks a monitor flag. Click a dot to replay it.";
    }
    function swarmAxes(list, plan, kindNow) {
      const rows = [], cols = [];
      const add = (arr, v) => { if (v && !arr.includes(v)) arr.push(v); };
      list.forEach((e) => { add(rows, e.peer); add(cols, e.requester); });
      if (!list.length || kindNow === "pilot" || kindNow === "main") { (plan.workers || []).forEach((w) => add(rows, w)); (plan.orchestrators || []).forEach((o) => add(cols, o)); }
      return [rows, cols];
    }

    function addEps(list, b) {
      for (const e of list) {
        eps.push(e);
        const cell = document.getElementById(`c-${e.requester}-${e.peer}`) && KP.$(".dots", document.getElementById(`c-${e.requester}-${e.peer}`));
        if (cell) {
          const a = document.createElement("a");
          a.href = `#/episode/${encodeURIComponent(b)}/${encodeURIComponent(e.episode_id)}`;
          a.className = e.flagged ? "flagged" : "";
          a.title = `${e.episode_id} · ${e.group || e.claim}${e.variant ? " · " + e.variant : ""} · ${KP.OUTLABEL[e.category] || e.error || "error"}${e.crossing ? " · crossing " + e.crossing : ""}`;
          a.dataset.src = e._src;
          a.innerHTML = KP.shape(e.error ? null : e.category, 14);
          cell.appendChild(a);
          const c = cell.parentElement; c.classList.add("flash"); setTimeout(() => c.classList.remove("flash"), 700);
        }
      }
    }

    function drawSide(snap, run) {
      const m = snap.manifest || {};
      const cap = m.max_cost_usd || snap.ceiling.usd;
      const frac = Math.min(1, snap.cost_usd / cap);
      KP.$("#cost").innerHTML = `<span${KP.src(snap.path + "/episodes.jsonl · sum of cost_usd over " + snap.total + " lines")}>${KP.fmtUsd(snap.cost_usd, 4)}</span>`;
      const mt = KP.$("#meter"); mt.className = "meter" + (frac > 0.9 ? " bad" : frac > 0.7 ? " warn" : ""); mt.firstElementChild.style.width = (100 * frac).toFixed(1) + "%";
      KP.$("#costsub").innerHTML = `${m.max_cost_usd ? `of this batch's cap <b>${KP.fmtUsd(m.max_cost_usd, 2)}</b> (manifest max_cost_usd) · ` : ""}sprint ceiling £${snap.ceiling.gbp} ≈ ${KP.fmtUsd(snap.ceiling.usd, 0)} at ${snap.ceiling.gbp_usd} USD/GBP (set KIN_GBP_USD)`;
      const planned = m.n_planned || m.n_episodes || "?";
      KP.$("#prog").innerHTML = `${snap.total}<span class="muted" style="font-size:20px"> / ${planned}</span>`;
      const cats = {}; eps.forEach((e) => (cats[e.category || "error"] = (cats[e.category || "error"] || 0) + 1));
      KP.$("#tally").innerHTML = KP.OUT.filter((c) => cats[c]).map((c) => `<div>${KP.og(c)} <b class="num">${cats[c]}</b></div>`).join("") + (cats.error ? `<div class="muted">errors ${cats.error}</div>` : "");
      KP.$("#stack").innerHTML = KP.stackbar(cats, eps.length);
      KP.$("#feed").innerHTML = eps.slice(-14).reverse().map((e) => `<a href="#/episode/${encodeURIComponent(snap.batch_id)}/${encodeURIComponent(e.episode_id)}">${KP.shape(e.category)}<span class="mono tiny">${esc(e.episode_id)}</span><span class="small">${esc(e.requester)} → ${esc(e.peer)} <span class="muted">${esc(e.group || e.claim)}</span></span><span class="tiny muted num">${KP.fmtUsd(e.cost_usd, 4)}</span></a>`).join("") || '<span class="small muted">Nothing yet.</span>';
      const st = m.status || "?";
      KP.$("#lv-status").innerHTML = `${KP.fake(snap.fake)} <span class="pill ${st === "complete" ? "ok" : st === "running" ? "warn" : st === "aborted" ? "bad" : ""}">${st === "running" ? '<span class="pulse"></span> ' : ""}${esc(st)}</span>`;
      KP.$("#lv-fake").innerHTML = snap.fake ? `<div class="fakebar" style="margin:-34px -44px 22px">FAKE DEMO BATCH · synthetic fixture data, not experimental results</div>` : "";
    }

    function drawRun(run) {
      const active = run && run.active;
      KP.$("#stop").classList.toggle("hidden", !active);
      KP.$("#start").classList.toggle("hidden", !!active);
      if (run && run.output) {
        const c = KP.$("#console"); const atBottom = c.scrollTop + c.clientHeight >= c.scrollHeight - 20;
        c.innerHTML = run.output.map((l) => `<div class="${/REFUSED|ERROR|BUG|Traceback/i.test(l) ? "err" : /closed|complete/i.test(l) ? "ok" : ""}">${esc(l)}</div>`).join("") +
          (!active && run.returncode != null ? `<div class="${run.returncode === 0 ? "ok" : "err"}">— process exited with code ${run.returncode}${run.stopped_by_user ? " (stopped by you)" : ""} —</div>` : "");
        if (atBottom) c.scrollTop = c.scrollHeight;
        KP.$("#cmd").textContent = run.cmd || "";
      }
    }

    let models = {};
    async function tick() {
      try {
        const live = await KP.api(`/api/live?${batch ? "batch=" + encodeURIComponent(batch) + "&" : ""}since=${since}`);
        drawRun(live.run); drawKinds(live);
        if (follow && live.run.batch_id && live.run.batch_id !== batch) {
          batch = live.run.batch_id; since = 0; eps = []; models = {}; gridKey = "";
          KP.setCtx({ view: "live", batch });
          const w = KP.$("#watch"); if (![...w.options].some((o) => o.value === batch)) w.insertAdjacentHTML("afterbegin", `<option value="${esc(batch)}">${esc(batch)} · running</option>`); w.value = batch;
          return tick();
        }
        const snap = live.snapshot;
        if (snap) {
          const ms = (snap.manifest || {}).models || {};
          const isSw = snap.mode === "swarm";
          const axes = isSw ? swarmAxes(eps.concat(snap.episodes), live.plan || {}, snap.kind) : null;
          const gk = JSON.stringify([ms, axes]);
          if (gk !== gridKey || !KP.$("#grid").children.length) { gridKey = gk; models = ms; drawGrid(models, axes); const old = eps; eps = []; addEps(old, snap.batch_id); }
          addEps(snap.episodes, snap.batch_id); since = snap.total; drawSide(snap, live.run);
        } else if (!KP.$("#grid").children.length) drawGrid({});
      } catch (e) { console.warn(e); }
      timer = setTimeout(tick, 1000);
    }
    drawGrid({});
    tick();
    return () => clearTimeout(timer);
  };
})();
