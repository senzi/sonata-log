# SonataLog

SonataLog is a piano practice analysis dashboard that automatically tracks your practice sessions, analyzes efficiency, and converts pure practice segments to MIDI.

## Features

- **Automatic Monitoring**: Watches the `uploads/` folder for new WAV recordings.
- **Practice Analysis**: Uses adaptive thresholding to detect valid practice intervals (excluding pauses/distractions).
- **MIDI Conversion**: Converts pure audio segments to MIDI using Google's Basic Pitch.
- **Visual Dashboard**:
  - Daily Stats (Duration, Keystrokes, Efficiency).
  - Waveform visualization with practice intervals highlighted.
  - Heatmap of practice history.
- **Data Archival**: Stores analysis data in SQLite and keeps organized MIDI files.

## Installation

1. Install dependencies:
   ```bash
   pip install flask flask-sqlalchemy librosa numpy soundfile mido basic-pitch
   ```

2. Run the application:
   ```bash
   python app.py
   ```

3. Open your browser and navigate to:
   `http://localhost:5000`

## Usage

1. **Upload**: Simply drag and drop (or copy) your piano recording `.wav` files into the `uploads/` folder.
2. **Analysis**: The system will automatically detect the file, analyze it, and generate a report on the dashboard.
   - The original file will be processed and removed from `uploads/`.
   - The generated MIDI file will be saved in `static/midi/`.
3. **View**: Refresh the dashboard to see your new session.

## Project Structure

- `app.py`: Main application and background worker.
- `analyzer.py`: Audio analysis and MIDI conversion logic.
- `uploads/`: Drop your WAV files here.
- `static/`: CSS, JS, and generated MIDI files.
- `templates/`: HTML templates.
- `instance/`: SQLite database.
