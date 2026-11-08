/* Results and the report-writing guide. James writes every word; the dashboard only saves his drafts. */
(function () {
  "use strict";
  const { esc } = KP;
  const WPP = 500; // rough words per page of text, used only for the page estimate

  KP.views.claimsTable = function (c, sectionSlug) {
    if (!c || !c.exists) return `<div class="empty" style="padding:22px">No <b>CLAIMS.md</b> yet. It is written by the analysis step: each number in the report maps to a script, a figure or table, and a batch.</div>`;
    let rows = c.rows;
    const si = c.headers.findIndex((h) => /section/i.test(h));
    if (sectionSlug && si >= 0) rows = rows.filter((r) => (r.cells[si] || "").toLowerCase().includes(sectionSlug.split("-")[0]));
    const link = (cell) => esc(cell).replace(/((?:figures|analysis|runs|harness|data|docs)\/[\w./\-]+)/g, (p) =>
      p.startsWith("analysis/") || p.startsWith("harness/") ? `<a href="#/code/${p}">${p}</a>` : p.startsWith("figures/") ? `<a href="#/results">${p}</a>` : p.startsWith("runs/") ? `<a href="#/integrity">${p}</a>` : p);
    return `<div class="scroll" style="max-height:420px"><table class="t"><thead><tr>${c.headers.map((h) => `<th>${esc(h)}</th>`).join("")}</tr></thead><tbody>
      ${rows.map((r) => `<tr>${r.cells.map((x, i) => `<td class="${i === 0 ? "" : "small"}"${i === 0 ? KP.src(r._src) : ""}>${link(x)}</td>`).join("")}</tr>`).join("") || `<tr><td colspan="${c.headers.length}" class="muted">No claims tagged for this section.</td></tr>`}</tbody></table></div>
      <p class="tiny muted" style="margin:8px 0 0">${rows.length} claim${rows.length === 1 ? "" : "s"} · <span class="mono">CLAIMS.md</span> sha256 ${KP.short(c.sha256, 12)}</p>`;
  };
  KP.views.figureGrid = function (figs) {
    if (!figs || !figs.length) return `<div class="empty" style="padding:22px">No figures in <b>figures/</b> yet.</div>`;
    return `<div class="figs">${figs.map((f) => `<figure class="card"><a href="${esc(f.url)}" target="_blank" rel="noopener">${/\.pdf$/i.test(f.name) ? `<div class="empty">PDF · open</div>` : `<img src="${esc(f.url)}" alt="${esc(f.name)}" loading="lazy">`}</a><figcaption class="spread"><span class="mono"${KP.src("figures/" + f.name)}>${esc(f.name)}</span><span class="faint mono">${KP.short(f.sha256, 8)}</span></figcaption></figure>`).join("")}</div>`;
  };

  const tabs = (on) => `<div class="tabs" style="margin-bottom:26px"><button data-h="#/results" class="${on === "results" ? "on" : ""}">Results</button><button data-h="#/report" class="${on === "report" ? "on" : ""}">Report writing guide</button></div>`;
  const wireTabs = (root) => KP.$$(".tabs button[data-h]", root).forEach((b) => b.addEventListener("click", () => KP.go(b.dataset.h)));

  KP.views.results = async function (params, root) {
    KP.setCtx({ view: "results" });
    const d = await KP.api("/api/claims");
    root.innerHTML = `<div class="page wide" style="max-width:1300px">${KP.head("Results and report", "What the analysis produced", "Figures from <span class='mono'>figures/</span> and every claim in <span class='mono'>CLAIMS.md</span>, each linked to the script and batch it came from. No number is typed by hand.")}
      ${tabs("results")}
      <h3>Figures</h3>${KP.views.figureGrid(d.figures)}
      <h3 style="margin-top:34px">Claims</h3><div class="card pad">${KP.views.claimsTable(d.claims)}</div></div>`;
    wireTabs(root);
  };

  KP.views.report = async function (params, root) {
    const list = await KP.api("/api/report/sections");
    const slug = params[0] || (list.sections.find((s) => !s.word_count && s.slug !== "abstract") || list.sections[1]).slug;
    const s = await KP.api("/api/report/section?slug=" + encodeURIComponent(slug));
    KP.setCtx({ view: "report", section: slug });
    const idx = list.sections.findIndex((x) => x.slug === slug);
    const prev = list.sections[idx - 1], next = list.sections[idx + 1];
    const counted = list.sections.filter((x) => !["references", "appendix", "author-contributions", "code-and-data", "llm-usage"].includes(x.slug));
    const totalWords = counted.reduce((a, x) => a + x.word_count, 0);
    const pageBudget = [["Intro & related work", 1, ["introduction", "related-work"]], ["Methods & results", 2.5, ["methods", "results"]], ["Discussion", 0.5, ["discussion", "conclusion"]]];

    root.innerHTML = `<div class="page wide" style="max-width:1400px">${KP.head("Results and report", "Write the report, one section at a time", "Follows the Apart template: about 4 pages excluding references and appendix. You write; drafts save to <span class='mono'>docs/report/&lt;section&gt;.md</span> as you type. The assistant can critique a draft but won't write it.")}
      ${tabs("report")}
      <div class="rep">
        <div class="card toc">
          <div style="padding:6px 10px 12px"><div class="small"><div class="muted tiny" style="letter-spacing:.1em;text-transform:uppercase">Body text so far</div><div class="num" style="font:400 22px var(--serif);margin-top:2px">${totalWords} words <span class="muted" style="font-size:15px">≈ ${(totalWords / WPP).toFixed(1)} of 4 pages</span></div></div>
            <div class="pagebar" style="margin-top:8px">${pageBudget.map(([l, p, ss]) => { const w = list.sections.filter((x) => ss.includes(x.slug)).reduce((a, x) => a + x.word_count, 0); const f = Math.min(1, w / (p * WPP)); return `<i style="flex:${p};background:linear-gradient(90deg,var(--ink-2) ${f * 100}%,var(--rule) ${f * 100}%)" title="${l}: ${w} words of ≈${p * WPP} (${p} page${p === 1 ? "" : "s"})"></i>`; }).join("")}</div>
            <div class="tiny faint" style="margin-top:5px">1p intro · 2.5p methods & results · 0.5p discussion · estimate at ${WPP} words/page</div></div>
          ${list.sections.map((x) => { const tgt = x.words[1]; const f = tgt ? Math.min(1, x.word_count / tgt) : 0; return `<a href="#/report/${x.slug}" class="${x.slug === slug ? "on" : ""}"><span>${esc(x.title)}</span><span class="wc">${x.word_count}${tgt ? "/" + tgt : ""}</span><span class="mini"><i class="${x.word_count > tgt && tgt ? "over" : x.word_count >= x.words[0] && tgt ? "full" : ""}" style="width:${f * 100}%"></i></span></a>`; }).join("")}
        </div>
        <div class="stack">
          <div class="spread"><div><div class="eyebrow small muted" style="letter-spacing:.14em;text-transform:uppercase">Section ${idx + 1} of ${list.sections.length} · ${esc(s.pages)}</div><h2 style="font:400 32px var(--serif);margin:6px 0 0">${esc(s.title)}</h2></div>
            <div class="row">${prev ? `<a class="btn sm ghost" href="#/report/${prev.slug}">← ${esc(prev.title)}</a>` : ""}${next ? `<a class="btn sm" href="#/report/${next.slug}">${esc(next.title)} →</a>` : ""}</div></div>
          <div class="card pad" style="display:grid;grid-template-columns:minmax(0,3fr) minmax(0,2fr);gap:28px">
            <p class="guidance">${esc(s.guide)}</p>
            <div><h4>For this project</h4>${s.project.length ? `<ul class="small" style="margin:0;padding-left:18px;line-height:1.6">${s.project.map((p) => `<li>${esc(p).replace(/(PREREG §\d|§\d)/g, '<a href="#/code/PREREG.md">$1</a>').replace(/(CLAIMS\.md|REVIEW_LOG\.md)/g, '<span class="mono">$1</span>')}</li>`).join("")}</ul>` : '<p class="small muted">Nothing project-specific.</p>'}
              <p class="tiny muted" style="margin-top:12px">Target: ${s.words[1] ? `${s.words[0]}–${s.words[1]} words` : "not counted"}</p></div>
          </div>
          ${s.claims_wanted ? `<div class="card pad"><h4>Numbers you can use here (from CLAIMS.md)</h4>${KP.views.claimsTable(s.claims, s.slug)}</div>` : ""}
          ${s.figures && s.figures.length ? `<div class="card pad"><h4>Figures</h4>${KP.views.figureGrid(s.figures)}</div>` : ""}
          <div>
            <div class="spread" style="margin-bottom:8px"><h4 style="margin:0">Your draft</h4><span class="small muted num" id="wc"></span></div>
            <div class="meter" style="margin-bottom:10px;height:5px"><i id="wcbar" style="width:0"></i></div>
            <textarea class="manuscript" id="draft" spellcheck="true" placeholder="Write ${esc(s.title.replace(/^\d+\. /, ""))} here, in your own words.">${esc(s.text)}</textarea>
            <div class="spread" style="margin-top:10px"><span class="tiny muted" id="saved">${s.saved_utc ? "Saved " + KP.when(s.saved_utc) : "Not saved yet"} · <span class="mono">${esc(s.path)}</span></span>
              <div class="row"><button class="btn sm" id="critique">Ask for a critique</button><button class="btn sm primary" id="save">Save now</button></div></div>
          </div>
        </div>
      </div></div>`;
    wireTabs(root);
    const ta = KP.$("#draft");
    const wc = () => {
      const n = ta.value.trim() ? ta.value.trim().split(/\s+/).length : 0, [lo, hi] = s.words;
      KP.$("#wc").textContent = hi ? `${n} words · target ${lo}–${hi}` : `${n} words`;
      const cur = KP.$(".toc a.on .wc"); if (cur) cur.textContent = n + (hi ? "/" + hi : "");
      const bar = KP.$("#wcbar"); bar.style.width = (hi ? Math.min(100, (100 * n) / hi) : 0) + "%"; bar.style.background = hi && n > hi ? "var(--warn)" : n >= lo && hi ? "var(--ok)" : "var(--ink)";
    };
    let t = null, last = s.text;
    const save = async () => {
      if (ta.value === last) return;
      try { const r = await KP.api("/api/report/save", { slug, text: ta.value }); last = ta.value; KP.$("#saved").innerHTML = `Saved ${KP.when(r.saved_utc || new Date().toISOString())} · <span class="mono">${esc(r.path)}</span>`; }
      catch (e) { KP.$("#saved").textContent = "Not saved: " + e.message; }
    };
    ta.addEventListener("input", () => { wc(); KP.$("#saved").textContent = "Editing…"; clearTimeout(t); t = setTimeout(save, 1200); });
    KP.$("#save").addEventListener("click", save);
    KP.$("#critique").addEventListener("click", async () => { await save(); KP.askOpen(`Critique my draft of "${s.title}" against the Apart guidance and CLAIMS.md. Point out unsupported numbers and overclaiming. Don't rewrite it.`); });
    wc();
    return () => { clearTimeout(t); if (ta.value !== last) save(); };
  };
})();
