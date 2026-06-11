// background.js (MV3 service worker)
//
// Calls the MindSafe FastAPI backend (async job pattern):
//   POST /evaluate  →  { job_id, status }
//   GET  /evaluate/{job_id}  →  poll until status == "done" | "failed"
//
// API_BASE_URL: set to your ECS ALB URL once deployed, or localhost for dev.
// To override without editing this file, open the extension's options page
// (or chrome.storage.local.set({ apiBaseUrl: "https://..." }) in DevTools).
//
const DEFAULT_API_BASE_URL = "http://localhost:5001";
const DEFAULT_CHILD_AGE = 4; // years

// Resolve base URL from storage (allows runtime override without a rebuild)
async function getApiBaseUrl() {
  return new Promise((resolve) => {
    chrome.storage.local.get("apiBaseUrl", (data) => {
      resolve((data && data.apiBaseUrl) || DEFAULT_API_BASE_URL);
    });
  });
}

// In-memory fallback so popup or content script can read
// the latest value even if storage fails.
let inMemoryLastScore = null;

// Helper: map 0–100 dev score to 1–10 rating
function devScoreToTenPoint(devScore) {
  if (typeof devScore !== "number" || Number.isNaN(devScore)) {
    return null;
  }
  const clamped = Math.max(0, Math.min(100, devScore));
  return Math.max(1, Math.min(10, Math.round(clamped / 10)));
}

// Helper: turn a 1–10 score into a label + reasons
function labelForScore(score) {
  if (typeof score !== "number") {
    return {
      label: "Analysis pending",
      reasons: ["The video is being analyzed by MindSafe."]
    };
  }
  if (score >= 8) {
    return {
      label: "Highly suitable",
      reasons: [
        "Calm and developmentally supportive content",
        "Low risk for negative emotional impact",
        "Aligns well with healthy screen-time habits"
      ]
    };
  } else if (score >= 5) {
    return {
      label: "Moderately suitable",
      reasons: [
        "Mostly appropriate but with some mild concerns",
        "Best viewed with some parental awareness",
        "Context matters more for younger children"
      ]
    };
  }
  return {
    label: "Not recommended",
    reasons: [
      "May be overstimulating or emotionally intense",
      "Themes might be confusing or stressful for young kids",
      "Consider more developmentally supportive content"
    ]
  };
}

// Call the MindSafe API to evaluate a video URL in the background.
// We do NOT hold the sendResponse callback open; instead we:
//   1) store a 'pending' state immediately
//   2) fire this async function
//   3) when it returns, update storage + notify content scripts
// Poll a job until done/failed, up to maxWaitMs.
async function pollJob(apiBase, jobId, maxWaitMs = 900_000) {
  const pollUrl = new URL(`/evaluate/${jobId}`, apiBase).toString();
  const deadline = Date.now() + maxWaitMs;
  let backoff = 3000; // start at 3s, cap at 15s

  while (Date.now() < deadline) {
    await new Promise((r) => setTimeout(r, backoff));
    backoff = Math.min(backoff * 1.5, 15_000);

    const resp = await fetch(pollUrl);
    if (!resp.ok) throw new Error(`Poll error ${resp.status}`);
    const job = await resp.json();

    if (job.status === "done") return job.result;
    if (job.status === "failed") throw new Error(job.error || "Pipeline failed");
    // status == "queued" | "processing" — keep polling
  }
  throw new Error("Evaluation timed out after 15 minutes");
}

async function evaluateVideoWithApi(videoUrl, childAge, meta, segments) {
  const apiBase = await getApiBaseUrl();

  // Routing, in order of fidelity:
  //  1. Captions available → /evaluate/transcript (full analysis, client-side)
  //  2. No captions → /evaluate/metadata (title-only estimate; always works)
  // We never use the server-side URL download from the extension — it hits
  // YouTube's bot-detection wall on datacenter IPs.
  const useTranscript = Array.isArray(segments) && segments.length > 0;
  let mode, submitUrl, submitBody;
  if (useTranscript) {
    mode = `transcript, ${segments.length} segments`;
    submitUrl = new URL("/evaluate/transcript", apiBase).toString();
    submitBody = { segments, age: childAge, url: videoUrl, title: meta && meta.title };
  } else {
    mode = "metadata (no captions)";
    submitUrl = new URL("/evaluate/metadata", apiBase).toString();
    submitBody = {
      title: (meta && meta.title) || "Video",
      age: childAge,
      channel: meta && meta.channel,
      url: videoUrl,
    };
  }

  console.log("[MindSafe BG] Submitting job to:", submitUrl, `(${mode})`);

  try {
    const submitResp = await fetch(submitUrl, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(submitBody),
    });

    if (!submitResp.ok) {
      const errBody = await submitResp.json().catch(() => ({}));
      throw new Error(errBody.detail || `Submit error ${submitResp.status}`);
    }

    const { job_id, status: initialStatus, cache_hit } = await submitResp.json();
    console.log("[MindSafe BG] Job submitted:", job_id, "status:", initialStatus);

    let data;
    if (initialStatus === "done" && cache_hit) {
      // Cache hit — result already available, fetch it
      const jobResp = await fetch(new URL(`/evaluate/${job_id}`, apiBase).toString());
      const job = await jobResp.json();
      data = job.result;
    } else {
      data = await pollJob(apiBase, job_id);
    }

    const resp = { ok: true, json: async () => data };

    if (!resp.ok) {
      throw new Error(`API error`);
    }

    if (!resp.ok) {
      throw new Error(`API error ${resp.status} ${resp.statusText}`);
    }

    console.log("[MindSafe BG] API response:", data);

    // Extract scores from either API shape
    let devScore =
      typeof data.dev_score === "number"
        ? data.dev_score
        : data.overall_scores && typeof data.overall_scores.development_score === "number"
        ? data.overall_scores.development_score
        : null;

    let brainrot =
      typeof data.brainrot_index === "number"
        ? data.brainrot_index
        : data.overall_scores && typeof data.overall_scores.brainrot_index === "number"
        ? data.overall_scores.brainrot_index
        : null;

    const tenPointScore = devScoreToTenPoint(devScore);
    const labelMeta = labelForScore(tenPointScore);

    const enriched = {
      ...meta,
      status: "done",
      videoUrl,
      childAge,
      devScore,
      brainrotIndex: brainrot,
      tenPointScore,
      label: labelMeta.label,
      reasons: labelMeta.reasons,
      rawApiResult: data,
      receivedAt: Date.now()
    };

    inMemoryLastScore = enriched;
    chrome.storage.local.set({ lastScore: enriched }, () => {
      if (chrome.runtime.lastError) {
        console.error(
          "[MindSafe BG] chrome.storage.local.set failed",
          chrome.runtime.lastError
        );
      } else {
        console.log("[MindSafe BG] Stored final evaluation in lastScore");
      }
    });

    // Notify all YouTube / YouTube Kids tabs that a fresh score is available
    chrome.tabs.query(
      {
        url: [
          "*://www.youtube.com/*",
          "*://youtu.be/*",
          "*://www.youtubekids.com/*",
          "*://kids.youtube.com/*"
        ]
      },
      (tabs) => {
        for (const tab of tabs) {
          chrome.tabs.sendMessage(tab.id, {
            type: "SCORE_UPDATED",
            lastScore: enriched
          });
        }
      }
    );
  } catch (err) {
    console.error("[MindSafe BG] Evaluation API call failed:", err);

    const errorResult = {
      ...meta,
      status: "error",
      videoUrl,
      childAge,
      error: err && err.message ? err.message : String(err),
      receivedAt: Date.now()
    };

    inMemoryLastScore = errorResult;
    chrome.storage.local.set({ lastScore: errorResult }, () => {
      if (chrome.runtime.lastError) {
        console.error(
          "[MindSafe BG] chrome.storage.local.set failed after error",
          chrome.runtime.lastError
        );
      }
    });

    chrome.tabs.query(
      {
        url: [
          "*://www.youtube.com/*",
          "*://youtu.be/*",
          "*://www.youtubekids.com/*",
          "*://kids.youtube.com/*"
        ]
      },
      (tabs) => {
        for (const tab of tabs) {
          chrome.tabs.sendMessage(tab.id, {
            type: "SCORE_UPDATED",
            lastScore: errorResult
          });
        }
      }
    );
  }
}

chrome.runtime.onMessage.addListener((msg, sender, sendResponse) => {
  // 1) NEW_VIDEO: content script detected a video
  if (msg.type === "NEW_VIDEO") {
    console.log("[MindSafe BG] NEW_VIDEO received", msg, "from", sender);

    const videoUrl = msg.videoUrl || null;
    const title = msg.title || "Video";
    const childAge =
      typeof msg.childAge === "number" ? msg.childAge : DEFAULT_CHILD_AGE;

    if (!videoUrl) {
      sendResponse({
        ok: false,
        error: "Missing videoUrl in NEW_VIDEO message"
      });
      return;
    }

    // Store a pending state immediately so popup / panel can show something
    const pending = {
      videoId: msg.videoId || null,
      videoUrl,
      title,
      childAge,
      status: "pending",
      devScore: null,
      brainrotIndex: null,
      tenPointScore: null,
      label: "Analysis pending",
      reasons: ["The video is being analyzed by MindSafe."],
      startedAt: Date.now()
    };

    inMemoryLastScore = pending;
    chrome.storage.local.set({ lastScore: pending }, () => {
      if (chrome.runtime.lastError) {
        console.error(
          "[MindSafe BG] chrome.storage.local.set failed (pending)",
          chrome.runtime.lastError
        );
      }
    });

    // Use persisted child age if available, else fall back to message value
    chrome.storage.local.get("childAge", (ageData) => {
      const resolvedAge =
        (ageData && typeof ageData.childAge === "number")
          ? ageData.childAge
          : childAge;
      evaluateVideoWithApi(videoUrl, resolvedAge, {
        videoId: msg.videoId || null,
        title,
        channel: msg.channel || null
      }, msg.segments);
    });

    // Respond quickly; we don't keep sendResponse open for minutes,
    // and we are not doing any async work tied to sendResponse here.
    sendResponse({ ok: true, lastScore: pending });
    return;
  }

  // 2) GET_LAST_SCORE: popup or content script asking for whatever we last stored
  if (msg.type === "GET_LAST_SCORE") {
    console.log("[MindSafe BG] GET_LAST_SCORE");

    if (inMemoryLastScore) {
      sendResponse({ lastScore: inMemoryLastScore });
      // Synchronous response, no async work for this branch.
      return;
    }

    chrome.storage.local.get("lastScore", (data) => {
      if (chrome.runtime.lastError) {
        console.error(
          "[MindSafe BG] chrome.storage.local.get failed",
          chrome.runtime.lastError
        );
        sendResponse({
          lastScore: null,
          error: chrome.runtime.lastError.message
        });
      } else {
        sendResponse({
          lastScore: data.lastScore || null
        });
      }
    });

    return true;
  }
});
