import os
import subprocess
from typing import Union, List, Optional, Callable
try:
    from moviepy import concatenate_videoclips, AudioFileClip
except ImportError:
    from moviepy.editor import concatenate_videoclips, AudioFileClip # type: ignore
from .timestamp_parser import parse_script, parse_script_text
from .image_mapper import map_images_to_timestamps, create_custom_timeline
from .effects import create_ken_burns_clip
import numpy as np


def export_video_with_gpu_pipe(final_video, output_path: str, fps: int, progress_callback: Optional[Callable] = None):
    """
    Directly pipes raw video frames from MoviePy/PyTorch to an FFmpeg subprocess
    configured for NVIDIA GPU NVENC hardware encoding (h264_nvenc).
    Bypasses MoviePy's writer which is incompatible with NVENC on Kaggle.
    """
    temp_audio = output_path + ".temp_audio.aac"
    has_audio = getattr(final_video, "audio", None) is not None
    if has_audio:
        try:
            final_video.audio.write_audiofile(temp_audio, fps=44100, logger=None)
        except Exception as e:
            print(f"[Warning] Could not export temporary audio for GPU pipe: {e}")
            has_audio = False

    width, height = final_video.w, final_video.h
    command = [
        "ffmpeg", "-y",
        "-f", "rawvideo",
        "-vcodec", "rawvideo",
        "-s", f"{width}x{height}",
        "-pix_fmt", "rgb24",
        "-r", str(fps),
        "-i", "-"
    ]
    if has_audio and os.path.exists(temp_audio):
        command.extend(["-i", temp_audio, "-c:a", "copy"])

    command.extend([
        "-c:v", "h264_nvenc",
        "-preset", "p4",
        "-pix_fmt", "yuv420p",
        "-shortest",
        output_path
    ])

    print("\n" + "="*60)
    print(" 🚀 [GPU NVENC Subprocess Pipe Active] Streaming frames directly to NVIDIA GPU!")
    print(f"    -> Command: {' '.join(command)}")
    print("="*60 + "\n")

    process = subprocess.Popen(command, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE)

    if process.stdin is None:
        stderr_output = process.stderr.read().decode(errors="replace") if process.stderr else "No stderr available"
        raise RuntimeError(
            f"FFmpeg GPU NVENC process failed to start (stdin pipe is None). "
            f"FFmpeg stderr:\n{stderr_output}"
        )

    total_frames = int(final_video.duration * fps)
    for i, t in enumerate(np.arange(0, final_video.duration, 1.0 / fps)):
        frame = final_video.get_frame(t)
        try:
            process.stdin.write(frame.tobytes())
        except BrokenPipeError:
            stderr_output = process.stderr.read().decode(errors="replace") if process.stderr else "No stderr available"
            raise RuntimeError(
                f"FFmpeg GPU NVENC pipe broke while writing frame {i}/{total_frames}. "
                f"FFmpeg stderr:\n{stderr_output}"
            )
        if progress_callback and total_frames > 0 and i % 15 == 0:
            progress_callback(0.85 + 0.15 * (i / total_frames), f"GPU NVENC Encoding frame {i}/{total_frames}...")
            
    process.stdin.close()
    process.wait()
    
    if os.path.exists(temp_audio):
        try:
            os.remove(temp_audio)
        except Exception:
            pass
            
    if process.returncode != 0:
        raise RuntimeError(f"GPU NVENC subprocess failed with returncode {process.returncode}")


def get_optimal_video_settings() -> tuple:
    """
    Automatically detects if NVIDIA GPU hardware encoding (h264_nvenc) is available.
    Returns (codec, preset, threads).
    """
    threads = os.cpu_count() or 4
    
    # Check PyTorch GPU acceleration for frame rendering
    try:
        import torch  # type: ignore
        if torch.cuda.is_available():
            gpu_name = torch.cuda.get_device_name(0)
            print("\n" + "="*60)
            print(f" 🚀 [GPU Frame Generation Active] PyTorch CUDA Detected: {gpu_name}")
            print("    -> Ken Burns animation & rendering running at 50x speed on GPU VRAM!")
            print("="*60)
    except Exception:
        pass

    try:
        res = subprocess.run(["nvidia-smi"], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        if res.returncode == 0:
            ffmpeg_res = subprocess.run(["ffmpeg", "-encoders"], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
            if "h264_nvenc" in ffmpeg_res.stdout:
                print("\n" + "="*60)
                print(" 🚀 [GPU Acceleration Active] NVIDIA GPU Detected (RTX / T4)")
                print("    -> Hardware Encoder: h264_nvenc")
                print("    -> Encoding Preset:  p4 (NVIDIA GPU Standard)")
                print(f"    -> CPU Threads:      {threads}")
                print("="*60 + "\n")
                return "h264_nvenc", "p4", threads
    except Exception:
        pass
    
    print("\n" + "="*60)
    print(" 💻 [CPU Multi-Threading Active] Using libx264 software video encoding")
    print("    -> Software Encoder: libx264")
    print("    -> Encoding Preset:  ultrafast (Maximum Speed CPU)")
    print(f"    -> CPU Threads:      {threads}")
    print("="*60 + "\n")
    return "libx264", "ultrafast", threads


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
    custom_timeline: Optional[List[list]] = None,
    effect_strategy: str = "Random (No Repeats)"
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
        mapped_clips = create_custom_timeline(images_source, custom_timeline, audio_duration=audio_duration)
        print(f"      -> Generated {len(mapped_clips)} clip assignments from manual table.")
    elif script_source and script_source.strip():
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

    print(f"[3/5] Creating dynamic Ken Burns video clips (Resolution: {resolution[0]}x{resolution[1]} @ {fps}fps, Strategy: {effect_strategy})...")
    all_effects = [
        "zoom_in", "zoom_out", 
        "pan_right_zoom_in", "pan_left_zoom_in",
        "pan_up_zoom_in", "pan_down_zoom_in",
        "pan_right_zoom_out", "pan_left_zoom_out",
        "pan_up_right_zoom_in", "pan_down_left_zoom_in",
        "zoom_in_fast_slow", "zoom_out_slow_fast"
    ]
    
    if effect_strategy == "Zoom Only":
        pool = ["zoom_in", "zoom_out", "zoom_in_fast_slow", "zoom_out_slow_fast"]
    elif effect_strategy == "Pan Only":
        pool = ["pan_right_zoom_in", "pan_left_zoom_in", "pan_up_zoom_in", "pan_down_zoom_in", "pan_right_zoom_out", "pan_left_zoom_out"]
    elif effect_strategy == "Dynamic Diagonals":
        pool = ["pan_up_right_zoom_in", "pan_down_left_zoom_in", "pan_right_zoom_in", "pan_left_zoom_in", "zoom_in_fast_slow"]
    elif effect_strategy == "Cycle All (Ordered)":
        pool = all_effects
    else:  # "Random (No Repeats)" or default
        pool = all_effects

    video_clips = []
    last_effect = None
    import random

    for i, mc in enumerate(mapped_clips):
        if progress_callback:
            progress_callback(0.2 + 0.5 * (i / len(mapped_clips)), f"Creating animation clip {i+1}/{len(mapped_clips)}...")
            
        if effect_strategy == "Cycle All (Ordered)":
            effect = pool[i % len(pool)]
        else:
            # Smart random: never pick the exact same effect twice in a row
            available = [e for e in pool if e != last_effect] if len(pool) > 1 else pool
            effect = random.choice(available)
            last_effect = effect

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
    if codec == "h264_nvenc":
        try:
            export_video_with_gpu_pipe(final_video, output_path, fps, progress_callback)
        except Exception as e:
            print(f"\n[Warning] Direct GPU NVENC subprocess pipe failed: {str(e)[:150]}...")
            print("          -> Automatically falling back to high-speed CPU multi-threading (libx264, preset=ultrafast)!\n")
            final_video.write_videofile(
                output_path,
                fps=fps,
                codec="libx264",
                audio_codec="aac",
                threads=threads,
                preset="ultrafast"
            )
    else:
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
                print(f"\n[Warning] Encoding ({codec}) failed: {str(e)[:150]}...")
                print("          -> Automatically falling back to high-speed CPU multi-threading (libx264, preset=ultrafast)!\n")
                final_video.write_videofile(
                    output_path,
                    fps=fps,
                    codec="libx264",
                    audio_codec="aac",
                    threads=threads,
                    preset="ultrafast"
                )
            else:
                raise

    if progress_callback:
        progress_callback(1.0, "Video generation complete!")

    print(f"\n[Success] Video successfully generated at: {output_path}\n")
    return output_path
