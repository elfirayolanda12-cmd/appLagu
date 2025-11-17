/** @format */
// Enhanced version with Pause/Resume functionality

document.addEventListener("DOMContentLoaded", () => {
  const recordBtn = document.getElementById("recordBtn");
  const pauseBtn = document.getElementById("pauseBtn");
  const resumeBtn = document.getElementById("resumeBtn");
  const stopBtn = document.getElementById("stopBtn");
  const statusEl = document.getElementById("status");
  const lyricLine = document.getElementById("lyricLine");
  const timerEl = document.getElementById("timer");
  const backsoundEl = document.getElementById("backsound");

  // Lyric timings
  const lyricTimings = [
    { time: 5.0, text: "Indonesia tanah airku" },
    { time: 10.0, text: "Tanah tumpah darahku" },
    { time: 14.0, text: "Di sanalah aku berdiri" },
    { time: 19.0, text: "Jadi pandu ibuku" },
    { time: 25.0, text: "Indonesia kebangsaanku" },
    { time: 30.0, text: "Bangsa dan tanah airku" },
    { time: 35.0, text: "Marilah kita berseru" },
    { time: 40.0, text: "Indonesia bersatu" },
    { time: 45.0, text: "Hiduplah tanahku, Hiduplah neg'riku" },
    { time: 50.0, text: "Bangsaku, rakyatku, semuanya" },
    { time: 55.0, text: "Bangunlah jiwanya, Bangunlah badannya" },
    { time: 60.0, text: "Untuk Indonesia Raya" },
    { time: 65.0, text: "Indonesia Raya, Merdeka, merdeka" },
    { time: 70.0, text: "Tanahku, neg'riku yang kucinta!" },
    { time: 75.0, text: "Indonesia Raya, Merdeka, merdeka" },
    { time: 80.0, text: "Hiduplah Indonesia Raya" },
  ];

  // State
  let mediaRecorder = null;
  let recordedChunks = [];
  let lyricTimer = null;
  let recordingStartTime = 0;
  let elapsedTime = 0;
  let isPaused = false;

  function logStatus(msg) {
    console.log("[KARAOKE]", msg);
    if (statusEl) statusEl.textContent = msg;
  }

  function formatTime(seconds) {
    const mins = Math.floor(seconds / 60);
    const secs = Math.floor(seconds % 60);
    return `${String(mins).padStart(2, "0")}:${String(secs).padStart(2, "0")}`;
  }

  function updateLyricByTime(t) {
    for (let i = lyricTimings.length - 1; i >= 0; i--) {
      if (t >= lyricTimings[i].time) {
        if (lyricLine && lyricLine.textContent !== lyricTimings[i].text) {
          lyricLine.textContent = "🎵 " + lyricTimings[i].text;
        }
        return;
      }
    }
    if (lyricLine) lyricLine.textContent = "🎤 Bersiap...";
  }

  async function startRecordingSequence() {
    logStatus("Meminta izin mikrofon...");
    recordedChunks = [];

    // Request microphone
    let stream;
    try {
      stream = await navigator.mediaDevices.getUserMedia({ audio: true });
    } catch (err) {
      logStatus("❌ Gagal akses mikrofon: " + err.message);
      console.error(err);
      return;
    }

    logStatus("✅ Izin diterima. Menyiapkan perekam...");

    // Create MediaRecorder
    try {
      mediaRecorder = new MediaRecorder(stream);
    } catch (err) {
      logStatus("❌ MediaRecorder tidak tersedia di browser ini.");
      console.error(err);
      return;
    }

    mediaRecorder.ondataavailable = (e) => {
      if (e.data && e.data.size > 0) recordedChunks.push(e.data);
    };

    mediaRecorder.onstop = async () => {
      logStatus("📤 Mengirim rekaman ke server...");

      const blob = new Blob(recordedChunks, { type: "audio/webm" });
      const fd = new FormData();
      fd.append("audio", blob, "recording.webm");

      try {
        const resp = await fetch("/record", { method: "POST", body: fd });
        const j = await resp.json();

        if (j && j.status === "ok") {
          logStatus("✅ Analisis selesai!");
          window.location.href = j.result_url;
        } else {
          logStatus("❌ Server gagal memproses rekaman.");
          console.error("Server response:", j);
        }
      } catch (err) {
        logStatus("❌ Gagal mengirim rekaman: " + err.message);
        console.error(err);
      }
    };

    // Start recording
    try {
      mediaRecorder.start();
      recordingStartTime = Date.now();
      logStatus("🎙️ Merekam...");

      // Show control buttons
      recordBtn.style.display = "none";
      pauseBtn.style.display = "inline-block";
      pauseBtn.disabled = false;
      stopBtn.style.display = "inline-block";
      stopBtn.disabled = false;
      timerEl.style.display = "block";

      // Try to play backsound
      if (backsoundEl) {
        try {
          backsoundEl.currentTime = 0;
          await backsoundEl.play();
          logStatus("🎵 Backsound diputar. Mulai nyanyi!");
        } catch (err) {
          logStatus("⚠️ Backsound tidak bisa diputar. Rekaman tetap berjalan.");
          console.error("Backsound error:", err);
          document.getElementById("noBacksoundWarning").style.display = "block";
        }
      }

      // Update timer and lyrics
      lyricTimer = setInterval(() => {
        if (!isPaused) {
          elapsedTime = (Date.now() - recordingStartTime) / 1000;
          timerEl.textContent = formatTime(elapsedTime);

          if (backsoundEl && !backsoundEl.paused) {
            updateLyricByTime(backsoundEl.currentTime);

            // Auto stop when backsound ends
            if (backsoundEl.ended) {
              stopRecording();
            }
          }
        }
      }, 100);
    } catch (err) {
      logStatus("❌ Gagal memulai perekam: " + err.message);
      console.error(err);
    }
  }

  function pauseRecording() {
    if (mediaRecorder && mediaRecorder.state === "recording") {
      mediaRecorder.pause();
      if (backsoundEl && !backsoundEl.paused) {
        backsoundEl.pause();
      }
      isPaused = true;
      logStatus("⏸️ Rekaman di-pause");

      pauseBtn.style.display = "none";
      resumeBtn.style.display = "inline-block";
      resumeBtn.disabled = false;
    }
  }

  function resumeRecording() {
    if (mediaRecorder && mediaRecorder.state === "paused") {
      mediaRecorder.resume();
      if (backsoundEl && backsoundEl.paused) {
        backsoundEl.play();
      }
      recordingStartTime = Date.now() - elapsedTime * 1000;
      isPaused = false;
      logStatus("▶️ Rekaman dilanjutkan");

      resumeBtn.style.display = "none";
      pauseBtn.style.display = "inline-block";
      pauseBtn.disabled = false;
    }
  }

  function stopRecording() {
    if (
      mediaRecorder &&
      (mediaRecorder.state === "recording" || mediaRecorder.state === "paused")
    ) {
      mediaRecorder.stop();
      if (backsoundEl) {
        backsoundEl.pause();
        backsoundEl.currentTime = 0;
      }
      if (lyricTimer) {
        clearInterval(lyricTimer);
      }

      pauseBtn.disabled = true;
      resumeBtn.disabled = true;
      stopBtn.disabled = true;

      logStatus("⏹️ Rekaman selesai. Memproses...");
    }
  }

  // Event listeners
  recordBtn.addEventListener("click", async () => {
    recordBtn.disabled = true;
    await startRecordingSequence();
  });

  pauseBtn.addEventListener("click", pauseRecording);
  resumeBtn.addEventListener("click", resumeRecording);
  stopBtn.addEventListener("click", stopRecording);

  // Check backsound availability
  if (backsoundEl) {
    backsoundEl.addEventListener("error", () => {
      console.warn("Backsound file not found or cannot be loaded");
      document.getElementById("noBacksoundWarning").style.display = "block";
    });
  }

  logStatus("✅ Siap. Klik 'Mulai Rekam' untuk memulai!");
});
