import os
import time
import threading
import json
from datetime import datetime, timedelta
from flask import Flask, render_template, jsonify, request
from flask_sqlalchemy import SQLAlchemy
from analyzer import get_file_hash, analyze_audio, calculate_metrics_from_midi

app = Flask(__name__)
# Configure DB
BASE_DIR = os.path.abspath(os.path.dirname(__file__))
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///' + os.path.join(BASE_DIR, 'instance', 'sonata.db')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)

# Ensure directories exist
UPLOAD_FOLDER = os.path.join(BASE_DIR, 'uploads')
MIDI_FOLDER = os.path.join(BASE_DIR, 'static', 'midi')
INSTANCE_FOLDER = os.path.join(BASE_DIR, 'instance')

os.makedirs(UPLOAD_FOLDER, exist_ok=True)
os.makedirs(MIDI_FOLDER, exist_ok=True)
os.makedirs(INSTANCE_FOLDER, exist_ok=True)

# Database Model
class Session(db.Model):
    __tablename__ = 'sessions'
    hash = db.Column(db.String(64), primary_key=True)
    date = db.Column(db.DateTime, default=datetime.now)
    filename = db.Column(db.String(256))
    total_duration = db.Column(db.Float)
    active_duration = db.Column(db.Float)
    keystrokes = db.Column(db.Integer)
    efficiency = db.Column(db.Float)
    waveform_json = db.Column(db.Text)
    intervals_json = db.Column(db.Text)
    midi_url = db.Column(db.String(256))

    def to_dict(self):
        return {
            'hash': self.hash,
            'date': self.date.isoformat(),
            'filename': self.filename,
            'total_duration': self.total_duration,
            'active_duration': self.active_duration,
            'keystrokes': self.keystrokes,
            'efficiency': self.efficiency,
            'waveform': json.loads(self.waveform_json) if self.waveform_json else [],
            'intervals': json.loads(self.intervals_json) if self.intervals_json else [],
            'midi_url': self.midi_url
        }

import shutil

# Background Worker
def process_uploads():
    """Background thread to process files in uploads/"""
    print("Background worker started...")
    while True:
        try:
            files = [f for f in os.listdir(UPLOAD_FOLDER) if f.lower().endswith('.wav')]
            for f in files:
                file_path = os.path.join(UPLOAD_FOLDER, f)
                
                # Check if file is fully written (simple check: size stable?)
                # Or just try to process.
                
                print(f"Processing {f}...")
                
                # Check for file stability (avoid processing partial copies)
                try:
                    init_size = os.path.getsize(file_path)
                    time.sleep(1) # Wait a bit
                    final_size = os.path.getsize(file_path)
                    if init_size != final_size:
                        print(f"File {f} is changing (copying?), skipping for now.")
                        continue
                    # Also check for zero size
                    if final_size == 0:
                         print(f"File {f} is empty, skipping.")
                         continue
                except Exception as e:
                    print(f"Error checking file stability {f}: {e}")
                    continue

                # 1. Hashing
                file_hash = get_file_hash(file_path)
                
                # Check DB
                with app.app_context():
                    existing = db.session.get(Session, file_hash)
                    if existing:
                        print(f"Duplicate file {f} (Hash: {file_hash}). Skipping.")
                        os.remove(file_path)
                        continue
                
                # 2. Analyze
                with app.app_context():
                    # We run analyze inside app context just in case, though analyzer is independent.
                    # analyze_audio returns a dict
                    result = analyze_audio(file_path, MIDI_FOLDER)
                
                if result:
                    # 3. Calculate Start Time (Metadata Extraction)
                    # Use mtime as end time, subtract duration to get start time
                    try:
                        mtime = os.path.getmtime(file_path)
                        dt_end = datetime.fromtimestamp(mtime)
                        # result['total_duration'] is float seconds
                        dt_start = dt_end - timedelta(seconds=result['total_duration'])
                        
                        # Fallback: Check filename for Date (YYMMDD prefix)
                        # Example: 260207_0009.wav -> 2026-02-07
                        if len(f) >= 6 and f[:6].isdigit():
                            try:
                                date_from_name = datetime.strptime(f[:6], '%y%m%d')
                                # If filename date differs from mtime date, trust filename for Day
                                if date_from_name.date() != dt_start.date():
                                    print(f"Date correction for {f}: {dt_start.date()} -> {date_from_name.date()}")
                                    dt_start = dt_start.replace(
                                        year=date_from_name.year,
                                        month=date_from_name.month,
                                        day=date_from_name.day
                                    )
                            except ValueError:
                                pass # Filename start with numbers but not a valid YYMMDD date

                    except Exception as e:
                        print(f"Error extracting time metadata, falling back to now: {e}")
                        dt_start = datetime.now()

                    new_session = Session(
                        hash=file_hash,
                        date=dt_start,
                        filename=f,
                        total_duration=result['total_duration'],
                        active_duration=result['active_duration'],
                        keystrokes=result['keystrokes'],
                        efficiency=result['efficiency'],
                        waveform_json=result['waveform'],
                        intervals_json=json.dumps(result['intervals']),
                        midi_url=result['midi_filename'] # This is just filename, frontend will prepend path
                    )

                    with app.app_context():
                        db.session.add(new_session)
                        db.session.commit()
                        print(f"Saved session for {f} (Date: {dt_start})")

                    # 4. Archive original file
                    if os.path.exists(file_path):
                        try:
                            archive_dir = os.path.join(BASE_DIR, 'archive')
                            os.makedirs(archive_dir, exist_ok=True)
                            
                            # Move file to archive directory
                            # Preserving original filename or potential unique name if collision?
                            # Hashes are unique, but filenames might repeat. Let's prepend hash or keep original.
                            # Just moving for now.
                            dest_path = os.path.join(archive_dir, f)
                            
                            # If destination exists, maybe rename?
                            if os.path.exists(dest_path):
                                base, ext = os.path.splitext(f)
                                dest_path = os.path.join(archive_dir, f"{base}_{file_hash[:6]}{ext}")
                                
                            os.rename(file_path, dest_path)
                            print(f"Archived {f} to {dest_path}")
                        except Exception as e:
                            print(f"Error archiving {f}: {e}")
                else:
                     print(f"Analysis failed for {f}")

        except Exception as e:
            print(f"Worker error: {e}")
        
        time.sleep(5) # Check every 5 seconds

# External Drive Sync Worker
def scan_external_drives():
    """Scans external drives for wav files and syncs to uploads"""
    print("External drive scanner started...")
    
    HISTORY_FILE = os.path.join(INSTANCE_FOLDER, 'sync_history.json')
    
    def load_history():
        if os.path.exists(HISTORY_FILE):
            try:
                with open(HISTORY_FILE, 'r') as f:
                    return json.load(f)
            except:
                return {}
        return {}

    def save_history(h):
        try:
            with open(HISTORY_FILE, 'w') as f:
                json.dump(h, f)
        except Exception as e:
            print(f"Error saving sync history: {e}")

    while True:
        try:
            # Detect Candidate Drives (D: to Z:)
            import string
            drives = []
            for letter in string.ascii_uppercase:
                if letter < 'D': continue 
                drive_path = f"{letter}:\\"
                music_path = os.path.join(drive_path, 'MUSIC')
                if os.path.exists(music_path):
                    drives.append(music_path)
            
            if drives:
                history = load_history()
                has_updates = False
                
                for music_dir in drives:
                    # Scan for wav files
                    try:
                        for f in os.listdir(music_dir):
                            if not f.lower().endswith('.wav'):
                                continue
                                
                            full_path = os.path.join(music_dir, f)
                            try:
                                stats = os.stat(full_path)
                                file_size = stats.st_size
                                file_mtime = stats.st_mtime
                                
                                # Identify file by path
                                file_key = full_path
                                
                                # Check History
                                if file_key in history:
                                    last_rec = history[file_key]
                                    if last_rec['size'] == file_size and abs(last_rec['mtime'] - file_mtime) < 1:
                                        continue # Skip, already processed
                                
                                # Also Check Archive (User Request: "Compare with Archive")
                                # Simple check: if filename exists in archive AND size matches, consider it done.
                                # This helps if history is lost but files are archived.
                                archive_path = os.path.join(BASE_DIR, 'archive', f)
                                if os.path.exists(archive_path):
                                    arc_stats = os.stat(archive_path)
                                    if arc_stats.st_size == file_size:
                                        # Likely same file
                                        print(f"Skipping {f} (Found in Archive)")
                                        # Update history to prevent re-check
                                        history[file_key] = {'size': file_size, 'mtime': file_mtime}
                                        has_updates = True
                                        continue
                                
                                # Check uploads (In case currently processing)
                                upload_dest = os.path.join(UPLOAD_FOLDER, f)
                                if os.path.exists(upload_dest):
                                    continue 
                                    
                                # COPY
                                print(f"Syncing new file: {full_path} -> {upload_dest}")
                                shutil.copy2(full_path, upload_dest)
                                
                                # Update History
                                history[file_key] = {'size': file_size, 'mtime': file_mtime}
                                has_updates = True
                                
                            except Exception as e:
                                print(f"Error checking file {f}: {e}")
                                
                    except Exception as e:
                        print(f"Error accessing {music_dir}: {e}")
                
                if has_updates:
                    save_history(history)
                    
        except Exception as e:
            print(f"Scanner error: {e}")
            
        time.sleep(10) # Scan every 10 seconds

# Start Workers
worker_thread = threading.Thread(target=process_uploads, daemon=True)
worker_thread.start()

scanner_thread = threading.Thread(target=scan_external_drives, daemon=True)
scanner_thread.start()

# Routes
@app.route('/')
def index():
    return render_template('index.html')

@app.route('/api/sessions')
def get_sessions():
    try:
        # Filter out sessions with < 50 keystrokes ("Touch Fish" / Noise)
        # Filter out empty/noise sessions (< 10 keystrokes)
        query = Session.query.filter(Session.keystrokes >= 10)
        
        # Optional Date Filter
        date_str = request.args.get('date')
        if date_str:
            try:
                target_date = datetime.strptime(date_str, '%Y-%m-%d')
                start_of_day = datetime(target_date.year, target_date.month, target_date.day, 0, 0, 0)
                end_of_day = datetime(target_date.year, target_date.month, target_date.day, 23, 59, 59)
                query = query.filter(Session.date >= start_of_day, Session.date <= end_of_day)
            except ValueError:
                print(f"Invalid date format received: {date_str}")
                pass 

        # Sort ascending for grouping
        sessions = query.order_by(Session.date.asc()).all()
        
        # 2. Grouping Logic (30 min threshold)
        groups = []
        if not sessions:
            return jsonify([])
            
        # Helper to ensure float
        def get_total_duration(s):
            return s.total_duration if s.total_duration is not None else 0.0

        current_group = {
            "sessions": [sessions[0]],
            "end_time": sessions[0].date + timedelta(seconds=get_total_duration(sessions[0]))
        }
        
        for i in range(1, len(sessions)):
            prev_end = current_group["end_time"]
            curr_start = sessions[i].date
            curr_end = sessions[i].date + timedelta(seconds=get_total_duration(sessions[i]))
            
            # Gap in seconds
            gap = (curr_start - prev_end).total_seconds()
            
            if gap < 1800: # 30 min = 1800 seconds
                # Add to current group
                current_group["sessions"].append(sessions[i])
                current_group["end_time"] = max(current_group["end_time"], curr_end)
            else:
                # Seal group and start new
                groups.append(current_group)
                current_group = {
                    "sessions": [sessions[i]],
                    "end_time": curr_end
                }
                
        groups.append(current_group)
        
        # 3. Format Output
        output = []
        for g in groups:
            s_list = g["sessions"]
            if not s_list:
                continue
                
            # Group summary
            group_start = s_list[0].date
            group_end = g["end_time"]
            
            # Safe summing
            total_active = sum((s.active_duration or 0) for s in s_list)
            total_keys = sum((s.keystrokes or 0) for s in s_list)
            
            output.append({
                "start_time": group_start.isoformat(),
                "end_time": group_end.isoformat(),
                "active_duration": total_active,
                "keystrokes": total_keys,
                "sessions": [s.to_dict() for s in s_list]
            })
            
        return jsonify(output)
    except Exception as e:
        print(f"Error in get_sessions: {e}")
        return jsonify({"error": str(e)}), 500

@app.route('/api/stats')
def get_stats():
    # Get date from query param or use today
    date_str = request.args.get('date')
    if date_str:
        target_date = datetime.strptime(date_str, '%Y-%m-%d')
    else:
        target_date = datetime.now()

    # Define "Day" boundaries (00:00:00 to 23:59:59)
    # Assuming system time is correct (User requested East 8, ensuring local consistency)
    start_of_day = datetime(target_date.year, target_date.month, target_date.day, 0, 0, 0)
    end_of_day = datetime(target_date.year, target_date.month, target_date.day, 23, 59, 59)
    
    # Filter < 50 keystrokes from stats
    sessions = Session.query.filter(
        Session.date >= start_of_day, 
        Session.date <= end_of_day,
        Session.keystrokes >= 10
    ).all()
    
    total_active_duration = sum(s.active_duration for s in sessions)
    total_keystrokes = sum(s.keystrokes for s in sessions)
    total_duration_today = sum(s.total_duration for s in sessions)
    avg_efficiency = (total_active_duration / total_duration_today) if total_duration_today > 0 else 0
    
    return jsonify({
        'date': start_of_day.strftime('%Y-%m-%d'),
        'today_duration': total_active_duration, # In seconds
        'today_keystrokes': total_keystrokes,
        'today_efficiency': avg_efficiency
    })

@app.route('/api/month_stats')
def get_month_stats():
    year = int(request.args.get('year', datetime.now().year))
    month = int(request.args.get('month', datetime.now().month))
    
    start_date = datetime(year, month, 1)
    if month == 12:
        end_date = datetime(year + 1, 1, 1)
    else:
        end_date = datetime(year, month + 1, 1)

    sessions = Session.query.filter(
        Session.date >= start_date, 
        Session.date < end_date,
        Session.keystrokes >= 10
    ).all()
    
    # Aggregate for Monthly Report
    total_audio_duration = sum(s.total_duration for s in sessions)
    total_active_duration = sum(s.active_duration for s in sessions)
    total_keystrokes = sum(s.keystrokes for s in sessions)
    monthly_efficiency = (total_active_duration / total_audio_duration) if total_audio_duration > 0 else 0
    
    # Daily breakdown for Calendar
    # Map: "YYYY-MM-DD" -> active_duration
    daily_map = {}
    for s in sessions:
        d_str = s.date.strftime('%Y-%m-%d')
        daily_map[d_str] = daily_map.get(d_str, 0) + s.active_duration
        
    return jsonify({
        'report': {
            'total_audio_duration': total_audio_duration,
            'total_active_duration': total_active_duration,
            'total_keystrokes': total_keystrokes,
            'efficiency': monthly_efficiency
        },
        'daily_map': daily_map
    })

# Admin Routes
@app.route('/admin')
def admin_page():
    return render_template('admin.html')

@app.route('/api/admin/sessions')
def admin_list_sessions():
    sessions = Session.query.order_by(Session.date.desc()).all()
    result = []
    
    # Simple cache for archive check performance if many files?
    # No need for now.
    
    for s in sessions:
        # Check archive existence
        # Note: Filename might be different if it was renamed during archive?
        # Current logic tries to keep filename.
        archive_path = os.path.join(BASE_DIR, 'archive', s.filename)
        
        result.append({
            "hash": s.hash,
            "date": s.date.isoformat(),
            "filename": s.filename,
            "total_duration": s.total_duration,
            "active_duration": s.active_duration,
            "keystrokes": s.keystrokes,
            "has_archive": os.path.exists(archive_path)
        })
    return jsonify(result)

@app.route('/api/admin/session/<hash_id>', methods=['DELETE'])
def admin_delete_session(hash_id):
    with app.app_context():
        s = db.session.get(Session, hash_id)
        if not s:
             return jsonify({"error": "Not found"}), 404
        
        # Delete MIDI
        if s.midi_url:
             midi_path = os.path.join(MIDI_FOLDER, s.midi_url)
             if os.path.exists(midi_path):
                 try: os.remove(midi_path)
                 except: pass
        
        db.session.delete(s)
        db.session.commit()
        return jsonify({"success": True})

@app.route('/api/admin/session/<hash_id>/reprocess', methods=['POST'])
def admin_reprocess_session(hash_id):
    with app.app_context():
        s = db.session.get(Session, hash_id)
        if not s:
             return jsonify({"error": "Not found"}), 404
        
        archive_path = os.path.join(BASE_DIR, 'archive', s.filename)
        if not os.path.exists(archive_path):
             return jsonify({"error": "Archive file not found in 'archive/'"}), 400
        
        try:
            # Copy back to uploads
            dest = os.path.join(UPLOAD_FOLDER, s.filename)
            print(f"Admin: Reprocessing {s.filename}, copy to {dest}")
            shutil.copy2(archive_path, dest)
            
            # Delete DB record & MIDI to ensure clean slate
            if s.midi_url:
                 midi_path = os.path.join(MIDI_FOLDER, s.midi_url)
                 if os.path.exists(midi_path):
                     try: os.remove(midi_path)
                     except: pass

            db.session.delete(s)
            db.session.commit()
            
            return jsonify({"success": True})
        except Exception as e:
            print(f"Reprocess error: {e}")
            return jsonify({"error": str(e)}), 500

@app.route('/api/admin/session/<hash_id>/recalc_stats', methods=['POST'])
def admin_recalc_stats(hash_id):
    with app.app_context():
        s = db.session.get(Session, hash_id)
        if not s or not s.midi_url:
             return jsonify({"error": "No MIDI found"}), 404
        
        midi_path = os.path.join(MIDI_FOLDER, s.midi_url)
        if not os.path.exists(midi_path):
             return jsonify({"error": "MIDI file missing"}), 404
        
        # We need duration_orig. It should be in s.total_duration
        if not s.total_duration:
             return jsonify({"error": "Total duration missing"}), 400
        
        metrics = calculate_metrics_from_midi(midi_path, s.total_duration)
        if metrics:
            s.active_duration = metrics['active_duration']
            s.efficiency = metrics['efficiency']
            s.keystrokes = metrics['keystrokes']
            if metrics['intervals']:
                s.intervals_json = json.dumps(metrics['intervals'])
            else:
                s.intervals_json = json.dumps([])
                
            db.session.commit()
            return jsonify({"success": True})
        else:
            return jsonify({"error": "Recalculation failed"}), 500

if __name__ == '__main__':
    with app.app_context():
        db.create_all()
    
    # Get local IP for convenience
    import socket
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        local_ip = s.getsockname()[0]
        s.close()
        print(f" * LAN Access: http://{local_ip}:5000")
    except:
        print(" * Could not determine LAN IP")

    app.run(host='0.0.0.0', port=5000, debug=True, use_reloader=False)
