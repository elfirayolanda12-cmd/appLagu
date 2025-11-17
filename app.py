# app.py - IMPLEMENTASI REFERENCE PER BARIS LAGU
from flask import Flask, render_template, request, jsonify, url_for
from flask_mysqldb import MySQL
import os, datetime, io, base64
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

# Optional libs
HAS_LIBROSA = True
try:
    import librosa
    import librosa.display
except Exception:
    HAS_LIBROSA = False

HAS_PYDUB = True
try:
    from pydub import AudioSegment
except Exception:
    HAS_PYDUB = False

from scipy.stats import pearsonr
from scipy.spatial.distance import euclidean
from fastdtw import fastdtw

app = Flask(__name__)

# ---------- CONFIG DB ----------
app.config['MYSQL_HOST'] = 'localhost'
app.config['MYSQL_USER'] = 'root'
app.config['MYSQL_PASSWORD'] = ''
app.config['MYSQL_DB'] = 'db_prosodi'
mysql = MySQL(app)

# ---------- UPLOAD FOLDER ----------
app.config['UPLOAD_FOLDER'] = os.path.join(os.getcwd(), 'uploads')
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

# ---------- REFERENSI VEKTOR PER BARIS ----------
REFERENCE_PATH = r"D:\##SKRIPSI\project\v_referensi_hybrid.npy"
reference_per_line = None

print(f"\n{'='*60}")
print(f"🔄 LOADING REFERENCE DATA")
print(f"{'='*60}")

if os.path.exists(REFERENCE_PATH):
    try:
        v_ref_raw = np.load(REFERENCE_PATH, allow_pickle=True)
        print(f"✅ Reference file found: {REFERENCE_PATH}")
        print(f"   Raw shape/type: {v_ref_raw.shape if hasattr(v_ref_raw, 'shape') else type(v_ref_raw)}")
        
        # Check if it's a dictionary (per-line reference)
        if isinstance(v_ref_raw, dict):
            reference_per_line = v_ref_raw
            print(f"✅ Using dictionary-based reference")
            print(f"   Number of lines: {len(reference_per_line)}")
            print(f"   Keys: {list(reference_per_line.keys())[:5]}...")
            
        # Check if it's item() wrapped (numpy 0-d array)
        elif hasattr(v_ref_raw, 'item') and isinstance(v_ref_raw.item(), dict):
            reference_per_line = v_ref_raw.item()
            print(f"✅ Unwrapped numpy 0-d array to dictionary")
            print(f"   Number of lines: {len(reference_per_line)}")
            
        # Check if it's 2D array with 16 rows
        elif hasattr(v_ref_raw, 'shape') and len(v_ref_raw.shape) == 2 and v_ref_raw.shape[0] == 16:
            reference_per_line = {i+1: v_ref_raw[i] for i in range(16)}
            print(f"✅ Converted 2D array to per-line reference")
            print(f"   Shape: {v_ref_raw.shape}")
            
        else:
            # Fallback: split equally into 16 parts
            ref_flat = np.asarray(v_ref_raw).flatten()
            seg_len = len(ref_flat) // 16
            if seg_len > 0:
                reference_per_line = {i+1: ref_flat[i*seg_len:(i+1)*seg_len] for i in range(16)}
                print(f"⚠️ Using fallback: splitting reference into 16 equal parts")
                print(f"   Segment length: {seg_len}")
            else:
                print(f"❌ Reference data too small to split")
                reference_per_line = None
        
        # Validate reference
        if reference_per_line:
            print(f"\n📊 Reference validation:")
            for line_num in [1, 2, 3]:
                if line_num in reference_per_line:
                    ref_shape = reference_per_line[line_num].shape if hasattr(reference_per_line[line_num], 'shape') else 'N/A'
                    print(f"   Line {line_num}: shape = {ref_shape}")
        
    except Exception as e:
        print(f"❌ Failed to load reference: {e}")
        import traceback
        traceback.print_exc()
        reference_per_line = None
else:
    print(f"❌ Reference file not found: {REFERENCE_PATH}")

print(f"{'='*60}\n")

# CRITICAL: Exit if no reference
if reference_per_line is None:
    print("⚠️ WARNING: Running without reference data!")
    print("   Per-line comparison will NOT work.")
    print("   Only simple overall scoring will be used.\n")


# ---------- LYRICS WITH TIMING ----------
LYRICS_WITH_TIMING = [
    {"line": 1, "text": "Indonesia tanah airku", "start": 5.0, "end": 10.0},
    {"line": 2, "text": "Tanah tumpah darahku", "start": 10.0, "end": 14.0},
    {"line": 3, "text": "Di sanalah aku berdiri", "start": 14.0, "end": 19.0},
    {"line": 4, "text": "Jadi pandu ibuku", "start": 19.0, "end": 25.0},
    {"line": 5, "text": "Indonesia kebangsaanku", "start": 25.0, "end": 30.0},
    {"line": 6, "text": "Bangsa dan tanah airku", "start": 30.0, "end": 35.0},
    {"line": 7, "text": "Marilah kita berseru", "start": 35.0, "end": 40.0},
    {"line": 8, "text": "Indonesia bersatu", "start": 40.0, "end": 45.0},
    {"line": 9, "text": "Hiduplah tanahku, Hiduplah neg'riku", "start": 45.0, "end": 50.0},
    {"line": 10, "text": "Bangsaku, rakyatku, semuanya", "start": 50.0, "end": 55.0},
    {"line": 11, "text": "Bangunlah jiwanya, Bangunlah badannya", "start": 55.0, "end": 60.0},
    {"line": 12, "text": "Untuk Indonesia Raya", "start": 60.0, "end": 65.0},
    {"line": 13, "text": "Indonesia Raya, Merdeka, merdeka", "start": 65.0, "end": 70.0},
    {"line": 14, "text": "Tanahku, neg'riku yang kucinta!", "start": 70.0, "end": 75.0},
    {"line": 15, "text": "Indonesia Raya, Merdeka, merdeka", "start": 75.0, "end": 80.0},
    {"line": 16, "text": "Hiduplah Indonesia Raya", "start": 80.0, "end": 85.0},
]

LYRICS = [item["text"] for item in LYRICS_WITH_TIMING]

# ========== NEW: Audio Pre-processing ==========
def preprocess_audio_for_analysis(audio_path):
    """
    Pre-process audio untuk meningkatkan kualitas deteksi pitch
    - Normalisasi volume
    - Filter noise
    - Boost signal
    """
    print(f"\n🔧 Pre-processing audio: {os.path.basename(audio_path)}")
    
    if not HAS_PYDUB:
        print("   ⚠️ pydub not available, skipping pre-processing")
        return audio_path
    
    try:
        # Load audio
        sound = AudioSegment.from_file(audio_path)
        
        # 1. Normalisasi volume (boost signal)
        sound = sound.normalize()
        print(f"   ✅ Normalized volume")
        
        # 2. High-pass filter (remove low frequency noise)
        sound = sound.high_pass_filter(80)
        print(f"   ✅ Applied high-pass filter (80 Hz)")
        
        # 3. Low-pass filter (remove high frequency noise)
        sound = sound.low_pass_filter(500)
        print(f"   ✅ Applied low-pass filter (500 Hz)")
        
        # 4. Increase gain (amplify)
        sound = sound + 10  # Increase by 10 dB
        print(f"   ✅ Increased gain by 10 dB")
        
        # 5. Convert to mono & standard sample rate
        sound = sound.set_channels(1)
        sound = sound.set_frame_rate(22050)
        print(f"   ✅ Converted to mono, 22050 Hz")
        
        # 6. Save processed version
        processed_path = audio_path.replace('.wav', '_processed.wav')
        sound.export(processed_path, format='wav')
        print(f"   ✅ Saved to: {os.path.basename(processed_path)}")
        
        return processed_path
        
    except Exception as e:
        print(f"   ❌ Pre-processing failed: {e}")
        return audio_path  # Return original if failed


# ========== Helper: convert to WAV ==========
def convert_to_wav(in_path):
    name, ext = os.path.splitext(in_path)
    ext = ext.lower()
    out_path = f"{name}.wav"
    if ext == '.wav':
        return in_path
    if not HAS_PYDUB:
        return in_path
    try:
        audio = AudioSegment.from_file(in_path)
        audio.export(out_path, format='wav')
        return out_path
    except Exception as e:
        print("Conversion failed:", e)
        return in_path

# ========== Audio Analysis ==========
def safe_load_audio(path):
    path_read = convert_to_wav(path)
    if not HAS_LIBROSA:
        raise RuntimeError("librosa not installed.")
    y, sr = librosa.load(path_read, sr=None)
    return y, sr

def analyze_audio_features(path, max_secs=None):
    print(f"\n{'='*60}")
    print(f"🎵 ANALYZING AUDIO: {os.path.basename(path)}")
    print(f"{'='*60}")
    
    try:
        y, sr = safe_load_audio(path)
        print(f"✅ Audio loaded successfully")
        print(f"   Sample rate: {sr} Hz")
        print(f"   Audio length: {len(y)} samples ({len(y)/sr:.2f} seconds)")
    except Exception as e:
        print(f"❌ Error loading audio: {e}")
        return {"duration":0, "tempo":0, "intensity":0, "f0":[], "avg_pitch":0, "pitch_std":0, "y":None, "sr":None}

    if max_secs and len(y) > sr * max_secs:
        y = y[:sr*max_secs]
        print(f"⚠️ Audio trimmed to {max_secs} seconds")

    # Deteksi silence - LEBIH TOLERAN
    print(f"\n🔍 Checking for silence...")
    non_silent_intervals = librosa.effects.split(y, top_db=40)
    
    if len(non_silent_intervals) == 0:
        print("❌ Audio hanya berisi keheningan")
        return {
            'error': 'Audio hanya berisi keheningan. Silakan rekam dengan bernyanyi.',
            'duration': 0, 'tempo': 0, 'intensity': 0, 'f0': [],
            'avg_pitch': 0, 'pitch_std': 0, 'y': None, 'sr': None
        }
    
    total_non_silent = np.sum(non_silent_intervals[:, 1] - non_silent_intervals[:, 0]) / sr
    print(f"✅ Non-silent duration: {total_non_silent:.2f} seconds")
    print(f"   Number of voice segments: {len(non_silent_intervals)}")
    
    # THRESHOLD: 3 detik (lebih toleran)
    if total_non_silent < 3:
        print(f"❌ Audio terlalu pendek: {total_non_silent:.2f} detik")
        return {
            'error': f'Suara terdeteksi hanya {total_non_silent:.1f} detik. Minimal 3 detik.',
            'duration': 0, 'tempo': 0, 'intensity': 0, 'f0': [],
            'avg_pitch': 0, 'pitch_std': 0, 'y': None, 'sr': None
        }

    # Basic features
    duration = float(librosa.get_duration(y=y, sr=sr))
    print(f"\n📊 Basic Features:")
    print(f"   Total duration: {duration:.2f} seconds")
    
    tempo_arr = librosa.beat.tempo(y=y, sr=sr)
    tempo = float(tempo_arr[0]) if tempo_arr.size>0 else 0.0
    print(f"   Tempo: {tempo:.2f} BPM")
    
    rms = librosa.feature.rms(y=y)
    intensity = float(np.mean(rms)) if rms.size>0 else 0.0
    print(f"   Intensity (RMS): {intensity:.4f}")
    
    # Pitch extraction dengan parameter lebih robust
    print(f"\n🎼 Extracting pitch (f0)...")
    try:
        f0 = librosa.yin(
            y, 
            fmin=60,      # Lebih rendah
            fmax=500,     # Lebih tinggi
            frame_length=2048, 
            hop_length=256,
            trough_threshold=0.1
        )
        
        print(f"   Total f0 frames: {len(f0)}")
        
        valid_f0 = f0[~np.isnan(f0)]
        print(f"   Valid pitch frames: {len(valid_f0)} ({len(valid_f0)/len(f0)*100:.1f}%)")
        
        if len(valid_f0) > 0:
            avg_pitch = float(np.mean(valid_f0))
            pitch_std = float(np.std(valid_f0))
            min_pitch = float(np.min(valid_f0))
            max_pitch = float(np.max(valid_f0))
            
            print(f"   ✅ Pitch statistics:")
            print(f"      Mean: {avg_pitch:.2f} Hz")
            print(f"      Std: {pitch_std:.2f} Hz")
            print(f"      Range: {min_pitch:.2f} - {max_pitch:.2f} Hz")
        else:
            print(f"   ❌ No valid pitch detected")
            avg_pitch = 0.0
            pitch_std = 0.0
            
    except Exception as e:
        print(f"❌ Pitch extraction failed: {e}")
        f0 = np.array([])
        avg_pitch = 0.0
        pitch_std = 0.0

    print(f"{'='*60}\n")
    
    return {
        "duration": round(duration,2),
        "tempo": round(tempo,2),
        "intensity": round(intensity,4),
        "f0": f0,
        "avg_pitch": round(avg_pitch,2),
        "pitch_std": round(pitch_std,2),
        "y": y,
        "sr": sr
    }

# ========== Extract Features Per Line (Prosody) ==========
def extract_prosody_features(f0_segment, duration_sec):
    """Extract prosody features from a pitch segment"""
    valid_f0 = f0_segment[~np.isnan(f0_segment)]
    
    print(f"      📊 Pitch points: {len(valid_f0)} valid out of {len(f0_segment)} total")
    
    if len(valid_f0) < 3:
        print(f"      ⚠️ Too few valid pitch points ({len(valid_f0)})")
        return None
    
    features = {
        'mean_pitch': float(np.mean(valid_f0)),
        'std_pitch': float(np.std(valid_f0)),
        'min_pitch': float(np.min(valid_f0)),
        'max_pitch': float(np.max(valid_f0)),
        'range_pitch': float(np.max(valid_f0) - np.min(valid_f0)),
        'duration': duration_sec,
        'pitch_contour': valid_f0
    }
    
    return features

def segment_audio_by_timing(y, sr, f0, lyrics_timing):
    """Segment audio and pitch based on timing info"""
    hop_length = 256
    segments = []
    
    for item in lyrics_timing:
        line_num = item['line']
        start_sec = item['start']
        end_sec = item['end']
        text = item['text']
        
        start_sample = int(start_sec * sr)
        end_sample = int(end_sec * sr)
        start_frame = int(start_sec * sr / hop_length)
        end_frame = int(end_sec * sr / hop_length)
        
        y_seg = y[start_sample:end_sample]
        f0_seg = f0[start_frame:end_frame]
        
        duration = end_sec - start_sec
        features = extract_prosody_features(f0_seg, duration)
        
        segments.append({
            'line': line_num,
            'text': text,
            'features': features,
            'f0_segment': f0_seg,
            'y_segment': y_seg
        })
    
    return segments

# ========== Compare with Reference (Per Line) ==========
def compare_with_reference_per_line(user_segments, reference_dict):
    """Compare user segments with pre-computed reference per line"""
    if not user_segments or not reference_dict:
        print("⚠️ Empty segments or reference")
        return [], 0.0
    
    feedback = []
    similarities = []
    
    for seg in user_segments:
        line_num = seg['line']
        text = seg['text']
        user_feat = seg['features']
        
        print(f"🔍 Processing Line {line_num}: {text}")
        
        if user_feat is None:
            print(f"   ❌ No features extracted for line {line_num}")
            feedback.append({
                'line': line_num,
                'text': text,
                'status': 'Tidak terdeteksi suara',
                'similarity': 0
            })
            similarities.append(0)
            continue
        
        print(f"   ✅ User features: pitch={user_feat['mean_pitch']:.2f}, duration={user_feat['duration']:.2f}s")
        
        ref_feat = reference_dict.get(line_num)
        
        if ref_feat is None:
            print(f"   ⚠️ No reference for line {line_num}")
            feedback.append({
                'line': line_num,
                'text': text,
                'status': 'Tidak ada referensi',
                'similarity': 0
            })
            similarities.append(0)
            continue
        
        if isinstance(ref_feat, np.ndarray) and len(ref_feat.shape) == 1:
            ref_mean_pitch = 180
            ref_std_pitch = 30
            
            pitch_diff = abs(user_feat['mean_pitch'] - ref_mean_pitch)
            
            if pitch_diff < 10:
                pitch_similarity = 100
            elif pitch_diff < 20:
                pitch_similarity = 90
            elif pitch_diff < 30:
                pitch_similarity = 80
            elif pitch_diff < 50:
                pitch_similarity = 60
            else:
                pitch_similarity = max(0, 100 - pitch_diff)
            
            if user_feat['std_pitch'] > 50:
                stability_penalty = 10
            elif user_feat['std_pitch'] > 30:
                stability_penalty = 5
            else:
                stability_penalty = 0
            
            similarity = max(0, pitch_similarity - stability_penalty)
            
        else:
            try:
                ref_features = ref_feat if isinstance(ref_feat, dict) else {}
                ref_mean_pitch = ref_features.get('mean_pitch', 180)
                
                pitch_diff = abs(user_feat['mean_pitch'] - ref_mean_pitch)
                similarity = max(0, 100 - pitch_diff * 2)
                
            except Exception as e:
                print(f"   ⚠️ Error processing reference: {e}")
                similarity = 50
        
        similarities.append(similarity)
        
        if similarity >= 85:
            status = "✅ Sangat Baik"
        elif similarity >= 70:
            status = "👍 Baik"
        elif similarity >= 50:
            status = "😊 Cukup Baik"
        elif similarity >= 30:
            status = "📈 Perlu Latihan"
        else:
            status = "💪 Tetap Semangat"
        
        print(f"   📊 Similarity: {similarity:.1f}%, Status: {status}")
        
        feedback.append({
            'line': line_num,
            'text': text,
            'status': status,
            'similarity': round(similarity, 1)
        })
    
    if similarities:
        overall_similarity = np.mean(similarities)
        print(f"\n🎯 Overall Similarity: {overall_similarity:.2f}%")
    else:
        overall_similarity = 0.0
        print(f"\n❌ No valid similarities calculated")
    
    return feedback, round(overall_similarity, 2)

# ========== Plotting ==========
def plot_waveform_base64(y, sr):
    fig, ax = plt.subplots(figsize=(8,2.2), dpi=100)
    librosa.display.waveshow(y, sr=sr, ax=ax, color='steelblue')
    ax.set(title='Waveform')
    buf = io.BytesIO()
    plt.tight_layout()
    fig.savefig(buf, format='png')
    plt.close(fig)
    buf.seek(0)
    return base64.b64encode(buf.read()).decode('ascii')

def plot_pitch_base64(f0, sr, hop_length=256):
    fig, ax = plt.subplots(figsize=(8,2.2), dpi=100)
    if f0 is None or len(f0)==0:
        ax.text(0.5,0.5,"No pitch data", ha='center', va='center')
    else:
        times = librosa.times_like(f0, sr=sr, hop_length=hop_length)
        ax.plot(times, f0, color='tomato')
    ax.set(title='Pitch contour (Hz)', xlabel='Time (s)', ylabel='Hz')
    buf = io.BytesIO()
    plt.tight_layout()
    fig.savefig(buf, format='png')
    plt.close(fig)
    buf.seek(0)
    return base64.b64encode(buf.read()).decode('ascii')

# ========== NEW: Fallback Simple Scoring ==========
def calculate_simple_overall_score(analysis):
    """
    Simple scoring based on overall audio statistics
    Fallback jika per-line comparison gagal
    """
    print(f"\n🎯 Calculating simple overall score...")
    
    score = 0
    
    # 1. Pitch accuracy (40%)
    ref_mean_pitch = 180  # Hz untuk Indonesia Raya
    pitch_diff = abs(analysis['avg_pitch'] - ref_mean_pitch)
    
    if pitch_diff < 10:
        pitch_score = 40
    elif pitch_diff < 20:
        pitch_score = 35
    elif pitch_diff < 30:
        pitch_score = 30
    elif pitch_diff < 50:
        pitch_score = 20
    else:
        pitch_score = 10
    
    print(f"   Pitch score: {pitch_score}/40 (diff: {pitch_diff:.1f} Hz)")
    
    # 2. Pitch stability (30%)
    if analysis['pitch_std'] < 20:
        stability_score = 30
    elif analysis['pitch_std'] < 30:
        stability_score = 25
    elif analysis['pitch_std'] < 40:
        stability_score = 20
    else:
        stability_score = 10
    
    print(f"   Stability score: {stability_score}/30 (std: {analysis['pitch_std']:.1f})")
    
    # 3. Duration (15%)
    if 80 < analysis['duration'] < 100:
        duration_score = 15
    elif 70 < analysis['duration'] < 110:
        duration_score = 10
    else:
        duration_score = 5
    
    print(f"   Duration score: {duration_score}/15 (duration: {analysis['duration']:.1f}s)")
    
    # 4. Intensity (15%)
    if analysis['intensity'] > 0.01:
        intensity_score = 15
    elif analysis['intensity'] > 0.005:
        intensity_score = 10
    else:
        intensity_score = 5
    
    print(f"   Intensity score: {intensity_score}/15 (intensity: {analysis['intensity']:.4f})")
    
    total_score = pitch_score + stability_score + duration_score + intensity_score
    print(f"   📊 Total score: {total_score}/100\n")
    
    return min(100, total_score)

# ========== Komentar lucu ==========
def generate_comment(analysis, similarity, pitch_feedback):
    score = similarity
    avg_pitch = analysis.get('avg_pitch', 0)
    pitch_std = analysis.get('pitch_std', 0)

    if score >= 90:
        base = "🎤 Wah! Suaramu hampir sekelas penyanyi profesional! 😎"
    elif score >= 80:
        base = "Bagus! Tinggal sedikit lagi biar makin keren 🎯"
    elif score >= 70:
        base = "Oke juga, tapi masih bisa diasah lagi 💪"
    elif score >= 50:
        base = "Lumayan, masih perlu latihan lagi 🎵"
    else:
        base = "Tenang, latihan bikin jago! Semua penyanyi pernah fals kok 🎵"

    extra = []
    if pitch_std > 30:
        extra.append("Coba latihan stabilisasi nada biar lebih konsisten 🎶")
    if avg_pitch < 120:
        extra.append("Nada rendah dominan – perbanyak latihan nada tinggi 📈")
    
    low_score_lines = [p for p in pitch_feedback if p.get('similarity', 100) < 60]
    if low_score_lines:
        extra.append(f"Perhatikan baris {', '.join(str(p['line']) for p in low_score_lines[:3])} yang masih perlu diperbaiki 📊")

    return base + " " + " ".join(extra)

# ========== ROUTES ==========
@app.route('/leaderboard')
def leaderboard():
    """Halaman leaderboard lengkap"""
    try:
        cur = mysql.connection.cursor()
        cur.execute("""
            SELECT 
                nama_user, 
                similarity_score, 
                avg_pitch, 
                tempo,
                pitch_var,
                duration,
                tanggal 
            FROM evaluasi_user 
            ORDER BY similarity_score DESC, tanggal DESC 
            LIMIT 20
        """)
        top_users = cur.fetchall()
        cur.close()
    except Exception as e:
        print("Leaderboard query error:", e)
        top_users = []
    
    try:
        cur = mysql.connection.cursor()
        cur.execute("SELECT COUNT(*), AVG(similarity_score), MAX(similarity_score) FROM evaluasi_user")
        stats = cur.fetchone()
        cur.close()
        
        total_users = stats[0] if stats else 0
        avg_score = round(stats[1], 2) if stats and stats[1] else 0
        top_score = round(stats[2], 2) if stats and stats[2] else 0
    except Exception as e:
        print("Stats error:", e)
        total_users = 0
        avg_score = 0
        top_score = 0
    
    return render_template('leaderboard.html', 
                         leaderboard=top_users,
                         total_users=total_users,
                         avg_score=avg_score,
                         top_score=top_score)

@app.route('/belajar')
def belajar():
    """Halaman pembelajaran interaktif Indonesia Raya"""
    return render_template('belajar.html')

@app.route('/')
def index():
    return render_template('index_webaudio.html')

@app.route('/record', methods=['POST'])
def record():
    if 'audio' not in request.files:
        return jsonify({"status": "error", "message": "No audio file uploaded"}), 400

    in_file = request.files['audio']
    ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    base_name = f"user_record_{ts}"
    webm_path = os.path.join(app.config['UPLOAD_FOLDER'], f"{base_name}.webm")
    wav_path = os.path.join(app.config['UPLOAD_FOLDER'], f"{base_name}.wav")

    in_file.save(webm_path)
    print(f"\n💾 File uploaded: {os.path.basename(webm_path)} ({os.path.getsize(webm_path)} bytes)")

    # --- KONVERSI ke WAV dengan verifikasi ---
    try:
        if HAS_PYDUB:
            print(f"🔄 Converting to WAV...")
            sound = AudioSegment.from_file(webm_path, format="webm")
            
            # PENTING: Normalisasi audio untuk meningkatkan volume
            sound = sound.normalize()
            
            sound.export(wav_path, format="wav", parameters=["-ar", "22050", "-ac", "1"])
            os.remove(webm_path)
            saved_path = wav_path
            print(f"✅ Converted to WAV: {os.path.basename(wav_path)} ({os.path.getsize(wav_path)} bytes)")
        else:
            saved_path = webm_path
            print("⚠️ pydub not available, using webm directly")
    except Exception as e:
        print(f"❌ Conversion error: {e}")
        saved_path = webm_path

    # === Analisis audio ===
    analysis = analyze_audio_features(saved_path, max_secs=90)
    
    # ========== VALIDASI DENGAN THRESHOLD LEBIH RENDAH ==========
    comment = ""
    pitch_feedback = []
    similarity_score = 0
    
    # Cek jika ada error dari analyze_audio_features
    if 'error' in analysis:
        similarity_score = 0
        comment = analysis['error']
        pitch_feedback = []
        print(f"⚠️ Analysis returned error: {comment}")
    
    # PERUBAHAN: Threshold lebih rendah dan toleran
    elif analysis["duration"] < 2:  # Turunkan dari 3
        similarity_score = 0
        comment = "⚠️ Rekaman terlalu pendek! Minimal 2 detik ya."
        pitch_feedback = []
        print(f"⚠️ Duration too short: {analysis['duration']}s")

    elif analysis["intensity"] < 0.0005:  # Turunkan dari 0.0015
        similarity_score = 0
        comment = "🔇 Tidak terdeteksi suara yang cukup kuat. Coba nyanyi lebih keras!"
        pitch_feedback = []
        print(f"⚠️ Intensity too low: {analysis['intensity']}")

    elif analysis["f0"] is None or len(analysis["f0"]) == 0:
        similarity_score = 0
        comment = "🎵 Tidak terdeteksi pitch/nada. Pastikan kamu benar-benar bernyanyi!"
        pitch_feedback = []
        print(f"⚠️ No f0 data")

    elif len(analysis["f0"]) > 0:
        valid_ratio = 1 - (np.isnan(analysis["f0"]).sum() / len(analysis["f0"]))
        print(f"📊 Valid pitch ratio: {valid_ratio*100:.1f}%")
        
        # PERUBAHAN: Cukup 5% valid pitch (sangat toleran)
        if valid_ratio < 0.05:
            similarity_score = 0
            comment = "🎤 Pitch terlalu sedikit terdeteksi. Nyanyi dengan nada yang jelas ya!"
            pitch_feedback = []
            print(f"⚠️ Valid pitch ratio too low: {valid_ratio*100:.1f}%")
        
        # PERUBAHAN: Range pitch lebih lebar
        elif analysis["avg_pitch"] < 50 or analysis["avg_pitch"] > 600:
            similarity_score = 0
            comment = "🎶 Pitch di luar jangkauan normal. Ada yang janggal nih..."
            pitch_feedback = []
            print(f"⚠️ Pitch out of range: {analysis['avg_pitch']} Hz")
        
        else:
            # === SEGMENT PER BARIS & COMPARE ===
            print(f"\n{'='*60}")
            print(f"🎵 SEGMENTING & COMPARING")
            print(f"{'='*60}")
            
            user_segments = segment_audio_by_timing(
                analysis['y'],
                analysis['sr'],
                analysis['f0'],
                LYRICS_WITH_TIMING
            )
            
            print(f"✅ Created {len(user_segments)} segments\n")
            
            pitch_feedback, similarity_score = compare_with_reference_per_line(
                user_segments,
                reference_per_line
            )
            
            print(f"\n{'='*60}")
            print(f"📊 FINAL RESULTS")
            print(f"{'='*60}")
            print(f"✅ Generated {len(pitch_feedback)} feedback items")
            print(f"🎯 Final Score: {similarity_score}/100")
            print(f"{'='*60}\n")
            
            if similarity_score == 0 and len(pitch_feedback) == 0:
                comment = "⚠️ Gagal menganalisis. Coba rekam ulang dengan suara lebih jelas."
            else:
                comment = generate_comment(analysis, similarity_score, pitch_feedback)

    else:
        # Fallback
        similarity_score = 0
        comment = "⚠️ Tidak dapat menganalisis audio. Coba lagi."
        pitch_feedback = []

    # === Generate grafik ===
    try:
        y, sr = analysis['y'], analysis['sr']
        if y is not None and sr is not None:
            waveform_b64 = plot_waveform_base64(y, sr)
            pitch_b64 = plot_pitch_base64(analysis.get('f0', np.array([])), sr)
        else:
            waveform_b64 = None
            pitch_b64 = None
    except Exception as e:
        print(f"❌ Plot error: {e}")
        waveform_b64 = None
        pitch_b64 = None

    # === Simpan ke database ===
    try:
        cur = mysql.connection.cursor()
        cur.execute("""
            INSERT INTO evaluasi_user
            (nama_user, file_path, similarity_score, duration, avg_pitch, intensity, tempo, pitch_var, comment, tanggal)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,NOW())
        """, (
            "anon",
            saved_path,
            similarity_score,
            analysis.get('duration', 0.0),
            analysis.get('avg_pitch', 0.0),
            analysis.get('intensity', 0.0),
            analysis.get('tempo', 0.0),
            analysis.get('pitch_std', 0.0),
            comment
        ))
        mysql.connection.commit()
        cur.close()
        print(f"✅ Data saved to database")
    except Exception as e:
        print(f"❌ DB insert error: {e}")

    return jsonify({
        "status": "ok",
        "filename": os.path.basename(saved_path),
        "score": similarity_score,
        "comment": comment,
        "waveform_b64": waveform_b64,
        "pitch_b64": pitch_b64,
        "result_url": url_for('result', filename=os.path.basename(saved_path), score=similarity_score)
    })

    if 'audio' not in request.files:
        return jsonify({"status": "error", "message": "No audio file uploaded"}), 400

    in_file = request.files['audio']
    ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    base_name = f"user_record_{ts}"
    webm_path = os.path.join(app.config['UPLOAD_FOLDER'], f"{base_name}.webm")
    wav_path = os.path.join(app.config['UPLOAD_FOLDER'], f"{base_name}.wav")

    in_file.save(webm_path)

    # --- KONVERSI ke WAV ---
    try:
        if HAS_PYDUB:
            sound = AudioSegment.from_file(webm_path, format="webm")
            sound.export(wav_path, format="wav")
            os.remove(webm_path)
            saved_path = wav_path
            print("✅ Converted to WAV:", wav_path)
        else:
            saved_path = webm_path
    except Exception as e:
        print("Conversion error:", e)
        saved_path = webm_path

    # === Analisis audio ===
    analysis = analyze_audio_features(saved_path, max_secs=90)
    
    # ========== PERBAIKAN INDENTASI: INI HARUS DI DALAM FUNGSI record() ==========
    comment = ""
    pitch_feedback = []
    similarity_score = 0
    
    # Cek jika ada error dari analyze_audio_features
    if 'error' in analysis:
        similarity_score = 0
        comment = analysis['error']
        pitch_feedback = []
    
    # --- VALIDASI KEHENINGAN ---
    elif analysis["duration"] < 3:
        similarity_score = 0
        comment = "⚠️ Rekaman terlalu pendek! Minimal 3 detik ya."
        pitch_feedback = []

    elif analysis["intensity"] < 0.0015:
        similarity_score = 0
        comment = "🔇 Tidak terdeteksi suara yang cukup kuat. Coba nyanyi lebih keras!"
        pitch_feedback = []

    elif analysis["f0"] is None or len(analysis["f0"]) == 0:
        similarity_score = 0
        comment = "🎵 Tidak terdeteksi pitch/nada. Pastikan kamu benar-benar bernyanyi!"
        pitch_feedback = []

    elif np.isnan(analysis["f0"]).sum() / len(analysis["f0"]) > 0.9:
        similarity_score = 0
        comment = "🎤 Pitch terlalu sedikit terdeteksi. Nyanyi dengan nada yang jelas ya!"
        pitch_feedback = []

    elif analysis["avg_pitch"] < 60 or analysis["avg_pitch"] > 500:
        similarity_score = 0
        comment = "🎶 Pitch di luar jangkauan normal. Ada yang janggal nih..."
        pitch_feedback = []

    else:
        # === SEGMENT PER BARIS & COMPARE ===
        print("\n🎵 Segmenting audio by lines...")
        user_segments = segment_audio_by_timing(
            analysis['y'],
            analysis['sr'],
            analysis['f0'],
            LYRICS_WITH_TIMING
        )
        
        print(f"✅ Created {len(user_segments)} segments")
        
        print("\n🔄 Comparing with reference...")
        pitch_feedback, similarity_score = compare_with_reference_per_line(
            user_segments,
            reference_per_line
        )
        
        print(f"✅ Generated {len(pitch_feedback)} feedback items")
        print(f"🎯 Final Score: {similarity_score}")
        
        if similarity_score == 0 and len(pitch_feedback) == 0:
            comment = "⚠️ Gagal menganalisis. Coba rekam ulang dengan suara lebih jelas."
        else:
            comment = generate_comment(analysis, similarity_score, pitch_feedback)

    # === Generate grafik ===
    try:
        y, sr = analysis['y'], analysis['sr']
        if y is not None and sr is not None:
            waveform_b64 = plot_waveform_base64(y, sr)
            pitch_b64 = plot_pitch_base64(analysis.get('f0', np.array([])), sr)
        else:
            waveform_b64 = None
            pitch_b64 = None
    except Exception as e:
        print("Plot error:", e)
        waveform_b64 = None
        pitch_b64 = None

    # === Simpan ke database ===
    try:
        cur = mysql.connection.cursor()
        cur.execute("""
            INSERT INTO evaluasi_user
            (nama_user, file_path, similarity_score, duration, avg_pitch, intensity, tempo, pitch_var, comment, tanggal)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,NOW())
        """, (
            "anon",
            saved_path,
            similarity_score,
            analysis.get('duration', 0.0),
            analysis.get('avg_pitch', 0.0),
            analysis.get('intensity', 0.0),
            analysis.get('tempo', 0.0),
            analysis.get('pitch_std', 0.0),
            comment
        ))
        mysql.connection.commit()
        cur.close()
    except Exception as e:
        print("DB insert error:", e)

    return jsonify({
        "status": "ok",
        "filename": os.path.basename(saved_path),
        "score": similarity_score,
        "comment": comment,
        "waveform_b64": waveform_b64,
        "pitch_b64": pitch_b64,
        "result_url": url_for('result', filename=os.path.basename(saved_path), score=similarity_score)
    })

@app.route('/result/<filename>/<float:score>')
def result(filename, score):
    path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
    try:
        wav = convert_to_wav(path)
        analysis = analyze_audio_features(wav)
        
        user_segments = segment_audio_by_timing(
            analysis['y'], 
            analysis['sr'], 
            analysis['f0'], 
            LYRICS_WITH_TIMING
        )
        pitch_feedback, _ = compare_with_reference_per_line(user_segments, reference_per_line)
        
        y, sr = analysis['y'], analysis['sr']
        waveform_b64 = plot_waveform_base64(y, sr)
        pitch_b64 = plot_pitch_base64(analysis.get('f0', np.array([])), sr)
    except Exception as e:
        print("result page error", e)
        analysis = {"duration":0,"tempo":0,"intensity":0,"avg_pitch":0,"pitch_std":0}
        waveform_b64 = None
        pitch_b64 = None
        pitch_feedback = []

    leaderboard = []
    try:
        cur = mysql.connection.cursor()
        cur.execute("SELECT nama_user, similarity_score, tempo, avg_pitch, tanggal FROM evaluasi_user ORDER BY similarity_score DESC LIMIT 5")
        leaderboard = cur.fetchall()
        cur.close()
    except Exception as e:
        print("Leaderboard error:", e)

    comment = generate_comment(analysis, score, pitch_feedback)

    return render_template('result.html', filename=filename, score=score,
                           analysis=analysis, waveform_b64=waveform_b64,
                           pitch_b64=pitch_b64, comment=comment,
                           pitch_feedback=pitch_feedback, leaderboard=leaderboard,
                           similarity_score=score)

if __name__ == '__main__':
    app.run(debug=True)
