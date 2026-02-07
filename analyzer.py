import os
# 屏蔽 TensorFlow 杂讯
os.environ['TF_CPP_MIN_LOG_LEVEL'] = '3'

import hashlib
import json
import librosa
import numpy as np
import soundfile as sf
import mido
from basic_pitch.inference import predict_and_save
from basic_pitch import ICASSP_2022_MODEL_PATH

def get_file_hash(file_path):
    """Calculates SHA-256 hash of a file."""
    sha256_hash = hashlib.sha256()
    with open(file_path, "rb") as f:
        for byte_block in iter(lambda: f.read(4096), b""):
            sha256_hash.update(byte_block)
    return sha256_hash.hexdigest()

def generate_waveform_data(y, sr):
    """Generates a compressed waveform envelope (100Hz)."""
    target_sr = 100
    hop_length = sr // target_sr
    if hop_length <= 0:
        hop_length = 1
    
    # Calculate max amplitude for each window
    envelope = [float(np.max(np.abs(y[i:i+hop_length]))) for i in range(0, len(y), hop_length)]
    return json.dumps(envelope)

def analyze_audio(file_path, output_midi_dir):
    """
    Analyzes the audio file:
    1. Load audio
    2. Calculate adaptive threshold and split (remove silence)
    3. Generate pure audio
    4. Convert to MIDI
    5. Calculate stats
    6. Return analysis data
    """
    if not os.path.exists(file_path):
        return None

    # 1. Load Audio
    y, sr = librosa.load(file_path, sr=None)
    y_norm = y / (np.max(np.abs(y)) + 1e-9)
    duration_orig = float(len(y) / sr)

    # 2. Adaptive Threshold & Split
    hop_length = 512
    rms = librosa.feature.rms(y=y_norm, hop_length=hop_length)[0]
    
    # Check if rms is empty or all zeros
    if len(rms) == 0 or np.max(rms) == 0:
        return {
            "total_duration": duration_orig,
            "active_duration": 0.0,
            "efficiency": 0.0,
            "keystrokes": 0,
            "intervals": [],
            "waveform": generate_waveform_data(y_norm, sr),
            "midi_filename": None
        }

    rms_db = librosa.amplitude_to_db(rms, ref=np.max)
    
    # 1. Calculate Adaptive Threshold
    noise_floor_ref = np.percentile(rms_db, 25)
    dynamic_threshold_db = noise_floor_ref + 15
    
    # 2. Safety Ceiling Logic (Critical Fix)
    # If the threshold is too high (meaning the recording is loud throughout), force it to a reasonable piano activity threshold.
    # Threshold is negative dB relative to max. split() uses positive top_db.
    # librosa.effects.split's top_db argument means "threshold below reference".
    # If dynamic_threshold_db is e.g. -10dB (very loud noise floor), top_db would be 10.
    # The user request logic says: "if dynamic_threshold_db > -30: dynamic_threshold_db = -45.0"
    # Note: rms_db values are usually negative (since ref=np.max).
    
    if dynamic_threshold_db > -30:
        dynamic_threshold_db = -45.0  # Empirical value for normalized piano recording
        
    # 3. Use corrected threshold for splitting
    # librosa.effects.split takes top_db as a positive value representing distance from peak.
    # If our threshold is -45dB, top_db should be 45.
    # So we pass -dynamic_threshold_db.
    
    intervals_samples = librosa.effects.split(y_norm, top_db=-dynamic_threshold_db, frame_length=2048, hop_length=hop_length)
    
    # Convert intervals to seconds for storage
    intervals_sec = [[float(start/sr), float(end/sr)] for start, end in intervals_samples]

    # Calculate active duration from intervals
    active_samples = 0
    for start, end in intervals_samples:
        active_samples += (end - start)
    
    duration_pure = float(active_samples / sr)
    
    # 4. MIDI Conversion (Direct from original file)
    midi_filename = None
    keystrokes = 0
    
    try:
        # Predict and save into output_midi_dir
        predict_and_save(
            audio_path_list=[file_path],
            output_directory=output_midi_dir,
            save_midi=True,
            sonify_midi=False,
            save_model_outputs=False,
            save_notes=False,
            model_or_model_path=ICASSP_2022_MODEL_PATH
        )
        
        # Construct expected MIDI filename
        # basic_pitch appends _basic_pitch.mid to the input filename
        base_name = os.path.basename(file_path)
        name_without_ext = os.path.splitext(base_name)[0]
        generated_midi_name = name_without_ext + "_basic_pitch.mid"
        midi_path = os.path.join(output_midi_dir, generated_midi_name)
        
        if os.path.exists(midi_path):
            midi_filename = generated_midi_name
            
            # 5. Count Keystrokes
            mid = mido.MidiFile(midi_path)
            for msg in mid:
                if msg.type == 'note_on' and msg.velocity > 0:
                    keystrokes += 1
        else:
             print(f"Warning: Expected MIDI file not found: {midi_path}")

    except Exception as e:
        print(f"MIDI generation failed: {e}")
        
    return {
        "total_duration": duration_orig,
        "active_duration": duration_pure,
        "efficiency": (duration_pure / duration_orig) if duration_orig > 0 else 0,
        "keystrokes": keystrokes,
        "intervals": intervals_sec, # List of [start, end]
        "waveform": generate_waveform_data(y_norm, sr), # JSON string
        "midi_filename": midi_filename
    }
