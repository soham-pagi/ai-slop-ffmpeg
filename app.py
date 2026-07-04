import os
import argparse
import gradio as gr
from typing import Any
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
    timeline_table,
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

        # 6. Check Custom Timeline Table
        custom_tl = None
        if timeline_table is not None and hasattr(timeline_table, "__len__") and len(timeline_table) > 0:
            valid_rows = [row for row in timeline_table if row and len(row) >= 3 and str(row[1]).strip() != "" and "Please select" not in str(row[1]) and "Error:" not in str(row[1])]
            if len(valid_rows) > 0:
                custom_tl = valid_rows

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


import base64
from PIL import Image
import io

def get_image_thumbnail_html(image_path, max_size=(100, 60)):
    try:
        if not os.path.exists(image_path):
            return "🖼️ [Missing]"
        with Image.open(image_path) as img:
            img.thumbnail(max_size)
            buf = io.BytesIO()
            img.save(buf, format="JPEG", quality=75)
            b64 = base64.b64encode(buf.getvalue()).decode('utf-8')
            return f'<img src="data:image/jpeg;base64,{b64}" style="max-height: 50px; border-radius: 4px; display: inline-block;" />'
    except Exception:
        return "🖼️ [Image]"


def populate_timeline_table(script_mode, script_file, script_text, audio_file, image_mode, images_folder, uploaded_images, mapping_mode):
    try:
        from src.image_mapper import get_image_files, map_images_to_timestamps
        from src.timestamp_parser import parse_script, parse_script_text
        try:
            from moviepy import AudioFileClip
        except ImportError:
            from moviepy.editor import AudioFileClip # type: ignore
        
        images_source = ""
        if image_mode == "Select Local Folder" and images_folder and os.path.exists(images_folder):
            images_source = images_folder
        elif image_mode == "Upload Image Files" and uploaded_images:
            images_source = [f.name if hasattr(f, "name") else f for f in uploaded_images]
        else:
            return [["🖼️", "Please select/upload images first", "0.0", "5.0"]]
            
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
            thumb_html = get_image_thumbnail_html(mc.image_path)
            rows.append([thumb_html, os.path.basename(mc.image_path), str(round(mc.start_time, 2)), str(round(mc.duration, 2))])
        return rows
    except Exception as e:
        return [["❌", f"Error: {str(e)}", "0.0", "5.0"]]


def equalize_table_durations(audio_file, table_data):
    try:
        if not table_data or len(table_data) == 0:
            return table_data
        try:
            from moviepy import AudioFileClip
        except ImportError:
            from moviepy.editor import AudioFileClip # type: ignore
            
        if not audio_file or not os.path.exists(audio_file):
            dur = 5.0
        else:
            clip = AudioFileClip(audio_file)
            audio_dur = clip.duration or 0.0
            dur = round(audio_dur / len(table_data), 2) if len(table_data) > 0 else 5.0
            
        new_rows = []
        curr_t = 0.0
        for row in table_data:
            if len(row) >= 2:
                thumb = row[0]
                fname = row[1]
                new_rows.append([thumb, fname, str(round(curr_t, 2)), str(dur)])
                curr_t += dur
        return new_rows
    except Exception:
        return table_data


# Handle Gradio theme compatibility between v4/v5 (Kaggle) and v6+ (Local)
try:
    GRADIO_V6 = int(gr.__version__.split(".")[0]) >= 6
except Exception:
    GRADIO_V6 = False

blocks_kwargs: dict[str, Any] = {"title": "Salt-2-Artstyle Video Generator"}
if not GRADIO_V6:
    blocks_kwargs["theme"] = gr.themes.Default() # type: ignore

# Build Gradio Interface
with gr.Blocks(**blocks_kwargs) as demo:
    gr.Markdown(
        """
        # 🎬 Automated Video Generator with Ken Burns Effects & Audio Sync
        Generate engaging, dynamic videos from script timestamps, audio, and images.
        Designed for both **Local Execution** and **Kaggle Notebooks**!
        """
    )
    
    with gr.Row():
        with gr.Column(scale=5):
            gr.Markdown("### 1. Script & Timestamps (Optional)")
            script_mode = gr.Radio(
                choices=["Paste Text", "Upload File", "No Script (Automatic / Manual)"],
                value="Paste Text",
                label="Script Input Method"
            )
            script_text = gr.Textbox(
                label="Script Text (with [MM:SS - MM:SS] timestamps)",
                value=DEFAULT_SCRIPT_TEXT,
                lines=12,
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

            gr.Markdown("### 2. Audio Narration")
            audio_file = gr.Audio(
                label="Audio File (.wav, .mp3)",
                type="filepath",
                value=DEFAULT_AUDIO_PATH if os.path.exists(DEFAULT_AUDIO_PATH) else None
            )

        with gr.Column(scale=5):
            gr.Markdown("### 3. Images")
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

            gr.Markdown("### 4. Video Settings")
            with gr.Row():
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
            with gr.Row():
                mapping_radio = gr.Radio(
                    choices=["index", "sequential"],
                    value="index",
                    label="Mapping Strategy"
                )
                transition_slider = gr.Slider(
                    minimum=0.0, maximum=1.0, value=0.4, step=0.1,
                    label="Transition Duration (s)"
                )

            with gr.Accordion("🕒 Manual Image Alignment & Timeline Table (Optional)", open=False):
                gr.Markdown(
                    "Upload or select your images above, then click **'🔄 Populate Table from Images & Script/Audio'** "
                    "to view and edit exact image ordering and durations! You can manually re-order images or change durations."
                )
                with gr.Row():
                    populate_btn = gr.Button("🔄 Populate Table from Images & Script/Audio", variant="secondary")
                    equalize_btn = gr.Button("⏱️ Equalize Durations to Audio", variant="secondary")
                
                timeline_table = gr.Dataframe(
                    headers=["Preview", "Image Filename", "Start Timestamp (s)", "Duration (s) (Optional)"],
                    interactive=True,
                    label="Custom Timeline Table"
                )

                populate_btn.click(
                    fn=populate_timeline_table,
                    inputs=[script_mode, script_file, script_text, audio_file, image_mode, images_folder, uploaded_images, mapping_radio],
                    outputs=[timeline_table]
                )
                equalize_btn.click(
                    fn=equalize_table_durations,
                    inputs=[audio_file, timeline_table],
                    outputs=[timeline_table]
                )

            generate_btn = gr.Button("🎬 Generate Video", variant="primary", size="lg")

    with gr.Row():
        with gr.Column():
            output_status = gr.Textbox(label="Status / Logs", interactive=False)
            output_video = gr.Video(label="Generated Video")

    generate_btn.click(
        fn=run_gradio_generation,
        inputs=[
            script_mode, script_file, script_text, audio_file,
            image_mode, images_folder, uploaded_images,
            res_dropdown, fps_dropdown, transition_slider, mapping_radio,
            timeline_table
        ],
        outputs=[output_video, output_status]
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Launch Gradio Web UI for Salt-2-Artstyle")
    parser.add_argument("--share", action="store_true", help="Create a publicly shareable Gradio link (recommended on Kaggle!)")
    parser.add_argument("--port", type=int, default=7860, help="Port to run the server on")
    args = parser.parse_args()

    print(f"\nLaunching Gradio Interface (Share={args.share}, Port={args.port}, Gradio v{gr.__version__})...")
    launch_kwargs: dict[str, Any] = {"share": args.share, "server_port": args.port}
    if GRADIO_V6:
        launch_kwargs["theme"] = gr.themes.Default() # type: ignore
        
    demo.launch(**launch_kwargs)
