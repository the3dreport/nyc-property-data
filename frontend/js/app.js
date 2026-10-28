(function () {
  const API = "/api/v1";

  function isBbl(q) {
    const d = String(q).replace(/\D/g, "");
    return d.length === 10;
  }

  async function search(q) {
    if (isBbl(q)) {
      window.location.href = `/property?bbl=${encodeURIComponent(q.replace(/\D/g, ""))}`;
      return [];
    }
    const r = await fetch(`${API}/search?q=${encodeURIComponent(q)}`);
    if (!r.ok) throw new Error(await r.text());
    return (await r.json()).results || [];
  }

  function renderResults(el, results) {
    if (!results.length) {
      el.hidden = false;
      el.innerHTML = `<div class="empty" style="margin:8px">No matches with a BBL. Try a fuller address.</div>`;
      return;
    }
    el.hidden = false;
    el.innerHTML = results
      .map(
        (h) => `
      <button type="button" class="result-item" data-bbl="${h.bbl || ""}">
        <div>${escapeHtml(h.label || h.address)}</div>
        <div class="meta">BBL ${h.bbl || "—"} · ${escapeHtml(h.borough || "")} ${h.postalcode || ""}</div>
      </button>`
      )
      .join("");
    el.querySelectorAll("[data-bbl]").forEach((btn) => {
      btn.addEventListener("click", () => {
        const bbl = btn.getAttribute("data-bbl");
        if (bbl) window.location.href = `/property?bbl=${encodeURIComponent(bbl)}`;
      });
    });
  }

  function escapeHtml(s) {
    return String(s || "")
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  }

  async function runSearch(q) {
    const resultsEl = document.getElementById("results");
    if (!resultsEl) return;
    resultsEl.hidden = false;
    resultsEl.innerHTML = `<div class="loading"><div class="spinner"></div> Searching…</div>`;
    try {
      const results = await search(q);
      if (results) renderResults(resultsEl, results);
    } catch (e) {
      resultsEl.innerHTML = `<div class="error">${escapeHtml(e.message)}</div>`;
    }
  }

  function bindLanding() {
    const form = document.getElementById("search-form");
    if (!form) return;
    form.addEventListener("submit", (e) => {
      e.preventDefault();
      const q = document.getElementById("q").value.trim();
      if (q) runSearch(q);
    });
  }

  window.NYCProp = { API, search, runSearch, isBbl, escapeHtml };
  document.addEventListener("DOMContentLoaded", bindLanding);
})();
