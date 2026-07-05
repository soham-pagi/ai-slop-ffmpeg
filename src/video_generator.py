import subprocess
import random
import os
import json

def generate_video(timeline_data, audio_path, output_path, w=1920, h=1080, fps=60, trans_dur=0.5, transition_style="Random"):
    """Native FFmpeg Filtergraph Generator. Bypasses Python pixel-piping. Renders at C++ speeds."""
    inputs = []
    filter_parts = []
    prev_label = ""
    
    for i, item in enumerate(timeline_data):
        img = item.get('path') or item.get('filename') or ""
        if not img or not os.path.exists(img):
            raise FileNotFoundError(f"Image file not found for timeline item #{i+1}: '{img}'")
        inputs.extend(["-i", img])
    
    has_audio = audio_path and os.path.exists(audio_path)
    if has_audio: inputs.extend(["-i", audio_path])
    
    cumulative_time = 0.0
    for i, item in enumerate(timeline_data):
        dur = float(item.get('duration', 5.0))
        frames = max(1, int(dur * fps))
        eff_str = str(item.get('effect', '')).lower()
        if 'zoom in' in eff_str or eff_str == 'zoom_in':
            effect = 'zoom_in'
        elif 'zoom out' in eff_str or eff_str == 'zoom_out':
            effect = 'zoom_out'
        elif 'pan right' in eff_str or eff_str == 'pan_right':
            effect = 'pan_right'
        elif 'pan left' in eff_str or eff_str == 'pan_left':
            effect = 'pan_left'
        else:
            effect = random.choice(['zoom_in', 'zoom_out', 'pan_right', 'pan_left'])
        
        if effect == 'zoom_in': zp = f"z='min(1.0+0.0005*on,1.3)':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)'"
        elif effect == 'zoom_out': zp = f"z='max(1.3-0.0005*on,1.0)':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)'"
        elif effect == 'pan_right': zp = f"z='1.2':x='min(on*1.5,iw-iw/zoom)':y='ih/2-(ih/zoom/2)'"
        else: zp = f"z='1.2':x='max(iw-iw/zoom-on*1.5,0)':y='ih/2-(ih/zoom/2)'"
        
        in_label, out_label = f"[{i}:v]", f"[v{i}]"
        # True 8K UHD base (7680x4320 for 16:9) aligned to 16/32-byte SIMD vector boundaries to eliminate swscaler data alignment warnings & boost speed
        canvas_w = 7680
        canvas_h = int(round((7680 * h / w) / 16.0) * 16)
        filter_parts.append(f"{in_label}scale=w={canvas_w}:h={canvas_h}:force_original_aspect_ratio=increase:flags=lanczos,crop={canvas_w}:{canvas_h},zoompan={zp}:d={frames}:s={w}x{h}:fps={fps},format=yuva420p{out_label}")
        
        if i == 0:
            prev_label = out_label
            cumulative_time = dur
        else:
            safe_dur = max(0.05, trans_dur)
            offset = cumulative_time - safe_dur
            next_label = f"[t{i}]" if i < len(timeline_data) - 1 else "[outv]"
            
            # Resolve transition style from item or global dropdown
            trans_str = str(item.get('transition', '')).lower()
            if not trans_str or 'random' in trans_str:
                trans_str = str(transition_style or '').lower()
                
            if 'black' in trans_str: xfade_name = 'fadeblack'
            elif 'white' in trans_str or 'gold' in trans_str or 'cyan' in trans_str: xfade_name = 'fadewhite'
            elif 'from left' in trans_str: xfade_name = 'slideright'
            elif 'from right' in trans_str: xfade_name = 'slideleft'
            elif 'from top' in trans_str: xfade_name = 'slidedown'
            elif 'from bottom' in trans_str: xfade_name = 'slideup'
            elif 'dissolve' in trans_str or 'fade' in trans_str: xfade_name = 'fade'
            else: xfade_name = random.choice(['fade', 'fadeblack', 'fadewhite', 'smoothleft', 'smoothright', 'circlecrop', 'distance'])
            
            filter_parts.append(f"{prev_label}{out_label}xfade=transition={xfade_name}:duration={safe_dur}:offset={offset}{next_label}")
            prev_label = next_label
            cumulative_time += (dur - safe_dur)
            
    if len(timeline_data) == 1: filter_parts.append(f"[v0]format=yuv420p[outv]")
        
    audio_idx = len(timeline_data)
    # Add -hide_banner, -nostdin, and -sws_flags lanczos+accurate_rnd+full_chroma_int for sub-pixel accurate Lanczos resampling without shimmering or vibration
    cmd_base = ["ffmpeg", "-y", "-hide_banner", "-nostdin", "-sws_flags", "lanczos+accurate_rnd+full_chroma_int"] + inputs + ["-filter_complex", ";".join(filter_parts), "-map", "[outv]"]
    if has_audio: cmd_base.extend(["-map", f"{audio_idx}:a", "-c:a", "aac", "-b:a", "320k"])
    
    # Check if NVIDIA GPU hardware encoding is available
    use_nvenc = False
    try:
        res = subprocess.run(["ffmpeg", "-encoders"], capture_output=True, text=True)
        if "h264_nvenc" in res.stdout:
            use_nvenc = True
    except Exception:
        pass

    common_flags = ["-profile:v", "high", "-pix_fmt", "yuv420p", "-colorspace", "bt709", "-color_trc", "bt709", "-color_primaries", "bt709", "-movflags", "+faststart", "-shortest", output_path]

    if use_nvenc:
        print("  [GPU Accelerated] Attempting NVIDIA h264_nvenc Hardware Encoder...")
        # Use modern standard preset 'slow' and -b:v 0 to enable constant quality CQ 16 without EINVAL
        cmd_nvenc = cmd_base + ["-c:v", "h264_nvenc", "-preset", "slow", "-cq", "16", "-b:v", "0"] + common_flags
        try:
            print("Executing Native FFmpeg C++ Engine (GPU NVENC)...")
            subprocess.run(cmd_nvenc, check=True)
            return output_path
        except subprocess.CalledProcessError as e:
            print(f"  [NVENC Warning] GPU hardware encoding failed (driver mismatch/exit code {e.returncode}). Automatically falling back to fast CPU software encoding...")

    print("  [CPU Fallback] Using libx264 Software Encoder (-crf 16 -preset veryfast -threads 0)...")
    cmd_cpu = cmd_base + ["-c:v", "libx264", "-preset", "veryfast", "-crf", "16", "-threads", "0"] + common_flags
    print("Executing Native FFmpeg C++ Engine (CPU x264)...")
    subprocess.run(cmd_cpu, check=True)
    return output_path

def run_gradio_generation(script_mode, script_file, script_text, audio_file,
                          image_mode, images_folder, uploaded_images,
                          res_dropdown, fps_dropdown, transition_slider, mapping_radio,
                          timeline_json_bridge, effect_strategy_dropdown, transition_style_dropdown):
    import json, os, traceback
    try:
        timeline_data = json.loads(timeline_json_bridge) if timeline_json_bridge else []
        if not timeline_data: return None, None, "Error: Timeline is empty."
            
        w, h = map(int, res_dropdown.lower().split('x'))
        fps = int(fps_dropdown)
        trans_dur = float(transition_slider)
        audio_path = audio_file if isinstance(audio_file, str) else (audio_file.name if audio_file else None)
        
        os.makedirs("output_video", exist_ok=True)
        output_path = "output_video/native_render.mp4"
        
        generate_video(timeline_data, audio_path, output_path, w, h, fps, trans_dur, transition_style_dropdown)
        return output_path, output_path, "Success! Rendered via Native FFmpeg C++ Engine (Web Optimized)."
    except Exception as e:
        return None, None, f"Error: {str(e)}\n{traceback.format_exc()}"
