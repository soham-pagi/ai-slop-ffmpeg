import os
import subprocess
from typing import Union, List, Optional, Callable
try:
    from moviepy import concatenate_videoclips, AudioFileClip, CompositeVideoClip, vfx
    MOVIEPY_V2 = True
except ImportError:
    from moviepy.editor import concatenate_videoclips, AudioFileClip, CompositeVideoClip, vfx # type: ignore
    MOVIEPY_V2 = False
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

    total_frames = int(final_video.duration * fps) if final_video.duration else 0
    try:
        for i, frame in enumerate(final_video.iter_frames(fps=fps, dtype='uint8')):
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
    finally:
        if process.stdin:
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


def apply_moviepy_transitions(video_clips, cut_transitions, transition_duration):
    """
    Concatenates clips. If any MoviePy clip-level transitions (SlideIn, CrossFade, Fade)
    are present, builds a CompositeVideoClip with exact timing and overlays.
    Otherwise uses fast standard concatenation.
    """
    MOVIEPY_TRANSITIONS = {
        "Slide In from Left", "Slide In from Right",
        "Slide In from Top", "Slide In from Bottom",
        "Cross Fade (MoviePy)", "Fade through Black (MoviePy)"
    }
    
    # Check if we need MoviePy compositing
    needs_compositing = any(t in MOVIEPY_TRANSITIONS for t in cut_transitions)
    if not needs_compositing:
        return concatenate_videoclips(video_clips)
        
    composited_clips = []
    current_start = 0.0
    
    for i, clip in enumerate(video_clips):
        # Set start time for clip i
        if hasattr(clip, "with_start"):
            positioned_clip = clip.with_start(current_start)
        else:
            positioned_clip = clip.set_start(current_start)
            
        if i > 0:
            trans_name = cut_transitions[i - 1]
            if trans_name in MOVIEPY_TRANSITIONS:
                # Apply incoming MoviePy transition effect to clip i
                effect_obj = None
                if trans_name == "Slide In from Left":
                    effect_obj = vfx.SlideIn(transition_duration, "left")
                elif trans_name == "Slide In from Right":
                    effect_obj = vfx.SlideIn(transition_duration, "right")
                elif trans_name == "Slide In from Top":
                    effect_obj = vfx.SlideIn(transition_duration, "top")
                elif trans_name == "Slide In from Bottom":
                    effect_obj = vfx.SlideIn(transition_duration, "bottom")
                elif trans_name == "Cross Fade (MoviePy)":
                    effect_obj = vfx.CrossFadeIn(transition_duration)
                elif trans_name == "Fade through Black (MoviePy)":
                    effect_obj = vfx.FadeIn(transition_duration)
                    
                if effect_obj is not None:
                    if hasattr(positioned_clip, "with_effects"):
                        positioned_clip = positioned_clip.with_effects([effect_obj])
                    else:
                        if trans_name.startswith("Slide In"):
                            side = trans_name.split("from ")[-1].lower()
                            positioned_clip = positioned_clip.fx(vfx.slide_in, transition_duration, side)  # type: ignore
                        elif trans_name == "Cross Fade (MoviePy)":
                            positioned_clip = positioned_clip.fx(vfx.crossfadein, transition_duration)  # type: ignore
                        elif trans_name == "Fade through Black (MoviePy)":
                            positioned_clip = positioned_clip.fx(vfx.fadein, transition_duration)  # type: ignore
                
                # Extend previous clip duration so it stays visible underneath during transition
                if trans_name != "Fade through Black (MoviePy)":
                    prev_clip = composited_clips[-1]
                    new_dur = prev_clip.duration + transition_duration
                    if hasattr(prev_clip, "with_duration"):
                        composited_clips[-1] = prev_clip.with_duration(new_dur)
                    else:
                        composited_clips[-1] = prev_clip.set_duration(new_dur)
                        
        composited_clips.append(positioned_clip)
        current_start += clip.duration
        
    return CompositeVideoClip(composited_clips)


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
    effect_strategy: str = "Random (No Consecutive Repeats)",
    transition_style: str = "Random Cinematic"
):
    """
    Orchestrates parsing, image mapping, Ken Burns animation, audio syncing, and video export.
    Supports both file paths and raw string inputs (for Gradio UI).
    """
    print(f"\n=======================================================")
    print(f"       AI Image-to-Video Maker       ")
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
        "Slow Zoom In", "Slow Zoom Out", 
        "Pan Right + Zoom In", "Pan Left + Zoom In",
        "Pan Up + Zoom In", "Pan Down + Zoom In",
        "Pan Right + Zoom Out", "Pan Left + Zoom Out",
        "Diagonal Up-Right + Zoom", "Diagonal Down-Left + Zoom",
        "Zoom In (Ease Out)", "Zoom Out (Ease In)",
        "Mirror Horizontal (MoviePy)", "Mirror Vertical (MoviePy)",
        "Black and White (MoviePy)", "Invert Colors (MoviePy)",
        "Static / No Effect"
    ]
    
    if effect_strategy == "Zoom Only":
        pool = ["Slow Zoom In", "Slow Zoom Out", "Zoom In (Ease Out)", "Zoom Out (Ease In)"]
    elif effect_strategy == "Pan Only":
        pool = ["Pan Right + Zoom In", "Pan Left + Zoom In", "Pan Up + Zoom In", "Pan Down + Zoom In", "Pan Right + Zoom Out", "Pan Left + Zoom Out"]
    elif effect_strategy == "Dynamic Diagonals":
        pool = ["Diagonal Up-Right + Zoom", "Diagonal Down-Left + Zoom", "Pan Right + Zoom In", "Pan Left + Zoom In", "Zoom In (Ease Out)"]
    elif effect_strategy == "Static / No Effect":
        pool = ["Static / No Effect"]
    elif effect_strategy == "Cycle All (Ordered)":
        pool = all_effects
    else:  # "Random (No Consecutive Repeats)" or default
        pool = all_effects

    video_clips = []
    last_effect = None
    import random

    # Pre-generate distinct transition styles for every single cut in the video!
    # cut_transitions[j] represents the cut BETWEEN clip j and clip j+1.
    # A clip's per-row transition setting controls how it ENTERS (its incoming transition).
    # So clip j+1's transition setting -> cut_transitions[j].
    cut_transitions = []
    all_styles = [
        "Cross Dissolve", "Dip to White", "Dip to Black", 
        "Dip to Warm Gold", "Dip to Cool Cyan",
        "Slide In from Left", "Slide In from Right",
        "Slide In from Top", "Slide In from Bottom",
        "Cross Fade (MoviePy)", "Fade through Black (MoviePy)"
    ]
    for j in range(max(0, len(mapped_clips) - 1)):
        # The clip entering at this cut is mapped_clips[j+1]
        mc_trans = getattr(mapped_clips[j + 1], "transition", "Random / Global")
        if mc_trans and mc_trans not in ["Random / Global", "Random", "Auto", "Global Strategy", "", "Random Cinematic"]:
            cut_transitions.append(mc_trans)
        elif transition_style in ["Random Cinematic", "Random", "Random / Global"]:
            cut_transitions.append(random.choice(all_styles))
        else:
            cut_transitions.append(transition_style)

    for i, mc in enumerate(mapped_clips):
        if progress_callback:
            progress_callback(0.2 + 0.5 * (i / len(mapped_clips)), f"Creating animation clip {i+1}/{len(mapped_clips)}...")
            
        mc_eff = getattr(mc, "effect", "Random / Global")
        if mc_eff and mc_eff not in ["Random / Global", "Random", "Auto", "Global Strategy", ""]:
            effect = mc_eff
            last_effect = effect
        elif effect_strategy == "Cycle All (Ordered)":
            effect = pool[i % len(pool)]
        else:
            # Smart random: never pick the exact same effect twice in a row
            available = [e for e in pool if e != last_effect] if len(pool) > 1 else pool
            effect = random.choice(available)
            last_effect = effect

        start_trans = "Hard Cut (No Fade)" if i == 0 else cut_transitions[i - 1]
        end_trans = "Hard Cut (No Fade)" if i == len(mapped_clips) - 1 else cut_transitions[i]
        prev_path = mapped_clips[i - 1].image_path if i > 0 else None
        next_path = mapped_clips[i + 1].image_path if i < len(mapped_clips) - 1 else None

        print(f"      - Clip {i+1:02d}/{len(mapped_clips):02d}: {os.path.basename(mc.image_path)} "
              f"({mc.duration:.2f}s, Segment #{mc.segment_index}) -> Effect: {effect} | In: {start_trans} | Out: {end_trans}")
        
        clip = create_ken_burns_clip(
            image_path=mc.image_path,
            duration=mc.duration,
            effect_type=effect,
            target_size=resolution,
            fps=fps,
            transition_duration=transition_duration,
            start_transition=start_trans,
            end_transition=end_trans,
            prev_image_path=prev_path,
            next_image_path=next_path
        )
        video_clips.append(clip)

    if progress_callback:
        progress_callback(0.75, "Concatenating video clips and syncing audio...")

    print(f"[4/5] Concatenating clips and synchronizing audio (Style: {transition_style})...")
    final_video = apply_moviepy_transitions(video_clips, cut_transitions, transition_duration)

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
