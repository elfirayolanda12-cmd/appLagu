/** @format */

// static/script_webaudio.js — replacement (robust, diagnostics, lyric sync)
// Elements expected in HTML: recordBtn, stopBtn (optional), status, lyricLine, backsound (audio element)
document.addEventListener("DOMContentLoaded", () => {
  const recordBtn =
    document.getElementById("startBtn") || document.getElementById("recordBtn");
  const statusEl =
    document.getElementById("status") || document.createElement("div");
  const lyricLine =
    document.getElementById("lyricLine") ||
    document.getElementById("current-line");
  const backsoundEl = document.getElementById("backsound");

  // lyric timings you provided (seconds)
  const lyricTimings = [
    { time: 5.0, text: "Indonesia tanah airku" },
    { time: 10.0, text: "Tanah tumpah darahku" },
    { time: 14.0, text: "Di sanalah aku berdiri" },
    { time: 19.0, text: "Jadi pandu ibuku" },
    { time: 25.0, text: "Indonesia kebangsaanku" },
    { time: 30.0, text: "Bangsa dan tanah airku" },
    { time: 35.0, text: "Marilah kita berseru" },
    { time: 40.0, text: "Indonesia bersatu" },
    { time: 45.0, text: "Hiduplah tanahku, Hiduplah neg’riku" },
    { time: 50.0, text: "Bangsaku, rakyatku, semuanya" },
    { time: 55.0, text: "Bangunlah jiwanya, Bangunlah badannya" },
    { time: 60.0, text: "Untuk Indonesia Raya" },
    { time: 65.0, text: "Indonesia Raya, Merdeka, merdeka" },
    { time: 70.0, text: "Tanahku, neg’riku yang kucinta!" },
    { time: 75.0, text: "Indonesia Raya, Merdeka, merdeka" },
    { time: 80.0, text: "Hiduplah Indonesia Raya" },
    { time: 85.0, text: "Indonesia Raya, Merdeka, merdeka" },
    { time: 90.0, text: "Tanahku, neg’riku yang kucinta!" },
    { time: 94.0, text: "Indonesia Raya, Merdeka, merdeka" },
    { time: 99.0, text: "Hiduplah Indonesia Raya" },
  ];

  // state
  let mediaRecorder = null;
  let recordedChunks = [];
  let lyricTimer = null;

  function logStatus(msg) {
    console.log("[KARAOKE]", msg);
    if (statusEl) statusEl.textContent = msg;
  }

  function updateLyricByTime(t) {
    // find last lyric whose time <= t
    for (let i = lyricTimings.length - 1; i >= 0; i--) {
      if (t >= lyricTimings[i].time) {
        if (lyricLine && lyricLine.textContent !== lyricTimings[i].text) {
          lyricLine.textContent = lyricTimings[i].text;
          // small CSS "pop" effect if present
          lyricLine.classList && lyricLine.classList.add("fadeIn");
          setTimeout(
            () => lyricLine.classList && lyricLine.classList.remove("fadeIn"),
            700
          );
        }
        return;
      }
    }
    // fallback before first lyric
    if (lyricLine) lyricLine.textContent = "Siap... tunggu bagianmu di lagu";
  }

  async function startRecordingSequence() {
    logStatus("Meminta izin mikrofon...");
    recordedChunks = [];

    // 1) request mic
    let stream;
    try {
      stream = await navigator.mediaDevices.getUserMedia({ audio: true });
    } catch (err) {
      logStatus("Gagal akses mikrofon: " + err.message);
      console.error(err);
      return;
    }

    logStatus("Izin diterima. Menyiapkan perekam...");
    // 2) create MediaRecorder with safe mimeType fallback
    let options = {};
    // try best mimeTypes known; browser will ignore unsupported fields
    const preferredTypes = [
      "audio/webm;codecs=opus",
      "audio/ogg;codecs=opus",
      "audio/webm",
      "audio/ogg",
      "",
    ];
    let mr = null;
    for (let t of preferredTypes) {
      try {
        mr = t
          ? new MediaRecorder(stream, { mimeType: t })
          : new MediaRecorder(stream);
        // if constructed OK and state valid, choose it
        if (mr && mr.state !== undefined) {
          options.mimeType = t;
          mediaRecorder = mr;
          break;
        }
      } catch (_) {
        /* try next */
      }
    }
    if (!mediaRecorder) {
      try {
        mediaRecorder = new MediaRecorder(stream);
      } catch (err) {
        logStatus("MediaRecorder tidak tersedia di browser ini.");
        console.error(err);
        return;
      }
    }

    mediaRecorder.ondataavailable = (e) => {
      if (e.data && e.data.size > 0) recordedChunks.push(e.data);
    };

    mediaRecorder.onstop = async () => {
      logStatus("Merekam selesai — mengirim ke server...");
      // build blob (keep original mime type — server will convert to wav)
      const blob = new Blob(recordedChunks, {
        type: recordedChunks[0]?.type || "audio/webm",
      });
      // debug info
      console.log("Recorded blob type:", blob.type, "size:", blob.size);
      // upload
      const fd = new FormData();
      fd.append(
        "audio",
        blob,
        "recording." + (blob.type.includes("wav") ? "wav" : "webm")
      );
      try {
        const resp = await fetch("/record", { method: "POST", body: fd });
        const j = await resp.json();
        if (j && j.status === "ok") {
          logStatus("Analisis selesai — membuka hasil...");
          // redirect to result page
          window.location.href = j.result_url;
        } else {
          logStatus("Server gagal memproses rekaman.");
          console.error("Server response:", j);
        }
      } catch (err) {
        logStatus("Gagal mengirim rekaman: " + err.message);
        console.error(err);
      }
    };

    // 3) start recorder, but ensure recorder is started before playing backsound
    try {
      mediaRecorder.start();
      logStatus("Merekam... segera mulai backsound");
    } catch (err) {
      logStatus("Gagal memulai perekam: " + err.message);
      console.error(err);
      return;
    }

    // 4) set up lyric sync using backsound.currentTime
    if (!backsoundEl) {
      logStatus("Tidak menemukan elemen backsound di halaman.");
      // we still record but won't sync lyrics
    } else {
      // ensure audio is reset
      try {
        // some browsers prevent play() without user gesture — but we are inside click handler
        backsoundEl.currentTime = 0;
        await backsoundEl.play();
      } catch (err) {
        logStatus("Gagal memutar backsound: " + err.message);
        console.error(err);
      }

      // update lyrics frequently (every 200ms)
      lyricTimer = setInterval(() => {
        try {
          updateLyricByTime(backsoundEl.currentTime);
          // stop when backsound ends
          if (backsoundEl.ended) {
            clearInterval(lyricTimer);
            try {
              if (mediaRecorder && mediaRecorder.state === "recording")
                mediaRecorder.stop();
            } catch (e) {
              console.warn(e);
            }
          }
        } catch (e) {
          console.error(e);
        }
      }, 200);
    }
  } // end startRecordingSequence

  // Hook button
  recordBtn.addEventListener("click", async (ev) => {
    recordBtn.disabled = true;
    await startRecordingSequence();
  });

  // Fallback: show environment info
  console.log(
    "script_webaudio.js loaded. MediaRecorder supported:",
    !!window.MediaRecorder,
    "navigator.mediaDevices:",
    !!navigator.mediaDevices
  );
  logStatus("Siap. Klik 'Mulai Nyanyi' untuk memulai rekaman.");
});
