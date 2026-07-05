import subprocess
import random
import os
import json

def generate_video(timeline_data, audio_path, output_path, w=1920, h=1080, fps=60, trans_dur=0.5):
    """Native FFmpeg Filtergraph Generator. Bypasses Python pixel-piping. Renders at C++ speeds."""
    inputs = []
    filter_parts = []
    prev_label = ""
    
    for i, item in enumerate(timeline_data):
        dur = float(item.get('duration', 5.0))
        img = item.get('path')
        inputs.extend(["-loop", "1", "-t", str(dur), "-i", img])
    
    has_audio = audio_path and os.path.exists(audio_path)
    if has_audio: inputs.extend(["-i", audio_path])
    
    cumulative_time = 0.0
    for i, item in enumerate(timeline_data):
        dur = float(item.get('duration', 5.0))
        frames = max(1, int(dur * fps))
        effect = random.choice(['zoom_in', 'zoom_out', 'pan_right', 'pan_left'])
        
        if effect == 'zoom_in': zp = f"z='min(zoom+0.0015,1.5)':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)'"
        elif effect == 'zoom_out': zp = f"z='if(eq(on,1),1.5,max(zoom-0.0015,1.0))':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)'"
        elif effect == 'pan_right': zp = f"z='1.2':x='if(eq(on,1),0,min(x+2,iw-iw/zoom))':y='ih/2-(ih/zoom/2)'"
        else: zp = f"z='1.2':x='if(eq(on,1),iw-iw/zoom,max(x-2,0))':y='ih/2-(ih/zoom/2)'"
        
        in_label, out_label = f"[{i}:v]", f"[v{i}]"
        # Scale to 8K internally for crisp zooming, then output target res
        filter_parts.append(f"{in_label}scale=8000:-1,zoompan={zp}:d={frames}:s={w}x{h}:fps={fps},format=yuva420p{out_label}")
        
        if i == 0:
            prev_label = out_label
            cumulative_time = dur
        else:
            offset = cumulative_time - trans_dur
            next_label = f"[t{i}]" if i < len(timeline_data) - 1 else "[outv]"
            filter_parts.append(f"{prev_label}{out_label}xfade=transition=fade:duration={trans_dur}:offset={offset}{next_label}")
            prev_label = next_label
            cumulative_time += (dur - trans_dur)
            
    if len(timeline_data) == 1: filter_parts.append(f"[v0]format=yuv420p[outv]")
        
    audio_idx = len(timeline_data)
    cmd = ["ffmpeg", "-y"] + inputs + ["-filter_complex", ";".join(filter_parts), "-map", "[outv]"]
    if has_audio: cmd.extend(["-map", f"{audio_idx}:a", "-c:a", "aac", "-b:a", "192k"])
    cmd.extend(["-c:v", "libx264", "-preset", "ultrafast", "-crf", "18", "-shortest", output_path])
    
    print("Executing Native FFmpeg C++ Engine...")
    subprocess.run(cmd, check=True)
    return output_path

def run_gradio_generation(script_mode, script_file, script_text, audio_file,
                          image_mode, images_folder, uploaded_images,
                          res_dropdown, fps_dropdown, transition_slider, mapping_radio,
                          timeline_json_bridge, effect_strategy_dropdown, transition_style_dropdown):
    import json, os, traceback
    try:
        timeline_data = json.loads(timeline_json_bridge) if timeline_json_bridge else []
        if not timeline_data: return None, "Error: Timeline is empty."
            
        w, h = map(int, res_dropdown.lower().split('x'))
        fps = int(fps_dropdown)
        trans_dur = float(transition_slider)
        audio_path = audio_file.name if audio_file else None
        
        os.makedirs("output_video", exist_ok=True)
        output_path = "output_video/native_render.mp4"
        
        generate_video(timeline_data, audio_path, output_path, w, h, fps, trans_dur)
        return output_path, "Success! Rendered via Native FFmpeg C++ Engine."
    except Exception as e:
        return None, f"Error: {str(e)}\n{traceback.format_exc()}"
