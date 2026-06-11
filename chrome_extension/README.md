# MindSafe Chrome Extension

Chrome MV3 extension that injects a real-time developmental safety score into YouTube and YouTube Kids watch pages.

---

## What it does

- Detects when the user navigates to a YouTube watch page
- Sends the video URL to the MindSafe API (background service worker)
- Shows an "Analyzing…" card immediately, then updates when the score arrives
- Renders a **1–10 score badge** (green / orange / red) + label + 6 dimension scores
- Popup shows the last evaluated video score

---

## Install (unpacked / sideload)

1. `chrome://extensions` → enable **Developer mode** (top right)
2. **Load unpacked** → select this `chrome_extension/` folder
3. Open any YouTube watch page — the MindSafe card appears in the right column

---

## Pointing at a deployed API

By default the extension talks to `http://localhost:5001`.

To point at a deployed API (AWS, Railway, EC2), open Chrome DevTools console on any page and run:

```javascript
chrome.storage.local.set({ apiBaseUrl: "https://YOUR_API_URL" })
```

This persists across browser restarts. To reset to localhost:

```javascript
chrome.storage.local.remove("apiBaseUrl")
```

---

## Files

| File | Purpose |
|---|---|
| `manifest.json` | MV3 manifest — permissions, content script declaration |
| `background.js` | Service worker — receives `NEW_VIDEO`, submits to API, polls for result, notifies tabs |
| `content_script.js` | Injected into YouTube pages — detects video changes, renders score card |
| `popup.html` / `popup.js` | Extension popup — shows last evaluated video |

---

## API contract

The extension uses the async job pattern:

```
POST /evaluate  { url, age }  →  { job_id, status }
GET  /evaluate/{job_id}       →  poll until status == "done" | "failed"
```

Polling uses exponential backoff: starts at 3s, caps at 15s, times out after 15 minutes.

---

## Permissions

| Permission | Why |
|---|---|
| `storage` | Persist last score + API URL override across sessions |
| `host_permissions: youtube.com` | Content script injection + tab messaging |
| `host_permissions: *.amazonaws.com` | Reach deployed ECS API |
