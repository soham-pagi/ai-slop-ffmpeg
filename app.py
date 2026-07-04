import os
import argparse
import gradio as gr
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
    progress=gr.Progress()
):
    try:
        # 1. Resolve Script Source
        if script_mode == "Upload File":
            if not script_file:
                raise ValueError("Please upload a script file!")
            script_source = script_file.name if hasattr(script_file, "name") else script_file
            is_script_text = False
        else:
            if not script_text or not script_text.strip():
                raise ValueError("Please paste script text!")
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

        # 6. Progress Callback
        def progress_cb(pct, msg):
            progress(pct, desc=msg)

        # 7. Generate Video
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
            progress_callback=progress_cb
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

blocks_kwargs = {"title": "Salt-2-Artstyle Video Generator"}
if not GRADIO_V6:
    blocks_kwargs["theme"] = gr.themes.Soft()

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
            gr.Markdown("### 1. Script & Timestamps")
            script_mode = gr.Radio(
                choices=["Paste Text", "Upload File"],
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
            res_dropdown, fps_dropdown, transition_slider, mapping_radio
        ],
        outputs=[output_video, output_status]
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Launch Gradio Web UI for Salt-2-Artstyle")
    parser.add_argument("--share", action="store_true", help="Create a publicly shareable Gradio link (recommended on Kaggle!)")
    parser.add_argument("--port", type=int, default=7860, help="Port to run the server on")
    args = parser.parse_args()

    print(f"\nLaunching Gradio Interface (Share={args.share}, Port={args.port}, Gradio v{gr.__version__})...")
    launch_kwargs = {"share": args.share, "server_port": args.port}
    if GRADIO_V6:
        launch_kwargs["theme"] = gr.themes.Soft()
        
    demo.launch(**launch_kwargs)
