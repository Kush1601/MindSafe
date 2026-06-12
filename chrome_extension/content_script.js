// content_script.js – MindSafe stats card in YouTube / YouTube Kids right column
// Talks to the background service worker, which calls the MindSafe API
// to get REAL evaluation data for the current video.

console.log("[MindSafe] content script loaded on", location.href);

// ====================== CAPTION FETCH ======================
// Fetch the video transcript from the user's own browser session.
// This runs on youtube.com with the user's cookies, so it bypasses the
// bot detection that blocks server-side downloads from datacenter IPs.
// Returns an array of {start, end, text} segments, or null if unavailable.

function getVideoId() {
  try {
    return new URL(location.href).searchParams.get("v");
  } catch (_) {
    return null;
  }
}

// Best-effort channel name from the watch page DOM.
function getChannelName() {
  const el =
    document.querySelector("ytd-channel-name #text a") ||
    document.querySelector("ytd-channel-name a") ||
    document.querySelector("#owner #channel-name a");
  return el ? el.textContent.trim() : null;
}

// Strip the trailing " - YouTube" that document.title carries.
function getCleanTitle() {
  return document.title.replace(/\s*-\s*YouTube\s*$/, "").trim();
}

// Get the caption track list by scraping the watch page HTML, which embeds a
// "captionTracks" JSON blob. Runs in the user's session (cookies), so it works
// where server-side fetches are bot-blocked. Content scripts can't read the
// page's ytInitialPlayerResponse directly (isolated world), so we re-fetch the
// page HTML and parse it.
async function getCaptionTracks(videoId) {
  try {
    const html = await (await fetch(location.href, { credentials: "include" })).text();
    const m = html.match(/"captionTracks":(\[.*?\])/);
    if (m) {
      const tracks = JSON.parse(m[1].replace(/\\u0026/g, "&").replace(/\\"/g, '"'));
      if (tracks.length) return tracks;
    }
  } catch (e) { console.warn("[MindSafe] caption track lookup failed:", e); }

  return null;
}

async function fetchTranscriptSegments() {
  try {
    const videoId = getVideoId();
    if (!videoId) {
      console.warn("[MindSafe] no video id in URL");
      return null;
    }

    const tracks = await getCaptionTracks(videoId);
    if (!tracks || tracks.length === 0) {
      console.warn("[MindSafe] no caption tracks available for", videoId);
      return null;
    }

    // Prefer manual English, then any English, then first track.
    const track =
      tracks.find((t) => (t.languageCode || "").startsWith("en") && t.kind !== "asr") ||
      tracks.find((t) => (t.languageCode || "").startsWith("en")) ||
      tracks[0];

    const decoder = document.createElement("textarea");
    const decode = (s) => { decoder.innerHTML = s || ""; return decoder.value.replace(/\s+/g, " ").trim(); };

    // Try the default format first, then srv3 (asr tracks often need fmt=srv3).
    for (const url of [track.baseUrl, track.baseUrl + "&fmt=srv3"]) {
      const resp = await fetch(url, { credentials: "include" });
      if (!resp.ok) continue;
      const xml = await resp.text();
      const doc = new DOMParser().parseFromString(xml, "text/xml");

      // Legacy format: <text start="s" dur="s">
      let segments = Array.from(doc.getElementsByTagName("text")).map((n) => {
        const start = parseFloat(n.getAttribute("start") || "0");
        const dur = parseFloat(n.getAttribute("dur") || "0");
        return { start, end: start + dur, text: decode(n.textContent) };
      }).filter((s) => s.text.length > 0);

      // srv3 format: <p t="ms" d="ms"> with <s> word children
      if (segments.length === 0) {
        segments = Array.from(doc.getElementsByTagName("p")).map((p) => {
          const start = parseFloat(p.getAttribute("t") || "0") / 1000;
          const dur = parseFloat(p.getAttribute("d") || "0") / 1000;
          return { start, end: start + dur, text: decode(p.textContent) };
        }).filter((s) => s.text.length > 0);
      }

      if (segments.length > 0) {
        console.log(`[MindSafe] fetched ${segments.length} caption segments`);
        return segments;
      }
    }

    console.warn("[MindSafe] caption track empty");
    return null;
  } catch (err) {
    console.warn("[MindSafe] caption fetch failed:", err);
    return null;
  }
}

// ====================== IN-BROWSER WHISPER ======================
// When a video has no captions, transcribe its audio locally with Whisper
// (transformers.js, WebGPU/WASM). Runs entirely in the user's browser, so it
// works on any device with no server cost. Shows progress on the panel.

let _whisperModule = null;

async function tryWhisperTranscription() {
  try {
    const showStatus = (text) =>
      renderPanel({
        videoUrl: location.href,
        title: getCleanTitle(),
        status: "pending",
        label: "Listening to video…",
        reasons: [text]
      });

    showStatus("No captions found — transcribing audio locally…");

    if (!_whisperModule) {
      const url = chrome.runtime.getURL("whisper.js");
      _whisperModule = await import(url);
    }

    const segments = await _whisperModule.transcribeCurrentVideo(showStatus);
    if (segments && segments.length > 0) {
      console.log(`[MindSafe] Whisper produced ${segments.length} segments`);
      return segments;
    }
    console.warn("[MindSafe] Whisper produced no segments");
    return null;
  } catch (err) {
    console.warn("[MindSafe] in-browser Whisper failed:", err);
    return null; // fall through to metadata estimate
  }
}

// ====================== URL HELPERS ======================

function isWatchPage(urlString) {
  try {
    const url = new URL(urlString);
    return (
      url.pathname === "/watch" &&
      (url.hostname.includes("youtube.com") ||
        url.hostname.includes("youtubekids.com") ||
        url.hostname.includes("kids.youtube.com"))
    );
  } catch (e) {
    return false;
  }
}

// ====================== RIGHT COLUMN LOOKUP ======================

// Kids:   #secondary-results #related
// Normal: #secondary-inner / #secondary
function findRightColumn() {
  const kids =
    document.querySelector("#secondary-results #related") ||
    document.querySelector("#related");
  if (kids) return kids;

  const regular =
    document.querySelector("#secondary-inner") ||
    document.querySelector("#secondary");
  if (regular) return regular;

  return null;
}

// ====================== PANEL RENDERING ======================

// Inject the panel stylesheet once.
function ensureMindsafeStyles() {
  if (document.getElementById("mindsafe-styles")) return;
  const style = document.createElement("style");
  style.id = "mindsafe-styles";
  style.textContent = `
    #mindsafe-stats-panel {
      --ms-ink: #0B1120;
      --ms-muted: #5B6472;
      --ms-line: #E8EDF4;
      --ms-safe: #16A34A;
      --ms-caution: #F59E0B;
      --ms-concern: #DC2626;
      margin-bottom: 12px;
      padding: 0;
      box-sizing: border-box;
      font-family: "Inter", "Roboto", system-ui, -apple-system, sans-serif;
      color: var(--ms-ink);
      background: #FFFFFF;
      border: 1px solid var(--ms-line);
      border-radius: 14px;
      overflow: hidden;
      box-shadow: 0 1px 2px rgba(11,17,32,0.04), 0 8px 24px rgba(11,17,32,0.06);
      animation: ms-rise 0.4s cubic-bezier(0.16,1,0.3,1);
    }
    @keyframes ms-rise {
      from { opacity: 0; transform: translateY(8px); }
      to { opacity: 1; transform: translateY(0); }
    }
    .ms-head {
      display: flex; align-items: center; gap: 8px;
      padding: 12px 14px 10px;
      border-bottom: 1px solid var(--ms-line);
    }
    .ms-mark {
      width: 22px; height: 22px; border-radius: 7px;
      background: linear-gradient(135deg, #6366F1, #0EA5E9);
      display: inline-flex; align-items: center; justify-content: center;
      color: #fff; font-size: 11px; font-weight: 800; letter-spacing: -0.02em;
    }
    .ms-wordmark { font-size: 13px; font-weight: 700; letter-spacing: -0.01em; }
    .ms-eyebrow {
      margin-left: auto; font-size: 9px; font-weight: 700;
      text-transform: uppercase; letter-spacing: 0.08em; color: var(--ms-muted);
    }
    .ms-body { padding: 14px; }
    .ms-score-row { display: flex; align-items: center; gap: 14px; }
    .ms-ring {
      --pct: 0; --ring: var(--ms-muted);
      position: relative; flex: 0 0 auto;
      width: 64px; height: 64px; border-radius: 50%;
      background: conic-gradient(var(--ring) calc(var(--pct) * 1%), var(--ms-line) 0);
      display: grid; place-items: center;
      transition: --pct 0.6s ease;
    }
    .ms-ring::after {
      content: ""; position: absolute; inset: 6px;
      background: #fff; border-radius: 50%;
    }
    .ms-ring-num {
      position: relative; z-index: 1;
      font-size: 22px; font-weight: 800; line-height: 1; letter-spacing: -0.03em;
    }
    .ms-ring-num small { font-size: 10px; font-weight: 600; color: var(--ms-muted); }
    .ms-verdict { min-width: 0; }
    .ms-verdict-label { font-size: 15px; font-weight: 700; letter-spacing: -0.01em; line-height: 1.2; }
    .ms-verdict-sub { margin-top: 3px; font-size: 11px; color: var(--ms-muted); line-height: 1.4; }
    .ms-pending { display: flex; align-items: center; gap: 9px; font-size: 13px; color: var(--ms-muted); }
    .ms-spinner {
      width: 16px; height: 16px; border-radius: 50%;
      border: 2px solid var(--ms-line); border-top-color: #6366F1;
      animation: ms-spin 0.7s linear infinite;
    }
    @keyframes ms-spin { to { transform: rotate(360deg); } }
    .ms-error { font-size: 12px; color: var(--ms-concern); font-weight: 500; line-height: 1.4; }
    .ms-toggle {
      margin-top: 12px; width: 100%;
      display: flex; align-items: center; justify-content: space-between;
      padding: 8px 11px; border: 1px solid var(--ms-line); border-radius: 9px;
      background: #FAFBFC; cursor: pointer; font: inherit;
      font-size: 11px; font-weight: 600; color: var(--ms-ink);
      transition: background 0.15s, border-color 0.15s;
    }
    .ms-toggle:hover { background: #F3F5F9; border-color: #D8DFEA; }
    .ms-toggle .ms-chev { transition: transform 0.2s; color: var(--ms-muted); }
    .ms-toggle[aria-expanded="true"] .ms-chev { transform: rotate(180deg); }
    .ms-details { display: none; margin-top: 10px; }
    .ms-details.open { display: block; }
    .ms-stat { display: flex; align-items: center; justify-content: space-between; padding: 6px 0; font-size: 12px; }
    .ms-stat + .ms-stat { border-top: 1px solid var(--ms-line); }
    .ms-stat-k { color: var(--ms-muted); }
    .ms-stat-v { font-weight: 700; font-variant-numeric: tabular-nums; }
    .ms-dim { margin-top: 4px; }
    .ms-dim-row { padding: 7px 0; }
    .ms-dim-row + .ms-dim-row { border-top: 1px solid var(--ms-line); }
    .ms-dim-top { display: flex; justify-content: space-between; font-size: 11px; margin-bottom: 5px; }
    .ms-dim-name { color: var(--ms-ink); font-weight: 500; }
    .ms-dim-val { color: var(--ms-muted); font-variant-numeric: tabular-nums; }
    .ms-bar { height: 5px; border-radius: 99px; background: var(--ms-line); overflow: hidden; }
    .ms-bar-fill { height: 100%; border-radius: 99px; transition: width 0.5s ease; }
    .ms-summary {
      margin-top: 11px; padding: 10px 11px;
      background: #F6F8FE; border: 1px solid #E4E9F7; border-radius: 9px;
      font-size: 11px; line-height: 1.5; color: #313A4E;
    }
    .ms-summary b { color: var(--ms-ink); }
    .ms-foot { margin-top: 11px; font-size: 10px; line-height: 1.4; color: #9AA3B2; }
    @media (prefers-reduced-motion: reduce) {
      #mindsafe-stats-panel, .ms-spinner, .ms-ring, .ms-bar-fill { animation: none; transition: none; }
    }
  `;
  (document.head || document.documentElement).appendChild(style);
}

// Map a 1–10 score to a tier { color, label-tone }.
function scoreTier(score) {
  if (typeof score !== "number" || Number.isNaN(score)) return { color: "var(--ms-muted)", key: "na" };
  if (score >= 8) return { color: "var(--ms-safe)", key: "safe" };
  if (score >= 5) return { color: "var(--ms-caution)", key: "caution" };
  return { color: "var(--ms-concern)", key: "concern" };
}

function esc(s) {
  return String(s).replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
}

function renderPanel(data) {
  const container = findRightColumn();
  if (!container) return false;

  ensureMindsafeStyles();

  let panel = document.getElementById("mindsafe-stats-panel");
  const isNew = !panel;
  if (!panel) {
    panel = document.createElement("div");
    panel.id = "mindsafe-stats-panel";
  }

  const status = data && data.status;
  let tenPointScore =
    data && typeof data.tenPointScore === "number" ? data.tenPointScore : null;
  if (
    tenPointScore == null &&
    data &&
    typeof data.devScore === "number" &&
    !Number.isNaN(data.devScore)
  ) {
    const clamped = Math.max(0, Math.min(100, data.devScore));
    tenPointScore = Math.max(1, Math.min(10, Math.round(clamped / 10)));
  }
  const label = data && data.label ? data.label : "Analysis pending";
  const reasons = Array.isArray(data && data.reasons) ? data.reasons : [];

  // ----- Body by status -----
  let bodyHtml = "";
  if (status === "done") {
    const tier = scoreTier(tenPointScore);
    const pct = tenPointScore != null ? tenPointScore * 10 : 0;
    const sub = reasons.length > 0 ? esc(reasons[0]) : "Tap details for the full breakdown.";
    bodyHtml = `
      <div class="ms-score-row">
        <div class="ms-ring" style="--pct:${pct}; --ring:${tier.color};">
          <span class="ms-ring-num" style="color:${tier.color};">${tenPointScore ?? "—"}<small>/10</small></span>
        </div>
        <div class="ms-verdict">
          <div class="ms-verdict-label" style="color:${tier.color};">${esc(label)}</div>
          <div class="ms-verdict-sub">${sub}</div>
        </div>
      </div>
      <button class="ms-toggle" id="mindsafe-toggle" aria-expanded="false">
        <span>View full breakdown</span>
        <span class="ms-chev">▾</span>
      </button>
      <div class="ms-details" id="mindsafe-score-details"></div>
      <div class="ms-foot">AI analysis — informational only, not medical advice.</div>
    `;
  } else if (status === "error") {
    bodyHtml = `<div class="ms-error">Couldn't analyze this video. Check that the MindSafe service is reachable, then reload the page.</div>`;
  } else {
    bodyHtml = `
      <div class="ms-pending">
        <span class="ms-spinner"></span>
        <span>Analyzing this video…</span>
      </div>`;
  }

  panel.innerHTML = `
    <div class="ms-head">
      <span class="ms-mark">MS</span>
      <span class="ms-wordmark">MindSafe</span>
      <span class="ms-eyebrow">Kids Shield</span>
    </div>
    <div class="ms-body">${bodyHtml}</div>
  `;

  if (isNew) {
    container.insertBefore(panel, container.firstChild);
    console.log("[MindSafe] stats panel inserted into right column");
  }

  // ----- Details toggle -----
  if (status === "done") {
    const toggle = panel.querySelector("#mindsafe-toggle");
    const detailsEl = panel.querySelector("#mindsafe-score-details");
    if (toggle && detailsEl) {
      let built = false;
      toggle.addEventListener("click", () => {
        const open = detailsEl.classList.toggle("open");
        toggle.setAttribute("aria-expanded", String(open));
        toggle.querySelector("span").textContent = open ? "Hide breakdown" : "View full breakdown";
        if (open && !built) {
          detailsEl.innerHTML = buildDetailsHtml(data);
          built = true;
        }
      });
    }
  }

  return true;
}

// Build the expanded breakdown (overall scores, per-dimension bars, summary).
function buildDetailsHtml(data) {
  const devScore =
    typeof data.devScore === "number" ? `${data.devScore.toFixed(0)}` : "—";
  const brainrot =
    typeof data.brainrotIndex === "number" ? `${data.brainrotIndex.toFixed(0)}` : "—";

  const dim =
    data.rawApiResult && data.rawApiResult.dimension_scores
      ? data.rawApiResult.dimension_scores
      : null;

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
    dimHtml = '<div class="ms-dim">' +
      Object.entries(dimMap).map(([k, labelText]) => {
        const v = dim[k];
        if (typeof v !== "number") return "";
        const clamped = Math.max(0, Math.min(100, v));
        let c = "var(--ms-concern)";
        if (clamped >= 70) c = "var(--ms-safe)";
        else if (clamped >= 45) c = "var(--ms-caution)";
        return `
          <div class="ms-dim-row">
            <div class="ms-dim-top">
              <span class="ms-dim-name">${labelText}</span>
              <span class="ms-dim-val">${clamped.toFixed(0)}</span>
            </div>
            <div class="ms-bar"><div class="ms-bar-fill" style="width:${clamped}%; background:${c};"></div></div>
          </div>`;
      }).join("") + "</div>";
  }

  const parentSummary =
    data.rawApiResult && typeof data.rawApiResult.parent_summary === "string"
      ? data.rawApiResult.parent_summary
      : null;
  const summaryHtml = parentSummary
    ? `<div class="ms-summary"><b>For parents — </b>${esc(parentSummary)}</div>`
    : "";

  return `
    <div class="ms-stat"><span class="ms-stat-k">Developmental score</span><span class="ms-stat-v">${devScore}<span style="color:var(--ms-muted);font-weight:500;">/100</span></span></div>
    <div class="ms-stat"><span class="ms-stat-k">Brainrot index</span><span class="ms-stat-v">${brainrot}<span style="color:var(--ms-muted);font-weight:500;">/100</span></span></div>
    ${dimHtml}
    ${summaryHtml}
  `;
}

// Ask the background script for whatever the last score is and render it.
// Returns nothing directly; polling logic lives in the interval callback.
function requestAndRenderLatestPanel(intervalRef) {
  const container = findRightColumn();
  if (!container) {
    console.log("[MindSafe] right column not found yet");
    return;
  }

  chrome.runtime.sendMessage({ type: "GET_LAST_SCORE" }, (resp) => {
    if (chrome.runtime.lastError) {
      // Fallback: read the lastScore directly from storage so the
      // panel still updates even if the service worker wasn't awake.
      chrome.storage.local.get("lastScore", (data) => {
        if (chrome.runtime.lastError) {
          console.warn(
            "[MindSafe] chrome.storage.local.get(lastScore) also failed:",
            chrome.runtime.lastError
          );
          renderPanel(null);
        } else {
          const stored = data && data.lastScore ? data.lastScore : null;
          renderPanel(stored);

          if (
            stored &&
            (stored.status === "done" || stored.status === "error")
          ) {
            if (intervalRef && intervalRef.id) {
              clearInterval(intervalRef.id);
              intervalRef.id = null;
            }
          }
        }
      });
      return;
    }

    const data = resp && resp.lastScore ? resp.lastScore : null;
    renderPanel(data);

    // Stop polling once we reach a terminal state
    if (data && (data.status === "done" || data.status === "error")) {
      if (intervalRef && intervalRef.id) {
        clearInterval(intervalRef.id);
        intervalRef.id = null;
      }
    }
  });
}

// Single shared polling reference so we can restart it when navigating to
// a new video on the same YouTube tab.
let mindsafeIntervalRef = { id: null };

// ====================== INIT ======================

async function startEvaluation() {
  console.log("[MindSafe] watch page detected, starting injection + API call");

  // Tier 1: captions (instant, full transcript).
  let segments = await fetchTranscriptSegments();

  // Tier 2: no captions → transcribe audio in-browser with Whisper.
  if (!segments || segments.length === 0) {
    segments = await tryWhisperTranscription();
  }
  // Tier 3 (if still none): background falls back to a metadata-only estimate.

  // Ask background to start a fresh evaluation for this video
  chrome.runtime.sendMessage(
    {
      type: "NEW_VIDEO",
      videoUrl: location.href,
      title: getCleanTitle(),
      channel: getChannelName(),
      segments: segments  // null/empty → background uses metadata-only estimate
    },
    (resp) => {
      if (chrome.runtime.lastError) {
        console.warn(
          "[MindSafe] NEW_VIDEO sendMessage error:",
          chrome.runtime.lastError
        );
        return;
      }
      if (resp && resp.lastScore) {
        const pendingData = resp.lastScore;
        // Render as soon as the right column is ready
        const intervalPending = setInterval(() => {
          if (renderPanel(pendingData)) {
            clearInterval(intervalPending);
          }
        }, 500);
        setTimeout(() => clearInterval(intervalPending), 10000);
      }
    }
  );

  // Poll for updates until we reach a terminal state (done/error)
  mindsafeIntervalRef.id = setInterval(() => {
    requestAndRenderLatestPanel(mindsafeIntervalRef);
  }, 2000);

  // Listen for updates when the background finishes analysis
  chrome.runtime.onMessage.addListener((msg) => {
    if (!msg || msg.type !== "SCORE_UPDATED") return;
    if (!isWatchPage(location.href)) return;
    renderPanel(msg.lastScore);
  });
}

if (isWatchPage(location.href)) {
  startEvaluation();
} else {
  console.log("[MindSafe] not a /watch page, doing nothing");
}

// ====================== SPA NAVIGATION WATCHER ======================
// Watch for URL changes in this tab and restart analysis when a new watch page is loaded.
let mindsafeCurrentVideoUrl = location.href;
setInterval(() => {
  const current = location.href;
  if (current === mindsafeCurrentVideoUrl) return;
  mindsafeCurrentVideoUrl = current;

  if (!isWatchPage(current)) {
    return;
  }

  console.log(
    "[MindSafe] Detected navigation to new watch page, resetting panel"
  );

  const pendingData = {
    videoUrl: current,
    title: document.title,
    status: "pending",
    devScore: null,
    brainrotIndex: null,
    tenPointScore: null,
    label: "Analysis pending",
    reasons: ["The video is being analyzed by MindSafe."]
  };

  renderPanel(pendingData);

  fetchTranscriptSegments().then((segments) => {
    chrome.runtime.sendMessage(
      {
        type: "NEW_VIDEO",
        videoUrl: current,
        title: getCleanTitle(),
        channel: getChannelName(),
        segments: segments
      },
      (resp) => {
        if (chrome.runtime.lastError) {
          console.warn(
            "[MindSafe] NEW_VIDEO sendMessage error (nav):",
            chrome.runtime.lastError
          );
        } else if (resp && resp.lastScore) {
          renderPanel(resp.lastScore);
        }
      }
    );
  });

  // Restart polling so GET_LAST_SCORE keeps updating until the new
  // evaluation reaches a terminal state.
  if (mindsafeIntervalRef.id) {
    clearInterval(mindsafeIntervalRef.id);
    mindsafeIntervalRef.id = null;
  }
  mindsafeIntervalRef.id = setInterval(() => {
    requestAndRenderLatestPanel(mindsafeIntervalRef);
  }, 2000);
}, 1000);
