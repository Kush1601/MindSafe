// content_script.js – MindSafe stats card in YouTube / YouTube Kids right column
// Talks to the background service worker, which calls the MindSafe API
// to get REAL evaluation data for the current video.

console.log("[MindSafe] content script loaded on", location.href);

// ====================== CAPTION FETCH ======================
// Fetch the video transcript from the user's own browser session.
// This runs on youtube.com with the user's cookies, so it bypasses the
// bot detection that blocks server-side downloads from datacenter IPs.
// Returns an array of {start, end, text} segments, or null if unavailable.

async function fetchTranscriptSegments() {
  try {
    // ytInitialPlayerResponse holds the caption track list
    let player = window.ytInitialPlayerResponse;
    if (!player) {
      // Fallback: scrape it from the page HTML
      const html = document.documentElement.innerHTML;
      const m = html.match(/ytInitialPlayerResponse\s*=\s*(\{.+?\});/s);
      if (m) {
        try { player = JSON.parse(m[1]); } catch (_) {}
      }
    }
    const tracks =
      player &&
      player.captions &&
      player.captions.playerCaptionsTracklistRenderer &&
      player.captions.playerCaptionsTracklistRenderer.captionTracks;

    if (!tracks || tracks.length === 0) {
      console.warn("[MindSafe] no caption tracks available");
      return null;
    }

    // Prefer English, else first available
    const track =
      tracks.find((t) => (t.languageCode || "").startsWith("en")) || tracks[0];

    const resp = await fetch(track.baseUrl);
    if (!resp.ok) throw new Error(`caption fetch ${resp.status}`);
    const xml = await resp.text();

    const doc = new DOMParser().parseFromString(xml, "text/xml");
    const nodes = Array.from(doc.getElementsByTagName("text"));
    if (nodes.length === 0) return null;

    const decoder = document.createElement("textarea");
    const segments = nodes.map((n) => {
      const start = parseFloat(n.getAttribute("start") || "0");
      const dur = parseFloat(n.getAttribute("dur") || "0");
      decoder.innerHTML = n.textContent || "";
      return { start, end: start + dur, text: decoder.value.replace(/\n/g, " ").trim() };
    }).filter((s) => s.text.length > 0);

    console.log(`[MindSafe] fetched ${segments.length} caption segments`);
    return segments.length > 0 ? segments : null;
  } catch (err) {
    console.warn("[MindSafe] caption fetch failed:", err);
    return null;
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

function renderPanel(data) {
  const container = findRightColumn();
  if (!container) {
    // Right column not mounted yet; caller will keep polling.
    return false;
  }

  let panel = document.getElementById("mindsafe-stats-panel");
  const isNew = !panel;

  if (!panel) {
    panel = document.createElement("div");
    panel.id = "mindsafe-stats-panel";

    panel.style.marginBottom = "10px";
    panel.style.padding = "12px 14px";
    panel.style.borderRadius = "16px";
    panel.style.boxSizing = "border-box";
    panel.style.fontFamily = "Roboto, Arial, sans-serif";
    panel.style.fontSize = "12px";

    panel.style.background =
      "linear-gradient(135deg, rgba(187,247,208,0.96), rgba(219,234,254,0.98))";
    panel.style.color = "#111";
    panel.style.boxShadow = "0 10px 24px rgba(15,23,42,0.24)";
    panel.style.border = "1px solid rgba(52,211,153,0.9)";
  }

  const status = data && data.status;
  // Prefer tenPointScore from background; fall back to deriving from devScore if needed
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
  const title = data && data.title ? data.title : "this video";
  const label = data && data.label ? data.label : "Analysis pending";
  const reasons = Array.isArray(data && data.reasons) ? data.reasons : [];

  let scoreHtml = "";
  if (status === "done") {
    const scoreDisplay =
      tenPointScore != null ? `${tenPointScore}` : "N/A";
    scoreHtml = `
      <div style="display:flex; align-items:baseline; gap:6px; margin-bottom:4px;">
        <span class="mindsafe-score-value" style="font-size:26px; font-weight:700;">${scoreDisplay}</span>
        <span style="font-size:12px; opacity:0.8;">/ 10</span>
      </div>
    `;
  } else if (status === "error") {
    scoreHtml = `
      <div style="font-size:12px; font-weight:500; margin-bottom:4px; color:#b91c1c;">
        MindSafe analysis failed. Make sure the MindSafe API is running.
      </div>
    `;
  } else {
    scoreHtml = `
      <div style="font-size:12px; font-weight:500; margin-bottom:4px;">
        Running full MindSafe analysis for this video…
      </div>
    `;
  }

  const reasonsHtml =
    reasons.length > 0
      ? `<ul style="padding-left:18px; margin:0; font-size:11px;">
          ${reasons.map((r) => `<li>${r}</li>`).join("")}
        </ul>`
      : "";

  panel.innerHTML = `
    <div style="display:flex; align-items:center; gap:6px; margin-bottom:4px;">
      <span style="width:20px; height:20px; border-radius:999px; background:linear-gradient(135deg,#22c55e,#0ea5e9); display:inline-flex; align-items:center; justify-content:center; font-size:11px; font-weight:800; color:#f9fafb;">
        MS
      </span>
      <span style="font-size:13px; font-weight:700; letter-spacing:0.02em; color:#065f46;">
        MindSafe
      </span>
    </div>

    <div id="mindsafe-score-main" style="cursor:pointer;">
      ${scoreHtml}

      <div style="font-size:12px; font-weight:500; margin-bottom:4px;">
        ${label}
      </div>
    </div>

    <div id="mindsafe-score-details" style="display:none; margin-top:4px; font-size:11px; line-height:1.4;"></div>

    ${reasonsHtml}

    <div style="margin-top:6px; font-size:10px; opacity:0.7;">
      Click the score to see a full breakdown. Based on AI analysis of ${title}. This is informational only and not medical advice.
    </div>
  `;

  if (isNew) {
    container.insertBefore(panel, container.firstChild);
    console.log("[MindSafe] stats panel inserted into right column");
  }

  // Color-code the score value if available
  if (status === "done") {
    const scoreEl = panel.querySelector(".mindsafe-score-value");
    if (scoreEl && tenPointScore != null && !Number.isNaN(tenPointScore)) {
      const s = tenPointScore;
      let color = "#dc2626"; // default: red
      if (s >= 8) {
        color = "#16a34a"; // green
      } else if (s >= 5) {
        color = "#f97316"; // orange
      }
      scoreEl.style.color = color;
    }
  }

  // Attach click handler to toggle detailed scores
  if (status === "done") {
    const mainEl = panel.querySelector("#mindsafe-score-main");
    const detailsEl = panel.querySelector("#mindsafe-score-details");
    if (mainEl && detailsEl) {
      mainEl.addEventListener("click", () => {
        if (detailsEl.style.display === "none") {
          // Build details view from raw results
          const devScore =
            typeof data.devScore === "number"
              ? `${data.devScore.toFixed(1)}/100`
              : "N/A";
          const brainrot =
            typeof data.brainrotIndex === "number"
              ? `${data.brainrotIndex.toFixed(1)}/100`
              : "N/A";

          const dim =
            data.rawApiResult && data.rawApiResult.dimension_scores
              ? data.rawApiResult.dimension_scores
              : null;

          let dimHtml = "";
          if (dim) {
            // Map API keys to human labels; matches backend JSON keys
            const dimMap = {
              Pacing: "Pacing",
              Story: "Story",
              Language: "Language",
              SEL: "Social-Emotional Learning",
              Fantasy: "Fantasy",
              Interactivity: "Interactivity",
            };
            dimHtml =
              "<ul style='padding-left:16px; margin:4px 0;'> " +
              Object.entries(dimMap)
                .map(([apiKey, labelText]) => {
                  const v = dim[apiKey];
                  const score =
                    typeof v === "number" ? `${v.toFixed(1)}/100` : "N/A";
                  return `<li><b>${labelText}:</b> ${score}</li>`;
                })
                .join("") +
              "</ul>";
          } else {
            dimHtml =
              "<div>Detailed dimension scores are not available for this video.</div>";
          }

          const parentSummary =
            data.rawApiResult && typeof data.rawApiResult.parent_summary === "string"
              ? data.rawApiResult.parent_summary
              : null;
          const summaryHtml = parentSummary
            ? `<div style="margin-top:6px;"><b>For parents:</b> ${parentSummary
                .replace(/&/g, "&amp;")
                .replace(/</g, "&lt;")
                .replace(/>/g, "&gt;")}</div>`
            : "";

          detailsEl.innerHTML = `
            <div><b>Overall developmental score:</b> ${devScore}</div>
            <div><b>Brainrot index:</b> ${brainrot}</div>
            ${dimHtml}
            ${summaryHtml}
          `;
          detailsEl.style.display = "block";
        } else {
          detailsEl.style.display = "none";
        }
      });
    }
  }

  return true;
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

  // Fetch captions client-side first (bypasses server-side bot detection).
  const segments = await fetchTranscriptSegments();

  // Ask background to start a fresh evaluation for this video
  chrome.runtime.sendMessage(
    {
      type: "NEW_VIDEO",
      videoUrl: location.href,
      title: document.title,
      segments: segments  // null → background falls back to URL download
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
        title: document.title,
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
