async function loadJson(path) {
  const res = await fetch(path, { cache: "no-store" });
  if (!res.ok) throw new Error(`Failed to load ${path}: ${res.status}`);
  return await res.json();
}

function esc(s) {
  return String(s).replace(/[&<>"']/g, c => ({ "&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;" }[c]));
}

(async function main() {
  const latest = await loadJson("../results/latest.json");
  const meta = document.getElementById("meta");
  meta.innerHTML = `Platform: <b>${esc(latest.platform)}</b> • Run: <b>${esc(latest.runTimestamp)}</b>`;

  const tbody = document.querySelector("#tbl tbody");
  tbody.innerHTML = "";

  for (const c of latest.cases) {
    const tr = document.createElement("tr");
    tr.className = c.ok ? "ok" : "bad";

    const inputs = c.inputs || {};
    const pids = (c.product_ids || []).map(p => `<div><code>${esc(p)}</code></div>`).join("");
    const statusParts = [];
    if (c.ok) statusParts.push("✅ OK");
    else statusParts.push("❌ FAIL");
    if (c.error) statusParts.push(`<div>${esc(c.error)}</div>`);
    if (c.hygiene_issues && c.hygiene_issues.length) statusParts.push(`<div>Hygiene: ${esc(JSON.stringify(c.hygiene_issues))}</div>`);
    if (c.expectation_ok === false) statusParts.push(`<div>Expectation: ${esc(c.expectation_msg)}</div>`);

    tr.innerHTML = `
      <td><b>${esc(c.name)}</b></td>
      <td>
        country=${esc(inputs.appStoreCountryCode)}<br/>
        build_id=${esc(inputs.build_id)}<br/>
        logged_in=${esc(inputs.logged_in)}
      </td>
      <td>act=${esc(c.activityId)}<br/>exp=${esc(c.experienceId)}</td>
      <td>${pids || "<i>(none)</i>"}</td>
      <td>${statusParts.join("")}</td>
    `;
    tbody.appendChild(tr);
  }
})();