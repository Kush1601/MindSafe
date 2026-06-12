// whisper.js — in-browser transcription for caption-less videos.
//
// Loaded as a web-accessible ES module by the content script. Uses the
// vendored transformers.js + onnxruntime-web (WebGPU, WASM fallback) to run
// whisper-base entirely in the user's browser — no server, no cost, works on
// any device. The Whisper model (~75MB) is fetched from the HF CDN on first
// use and cached by the browser thereafter.
//
// Flow: capture 60s of audio from the playing <video> → decode to 16kHz mono
// PCM → Whisper → transcript segments shaped for /evaluate/transcript.

import {
  pipeline,
  env,
} from "./vendor/transformers.js";

// Point the ORT runtime at our bundled WASM (MV3 CSP blocks CDN script loads).
const VENDOR_BASE = chrome.runtime.getURL("vendor/");
env.backends.onnx.wasm.wasmPaths = VENDOR_BASE;
// Allow remote model download (weights only — not executable script), cache it.
env.allowRemoteModels = true;
env.allowLocalModels = false;

const MODEL_ID = "Xenova/whisper-base";
const CAPTURE_SECONDS = 60;
const TARGET_SR = 16000; // Whisper expects 16kHz mono

let _transcriber = null;

async function getTranscriber(onProgress) {
  if (_transcriber) return _transcriber;
  _transcriber = await pipeline("automatic-speech-recognition", MODEL_ID, {
    // Prefer WebGPU; transformers.js falls back to WASM automatically.
    device: (navigator.gpu ? "webgpu" : "wasm"),
    dtype: navigator.gpu ? "fp16" : "q8",
    progress_callback: (p) => {
      if (onProgress && p && p.status === "progress" && p.file && p.total) {
        onProgress(`Loading model… ${Math.round((p.loaded / p.total) * 100)}%`);
      }
    },
  });
  return _transcriber;
}

// Capture audio from the page's playing <video>, return Float32 PCM @ 16kHz.
async function captureAudioPCM(seconds, onProgress) {
  const video = document.querySelector("video");
  if (!video) throw new Error("no <video> element on page");

  const stream = video.captureStream
    ? video.captureStream()
    : video.mozCaptureStream();
  const audioTracks = stream.getAudioTracks();
  if (!audioTracks.length) throw new Error("no audio track in captureStream");

  // Record the live audio for `seconds`, then decode the blob.
  const mediaStream = new MediaStream([audioTracks[0]]);
  const recorder = new MediaRecorder(mediaStream);
  const chunks = [];
  recorder.ondataavailable = (e) => e.data.size && chunks.push(e.data);

  const wasMuted = video.muted;
  const wasPaused = video.paused;
  // Audio must actually flow to be captured; ensure playback, keep it quiet.
  video.muted = true;
  if (wasPaused) await video.play().catch(() => {});

  if (onProgress) onProgress(`Listening to audio (${seconds}s)…`);

  const blob = await new Promise((resolve, reject) => {
    recorder.onstop = () => resolve(new Blob(chunks, { type: "audio/webm" }));
    recorder.onerror = (e) => reject(e.error || new Error("recorder error"));
    recorder.start();
    setTimeout(() => recorder.state !== "inactive" && recorder.stop(), seconds * 1000);
  });

  // Restore the user's playback state.
  video.muted = wasMuted;
  if (wasPaused) video.pause();

  if (onProgress) onProgress("Processing audio…");

  // Decode webm/opus → PCM, resample to 16kHz mono.
  const arrayBuf = await blob.arrayBuffer();
  const audioCtx = new (window.AudioContext || window.webkitAudioContext)({
    sampleRate: TARGET_SR,
  });
  const decoded = await audioCtx.decodeAudioData(arrayBuf);

  // Mix to mono.
  let pcm;
  if (decoded.numberOfChannels === 1) {
    pcm = decoded.getChannelData(0);
  } else {
    const a = decoded.getChannelData(0);
    const b = decoded.getChannelData(1);
    pcm = new Float32Array(a.length);
    for (let i = 0; i < a.length; i++) pcm[i] = (a[i] + b[i]) / 2;
  }
  await audioCtx.close();
  return pcm;
}

// Public entry: transcribe the currently-playing video, return segments
// shaped like the caption path: [{ start, end, text }].
export async function transcribeCurrentVideo(onProgress) {
  const pcm = await captureAudioPCM(CAPTURE_SECONDS, onProgress);
  if (!pcm || pcm.length === 0) throw new Error("captured empty audio");

  const transcriber = await getTranscriber(onProgress);
  if (onProgress) onProgress("Transcribing…");

  const output = await transcriber(pcm, {
    chunk_length_s: 30,
    stride_length_s: 5,
    return_timestamps: true,
    language: "english",
    task: "transcribe",
  });

  // transformers.js returns { text, chunks: [{ timestamp: [s,e], text }] }
  const chunks = (output && output.chunks) || [];
  const segments = chunks
    .map((c) => ({
      start: (c.timestamp && c.timestamp[0]) || 0,
      end: (c.timestamp && c.timestamp[1]) || 0,
      text: (c.text || "").trim(),
    }))
    .filter((s) => s.text.length > 0);

  if (segments.length === 0 && output && output.text) {
    // No timestamps — fall back to one segment.
    return [{ start: 0, end: CAPTURE_SECONDS, text: output.text.trim() }];
  }
  return segments;
}
