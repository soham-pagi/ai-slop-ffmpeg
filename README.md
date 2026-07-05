# 🎬 AI Video Maker: Image-to-Video Generator

An automated, AI-ready video generation pipeline built with **MoviePy**, **Pillow**, **Gradio**, and **FFmpeg**. It takes timestamped narration scripts, audio recordings, and images, transforming them into premium, dynamic videos with Ken Burns zoom/pan animations and cinematic fade transitions.

---

## ✨ Features

- **Dynamic Ken Burns Animations**: Automatically cycles through smooth zoom-in, zoom-out, and subtle panning effects (`pan_right_zoom_in`, `pan_left_zoom_in`) using high-quality LANCZOS resampling.
- **Cinematic Transitions**: Soft fade-in and fade-out transitions between consecutive clips keep the video feeling alive and moving without causing timeline drift.
- **Smart Image Mapping**:
  - **Index Mode (Default)**: Group images by filename prefix (e.g., `9.png` and `9.1.png` automatically map to timestamp index #9 and divide its duration).
  - **Sequential Mode**: Evenly distribute available images across all timestamp intervals.
- **Flexible Inputs**: Upload script files or paste raw text directly in the UI. Upload multiple images or point to a local directory.
- **Audio Synchronization**: Automatically attaches narration audio and reports calibration notes if audio length differs from script timestamps.

---

## 🚀 How to Run on Kaggle (or with GPU)

Kaggle provides powerful hardware and fast video encoding. This repository is structured to run out-of-the-box on Kaggle Notebooks!

### 1. In a Kaggle Notebook Cell (Gradio Web UI)

Open a new notebook cell in Kaggle and use the following **idempotent snippet** (safe to re-run without creating nested folders):

```python
# 0. Always start from Kaggle root working directory to prevent nested cloning!
%cd /kaggle/working

# 1. Clone repository (ignores error if already cloned)
!git clone https://github.com/soham-pagi/ai-slop-ffmpeg.git 2>/dev/null || true
%cd ai-slop-ffmpeg

# 2. Pull latest updates from git
!git pull

# 3. Install required dependencies
!pip install -r requirements.txt

# 4. Launch Gradio with public shareable link
!python app.py --share
```
*Click the `https://xxxx.gradio.live` link generated in your output to open the full UI, paste your script, upload images/audio, and generate videos directly in your browser!*

### 2. Via Command Line (CLI)

If you prefer running via terminal or script without a UI:

```bash
pip install -r requirements.txt
python main.py --script "scripts/How Ancient Humans Used Salt.txt" --audio "audio/How Ancient Humans Used Salt.wav" --images "images/How Ancient Humans Used Salt" --res 1920x1080 --fps 60
```

---

## 💻 Local Setup (with `uv` or `pip`)

### Using `uv` (Recommended)
```bash
# Sync dependencies
uv sync

# Launch Gradio UI locally
uv run python app.py

# Or run via CLI
uv run python main.py
```

### Using standard Python / pip
```bash
python -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate
pip install -r requirements.txt

python app.py
```

---

## 📁 Repository Structure

```text
├── app.py                   # Gradio Web UI Entry Point (supports file uploads & text pasting)
├── main.py                  # CLI Entry Point
├── pyproject.toml           # Project configuration and dependency definitions
├── requirements.txt         # Standard requirements for Kaggle / pip
├── src/
│   ├── timestamp_parser.py  # Parses script timestamps [MM:SS - MM:SS] & narration text
│   ├── image_mapper.py      # Maps images to timestamp segments (index/sequential)
│   ├── effects.py           # Ken Burns zoom/pan frame generator & fade transitions
│   └── video_generator.py   # Orchestrates audio/video assembly and FFmpeg encoding
├── scripts/                 # Sample script files
├── audio/                   # Sample audio files
├── images/                  # Sample images
└── output_video/            # Generated video exports
```

---

## 🛠️ CLI Arguments for `main.py`

| Argument | Description | Default |
| :--- | :--- | :--- |
| `--script` | Path to script text file with timestamps | `scripts/How Ancient Humans Used Salt.txt` |
| `--audio` | Path to audio narration file | `audio/How Ancient Humans Used Salt.wav` |
| `--images` | Path to images directory | `images/How Ancient Humans Used Salt` |
| `--output` | Target output video path | `output_video/How_Ancient_Humans_Used_Salt.mp4` |
| `--mapping` | Strategy: `index` or `sequential` | `index` |
| `--res` | Resolution in WIDTHxHEIGHT | `1920x1080` |
| `--fps` | Video frame rate | `60` |
| `--transition` | Fade transition duration in seconds | `0.4` |
