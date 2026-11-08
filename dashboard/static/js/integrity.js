/* Data integrity: every batch, its manifest, its hashes verified now, and where every file lives. */
(function () {
  "use strict";
  const { esc } = KP;
  const tick = (ok, title) => `<span class="tick ${ok == null ? "na" : ok ? "ok" : "bad"}" title="${esc(title || "")}">${ok == null ? "–" : ok ? "✓" : "✕"}</span>`;

  KP.views.integrity = async function (params, root) {
    KP.setCtx({ view: "integrity" });
    const d = await KP.api("/api/integrity");
    const bad = d.batches.filter((b) => !b.verify.all_ok && b.status !== "running").length;
    root.innerHTML = `<div class="page wide" style="max-width:1400px">
      ${KP.head("Data integrity", "Is every byte still what was written?", "Hashes are re-computed now, every time you open this page. Batches are written once; only <span class='mono'>human_labels.jsonl</span> is appended later, and it is listed separately.",
        `<button class="btn" id="reverify">Verify again</button>`)}
      <div class="card pad" style="margin-bottom:22px;display:grid;grid-template-columns:repeat(3,1fr);gap:24px">
        <div><h4>PREREG.md now</h4><div class="hash">${esc(d.prereg_current || "missing")}</div></div>
        <div><h4>Signed at gate 1</h4><div class="hash">${esc(d.prereg_signed || "not signed yet")}</div>${d.prereg_signed ? (d.prereg_signed === d.prereg_current ? '<span class="pill ok" style="margin-top:8px">matches</span>' : '<span class="pill bad" style="margin-top:8px">PREREG changed since sign-off</span>') : ""}</div>
        <div><h4>Summary</h4><div class="small"><b class="num">${d.batches.filter((b) => !b.fake).length}</b> real batches · <b class="num">${d.batches.filter((b) => b.fake).length}</b> FAKE fixtures<br>${bad ? `<span class="c-leak"><b>${bad}</b> batch${bad > 1 ? "es" : ""} failing verification</span>` : '<span class="c-report">every closed batch verifies</span>'}<br><b class="num">${d.batches.filter((b) => b.analysed).length}</b> batch(es) eligible for analysis</div></div>
      </div>
      <div class="card"><table class="t"><thead><tr><th></th><th>Batch</th><th>Kind</th><th>Status</th><th class="r">Episodes</th><th>SHA256SUMS now</th><th>PREREG hash</th><th>Analysed?</th><th>On disk</th></tr></thead><tbody>
        ${d.batches.map((b, k) => {
          const v = b.verify, okN = v.files.filter((f) => f.ok).length;
          const pre = b.manifest.prereg_sha256;
          return `<tr class="click" data-k="${k}"><td style="width:28px">${b.status === "running" ? '<span class="pulse"></span>' : tick(v.all_ok, v.has_sums ? "" : "no SHA256SUMS yet")}</td>
            <td class="mono small">${esc(b.batch_id)} ${KP.fake(b.fake)}</td><td>${esc(b.kind)}</td>
            <td><span class="pill ${b.status === "complete" ? "ok" : b.status === "running" ? "warn" : "bad"}">${esc(b.status)}</span></td>
            <td class="r num"${KP.src(b.path + "/episodes.jsonl")}>${b.n_episodes}${b.n_planned != null && b.n_planned !== b.n_episodes ? `<span class="muted"> / ${b.n_planned}</span>` : ""}${b.bad_lines ? ` <span class="c-leak" title="unparsable lines">+${b.bad_lines}!</span>` : ""}</td>
            <td class="small">${v.has_sums ? `${okN}/${v.files.length} match${v.extra.filter((x) => !x.reviewer_file).length ? ` · <span class="c-leak">${v.extra.filter((x) => !x.reviewer_file).length} unlisted</span>` : ""}` : '<span class="muted">not written yet</span>'}</td>
            <td class="small">${pre ? `<span class="mono"${KP.src(b.path + "/manifest.json")}>${KP.short(pre, 10)}</span> ${b.prereg_match_signed ? '<span class="pill ok">signed</span>' : b.prereg_match_current ? '<span class="pill warn">current, unsigned</span>' : '<span class="pill bad">differs</span>'}` : '<span class="muted mono">null</span>'}</td>
            <td>${b.analysed ? '<span class="pill ok">yes</span>' : `<span class="pill line" title="${b.fake ? "FAKE fixture" : b.kind === "smoke" ? "smoke batches are never analysed" : "needs kind pilot/main and the signed PREREG hash"}">no</span>`}</td>
            <td class="path">${esc(b.path)}</td></tr>
            <tr class="hidden" id="x-${k}"><td></td><td colspan="8"><div class="filelist" style="padding:8px 0 14px">
              ${v.files.map((f) => `<div>${tick(f.ok, f.reason)}<span>${esc(f.file)}${f.ok ? "" : ` <span class="c-leak">${esc(f.reason)}</span>`}</span><span class="faint">${KP.short(f.actual || f.expected, 16)}</span></div>`).join("")}
              ${v.extra.map((f) => `<div>${f.reviewer_file ? '<span class="tick na">+</span>' : tick(false)}<span>${esc(f.file)} <span class="${f.reviewer_file ? "muted" : "c-leak"}">${f.reviewer_file ? "reviewer file, append-only, not in SHA256SUMS" : "not listed in SHA256SUMS"}</span></span><span class="faint">${KP.short(f.sha256, 16)}</span></div>`).join("")}
              <div class="tiny muted" style="border:0;padding-top:10px">manifest: created ${esc(b.manifest.created_utc)} · git ${esc(KP.short(b.manifest.git_commit, 10))} · data seed ${esc(b.manifest.data_seed)} · notes: ${esc(b.manifest.notes || "")}</div>
            </div></td></tr>`;
        }).join("")}</tbody></table></div>
      <h3 style="margin-top:34px">Every other file that matters</h3>
      <div class="card"><table class="t"><thead><tr><th>File</th><th>sha256</th><th class="r">Bytes</th><th>On disk</th></tr></thead><tbody>
        ${d.files.map((f) => `<tr><td class="mono small">${esc(f.file)}</td><td>${f.exists ? `<span class="mono tiny">${KP.short(f.sha256, 24)}</span>` : '<span class="muted small">not created yet</span>'}</td><td class="r num small">${f.bytes || ""}</td><td class="path">${esc(f.path)}</td></tr>`).join("")}
      </tbody></table></div>
      <p class="small muted" style="margin-top:14px">Runs: <span class="mono">${esc(d.runs_dir)}</span> · FAKE fixtures: <span class="mono">${esc(d.fixtures_dir)}</span> (never read by analysis) · Review log: <span class="mono">${esc(d.review_log)}</span></p>
    </div>`;
    KP.$$("tr.click", root).forEach((tr) => tr.addEventListener("click", () => KP.$("#x-" + tr.dataset.k).classList.toggle("hidden")));
    KP.$("#reverify").addEventListener("click", () => { KP.toast("Re-hashing every file…"); KP.go("#/integrity"); });
  };
})();
