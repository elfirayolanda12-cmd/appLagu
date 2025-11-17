/** @format */

let chunks = [];
let recorder;
const recordBtn = document.getElementById("recordBtn");
const backsound = document.getElementById("backsound");
const lyricLine = document.getElementById("lyric-line");
const statusText = document.getElementById("status");

const lyrics = [
  "Indonesia tanah airku",
  "Tanah tumpah darahku",
  "Di sanalah aku berdiri",
  "Jadi pandu ibuku",
  "Indonesia kebangsaanku",
  "Bangsa dan tanah airku",
  "Marilah kita berseru",
  "Indonesia bersatu",
  "Hiduplah tanahku, hiduplah negeriku",
  "Bangsaku, rakyatku, semuanya",
  "Bangunlah jiwanya, bangunlah badannya",
  "Untuk Indonesia Raya",
  "Indonesia Raya, Merdeka, merdeka",
  "Tanahku, negeriku yang kucinta!",
  "Indonesia Raya, Merdeka, merdeka",
  "Hiduplah Indonesia Raya",
];

let i = 0;

recordBtn.addEventListener("click", async () => {
  // Reset state
  chunks = [];
  i = 0;
  statusText.textContent = "";
  lyricLine.textContent = "Bersiaplah...";

  const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
  recorder = new MediaRecorder(stream);

  recorder.ondataavailable = (e) => chunks.push(e.data);
  recorder.onstop = uploadAudio;

  // Delay 2 detik sebelum mulai
  setTimeout(() => {
    backsound.play();
    recorder.start();
    recordBtn.textContent = "⏺️ Sedang merekam...";
    lyricLine.textContent = lyrics[i];
    i++;

    // Ganti lirik setiap 3 detik
    let lyricInterval = setInterval(() => {
      lyricLine.textContent = lyrics[i];
      i++;
      if (i >= lyrics.length) {
        clearInterval(lyricInterval);
      }
    }, 3000);

    // Stop rekaman setelah 48 detik
    setTimeout(() => {
      recorder.stop();
      recordBtn.textContent = "⏹️ Mengirim hasil...";
      backsound.pause();
      backsound.currentTime = 0;
      statusText.textContent = "Analisis sedang diproses...";
    }, 48000);
  }, 2000);
});

function uploadAudio() {
  const blob = new Blob(chunks, { type: "audio/wav" });
  const formData = new FormData();
  formData.append("audio", blob, "record.wav");

  fetch("/record", { method: "POST", body: formData })
    .then((r) => r.json())
    .then((data) => {
      statusText.textContent = `🎉 Skor kamu: ${data.score}%\n💬 ${data.comment}`;
      setTimeout(() => {
        window.location.href = "/leaderboard";
      }, 5000);
    })
    .catch((err) => {
      statusText.textContent = "❌ Terjadi kesalahan saat mengirim audio.";
      console.error(err);
    });
}
