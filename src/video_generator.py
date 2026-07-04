import os
import subprocess
from typing import Union, List, Optional, Callable
try:
    from moviepy import concatenate_videoclips, AudioFileClip
except ImportError:
    from moviepy.editor import concatenate_videoclips, AudioFileClip
from .timestamp_parser import parse_script, parse_script_text
from .image_mapper import map_images_to_timestamps, create_custom_timeline
from .effects import create_ken_burns_clip


def get_optimal_video_settings() -> tuple:
    """
    Automatically detects if NVIDIA GPU hardware encoding (h264_nvenc) is available.
    Returns (codec, preset, threads).
    """
    threads = os.cpu_count() or 4
    try:
        res = subprocess.run(["nvidia-smi"], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        if res.returncode == 0:
            ffmpeg_res = subprocess.run(["ffmpeg", "-encoders"], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
            if "h264_nvenc" in ffmpeg_res.stdout:
                print("\n" + "="*60)
                print(" 🚀 [GPU Acceleration Active] NVIDIA GPU Detected (RTX / T4)")
                print("    -> Hardware Encoder: h264_nvenc")
                print("    -> Encoding Preset:  fast")
                print(f"    -> CPU Threads:      {threads}")
                print("="*60 + "\n")
                return "h264_nvenc", "fast", threads
    except Exception:
        pass
    
    print("\n" + "="*60)
    print(" 💻 [CPU Multi-Threading Active] No NVIDIA GPU detected or NVENC unavailable")
    print("    -> Software Encoder: libx264")
    print("    -> Encoding Preset:  superfast (High Speed CPU)")
    print(f"    -> CPU Threads:      {threads}")
    print("="*60 + "\n")
    return "libx264", "superfast", threads


def generate_video(
    script_source: Optional[str] = None,
    audio_path: str = "",
    images_source: Union[str, List[str]] = "",
    output_path: str = "output.mp4",
    mapping_mode: str = "index",
    resolution: tuple = (1920, 1080),
    fps: int = 60,
    transition_duration: float = 0.4,
    is_script_text: bool = False,
    progress_callback: Optional[Callable] = None,
    custom_timeline: Optional[List[list]] = None
):
    """
    Orchestrates parsing, image mapping, Ken Burns animation, audio syncing, and video export.
    Supports both file paths and raw string inputs (for Gradio UI).
    """
    print(f"\n=======================================================")
    print(f"       Salt-2-Artstyle Automated Video Generator       ")
    print(f"=======================================================\n")
    
    # Load audio early if needed for duration calculation
    audio_clip = None
    audio_duration = 0.0
    if audio_path and os.path.exists(audio_path):
        try:
            audio_clip = AudioFileClip(audio_path)
            audio_duration = audio_clip.duration or 0.0
        except Exception as e:
            print(f"[Warning] Failed to load audio clip early: {e}")

    if custom_timeline and len(custom_timeline) > 0:
        print(f"[1/5 & 2/5] Using Custom Manual Image Alignment Timeline ({len(custom_timeline)} rows)...")
        if progress_callback:
            progress_callback(0.2, "Building custom timeline from manual table...")
        mapped_clips = create_custom_timeline(images_source, custom_timeline)
        print(f"      -> Generated {len(mapped_clips)} clip assignments from manual table.")
    elif script_source and str(script_source).strip():
        if progress_callback:
            progress_callback(0.1, "Parsing script timestamps...")

        if is_script_text:
            print(f"[1/5] Parsing script timestamps from raw text input...")
            title, timestamps = parse_script_text(script_source, default_title="Generated Video")
        else:
            print(f"[1/5] Parsing script timestamps from file: {script_source}")
            title, timestamps = parse_script(script_source)
            
        print(f"      -> Found {len(timestamps)} timestamp segments. Total timestamp duration: {timestamps[-1].end_time:.2f}s")

        if progress_callback:
            progress_callback(0.2, f"Mapping images (Mode: {mapping_mode})...")

        print(f"[2/5] Mapping images (Mode: {mapping_mode})...")
        mapped_clips = map_images_to_timestamps(images_source, timestamps, mode=mapping_mode)
        print(f"      -> Generated {len(mapped_clips)} clip assignments across {len(timestamps)} timestamps.")
    else:
        print(f"[1/5 & 2/5] No script provided. Creating automatic timeline for uploaded images...")
        if progress_callback:
            progress_callback(0.2, "Mapping images without script...")
        mapped_clips = map_images_to_timestamps(images_source, timestamps=None, mode=mapping_mode, audio_duration=audio_duration)
        print(f"      -> Generated {len(mapped_clips)} clip assignments.")

    print(f"[3/5] Creating dynamic Ken Burns video clips (Resolution: {resolution[0]}x{resolution[1]} @ {fps}fps)...")
    effect_types = ["zoom_in", "zoom_out", "pan_right_zoom_in", "pan_left_zoom_in"]
    video_clips = []

    for i, mc in enumerate(mapped_clips):
        if progress_callback:
            progress_callback(0.2 + 0.5 * (i / len(mapped_clips)), f"Creating animation clip {i+1}/{len(mapped_clips)}...")
            
        effect = effect_types[i % len(effect_types)]
        print(f"      - Clip {i+1:02d}/{len(mapped_clips):02d}: {os.path.basename(mc.image_path)} "
              f"({mc.duration:.2f}s, Segment #{mc.segment_index}) -> Effect: {effect}")
        
        clip = create_ken_burns_clip(
            image_path=mc.image_path,
            duration=mc.duration,
            effect_type=effect,
            target_size=resolution,
            fps=fps,
            transition_duration=transition_duration
        )
        video_clips.append(clip)

    if progress_callback:
        progress_callback(0.75, "Concatenating video clips and syncing audio...")

    print(f"[4/5] Concatenating clips and synchronizing audio...")
    final_video = concatenate_videoclips(video_clips, method="compose")

    if not audio_clip and audio_path and os.path.exists(audio_path):
        try:
            audio_clip = AudioFileClip(audio_path)
        except Exception as e:
            print(f"[Warning] Could not load audio: {e}")

    if not audio_clip:
        print(f"[Warning] Audio file not found or not provided. Exporting video without audio.")
    else:
        print(f"      -> Loaded audio: {audio_path} (Duration: {audio_clip.duration:.2f}s)")
        
        if audio_clip.duration is not None and final_video.duration is not None:
            if audio_clip.duration < final_video.duration:
                print(f"      [Note] Audio duration ({audio_clip.duration:.2f}s) is shorter than timestamp total ({final_video.duration:.2f}s).")
                print(f"             Video will continue with silence after audio ends (ideal for calibration preview).")
            elif audio_clip.duration > final_video.duration:
                print(f"      [Note] Audio duration ({audio_clip.duration:.2f}s) is longer than timestamp total ({final_video.duration:.2f}s).")

        if hasattr(final_video, "with_audio"):
            final_video = final_video.with_audio(audio_clip)
        elif hasattr(final_video, "set_audio"):
            final_video = final_video.set_audio(audio_clip)

    if progress_callback:
        progress_callback(0.85, "Encoding and exporting final video (this may take a moment)...")

    print(f"[5/5] Exporting final video to: {output_path}")
    os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)

    codec, preset, threads = get_optimal_video_settings()
    try:
        final_video.write_videofile(
            output_path,
            fps=fps,
            codec=codec,
            audio_codec="aac",
            threads=threads,
            preset=preset
        )
    except Exception as e:
        if codec != "libx264":
            print(f"\n[Warning] Hardware GPU encoding ({codec}) failed in MoviePy backend: {str(e)[:150]}...")
            print("          -> Automatically falling back to high-speed CPU multi-threading (libx264, preset=superfast)!\n")
            final_video.write_videofile(
                output_path,
                fps=fps,
                codec="libx264",
                audio_codec="aac",
                threads=threads,
                preset="superfast"
            )
        else:
            raise

    if progress_callback:
        progress_callback(1.0, "Video generation complete!")

    print(f"\n[Success] Video successfully generated at: {output_path}\n")
    return output_path
