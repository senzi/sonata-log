import os
import time
import threading
import json
from datetime import datetime, timedelta
from flask import Flask, render_template, jsonify, request
from flask_sqlalchemy import SQLAlchemy
from analyzer import get_file_hash, analyze_audio

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

# Start Worker
worker_thread = threading.Thread(target=process_uploads, daemon=True)
worker_thread.start()

# Routes
@app.route('/')
def index():
    return render_template('index.html')

@app.route('/api/sessions')
def get_sessions():
    # Filter out sessions with < 50 keystrokes ("Touch Fish" / Noise)
    query = Session.query.filter(Session.keystrokes >= 50)
    
    # Optional Date Filter
    date_str = request.args.get('date')
    if date_str:
        try:
            target_date = datetime.strptime(date_str, '%Y-%m-%d')
            start_of_day = datetime(target_date.year, target_date.month, target_date.day, 0, 0, 0)
            end_of_day = datetime(target_date.year, target_date.month, target_date.day, 23, 59, 59)
            query = query.filter(Session.date >= start_of_day, Session.date <= end_of_day)
        except ValueError:
            pass # Ignore invalid date format

    sessions = query.order_by(Session.date.asc()).all()
    return jsonify([s.to_dict() for s in sessions])

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
        Session.keystrokes >= 50
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
        Session.keystrokes >= 50
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
