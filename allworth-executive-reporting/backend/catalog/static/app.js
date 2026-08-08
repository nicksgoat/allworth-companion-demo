/* Data Catalog SPA — vanilla JS, talks to /catalog/api/*. */
(() => {
  "use strict";
  const BASE = window.CATALOG_BASE || "/catalog";
  const $ = (sel, root = document) => root.querySelector(sel);
  const $$ = (sel, root = document) => Array.from(root.querySelectorAll(sel));
  const esc = (s) =>
    String(s == null ? "" : s).replace(/[&<>"']/g, (c) =>
      ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c])
    );

  const state = {
    q: "",
    domain: "",
    schema: "",
    kind: "",
    pii: false,
    hideDep: false,
    selected: null,
  };

  async function api(path) {
    const res = await fetch(BASE + path, { headers: { Accept: "application/json" } });
    if (!res.ok) throw new Error(`${res.status} ${path}`);
    return res.json();
  }

  // ── Tables list + facets ─────────────────────────────────
  let debounce;
  function scheduleLoad() {
    clearTimeout(debounce);
    debounce = setTimeout(loadTables, 180);
  }

  async function loadTables() {
    const params = new URLSearchParams();
    if (state.q) params.set("q", state.q);
    if (state.domain) params.set("domain", state.domain);
    if (state.schema) params.set("schema", state.schema);
    if (state.kind) params.set("kind", state.kind);
    if (state.pii) params.set("pii", "1");
    params.set("deprecated", state.hideDep ? "0" : "1");
    const data = await api("/api/tables?" + params.toString());
    renderFacets(data.facets);
    renderList(data.tables, data.count);
  }

  function renderFacets(f) {
    const dom = $("#facet-domain");
    dom.innerHTML = f.domains
      .map(
        (d) =>
          `<span class="chip${state.domain === d.value ? " active" : ""}" data-domain="${esc(
            d.value
          )}">${esc(d.value)}<span class="n">${d.count}</span></span>`
      )
      .join("");
    const sch = $("#facet-schema");
    sch.innerHTML = f.schemas
      .map(
        (s) =>
          `<span class="chip${state.schema === s.value ? " active" : ""}" data-schema="${esc(
            s.value
          )}">${esc(s.value)}<span class="n">${s.count}</span></span>`
      )
      .join("");
    $("#stat").textContent = `${f.total} tables · ${f.deprecated} deprecated · ${f.pii} with PII`;
  }

  function renderList(tables, count) {
    $("#count").textContent = `${count} table${count === 1 ? "" : "s"}`;
    $("#list").innerHTML = tables
      .map(
        (t) => `
      <div class="card${state.selected === t.id ? " selected" : ""}" data-id="${t.id}">
        <div class="top">
          <span class="name">${esc(t.name)}</span>
          <span class="badge domain">${esc(t.domain || "")}</span>
        </div>
        ${t.business_name ? `<div class="biz">${esc(t.business_name)}</div>` : ""}
        <div class="meta">
          <span>${t.column_count} cols</span>
          <span>${t.measure_count} measures</span>
          ${t.deprecated ? '<span class="badge dep">deprecated</span>' : ""}
          ${t.has_pii ? '<span class="badge pii">PII</span>' : ""}
        </div>
      </div>`
      )
      .join("");
  }

  // ── Detail ───────────────────────────────────────────────
  async function loadDetail(id) {
    state.selected = id;
    $$(".card").forEach((c) => c.classList.toggle("selected", c.dataset.id === id));
    const t = await api("/api/tables/" + id);
    renderDetail(t);
  }

  function relRow(r, dir) {
    const arrow = dir === "out" ? "→" : "←";
    const card = r.one_to_one ? "1:1" : r.type || "";
    return `<div class="rel">
      <span>${arrow}</span>
      <a data-goto="${esc(r.to_id || r.from_id)}">${esc(r.to || r.from)}</a>
      <span class="card-badge">${esc(card)}</span>
      <span class="on">${esc(r.on || "")}</span>
    </div>`;
  }

  function renderDetail(t) {
    const d = $("#detail");
    d.classList.remove("empty");
    const cols = (t.columns || [])
      .map(
        (c) => `<tr class="${c.hot ? "hot" : ""}">
        <td><span class="col-name" data-col="${esc(c.name)}">${esc(c.name)}</span></td>
        <td><span class="type">${esc(c.data_type || "")}</span></td>
        <td class="k-${c.kind}">${c.kind === "measure" ? "Σ " + esc(c.aggregation || "measure") : "attribute"}</td>
        <td>${c.pii ? '<span class="dot-pii">PII</span>' : ""}</td>
        <td>${esc(c.description || "")}</td>
      </tr>`
      )
      .join("");

    const out = (t.relationships || []).filter((r) => r.to).map((r) => relRow(r, "out")).join("");
    const inb = (t.inbound_relationships || []).map((r) => relRow(r, "in")).join("");
    const ws = (t.worksheets || [])
      .map((w) => `<span class="ws-tag" data-ws="${esc(w)}">${esc(w)}</span>`)
      .join("");

    d.innerHTML = `
      <h2>${esc(t.name)}${t.deprecated ? ' <span class="badge dep">deprecated</span>' : ""}</h2>
      <div class="sub">${esc(t.business_name || "")}</div>
      <dl class="kv">
        <dt>Schema</dt><dd>${esc(t.schema || "")}.${esc(t.db_table || t.name)}</dd>
        <dt>Grain</dt><dd>${esc(t.grain || "—")}</dd>
        <dt>Primary key</dt><dd>${esc(t.pk || "—")}</dd>
        <dt>Domain</dt><dd>${esc(t.domain || "—")}</dd>
        <dt>Columns</dt><dd>${(t.columns || []).length}</dd>
      </dl>

      <div class="section-h">Description</div>
      <textarea class="edit-area" id="edit-desc" placeholder="Add a business description…">${esc(
        t.description || ""
      )}</textarea>
      <textarea class="edit-area" id="edit-notes" placeholder="Notes / caveats…" style="margin-top:8px">${esc(
        t.notes || ""
      )}</textarea>
      <div class="row-actions">
        <button class="btn primary" id="save-desc">Save</button>
        <span class="saved hidden" id="saved-msg">Saved ✓</span>
      </div>

      <div class="section-h">Columns (${(t.columns || []).length})</div>
      <table class="cols">
        <thead><tr><th>Name</th><th>Type</th><th>Kind</th><th></th><th>Description</th></tr></thead>
        <tbody>${cols}</tbody>
      </table>

      ${out ? `<div class="section-h">Joins out</div>${out}` : ""}
      ${inb ? `<div class="section-h">Referenced by</div>${inb}` : ""}
      ${ws ? `<div class="section-h">Worksheets (${(t.worksheets || []).length})</div><div class="ws-tags">${ws}</div>` : ""}
    `;

    $("#save-desc").addEventListener("click", async () => {
      const btn = $("#save-desc");
      btn.disabled = true;
      try {
        await fetch(BASE + "/api/tables/" + t.id + "/curation", {
          method: "PUT",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            description: $("#edit-desc").value,
            notes: $("#edit-notes").value,
            summary: "edited description",
          }),
        });
        $("#saved-msg").classList.remove("hidden");
        setTimeout(() => $("#saved-msg").classList.add("hidden"), 2000);
      } finally {
        btn.disabled = false;
      }
    });
  }

  // ── Where-used popover ───────────────────────────────────
  async function showWhereUsed(col) {
    const data = await api("/api/columns/" + encodeURIComponent(col) + "/where-used");
    let pop = $("#whereused");
    if (!pop) {
      pop = document.createElement("div");
      pop.id = "whereused";
      Object.assign(pop.style, {
        position: "fixed", right: "24px", bottom: "24px", zIndex: 50,
        background: "#fff", border: "1px solid rgba(0,32,92,.2)", borderRadius: "12px",
        padding: "14px 16px", boxShadow: "0 18px 44px -14px rgba(0,32,92,.3)", maxWidth: "360px",
        maxHeight: "60vh", overflow: "auto", fontSize: "12.5px",
      });
      document.body.appendChild(pop);
    }
    pop.innerHTML =
      `<div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:8px">
         <strong>Where used: <code>${esc(col)}</code></strong>
         <span style="cursor:pointer" id="wu-close">✕</span>
       </div>
       <div>Appears in <b>${data.count}</b> table(s):</div>` +
      data.tables
        .map(
          (t) =>
            `<div style="padding:4px 0"><a data-goto="${esc(t.table_id)}" style="color:#00205C;cursor:pointer;font-weight:600">${esc(
              t.table
            )}</a> <span class="type">${esc(t.data_type || "")} · ${esc(t.kind || "")}</span></div>`
        )
        .join("") +
      (data.joins.length
        ? `<div style="margin-top:8px;color:#8a94a8">Used in ${data.joins.length} join(s)</div>`
        : "");
    $("#wu-close").addEventListener("click", () => pop.remove());
  }

  // ── ER Graph ─────────────────────────────────────────────
  let worksheets = [];
  async function initGraph() {
    if (worksheets.length) return;
    const data = await api("/api/worksheets");
    worksheets = data.worksheets;
    const sel = $("#ws-select");
    sel.innerHTML =
      '<option value="">— whole warehouse (large) —</option>' +
      worksheets
        .map((w) => `<option value="${esc(w.name)}">${esc(w.name)} (${w.table_count})</option>`)
        .join("");
    // default to a representative worksheet
    const def = worksheets.find((w) => w.name === "Rollforward Historical") || worksheets[0];
    if (def) sel.value = def.name;
    renderGraph(sel.value);
  }

  function sanitize(name) {
    return name.replace(/[^A-Za-z0-9_]/g, "_");
  }

  async function renderGraph(ws) {
    const g = await api("/api/graph" + (ws ? "?worksheet=" + encodeURIComponent(ws) : ""));
    const meta = worksheets.find((w) => w.name === ws);
    $("#graph-stat").textContent = `${g.nodes.length} tables · ${g.edges.length} joins`;
    $("#graph-desc").textContent = meta ? meta.description : "";

    const idToName = {};
    g.nodes.forEach((n) => (idToName[n.id] = n.name));
    let src = "erDiagram\n";
    g.nodes.forEach((n) => {
      src += `  ${sanitize(n.name)} {\n  }\n`;
    });
    const seen = new Set();
    g.edges.forEach((e) => {
      const a = idToName[e.from_id], b = idToName[e.to_id];
      if (!a || !b) return;
      const key = a + "|" + b + "|" + (e.from_col || "");
      if (seen.has(key)) return;
      seen.add(key);
      const rel = e.one_to_one ? "||--||" : "}o--||";
      const label = (e.from_col || "fk").replace(/[^A-Za-z0-9_]/g, "_");
      src += `  ${sanitize(a)} ${rel} ${sanitize(b)} : ${label}\n`;
    });

    const wrap = $("#graph-wrap");
    if (window.MERMAID_FAILED || !window.mermaid) {
      wrap.innerHTML = `<div class="mermaid-src">${esc(src)}</div>`;
      return;
    }
    try {
      window.mermaid.initialize({ startOnLoad: false, theme: "neutral", er: { useMaxWidth: false } });
      const { svg } = await window.mermaid.render("erGraph" + Date.now(), src);
      wrap.innerHTML = svg;
    } catch (err) {
      wrap.innerHTML = `<div class="mermaid-src">${esc(src)}</div>`;
    }
  }

  // ── Glossary ─────────────────────────────────────────────
  let glossaryLoaded = false;
  async function initGlossary() {
    if (glossaryLoaded) return;
    glossaryLoaded = true;
    const data = await api("/api/glossary");
    const g = data.glossary || {};
    $("#gloss").innerHTML = Object.keys(g)
      .sort()
      .map((k) => `<dl><dt>${esc(k)}</dt><dd>${esc(g[k])}</dd></dl>`)
      .join("");
  }
  // ── Sources (systems where the data originates) ─────────
  let sourcesLoaded = false;
  async function initSources() {
    if (sourcesLoaded) return;
    sourcesLoaded = true;
    let data;
    try {
      data = await api("/api/sources");
    } catch (_e) {
      $("#sources").innerHTML = '<div class="muted">Unable to load sources.</div>';
      return;
    }
    const items = data.sources || [];
    if (!items.length) {
      $("#sources").innerHTML = '<div class="muted">No source systems documented yet.</div>';
      return;
    }
    $("#sources").innerHTML = items
      .map((s) => {
        const badges = [s.kind, s.ingestion, s.landing]
          .filter(Boolean)
          .map((b) => `<span class="pill">${esc(b)}</span>`)
          .join(" ");
        const usage = s.column_count
          ? `<div class="sub">Feeds ${s.column_count} documented column${s.column_count === 1 ? "" : "s"} across ${s.table_count} table${s.table_count === 1 ? "" : "s"}${s.tables && s.tables.length ? ": " + esc(s.tables.slice(0, 8).join(", ")) + (s.tables.length > 8 ? "\u2026" : "") : ""}</div>`
          : "";
        const notes = s.notes ? `<div class="muted" style="font-size:12px">${esc(s.notes)}</div>` : "";
        return `<dl><dt>${esc(s.name)} ${badges}</dt><dd>${esc(s.description || "")}${usage}${notes}</dd></dl>`;
      })
      .join("");
  }
  // ── Columns (searchable field dictionary from the TML tables) ──
  let columnsLoaded = false;
  let currentColumn = null;
  let currentTab = "columns";
  let colSearchTimer;

  async function loadColumns() {
    columnsLoaded = true;
    await columnSearch("");
  }

  function scheduleColumnSearch(q) {
    clearTimeout(colSearchTimer);
    colSearchTimer = setTimeout(() => columnSearch(q), 160);
  }

  async function columnSearch(q) {
    const query = (q || "").trim();
    let data;
    try {
      data = await api("/api/columns" + (query ? "?q=" + encodeURIComponent(query) : ""));
    } catch (_e) {
      $("#col-list").innerHTML = '<div class="muted">Unable to load columns.</div>';
      return;
    }
    const cols = data.columns || [];
    $("#col-count").textContent =
      `${data.count} column${data.count === 1 ? "" : "s"}${query ? " matching" : ""}`;
    $("#col-list").innerHTML = cols.length
      ? cols
          .map(
            (c) => `
        <div class="metric-item${currentColumn === c.name ? " selected" : ""}" data-column="${esc(c.name)}">
          <div class="mname">${esc(c.name)} ${c.kinds
              .map(
                (k) =>
                  `<span class="k-${k}" style="font-size:10px;font-weight:700">${
                    k === "measure" ? "Σ" : "A"
                  }</span>`
              )
              .join("")}${c.has_formula ? ' <span class="badge pii" style="font-size:9px">ƒ</span>' : ""}</div>
          <div class="mdesc">${
            c.description
              ? esc(c.description.length > 90 ? c.description.slice(0, 90) + "…" : c.description)
              : `in ${c.worksheet_count} model${c.worksheet_count === 1 ? "" : "s"}`
          }</div>
        </div>`
          )
          .join("")
      : '<div class="muted">No matches.</div>';
  }

  function startFnEdit(box) {
    if (!box) return;
    const name = box.dataset.fn;
    const current = box.dataset.plain || "";
    const plain = box.querySelector(".biz-fn-plain");
    plain.innerHTML =
      `<textarea class="edit-area fn-ta"></textarea>` +
      `<div class="row-actions"><button class="btn primary" data-fn-save="${esc(name)}">Save</button>` +
      `<button class="btn" data-fn-cancel="${esc(name)}">Cancel</button></div>`;
    const ta = plain.querySelector("textarea");
    ta.value = current;
    ta.focus();
  }

  async function saveFnEdit(name, box) {
    const ta = box && box.querySelector("textarea");
    if (!ta) return;
    const res = await fetch(BASE + "/api/business-logic/" + encodeURIComponent(name), {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ plain_english: ta.value, summary: "edited via catalog" }),
    });
    if (!res.ok) {
      alert("Save failed: " + res.status);
      return;
    }
    loadColumnDetail(currentColumn);
  }

  async function loadColumnDetail(name) {
    currentColumn = name;
    switchView("columns");
    $$("[data-column]").forEach((el) =>
      el.classList.toggle("selected", el.dataset.column === name)
    );
    let data;
    try {
      data = await api("/api/column?name=" + encodeURIComponent(name));
    } catch (_e) {
      $("#col-detail").className = "detail empty";
      $("#col-detail").textContent = "Column not found.";
      return;
    }
    renderColumnDetail(data);
  }

  function renderColumnDetail(c) {
    const d = $("#col-detail");
    d.classList.remove("empty");
    // Source systems (Salesforce / Tamarac / …) drawn from the load notebooks.
    const systems = [];
    (c.sources || []).forEach((s) => {
      ((s.logic && s.logic.source_systems) || []).forEach((sys) => {
        if (!systems.includes(sys)) systems.push(sys);
      });
    });
    const sysBadges = systems
      .map((s) => `<span class="badge sys">${esc(s)}</span>`)
      .join(" ");
    const sources = (c.sources || [])
      .map((s) => {
        const head = s.table_id
          ? `<div class="rel"><a data-goto="${esc(s.table_id)}">${esc(s.table)}</a><span class="on">${esc(
              s.column
            )}</span></div>`
          : `<div class="rel"><span>${esc(s.table)}</span><span class="on">${esc(s.column)}</span></div>`;
        const lg = s.logic;
        if (!lg) return head;
        const comments = (lg.comments || []).map((x) => `<div class="logic-cmt"># ${esc(x)}</div>`).join("");
        const fns = (lg.functions || [])
          .map((f) => `<span class="badge domain">${esc(f)}()</span>`)
          .join(" ");
        return (
          head +
          `<div class="logic">${comments}` +
          (lg.source_systems && lg.source_systems.length
            ? `<div class="logic-fns">source: ${lg.source_systems.map((s) => esc(s)).join(", ")}</div>`
            : "") +
          (fns ? `<div class="logic-fns">uses ${fns}</div>` : "") +
          `<pre class="mermaid-src" style="white-space:pre-wrap">${esc(lg.expression || "")}</pre>` +
          `<div class="muted" style="font-size:11px;margin-top:-4px">from ${esc(lg.notebook)}</div></div>`
        );
      })
      .join("");
    const formulas = (c.formulas || [])
      .map(
        (f) =>
          `<pre class="mermaid-src" style="white-space:pre-wrap">${esc(f.expr)}</pre>` +
          `<div class="muted" style="font-size:11px;margin:-6px 0 8px">from ${esc(f.worksheet)}</div>`
      )
      .join("");
    const descs = (c.descriptions || [])
      .map((x) => `<p>${esc(x)}</p>`)
      .join("");
    const ws = (c.worksheets || [])
      .map((w) => `<span class="ws-tag" data-ws="${esc(w)}">${esc(w)}</span>`)
      .join("");
    const bizfns = (c.functions || [])
      .map(
        (f) => `
        <div class="biz-fn" data-fn="${esc(f.name)}" data-plain="${esc(f.plain_english || "")}">
          <div class="biz-fn-h"><code>${esc(f.name)}()</code> <span class="muted">${esc(f.title || "")}</span>
            <button class="biz-fn-edit" data-fn-edit="${esc(f.name)}" title="Edit summary">✎ Edit</button></div>
          <div class="biz-fn-plain">${
            f.plain_english
              ? esc(f.plain_english)
              : '<span class="muted">No plain-English summary yet — click Edit to add one.</span>'
          }</div>
          ${f.description ? `<div class="mdesc">${esc(f.description)}</div>` : ""}
          <details class="biz-fn-code"><summary>Python code</summary><pre class="mermaid-src" style="white-space:pre-wrap;max-height:220px;overflow:auto">${esc(f.source || "")}</pre></details>
        </div>`
      )
      .join("");
    d.innerHTML = `
      <h2>${esc(c.name)} ${(c.kinds || [])
        .map((k) => `<span class="k-${k}" style="font-size:11px;font-weight:700">${k}</span>`)
        .join(" ")}</h2>
      <div class="sub">Appears in ${(c.worksheets || []).length} model${
      (c.worksheets || []).length === 1 ? "" : "s"
    }</div>
      ${sysBadges ? `<div style="margin:6px 0">${sysBadges}</div>` : ""}
      ${descs ? `<div class="section-h">Description</div><div class="prose">${descs}</div>` : ""}
      ${sources ? `<div class="section-h">Sourced from &amp; derivation</div>${sources}` : ""}
      ${formulas ? `<div class="section-h">Worksheet formula</div>${formulas}` : ""}
      ${bizfns ? `<div class="section-h">Business logic functions</div>${bizfns}` : ""}
      ${ws ? `<div class="section-h">Models (${(c.worksheets || []).length})</div><div class="ws-tags">${ws}</div>` : ""}
    `;
  }

  // ── Wiring ───────────────────────────────────────────────
  function switchView(name) {
    currentTab = name;
    $$(".tab").forEach((t) => t.classList.toggle("active", t.dataset.view === name));
    $$(".view").forEach((v) => (v.hidden = v.dataset.view !== name));
    // Reflect the active surface in the rail search placeholder.
    const q = $("#q");
    if (q) q.placeholder = name === "columns"
      ? "Search columns / fields…"
      : "Search tables, columns, synonyms…";
    if (name === "columns" && !columnsLoaded) loadColumns();
    if (name === "graph") initGraph();
    if (name === "glossary") initGlossary();
    if (name === "sources") initSources();
  }

  document.addEventListener("click", (e) => {
    const chipD = e.target.closest("[data-domain]");
    const chipS = e.target.closest("[data-schema]");
    const chipK = e.target.closest("[data-kind]");
    const card = e.target.closest(".card");
    const goto = e.target.closest("[data-goto]");
    const col = e.target.closest("[data-col]");
    const wsTag = e.target.closest("[data-ws]");
    const tab = e.target.closest(".tab");
    const metricItem = e.target.closest("[data-metric]");
    const metricGoto = e.target.closest("[data-metric-goto]");
    const metricGotoTable = e.target.closest("[data-metric-goto-table]");
    const columnItem = e.target.closest("[data-column]");

    if (columnItem) return void loadColumnDetail(columnItem.dataset.column);

    // Business-logic function summary editing
    const fnEdit = e.target.closest("[data-fn-edit]");
    if (fnEdit) return void startFnEdit(fnEdit.closest(".biz-fn"));
    const fnSave = e.target.closest("[data-fn-save]");
    if (fnSave) return void saveFnEdit(fnSave.dataset.fnSave, fnSave.closest(".biz-fn"));
    const fnCancel = e.target.closest("[data-fn-cancel]");
    if (fnCancel) return void loadColumnDetail(currentColumn);

    if (metricGotoTable) {
      switchView("tables");
      loadDetail(metricGotoTable.dataset.metricGotoTable);
      return;
    }
    if (metricGoto) {
      loadColumnDetail(metricGoto.dataset.metricGoto);
      return;
    }
    if (metricItem) return;

    if (tab) switchView(tab.dataset.view);
    else if (chipD) {
      state.domain = state.domain === chipD.dataset.domain ? "" : chipD.dataset.domain;
      loadTables();
    } else if (chipS) {
      state.schema = state.schema === chipS.dataset.schema ? "" : chipS.dataset.schema;
      loadTables();
    } else if (chipK) {
      state.kind = state.kind === chipK.dataset.kind ? "" : chipK.dataset.kind;
      $$("#facet-kind .chip").forEach((c) =>
        c.classList.toggle("active", c.dataset.kind === state.kind)
      );
      loadTables();
    } else if (goto) {
      switchView("tables");
      loadDetail(goto.dataset.goto);
      const wu = $("#whereused");
      if (wu) wu.remove();
    } else if (col) {
      showWhereUsed(col.dataset.col);
    } else if (wsTag) {
      switchView("graph");
      initGraph().then(() => {
        $("#ws-select").value = wsTag.dataset.ws;
        renderGraph(wsTag.dataset.ws);
      });
    } else if (card) {
      loadDetail(card.dataset.id);
    }
  });

  $("#q").addEventListener("input", (e) => {
    // The rail search follows the active tab: columns on the Columns tab,
    // tables everywhere else.
    if (currentTab === "columns") {
      const cq = $("#col-q");
      if (cq) cq.value = e.target.value;
      scheduleColumnSearch(e.target.value);
      return;
    }
    state.q = e.target.value.trim();
    scheduleLoad();
  });
  $("#pii-only").addEventListener("change", (e) => {
    state.pii = e.target.checked;
    loadTables();
  });
  $("#hide-dep").addEventListener("change", (e) => {
    state.hideDep = e.target.checked;
    loadTables();
  });
  $("#ws-select").addEventListener("change", (e) => renderGraph(e.target.value));

  const colQ = $("#col-q");
  if (colQ) colQ.addEventListener("input", (e) => scheduleColumnSearch(e.target.value));

  // ── Boot ─────────────────────────────────────────────────
  $("#q").placeholder = "Search columns / fields…";
  loadColumns();
  loadTables();
  api("/api/me").then((m) => ($("#me").textContent = "Signed in as " + (m.user || "—"))).catch(() => {});
})();
