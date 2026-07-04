import os
import json
import argparse
import base64
import io
import gradio as gr
from typing import Any
from PIL import Image
from src.video_generator import generate_video

# Default paths matching project repository structure
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DEFAULT_SCRIPT_PATH = os.path.join(BASE_DIR, "scripts", "How Ancient Humans Used Salt.txt")
DEFAULT_AUDIO_PATH = os.path.join(BASE_DIR, "audio", "How Ancient Humans Used Salt.wav")
DEFAULT_IMAGES_DIR = os.path.join(BASE_DIR, "images", "How Ancient Humans Used Salt")

# Load default script text if available
DEFAULT_SCRIPT_TEXT = ""
if os.path.exists(DEFAULT_SCRIPT_PATH):
    with open(DEFAULT_SCRIPT_PATH, "r", encoding="utf-8") as f:
        DEFAULT_SCRIPT_TEXT = f.read()


def get_image_thumbnail_b64(image_path, max_size=(80, 50)):
    """Return base64 thumbnail data URI for an image."""
    try:
        if not os.path.exists(image_path):
            return ""
        with Image.open(image_path) as img:
            img.thumbnail(max_size)
            buf = io.BytesIO()
            img.save(buf, format="JPEG", quality=75)
            b64 = base64.b64encode(buf.getvalue()).decode('utf-8')
            return f"data:image/jpeg;base64,{b64}"
    except Exception:
        return ""


def build_timeline_html(rows):
    """
    Build the HTML for the drag-and-drop timeline table.
    rows: list of dicts with keys: idx, thumb_b64, filename, path, start, duration
    """
    if not rows:
        return """
        <div style="text-align:center; padding:40px; color:#888; font-size:14px;">
            Click <b>"🔄 Populate Table"</b> after uploading images to build your timeline.
        </div>
        """

    row_html = ""
    for i, r in enumerate(rows):
        thumb = r.get("thumb_b64", "")
        fname = r.get("filename", "")
        start = r.get("start", "0.0")
        dur = r.get("duration", "5.0")
        path = r.get("path", "")
        thumb_img = f'<img src="{thumb}" style="height:44px; border-radius:4px; object-fit:cover;" />' if thumb else '<span style="font-size:20px;">🖼️</span>'

        row_html += f"""
        <tr data-idx="{i}" data-path="{path}" data-filename="{fname}"
            style="cursor:grab; transition: background 0.15s;"
            onmouseenter="this.style.background='#e3f0ff'"
            onmouseleave="this.style.background=''">
          <td style="width:32px; text-align:center; color:#aaa; font-size:16px; cursor:grab;">⠿</td>
          <td style="padding:4px 6px; text-align:center;">{thumb_img}</td>
          <td style="padding:4px 8px; font-size:13px; font-family:monospace; max-width:180px; overflow:hidden; text-overflow:ellipsis; white-space:nowrap;">{fname}</td>
          <td style="padding:4px 6px;">
            <input type="text" value="{start}" data-field="start"
                   style="width:70px; padding:3px 6px; border:1px solid #ccc; border-radius:4px; font-size:13px; text-align:center; font-family:monospace;"
                   onchange="window.__timelineChanged && window.__timelineChanged()" />
          </td>
          <td style="padding:4px 6px;">
            <input type="text" value="{dur}" data-field="duration"
                   style="width:70px; padding:3px 6px; border:1px solid #ccc; border-radius:4px; font-size:13px; text-align:center; font-family:monospace;"
                   onchange="window.__timelineChanged && window.__timelineChanged()" />
          </td>
        </tr>
        """

    return f"""
    <table id="timeline-drag-table" style="width:100%; border-collapse:collapse; font-size:14px;">
      <thead>
        <tr style="background:#f0f4fa; border-bottom:2px solid #d0d7e3;">
          <th style="width:32px; padding:6px;"></th>
          <th style="padding:6px 8px; text-align:center; font-size:12px; color:#555;">Preview</th>
          <th style="padding:6px 8px; text-align:left; font-size:12px; color:#555;">Filename</th>
          <th style="padding:6px 8px; text-align:center; font-size:12px; color:#555;">Start (s)</th>
          <th style="padding:6px 8px; text-align:center; font-size:12px; color:#555;">Duration (s)</th>
        </tr>
      </thead>
      <tbody id="timeline-tbody">
        {row_html}
      </tbody>
    </table>
    """


# JavaScript to initialize SortableJS and sync state back to Gradio via hidden JSON input
SORTABLE_INIT_JS = """
async () => {
    // Load SortableJS from CDN if not already loaded
    if (!window.Sortable) {
        await new Promise((resolve, reject) => {
            const script = document.createElement('script');
            script.src = 'https://cdn.jsdelivr.net/npm/sortablejs@1.15.6/Sortable.min.js';
            script.onload = resolve;
            script.onerror = reject;
            document.head.appendChild(script);
        });
    }

    function initSortable() {
        const tbody = document.getElementById('timeline-tbody');
        if (!tbody) {
            setTimeout(initSortable, 500);
            return;
        }
        if (tbody._sortableInstance) {
            tbody._sortableInstance.destroy();
        }
        tbody._sortableInstance = new Sortable(tbody, {
            animation: 200,
            handle: 'td:first-child',
            ghostClass: 'sortable-ghost',
            chosenClass: 'sortable-chosen',
            onEnd: function() {
                syncToGradio();
            }
        });
    }

    window.__timelineChanged = function() {
        syncToGradio();
    };

    function syncToGradio() {
        const tbody = document.getElementById('timeline-tbody');
        if (!tbody) return;
        const rows = tbody.querySelectorAll('tr');
        const data = [];
        rows.forEach((tr) => {
            const startInput = tr.querySelector('input[data-field="start"]');
            const durInput = tr.querySelector('input[data-field="duration"]');
            data.push({
                path: tr.getAttribute('data-path') || '',
                filename: tr.getAttribute('data-filename') || '',
                start: startInput ? startInput.value : '0.0',
                duration: durInput ? durInput.value : '5.0'
            });
        });
        // Write to hidden JSON textarea
        const hiddenEl = document.querySelector('#timeline-json-bridge textarea');
        if (hiddenEl) {
            hiddenEl.value = JSON.stringify(data);
            hiddenEl.dispatchEvent(new Event('input', { bubbles: true }));
        }
    }

    // Add ghost styling
    if (!document.getElementById('sortable-style')) {
        const style = document.createElement('style');
        style.id = 'sortable-style';
        style.textContent = `
            .sortable-ghost { background: #dbeafe !important; opacity: 0.6; }
            .sortable-chosen { background: #bfdbfe !important; box-shadow: 0 2px 8px rgba(0,0,0,0.12); }
            #timeline-drag-table tr td:first-child:hover { color: #2563eb !important; }
        `;
        document.head.appendChild(style);
    }

    // Observe DOM for table re-renders
    const observer = new MutationObserver(() => {
        if (document.getElementById('timeline-tbody')) {
            initSortable();
        }
    });
    observer.observe(document.body, { childList: true, subtree: true });

    initSortable();
}
"""


def populate_timeline(script_mode, script_file, script_text, audio_file, image_mode, images_folder, uploaded_images, mapping_mode):
    """Populate the timeline from uploaded images. Returns (html, json_data)."""
    try:
        from src.image_mapper import map_images_to_timestamps
        from src.timestamp_parser import parse_script, parse_script_text
        try:
            from moviepy import AudioFileClip
        except ImportError:
            from moviepy.editor import AudioFileClip  # type: ignore

        images_source = ""
        if image_mode == "Select Local Folder" and images_folder and os.path.exists(images_folder):
            images_source = images_folder
        elif image_mode == "Upload Image Files" and uploaded_images:
            images_source = [f.name if hasattr(f, "name") else f for f in uploaded_images]
        else:
            empty_html = build_timeline_html([])
            return empty_html, "[]"

        audio_dur = 0.0
        if audio_file and os.path.exists(audio_file):
            try:
                clip = AudioFileClip(audio_file)
                audio_dur = clip.duration or 0.0
            except Exception:
                pass

        timestamps = None
        if script_mode == "Upload File" and script_file:
            path = script_file.name if hasattr(script_file, "name") else script_file
            _, timestamps = parse_script(path)
        elif script_mode == "Paste Text" and script_text and script_text.strip():
            _, timestamps = parse_script_text(script_text)

        mapped = map_images_to_timestamps(images_source, timestamps=timestamps, mode=mapping_mode, audio_duration=audio_dur)

        rows = []
        for mc in mapped:
            rows.append({
                "thumb_b64": get_image_thumbnail_b64(mc.image_path),
                "filename": os.path.basename(mc.image_path),
                "path": mc.image_path,
                "start": str(round(mc.start_time, 2)),
                "duration": str(round(mc.duration, 2))
            })

        html = build_timeline_html(rows)
        json_data = json.dumps([{"path": r["path"], "filename": r["filename"], "start": r["start"], "duration": r["duration"]} for r in rows])
        return html, json_data
    except Exception as e:
        error_html = f'<div style="color:red; padding:12px;">❌ Error: {str(e)}</div>'
        return error_html, "[]"


def equalize_durations(audio_file, json_str):
    """Equalize durations across all rows based on audio length."""
    try:
        rows = json.loads(json_str) if json_str else []
        if not rows:
            return build_timeline_html([]), "[]"

        try:
            from moviepy import AudioFileClip
        except ImportError:
            from moviepy.editor import AudioFileClip  # type: ignore

        if audio_file and os.path.exists(audio_file):
            clip = AudioFileClip(audio_file)
            total_dur = clip.duration or 0.0
            per_dur = round(total_dur / len(rows), 2) if len(rows) > 0 else 5.0
        else:
            per_dur = 5.0

        new_rows = []
        curr_t = 0.0
        for r in rows:
            new_rows.append({
                "thumb_b64": get_image_thumbnail_b64(r.get("path", "")),
                "filename": r.get("filename", ""),
                "path": r.get("path", ""),
                "start": str(round(curr_t, 2)),
                "duration": str(per_dur)
            })
            curr_t += per_dur

        html = build_timeline_html(new_rows)
        json_data = json.dumps([{"path": r["path"], "filename": r["filename"], "start": r["start"], "duration": r["duration"]} for r in new_rows])
        return html, json_data
    except Exception:
        return build_timeline_html([]), "[]"


def sort_by_timestamp(json_str):
    """Sort rows by start timestamp."""
    try:
        rows = json.loads(json_str) if json_str else []
        if not rows:
            return build_timeline_html([]), "[]"

        from src.image_mapper import parse_time_str

        def get_ts(r):
            val = parse_time_str(r.get("start", "0"))
            return val if val is not None else 999999.0

        rows.sort(key=get_ts)

        new_rows = []
        for r in rows:
            new_rows.append({
                "thumb_b64": get_image_thumbnail_b64(r.get("path", "")),
                "filename": r.get("filename", ""),
                "path": r.get("path", ""),
                "start": r.get("start", "0.0"),
                "duration": r.get("duration", "5.0")
            })

        html = build_timeline_html(new_rows)
        json_data = json.dumps([{"path": r["path"], "filename": r["filename"], "start": r["start"], "duration": r["duration"]} for r in new_rows])
        return html, json_data
    except Exception:
        return build_timeline_html([]), "[]"


def run_gradio_generation(
    script_mode,
    script_file,
    script_text,
    audio_file,
    image_mode,
    images_folder,
    uploaded_images,
    res_str,
    fps,
    transition,
    mapping_mode,
    timeline_json_str,
    progress=gr.Progress()
):
    try:
        # 1. Resolve Script Source (Optional)
        script_source = None
        is_script_text = False
        if script_mode == "Upload File" and script_file:
            script_source = script_file.name if hasattr(script_file, "name") else script_file
        elif script_mode == "Paste Text" and script_text and script_text.strip():
            script_source = script_text
            is_script_text = True

        # 2. Resolve Audio Source
        audio_path = audio_file if audio_file else ""

        # 3. Resolve Image Source
        if image_mode == "Select Local Folder":
            if not images_folder or not os.path.exists(images_folder):
                raise ValueError(f"Images folder does not exist: {images_folder}")
            images_source = images_folder
        else:
            if not uploaded_images:
                raise ValueError("Please upload image files!")
            images_source = [f.name if hasattr(f, "name") else f for f in uploaded_images]

        # 4. Parse Resolution
        try:
            width, height = map(int, res_str.lower().split('x'))
            resolution = (width, height)
        except Exception:
            raise ValueError(f"Invalid resolution format: {res_str}. Use WIDTHxHEIGHT (e.g., 1920x1080).")

        # 5. Define Output Path
        output_path = os.path.join(BASE_DIR, "output_video", "gradio_generated.mp4")

        # 6. Check Custom Timeline from JSON bridge
        custom_tl = None
        if timeline_json_str:
            try:
                tl_rows = json.loads(timeline_json_str)
                if isinstance(tl_rows, list) and len(tl_rows) > 0:
                    valid_rows = []
                    for r in tl_rows:
                        fname = r.get("filename", "").strip()
                        if fname and "Please select" not in fname and "Error:" not in fname:
                            # Build row as [preview_placeholder, filename, start, duration]
                            valid_rows.append(["", fname, r.get("start", "0.0"), r.get("duration", "5.0")])
                    if valid_rows:
                        custom_tl = valid_rows
            except Exception:
                pass

        # 7. Progress Callback
        def progress_cb(pct, msg):
            progress(pct, desc=msg)

        # 8. Generate Video
        result_video = generate_video(
            script_source=script_source,
            audio_path=audio_path,
            images_source=images_source,
            output_path=output_path,
            mapping_mode=mapping_mode,
            resolution=resolution,
            fps=int(fps),
            transition_duration=float(transition),
            is_script_text=is_script_text,
            progress_callback=progress_cb,
            custom_timeline=custom_tl
        )

        return result_video, f"✅ Video successfully generated and saved to: {result_video}"

    except Exception as e:
        import traceback
        traceback.print_exc()
        return None, f"❌ Error: {str(e)}"


# Handle Gradio theme compatibility between v4/v5 (Kaggle) and v6+ (Local)
try:
    GRADIO_V6 = int(gr.__version__.split(".")[0]) >= 6
except Exception:
    GRADIO_V6 = False

blocks_kwargs: dict[str, Any] = {"title": "Salt-2-Artstyle Video Generator"}
if not GRADIO_V6:
    blocks_kwargs["theme"] = gr.themes.Default()  # type: ignore

# Build Gradio Interface
with gr.Blocks(**blocks_kwargs) as demo:
    gr.Markdown(
        """
        # 🎬 Automated Video Generator with Ken Burns Effects & Audio Sync
        Generate engaging, dynamic videos from script timestamps, audio, and images.
        """
    )

    with gr.Row():
        # ─── LEFT PANEL: Settings (compact) ───
        with gr.Column(scale=3, min_width=320):
            with gr.Accordion("📝 Script & Timestamps (Optional)", open=False):
                script_mode = gr.Radio(
                    choices=["Paste Text", "Upload File", "No Script (Automatic / Manual)"],
                    value="Paste Text",
                    label="Script Input Method"
                )
                script_text = gr.Textbox(
                    label="Script Text (with [MM:SS - MM:SS] timestamps)",
                    value=DEFAULT_SCRIPT_TEXT,
                    lines=8,
                    placeholder="TITLE: My Video\n\n[00:00 - 00:08]\nWelcome to my video..."
                )
                script_file = gr.File(
                    label="Upload Script (.txt)",
                    file_types=[".txt"],
                    visible=False
                )

                def toggle_script_mode(mode):
                    return {
                        script_text: gr.update(visible=(mode == "Paste Text")),
                        script_file: gr.update(visible=(mode == "Upload File"))
                    }

                script_mode.change(toggle_script_mode, inputs=[script_mode], outputs=[script_text, script_file])

            with gr.Accordion("🔊 Audio Narration", open=True):
                audio_file = gr.Audio(
                    label="Audio File (.wav, .mp3)",
                    type="filepath",
                    value=DEFAULT_AUDIO_PATH if os.path.exists(DEFAULT_AUDIO_PATH) else None
                )

            with gr.Accordion("🖼️ Images", open=True):
                image_mode = gr.Radio(
                    choices=["Select Local Folder", "Upload Image Files"],
                    value="Select Local Folder",
                    label="Image Input Method"
                )
                images_folder = gr.Textbox(
                    label="Local Images Directory Path",
                    value=DEFAULT_IMAGES_DIR
                )
                uploaded_images = gr.File(
                    label="Upload Multiple Image Files",
                    file_count="multiple",
                    file_types=["image"],
                    visible=False
                )

                def toggle_image_mode(mode):
                    return {
                        images_folder: gr.update(visible=(mode == "Select Local Folder")),
                        uploaded_images: gr.update(visible=(mode == "Upload Image Files"))
                    }

                image_mode.change(toggle_image_mode, inputs=[image_mode], outputs=[images_folder, uploaded_images])

            with gr.Accordion("⚙️ Video Settings", open=True):
                res_dropdown = gr.Dropdown(
                    choices=["1920x1080", "1280x720", "854x480", "1080x1920"],
                    value="1920x1080",
                    label="Resolution"
                )
                fps_dropdown = gr.Dropdown(
                    choices=[60, 30, 24],
                    value=60,
                    label="FPS"
                )
                mapping_radio = gr.Radio(
                    choices=["index", "sequential"],
                    value="index",
                    label="Mapping Strategy"
                )
                transition_slider = gr.Slider(
                    minimum=0.0, maximum=1.0, value=0.4, step=0.1,
                    label="Transition Duration (s)"
                )

            generate_btn = gr.Button("🎬 Generate Video", variant="primary", size="lg")

            output_status = gr.Textbox(label="Status", interactive=False)
            output_video = gr.Video(label="Generated Video")

        # ─── RIGHT PANEL: Timeline Table (main working area) ───
        with gr.Column(scale=7, min_width=500):
            gr.Markdown("### 🕒 Cinematic Timeline — Drag & Drop to Reorder")
            gr.Markdown(
                "Click **Populate Table** to load your images. **Drag rows by the ⠿ handle** to reorder. "
                "Edit Start and Duration directly in the cells."
            )

            with gr.Row():
                populate_btn = gr.Button("🔄 Populate Table", variant="primary")
                sort_btn = gr.Button("🔢 Sort by Timestamp", variant="secondary")
                equalize_btn = gr.Button("⏱️ Equalize Durations", variant="secondary")

            timeline_html = gr.HTML(
                value=build_timeline_html([]),
                label="Timeline"
            )

            # Hidden JSON bridge to sync drag-and-drop state from JS to Python
            timeline_json_bridge = gr.Textbox(
                value="[]",
                visible=False,
                elem_id="timeline-json-bridge"
            )

    # ─── Wire up event handlers ───

    populate_btn.click(
        fn=populate_timeline,
        inputs=[script_mode, script_file, script_text, audio_file, image_mode, images_folder, uploaded_images, mapping_radio],
        outputs=[timeline_html, timeline_json_bridge]
    )

    sort_btn.click(
        fn=sort_by_timestamp,
        inputs=[timeline_json_bridge],
        outputs=[timeline_html, timeline_json_bridge]
    )

    equalize_btn.click(
        fn=equalize_durations,
        inputs=[audio_file, timeline_json_bridge],
        outputs=[timeline_html, timeline_json_bridge]
    )

    generate_btn.click(
        fn=run_gradio_generation,
        inputs=[
            script_mode, script_file, script_text, audio_file,
            image_mode, images_folder, uploaded_images,
            res_dropdown, fps_dropdown, transition_slider, mapping_radio,
            timeline_json_bridge
        ],
        outputs=[output_video, output_status]
    )

    # Initialize SortableJS on page load
    demo.load(None, None, None, js=SORTABLE_INIT_JS)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Launch Gradio Web UI for Salt-2-Artstyle")
    parser.add_argument("--share", action="store_true", help="Create a publicly shareable Gradio link (recommended on Kaggle!)")
    parser.add_argument("--port", type=int, default=7860, help="Port to run the server on")
    args = parser.parse_args()

    print(f"\nLaunching Gradio Interface (Share={args.share}, Port={args.port}, Gradio v{gr.__version__})...")
    launch_kwargs: dict[str, Any] = {"share": args.share, "server_port": args.port}
    if GRADIO_V6:
        launch_kwargs["theme"] = gr.themes.Default()  # type: ignore

    demo.launch(**launch_kwargs)
