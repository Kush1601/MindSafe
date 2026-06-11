// popup.js
//
// Shows the latest MindSafe evaluation for the last analyzed video.

function esc(s) {
  return String(s).replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
}

function tierColor(score) {
  if (typeof score !== "number" || Number.isNaN(score)) return "var(--muted)";
  if (score >= 8) return "var(--safe)";
  if (score >= 5) return "var(--caution)";
  return "var(--concern)";
}

function renderResult(r) {
  const resultDiv = document.getElementById("result");

  if (!r) {
    resultDiv.innerHTML = `
      <div class="empty">
        No video analyzed yet. Open a YouTube or YouTube Kids video and MindSafe
        will score it automatically — then reopen this popup.
      </div>`;
    return;
  }

  const titleRow = `
    <div class="vid-title">
      <a href="${esc(r.videoUrl)}" target="_blank">${esc(r.title || "Video")}</a>
    </div>`;

  if (r.status === "pending") {
    resultDiv.innerHTML = `
      <div class="pending"><span class="spinner"></span><span>Analyzing this video…</span></div>
      ${titleRow}`;
    return;
  }

  if (r.status === "error") {
    resultDiv.innerHTML = `
      <div class="errbox">Couldn't analyze this video. Check that the MindSafe
      service is reachable, then reload the page.</div>
      ${titleRow}`;
    return;
  }

  // Done
  const ten = typeof r.tenPointScore === "number" ? r.tenPointScore : null;
  const color = tierColor(ten);
  const pct = ten != null ? ten * 10 : 0;
  const sub = Array.isArray(r.reasons) && r.reasons.length ? esc(r.reasons[0]) : "";

  const devScore = typeof r.devScore === "number" ? r.devScore.toFixed(0) : "—";
  const brainrot = typeof r.brainrotIndex === "number" ? r.brainrotIndex.toFixed(0) : "—";

  const dim =
    r.rawApiResult && r.rawApiResult.dimension_scores ? r.rawApiResult.dimension_scores : null;

  const dimMap = {
    Pacing: "Pacing",
    Story: "Story coherence",
    Language: "Language",
    SEL: "Social-emotional",
    Fantasy: "Fantasy/reality",
    Interactivity: "Interactivity",
  };

  let dimHtml = "";
  if (dim) {
    dimHtml = '<div class="dims">' +
      Object.entries(dimMap).map(([k, name]) => {
        const v = dim[k];
        if (typeof v !== "number") return "";
        const c = Math.max(0, Math.min(100, v));
        let col = "var(--concern)";
        if (c >= 70) col = "var(--safe)";
        else if (c >= 45) col = "var(--caution)";
        return `
          <div class="dim-row">
            <div class="dim-top"><span class="dim-name">${name}</span><span class="dim-val">${c.toFixed(0)}</span></div>
            <div class="bar"><div class="bar-fill" style="width:${c}%; background:${col};"></div></div>
          </div>`;
      }).join("") + "</div>";
  }

  resultDiv.innerHTML = `
    <div class="hero">
      <div class="ring" style="--pct:${pct}; --ring:${color};">
        <span class="ring-num" style="color:${color};">${ten ?? "—"}<small>/10</small></span>
      </div>
      <div>
        <div class="verdict-label" style="color:${color};">${esc(r.label || "—")}</div>
        ${sub ? `<div class="verdict-sub">${sub}</div>` : ""}
      </div>
    </div>
    ${titleRow}
    <div class="stats">
      <div class="stat"><span class="stat-k">Developmental score</span><span class="stat-v">${devScore}<span>/100</span></span></div>
      <div class="stat"><span class="stat-k">Brainrot index</span><span class="stat-v">${brainrot}<span>/100</span></span></div>
    </div>
    ${dimHtml}
  `;
}

// Load saved child age and wire up Save button
chrome.storage.local.get("childAge", (data) => {
  const ageInput = document.getElementById("age-input");
  if (ageInput && data.childAge) {
    ageInput.value = data.childAge;
  }
});

document.getElementById("age-save").addEventListener("click", () => {
  const ageInput = document.getElementById("age-input");
  const age = parseFloat(ageInput.value);
  if (!isNaN(age) && age >= 0 && age <= 18) {
    chrome.storage.local.set({ childAge: age }, () => {
      const savedEl = document.getElementById("age-saved");
      savedEl.style.display = "inline";
      setTimeout(() => { savedEl.style.display = "none"; }, 1500);
    });
  }
});

// Ask background for lastScore (with fallback to storage)
chrome.runtime.sendMessage({ type: "GET_LAST_SCORE" }, (resp) => {
  const resultDiv = document.getElementById("result");

  if (chrome.runtime.lastError) {
    try {
      chrome.storage.local.get("lastScore", (data) => {
        if (chrome.runtime.lastError) {
          resultDiv.innerHTML = `<div class="errbox">Storage error: ${esc(chrome.runtime.lastError.message)}</div>`;
        } else {
          renderResult(data.lastScore);
        }
      });
    } catch (e) {
      resultDiv.innerHTML = `<div class="errbox">Storage error: ${esc(e && e.message)}</div>`;
    }
    return;
  }

  if (resp && resp.error) {
    resultDiv.innerHTML = `<div class="errbox">Storage error: ${esc(resp.error)}</div>`;
    return;
  }

  renderResult(resp && resp.lastScore);
});
