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
        # Pre-calculate output path to clean up old files (force overwrite)
        base_name = os.path.basename(file_path)
        name_without_ext = os.path.splitext(base_name)[0]
        generated_midi_name = name_without_ext + "_basic_pitch.mid"
        expected_midi_path = os.path.join(output_midi_dir, generated_midi_name)
        
        if os.path.exists(expected_midi_path):
            try:
                os.remove(expected_midi_path)
            except Exception as e:
                print(f"Warning: Could not remove old MIDI {expected_midi_path}: {e}")

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
        
        if os.path.exists(expected_midi_path):
            midi_filename = generated_midi_name
            midi_path = expected_midi_path # Use consistency
            
            # Use shared calculation logic
            metrics = calculate_metrics_from_midi(midi_path, duration_orig)
            if metrics:
                active_duration_midi = metrics['active_duration']
                efficiency_midi = metrics['efficiency']
                keystrokes = metrics['keystrokes']
                intervals_sec = metrics['intervals']
                
    except Exception as e:
        print(f"MIDI generation/analysis failed: {e}")
        # Fallback to 0

    return {
        "total_duration": duration_orig,
        "active_duration": active_duration_midi,
        "efficiency": efficiency_midi,
        "keystrokes": keystrokes,
        "intervals": intervals_sec, # List of [start, end] derived from MIDI
        "waveform": generate_waveform_data(y_norm, sr),
        "midi_filename": midi_filename
    }

def calculate_metrics_from_midi(midi_path, duration_orig):
    """
    Recalculates metrics (active duration, efficiency, keystrokes) 
    from a MIDI file using current thresholds.
    """
    try:
        mid = mido.MidiFile(midi_path)
        
        # User defined threshold for "valid" practice
        MIN_VELOCITY = 70
        
        # 1. Extract valid note intervals
        valid_raw_intervals = []
        active_notes = {} # note -> start_time
        
        current_time = 0.0
        keystrokes = 0
        
        # mido.MidiFile is iterable and yields messages in playback order (delta times applied)
        for msg in mid:
            current_time += msg.time
            
            if msg.type == 'note_on' and msg.velocity >= MIN_VELOCITY:
                # Valid key press
                keystrokes += 1
                active_notes[msg.note] = current_time
                
            elif (msg.type == 'note_off') or (msg.type == 'note_on' and msg.velocity == 0):
                # Note ending
                if msg.note in active_notes:
                    start_t = active_notes.pop(msg.note)
                    end_t = current_time
                    if end_t > start_t: 
                        valid_raw_intervals.append((start_t, end_t))
        
        # Close any lingering notes
        for note, start_t in active_notes.items():
            if current_time > start_t:
                valid_raw_intervals.append((start_t, current_time))
        
        # 2. Merge Intervals
        intervals_sec = []
        active_duration_midi = 0.0
        efficiency_midi = 0.0
        
        if valid_raw_intervals:
            valid_raw_intervals.sort(key=lambda x: x[0])
            merged = []
            
            gap_threshold = 2.0
            
            # Initial
            curr_start, curr_end = valid_raw_intervals[0]
            
            for i in range(1, len(valid_raw_intervals)):
                next_start, next_end = valid_raw_intervals[i]
                
                if next_start - curr_end <= gap_threshold:
                    # Close enough, merge
                    curr_end = max(curr_end, next_end)
                else:
                    # Seal
                    start_padded = max(0, curr_start - 0.5)
                    end_padded = min(duration_orig, curr_end + 0.5)
                    merged.append([start_padded, end_padded])
                    
                    curr_start = next_start
                    curr_end = next_end
            
            # Last
            start_padded = max(0, curr_start - 0.5)
            end_padded = min(duration_orig, curr_end + 0.5)
            merged.append([start_padded, end_padded])
            
            intervals_sec = merged
            active_duration_midi = sum(end - start for start, end in merged)
            efficiency_midi = (active_duration_midi / duration_orig) if duration_orig > 0 else 0
            
        return {
            "active_duration": active_duration_midi,
            "efficiency": efficiency_midi,
            "keystrokes": keystrokes,
            "intervals": intervals_sec
        }
    except Exception as e:
        print(f"Error recalculating metrics from MIDI: {e}")
        return None
