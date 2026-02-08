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
    
    # 4. MIDI Generation (Direct from original file)
    midi_filename = None
    keystrokes = 0
    intervals_sec = []
    active_duration_midi = 0.0
    efficiency_midi = 0.0
    
    try:
        # Predict and save
        predict_and_save(
            audio_path_list=[file_path],
            output_directory=output_midi_dir,
            save_midi=True,
            sonify_midi=False,
            save_model_outputs=False,
            save_notes=False,
            model_or_model_path=ICASSP_2022_MODEL_PATH
        )
        
        base_name = os.path.basename(file_path)
        name_without_ext = os.path.splitext(base_name)[0]
        generated_midi_name = name_without_ext + "_basic_pitch.mid"
        midi_path = os.path.join(output_midi_dir, generated_midi_name)
        
        if os.path.exists(midi_path):
            midi_filename = generated_midi_name
            
            # --- New MIDI-based Efficiency Calculation ---
            mid = mido.MidiFile(midi_path)
            
            # 1. Extract note start/end times
            # Note: mido messages have 'time' as delta time. We need absolute time.
            # basic-pitch MIDI files are usually Type 0 or 1.
            # We need to iterate and accumulate time.
            
            notes = []
            
            # Helper to get absolute timing from MIDI
            # mido.MidiFile iteration yields messages with 'time' in seconds if not using raw ticks
            # basic-pitch output usually has normalized logic. 
            
            abs_time = 0.0
            pending_notes = {} # note_number -> start_time
            
            for msg in mid:
                abs_time += msg.time
                
                if msg.type == 'note_on' and msg.velocity > 0:
                    keystrokes += 1
                    if msg.note not in pending_notes:
                         pending_notes[msg.note] = abs_time
                         
                elif (msg.type == 'note_off') or (msg.type == 'note_on' and msg.velocity == 0):
                    if msg.note in pending_notes:
                        start_t = pending_notes.pop(msg.note)
                        notes.append((start_t, abs_time))
            
            # Also close any pending notes at the end? (Though typically note_off should exist)
            for note, start_t in pending_notes.items():
                notes.append((start_t, abs_time))
                
            # 2. Merge Intervals
            if notes:
                notes.sort(key=lambda x: x[0])
                merged = []
                
                # Logic: Gap Threshold = 2.0s
                # Merge logic from user request
                gap_threshold = 2.0
                
                # Initial interval
                curr_start = notes[0][0]
                curr_end = notes[0][1]
                
                for i in range(1, len(notes)):
                    next_start, next_end = notes[i]
                    
                    if next_start - curr_end <= gap_threshold:
                        # Close enough, merge
                        curr_end = max(curr_end, next_end)
                    else:
                        # Too far, seal current and start new
                        start_padded = max(0, curr_start - 0.5)
                        end_padded = min(duration_orig, curr_end + 0.5)
                        merged.append([start_padded, end_padded])
                        
                        curr_start = next_start
                        curr_end = next_end
                
                # Append last
                start_padded = max(0, curr_start - 0.5)
                end_padded = min(duration_orig, curr_end + 0.5)
                merged.append([start_padded, end_padded])
                
                intervals_sec = merged
                
                # 3. Calculate Efficiency
                active_duration_midi = sum(end - start for start, end in merged)
                efficiency_midi = (active_duration_midi / duration_orig) if duration_orig > 0 else 0
                
    except Exception as e:
        print(f"MIDI generation/analysis failed: {e}")
        # Fallback to 0 or original audio stats? 
        # User explicitly wants MIDI based. If it fails, 0 is safer than wrong audio calc.

    return {
        "total_duration": duration_orig,
        "active_duration": active_duration_midi,
        "efficiency": efficiency_midi,
        "keystrokes": keystrokes,
        "intervals": intervals_sec, # List of [start, end] derived from MIDI
        "waveform": generate_waveform_data(y_norm, sr),
        "midi_filename": midi_filename
    }
