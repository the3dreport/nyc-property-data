(function () {
  const { API, escapeHtml, isBbl, search } = window.NYCProp;

  function money(v) {
    if (v == null || v === "") return "—";
    const n = Number(v);
    if (Number.isNaN(n)) return String(v);
    return n.toLocaleString("en-US", { style: "currency", currency: "USD", maximumFractionDigits: 0 });
  }
  function num(v) {
    if (v == null || v === "") return "—";
    const n = Number(v);
    return Number.isNaN(n) ? String(v) : n.toLocaleString("en-US");
  }
  function dateish(v) {
    if (!v) return "—";
    return String(v).slice(0, 10);
  }
  function partyType(t) {
    return ({ "1": "Party 1", "2": "Party 2", "3": "Party 3" }[String(t)] || `Type ${t}`);
  }

  function sectionMeta(sec) {
    const bits = [sec.source];
    if (sec.dataset_id) bits.push(`dataset ${sec.dataset_id}`);
    bits.push(`${sec.count} record${sec.count === 1 ? "" : "s"}`);
    return `<div class="section-meta">${escapeHtml(bits.join(" · "))}</div>`;
  }
  function emptyOrError(sec) {
    if (sec.error) return `<div class="error">${escapeHtml(sec.error)}</div>`;
    if (!sec.count) return `<div class="empty">${escapeHtml(sec.note || "No records.")}</div>`;
    return null;
  }

  function renderOverview(data) {
    const s = data.summary || {};
    const p = data.pluto;
    const rows = [
      ["Owner (PLUTO)", s.ownername],
      ["Building class", s.bldgclass],
      ["Land use", s.landuse],
      ["Zoning", [s.zonedist1, s.zonedist2].filter(Boolean).join(" / ")],
      ["Year built", s.yearbuilt],
      ["Floors", s.numfloors],
      ["Res / total units", `${s.unitsres ?? "—"} / ${s.unitstotal ?? "—"}`],
      ["Lot / bldg area (sq ft)", `${num(s.lotarea)} / ${num(s.bldgarea)}`],
      ["Assessed land / total", `${money(s.assessland)} / ${money(s.assesstot)}`],
      ["Built FAR", s.builtfar],
      ["Landmark", s.landmark || "—"],
    ];
    let html = sectionMeta(p);
    const ee = emptyOrError(p);
    if (ee) return html + ee;
    html += `<table class="data"><tbody>${rows
      .map(([k, v]) => `<tr><th>${escapeHtml(k)}</th><td>${escapeHtml(v ?? "—")}</td></tr>`)
      .join("")}</tbody></table>`;
    if (p.note) html += `<p class="section-meta">${escapeHtml(p.note)}</p>`;
    return html;
  }

  function renderAssessment(sec) {
    let html = sectionMeta(sec);
    const ee = emptyOrError(sec);
    if (ee) return html + ee;
    html += `<table class="data"><thead><tr>
      <th>Year</th><th>Period</th><th>Tax class</th><th>Full market</th><th>Assessed land</th><th>Assessed total</th><th>Owner</th>
    </tr></thead><tbody>`;
    for (const r of sec.records) {
      html += `<tr>
        <td>${escapeHtml(r.year)}</td>
        <td>${escapeHtml(r.period)}</td>
        <td>${escapeHtml(r.taxclass)}</td>
        <td>${money(r.fullval)}</td>
        <td>${money(r.avland)}</td>
        <td>${money(r.avtot)}</td>
        <td>${escapeHtml(r.owner)}</td>
      </tr>`;
    }
    return html + "</tbody></table>";
  }

  function renderAcris(sec) {
    let html = sectionMeta(sec);
    const ee = emptyOrError(sec);
    if (ee) return html + ee;
    html += `<table class="data"><thead><tr>
      <th>Date</th><th>Type</th><th>Amount</th><th>Document</th><th>Parties</th>
    </tr></thead><tbody>`;
    for (const r of sec.records) {
      const parties = (r.parties || [])
        .map((p) => `${partyType(p.party_type)}: ${p.name || "—"}`)
        .join("<br/>");
      html += `<tr>
        <td>${dateish(r.document_date)}</td>
        <td><span class="pill">${escapeHtml(r.doc_type || "—")}</span></td>
        <td>${money(r.document_amt)}</td>
        <td><code>${escapeHtml(r.document_id)}</code><div class="section-meta">CRFN ${escapeHtml(r.crfn || "—")}</div></td>
        <td>${parties || "—"}</td>
      </tr>`;
    }
    return html + "</tbody></table>";
  }

  function renderDob(data) {
    const permits = data.dob_permits;
    const jobs = data.dob_jobs;
    let html = `<h3 style="margin:0 0 8px">Permits</h3>` + sectionMeta(permits);
    let ee = emptyOrError(permits);
    if (ee) html += ee;
    else {
      html += `<table class="data"><thead><tr>
        <th>Issued</th><th>Type</th><th>Status</th><th>Job #</th><th>Permittee</th><th>Owner</th>
      </tr></thead><tbody>`;
      for (const r of permits.records) {
        html += `<tr>
          <td>${escapeHtml(r.issuance_date || "—")}</td>
          <td>${escapeHtml(r.permit_type || "")} ${escapeHtml(r.permit_subtype || "")}</td>
          <td>${escapeHtml(r.permit_status || "—")}</td>
          <td>${escapeHtml(r.job__ || "—")}</td>
          <td>${escapeHtml([r.permittee_s_first_name, r.permittee_s_last_name].filter(Boolean).join(" "))}
            <div class="section-meta">${escapeHtml(r.permittee_s_business_name || "")}</div></td>
          <td>${escapeHtml(r.owner_s_business_name || [r.owner_s_first_name, r.owner_s_last_name].filter(Boolean).join(" "))}</td>
        </tr>`;
      }
      html += "</tbody></table>";
    }
    html += `<h3 style="margin:22px 0 8px">Job filings</h3>` + sectionMeta(jobs);
    ee = emptyOrError(jobs);
    if (ee) html += ee;
    else {
      html += `<table class="data"><thead><tr>
        <th>Filed</th><th>Job</th><th>Type</th><th>Status</th><th>Applicant</th>
      </tr></thead><tbody>`;
      for (const r of jobs.records) {
        html += `<tr>
          <td>${escapeHtml(r.pre__filing_date || "—")}</td>
          <td>${escapeHtml(r.job__ || "—")}</td>
          <td>${escapeHtml(r.job_type || "—")}</td>
          <td>${escapeHtml(r.job_status_descrp || r.job_status || "—")}</td>
          <td>${escapeHtml([r.applicant_s_first_name, r.applicant_s_last_name].filter(Boolean).join(" "))}</td>
        </tr>`;
      }
      html += "</tbody></table>";
    }
    return html;
  }

  function renderViolations(data) {
    const dob = data.dob_violations;
    const ecb = data.dob_ecb;
    const hpd = data.hpd_violations;
    let html = `<h3 style="margin:0 0 8px">DOB violations</h3>` + sectionMeta(dob);
    let ee = emptyOrError(dob);
    if (ee) html += ee;
    else {
      html += `<table class="data"><thead><tr><th>Issued</th><th>Number</th><th>Category</th><th>Type</th><th>Description</th></tr></thead><tbody>`;
      for (const r of dob.records) {
        const cat = (r.violation_category || "").toLowerCase();
        const cls = cat.includes("active") ? "open" : cat.includes("resolv") ? "resolved" : "";
        html += `<tr>
          <td>${escapeHtml(r.issue_date || "—")}</td>
          <td>${escapeHtml(r.number || "—")}</td>
          <td><span class="pill ${cls}">${escapeHtml(r.violation_category || "—")}</span></td>
          <td>${escapeHtml((r.violation_type || "").trim().slice(0, 40))}</td>
          <td>${escapeHtml(r.description || r.disposition_comments || "—")}</td>
        </tr>`;
      }
      html += "</tbody></table>";
    }
    html += `<h3 style="margin:22px 0 8px">ECB / OATH</h3>` + sectionMeta(ecb);
    ee = emptyOrError(ecb);
    if (ee) html += ee;
    else {
      html += `<table class="data"><thead><tr><th>Issued</th><th>ECB #</th><th>Status</th><th>Severity</th><th>Description</th></tr></thead><tbody>`;
      for (const r of ecb.records) {
        const st = (r.ecb_violation_status || "").toLowerCase();
        html += `<tr>
          <td>${escapeHtml(r.issue_date || "—")}</td>
          <td>${escapeHtml(r.ecb_violation_number || "—")}</td>
          <td><span class="pill ${st === "resolve" || st === "resolved" ? "resolved" : "open"}">${escapeHtml(r.ecb_violation_status || "—")}</span></td>
          <td>${escapeHtml(r.severity || "—")}</td>
          <td>${escapeHtml((r.violation_description || "").slice(0, 180))}</td>
        </tr>`;
      }
      html += "</tbody></table>";
    }
    html += `<h3 style="margin:22px 0 8px">HPD violations</h3>` + sectionMeta(hpd);
    ee = emptyOrError(hpd);
    if (ee) html += ee;
    else {
      html += `<table class="data"><thead><tr><th>Inspected</th><th>Class</th><th>Status</th><th>Description</th></tr></thead><tbody>`;
      for (const r of hpd.records) {
        const open = (r.violationstatus || "").toLowerCase() === "open";
        html += `<tr>
          <td>${dateish(r.inspectiondate)}</td>
          <td>${escapeHtml(r.class || "—")}</td>
          <td><span class="pill ${open ? "open" : "closed"}">${escapeHtml(r.violationstatus || r.currentstatus || "—")}</span></td>
          <td>${escapeHtml(r.novdescription || "—")}</td>
        </tr>`;
      }
      html += "</tbody></table>";
    }
    return html;
  }

  function renderHpd(data) {
    const regs = data.hpd_registrations;
    const contacts = data.hpd_contacts;
    let html = `<h3 style="margin:0 0 8px">Registrations</h3>` + sectionMeta(regs);
    let ee = emptyOrError(regs);
    if (ee) html += ee;
    else {
      html += `<table class="data"><thead><tr><th>ID</th><th>Address</th><th>Last registered</th><th>Expires</th></tr></thead><tbody>`;
      for (const r of regs.records) {
        html += `<tr>
          <td>${escapeHtml(r.registrationid)}</td>
          <td>${escapeHtml([r.housenumber, r.streetname].filter(Boolean).join(" "))}</td>
          <td>${dateish(r.lastregistrationdate)}</td>
          <td>${dateish(r.registrationenddate)}</td>
        </tr>`;
      }
      html += "</tbody></table>";
    }
    html += `<h3 style="margin:22px 0 8px">Registration contacts</h3>` + sectionMeta(contacts);
    if (contacts.note) html += `<div class="empty" style="margin-bottom:10px">${escapeHtml(contacts.note)}</div>`;
    ee = emptyOrError(contacts);
    if (ee && !contacts.count) html += ee;
    else if (contacts.count) {
      html += `<table class="data"><thead><tr><th>Type</th><th>Name / Corp</th><th>Title</th><th>Business address</th></tr></thead><tbody>`;
      for (const r of contacts.records) {
        const name = [r.firstname, r.lastname].filter(Boolean).join(" ") || r.corporationname || "—";
        const corp = r.corporationname && (r.firstname || r.lastname) ? r.corporationname : "";
        const addr = [r.businesshousenumber, r.businessstreetname, r.businessapartment, r.businesscity, r.businessstate, r.businesszip]
          .filter(Boolean)
          .join(", ");
        html += `<tr>
          <td>${escapeHtml(r.type || "—")}</td>
          <td>${escapeHtml(name)}${corp ? `<div class="section-meta">${escapeHtml(corp)}</div>` : ""}</td>
          <td>${escapeHtml(r.title || r.contactdescription || "—")}</td>
          <td>${escapeHtml(addr || "—")}</td>
        </tr>`;
      }
      html += "</tbody></table>";
    }
    return html;
  }


  function renderOwner(data) {
    let html = "";
    html += `<div class="section-meta">Owner identities consolidated from PLUTO, latest ACRIS deed grantee, and HPD registration contacts. Portfolio matches use normalized names + shared mailing addresses (capped, cached ~10 min).</div>`;
    if (data.notes && data.notes.length) {
      html += `<div class="empty" style="margin-bottom:14px">${data.notes.map(escapeHtml).join("<br/>")}${data.cached ? "<br/><em>Served from cache.</em>" : ""}</div>`;
    }
    html += `<h3 style="margin:0 0 8px">Identities on this lot</h3>`;
    const idents = data.identities || [];
    if (!idents.length) {
      html += `<div class="empty">No owner identities found.</div>`;
    } else {
      for (const id of idents) {
        html += `<div class="owner-card">
          <h4>${escapeHtml(id.name)}</h4>
          <div class="meta">
            <span class="pill">${escapeHtml(id.role)}</span>
            <span class="pill">${escapeHtml(id.source)}</span>
            ${id.normalized ? `<div>Normalized: <code>${escapeHtml(id.normalized)}</code></div>` : ""}
            ${id.address ? `<div>Mailing: ${escapeHtml(id.address)}</div>` : ""}
            ${id.document_date ? `<div>Deed date: ${dateish(id.document_date)} · ${escapeHtml(id.doc_type || "")}</div>` : ""}
          </div>
        </div>`;
      }
    }

    html += `<h3 style="margin:22px 0 8px">Other properties (portfolio)</h3>`;
    html += `<div class="confidence-legend">
      <span class="pill exact">exact name</span>
      <span class="pill fuzzy">fuzzy name</span>
      <span class="pill address">shared mailing address</span>
      <span class="pill current">this property</span>
    </div>`;
    html += `<div class="section-meta">${data.other_properties_count || 0} other lot(s) · ${data.portfolio_count || 0} total including current</div>`;
    const rows = data.portfolio || [];
    if (!rows.length) {
      html += `<div class="empty">No related properties found under these names.</div>`;
      return html;
    }
    html += `<table class="data"><thead><tr>
      <th>Address</th><th>Borough</th><th>BBL</th><th>Matched as</th><th>Source</th><th>Confidence</th>
    </tr></thead><tbody>`;
    for (const r of rows) {
      const conf = r.confidence || "fuzzy";
      const pill = r.is_current ? "current" : conf === "exact" ? "exact" : conf === "shared_address" ? "address" : "fuzzy";
      const label = r.is_current ? "this property" : conf.replace("_", " ");
      html += `<tr>
        <td>${r.is_current ? escapeHtml(r.address || "—") : `<a href="${escapeHtml(r.url || `/property?bbl=${r.bbl}`)}">${escapeHtml(r.address || r.bbl)}</a>`}</td>
        <td>${escapeHtml(r.borough || "—")}</td>
        <td><a href="/property?bbl=${escapeHtml(r.bbl)}"><code>${escapeHtml(r.bbl)}</code></a></td>
        <td>${escapeHtml(r.matched_name || "—")}</td>
        <td>${escapeHtml(r.match_source || "—")}</td>
        <td><span class="pill ${pill}">${escapeHtml(label)}</span></td>
      </tr>`;
    }
    html += `</tbody></table>`;
    return html;
  }

  function fillStats(s) {
    const items = [
      ["BBL", s.bbl],
      ["Owner", s.ownername || "—"],
      ["Year built", s.yearbuilt || "—"],
      ["Zoning", s.zonedist1 || "—"],
      ["Assessed total", money(s.assesstot)],
      ["Units", s.unitstotal ?? "—"],
    ];
    document.getElementById("stats").innerHTML = items
      .map(([k, v]) => `<div class="stat"><div class="k">${escapeHtml(k)}</div><div class="v">${escapeHtml(v)}</div></div>`)
      .join("");
  }

  function initMap(lat, lon, label) {
    const el = document.getElementById("map");
    if (lat == null || lon == null) {
      el.innerHTML = `<div class="empty" style="height:100%;display:grid;place-items:center">No coordinates</div>`;
      return;
    }
    const map = L.map(el).setView([lat, lon], 17);
    L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
      attribution: "&copy; OpenStreetMap",
      maxZoom: 19,
    }).addTo(map);
    L.marker([lat, lon]).addTo(map).bindPopup(escapeHtml(label || "Property"));
    setTimeout(() => map.invalidateSize(), 100);
  }

  let ownerLoaded = false;
  let ownerBbl = null;

  async function loadOwnerTab(bbl) {
    const panel = document.getElementById("panel-owner");
    if (ownerLoaded && ownerBbl === bbl) return;
    panel.innerHTML = `<div class="loading"><div class="spinner"></div> Resolving owner identities &amp; portfolio…</div>`;
    try {
      const r = await fetch(`${API}/property/${bbl}/owners`);
      if (!r.ok) throw new Error(await r.text());
      const data = await r.json();
      panel.innerHTML = renderOwner(data);
      ownerLoaded = true;
      ownerBbl = bbl;
    } catch (e) {
      panel.innerHTML = `<div class="error">${escapeHtml(e.message || String(e))}</div>`;
    }
  }

  function bindTabs(bbl) {
    document.querySelectorAll(".tab").forEach((tab) => {
      tab.addEventListener("click", () => {
        document.querySelectorAll(".tab").forEach((t) => t.classList.remove("active"));
        tab.classList.add("active");
        const id = tab.getAttribute("data-tab");
        ["overview", "assessment", "acris", "dob", "violations", "hpd", "owner"].forEach((name) => {
          document.getElementById(`panel-${name}`).hidden = name !== id;
        });
        if (id === "owner") loadOwnerTab(bbl);
      });
    });
  }

  async function load() {
    const params = new URLSearchParams(location.search);
    let bbl = params.get("bbl");
    if (!bbl) {
      const _load2 = document.getElementById("page-loading"); _load2.hidden = true; _load2.style.display = "none";
      document.getElementById("page-error").hidden = false;
      document.getElementById("page-error").textContent = "Missing ?bbl= parameter.";
      return;
    }
    bbl = bbl.replace(/\D/g, "");
    try {
      const r = await fetch(`${API}/property/${bbl}`);
      if (!r.ok) throw new Error(await r.text());
      const data = await r.json();
      const s = data.summary || {};
      const _load = document.getElementById("page-loading"); _load.hidden = true; _load.style.display = "none";
      document.getElementById("page-content").hidden = false;
      document.getElementById("addr").textContent = s.address || `BBL ${data.bbl}`;
      document.title = `${s.address || data.bbl} — NYC Property Data`;
      document.getElementById("subline").textContent =
        `${s.borough || ""} · Block ${data.block} Lot ${data.lot} · BBL ${data.bbl}` +
        (s.zipcode ? ` · ${s.zipcode}` : "");
      fillStats(s);
      initMap(s.latitude, s.longitude, s.address);
      document.getElementById("panel-overview").innerHTML = renderOverview(data);
      document.getElementById("panel-assessment").innerHTML = renderAssessment(data.assessment);
      document.getElementById("panel-acris").innerHTML = renderAcris(data.acris);
      document.getElementById("panel-dob").innerHTML = renderDob(data);
      document.getElementById("panel-violations").innerHTML = renderViolations(data);
      document.getElementById("panel-hpd").innerHTML = renderHpd(data);
      bindTabs(bbl);
    } catch (e) {
      const _load2 = document.getElementById("page-loading"); _load2.hidden = true; _load2.style.display = "none";
      document.getElementById("page-error").hidden = false;
      document.getElementById("page-error").textContent = e.message || String(e);
    }
  }

  document.getElementById("mini-search").addEventListener("submit", async (e) => {
    e.preventDefault();
    const q = document.getElementById("mini-q").value.trim();
    if (!q) return;
    if (isBbl(q)) {
      location.href = `/property?bbl=${q.replace(/\D/g, "")}`;
      return;
    }
    try {
      const results = await search(q);
      if (results && results[0] && results[0].bbl) {
        location.href = `/property?bbl=${results[0].bbl}`;
      } else {
        alert("No BBL found for that address.");
      }
    } catch (err) {
      alert(err.message);
    }
  });

  document.addEventListener("DOMContentLoaded", load);
})();
