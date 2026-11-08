/* Code: browse harness/ and analysis/ with highlighting, plus the recent git log (read-only). */
(function () {
  "use strict";
  const { esc } = KP;

  KP.views.code = async function (params, root) {
    const raw = params.join("/");
    const [path, lineStr] = raw.split(":");
    const line = parseInt(lineStr, 10) || null;
    const t = await KP.api("/api/code/tree");
    const files = t.groups.flatMap((g) => g.files.map((f) => f.path));
    const sel = path || files.find((f) => /checker\.py$/.test(f)) || files[0];
    KP.setCtx({ view: "code", file: sel });

    root.innerHTML = `<div class="page wide" style="max-width:1440px">
      ${KP.head("Code", "Read what the agents built", "The harness, the analysis and the contracts, exactly as they are on disk now. Nothing here can be edited from the dashboard.")}
      <div class="codewrap">
        <div class="card tree">${t.groups.map((g) => `<h4>${esc(g.root)}/</h4>${g.files.length ? g.files.map((f) => `<a href="#/code/${esc(f.path)}" class="${f.path === sel ? "on" : ""}">${esc(f.path.replace(g.root + "/", ""))}</a>`).join("") : '<div class="tiny muted" style="padding:0 8px">empty</div>'}`).join("")}
          <h4>git log --oneline -30</h4><div class="gitlog" style="padding:0 8px">${t.git_log.map((l) => { const [h, ...r] = l.split(" "); return `<div><span class="h">${esc(h)}</span> ${esc(r.join(" "))}</div>`; }).join("") || '<span class="muted">no commits</span>'}</div>
        </div>
        <div class="card" id="codeview"><div class="empty">${sel ? "Loading…" : "No files yet."}</div></div>
      </div></div>`;
    if (!sel) return;
    const f = await KP.api("/api/code/file?path=" + encodeURIComponent(sel));
    const md = f.markdown && !line;
    KP.$("#codeview").innerHTML = `<div class="spread" style="padding:14px 20px;border-bottom:1px solid var(--rule)">
        <div><div class="mono" style="font-size:14px;font-weight:600">${esc(f.path)}</div><div class="path">${esc(f.abs)}</div></div>
        <div class="row small">${f.markdown ? `<div class="seg-ctl"><button data-m="doc" class="${md ? "on" : ""}">Rendered</button><button data-m="src" class="${md ? "" : "on"}">Source</button></div>` : ""}<span class="muted num">${f.lines} lines</span><span class="hash" title="sha256">${KP.short(f.sha256, 16)}</span></div></div>
      <div id="cv-body"></div>`;
    const body = KP.$("#cv-body");
    const showSrc = () => {
      body.innerHTML = `<div class="code"><pre class="gut">${Array.from({ length: f.lines }, (_, i) => `<span id="L${i + 1}" class="${i + 1 === line ? "on" : ""}">${i + 1}</span>`).join("")}</pre><pre class="src">${line ? `<span class="lhl" style="top:calc(14px + ${line - 1} * 1.6em)"></span>` : ""}${f.html}</pre></div>`;
      if (line) { const c = KP.$(".code", body); c.scrollTop = Math.max(0, (line - 8) * 20); }
    };
    const showDoc = () => { body.innerHTML = `<div class="doc" style="padding:24px 30px;max-height:calc(100vh - 230px);overflow:auto">${f.markdown}</div>`; };
    md ? showDoc() : showSrc();
    KP.$$("[data-m]").forEach((b) => b.addEventListener("click", () => { KP.$$("[data-m]").forEach((x) => x.classList.toggle("on", x === b)); b.dataset.m === "doc" ? showDoc() : showSrc(); }));
  };
})();
