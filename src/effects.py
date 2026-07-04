import numpy as np
from PIL import Image
from moviepy import VideoClip
import moviepy.video.fx as vfx
from typing import cast


def create_ken_burns_clip(
    image_path: str,
    duration: float,
    effect_type: str = "zoom_in",
    target_size: tuple = (1920, 1080),
    fps: int = 60,
    transition_duration: float = 0.4
) -> VideoClip:
    """
    Creates a video clip from an image with Ken Burns zoom/pan animation and fade transitions.
    
    Args:
        image_path: Absolute path to the image file.
        duration: Exact duration of the clip in seconds.
        effect_type: 'zoom_in', 'zoom_out', 'pan_right_zoom_in', 'pan_left_zoom_in'.
        target_size: Tuple (width, height) for output resolution.
        fps: Frames per second.
        transition_duration: Duration of fade in/out transitions in seconds.
        
    Returns:
        VideoClip: The animated video clip ready for concatenation.
    """
    # Load image once into memory
    img = Image.open(image_path).convert('RGB')
    target_w, target_h = target_size
    
    # Pre-scale huge images once to ~1.35x target resolution for 10x faster per-frame cropping/resizing
    max_scale = 1.35
    if img.width > target_w * max_scale and img.height > target_h * max_scale:
        scale_factor = max((target_w * max_scale) / img.width, (target_h * max_scale) / img.height)
        new_w, new_h = int(img.width * scale_factor), int(img.height * scale_factor)
        img = img.resize((new_w, new_h), Image.Resampling.LANCZOS)

    W0, H0 = img.width, img.height
    r_target = target_w / target_h

    # Compute base crop dimensions matching target aspect ratio
    if W0 / H0 > r_target:
        h_base = H0
        w_base = H0 * r_target
    else:
        w_base = W0
        h_base = W0 / r_target

    def make_frame(t):
        p = min(1.0, max(0.0, t / duration)) if duration > 0 else 0.0

        if effect_type == "zoom_in":
            scale = 1.0 + 0.15 * p
            pan_x = 0.0
            pan_y = 0.0
        elif effect_type == "zoom_out":
            scale = 1.15 - 0.15 * p
            pan_x = 0.0
            pan_y = 0.0
        elif effect_type == "pan_right_zoom_in":
            scale = 1.05 + 0.10 * p
            pan_x = -0.03 + 0.06 * p
            pan_y = 0.0
        elif effect_type == "pan_left_zoom_in":
            scale = 1.05 + 0.10 * p
            pan_x = 0.03 - 0.06 * p
            pan_y = 0.0
        else:
            scale = 1.0
            pan_x = 0.0
            pan_y = 0.0

        w_crop = w_base / scale
        h_crop = h_base / scale

        max_shift_x = (W0 - w_crop) / 2.0
        max_shift_y = (H0 - h_crop) / 2.0

        xc = W0 / 2.0 + pan_x * max_shift_x
        yc = H0 / 2.0 + pan_y * max_shift_y

        left = xc - w_crop / 2.0
        top = yc - h_crop / 2.0
        right = xc + w_crop / 2.0
        bottom = yc + h_crop / 2.0

        cropped = img.crop((left, top, right, bottom))
        resized = cropped.resize(target_size, Image.Resampling.BICUBIC)
        return np.array(resized)

    clip = VideoClip(make_frame, duration=duration)
    
    # In MoviePy v2, set fps and apply fade effects
    if hasattr(clip, "with_fps"):
        clip = clip.with_fps(fps)
    else:
        setattr(clip, "fps", fps)

    # Apply smooth cinematic fade in/out transitions
    effects = []
    if transition_duration > 0 and duration > transition_duration * 2:
        effects.append(vfx.FadeIn(transition_duration))
        effects.append(vfx.FadeOut(transition_duration))
    elif transition_duration > 0 and duration > transition_duration:
        effects.append(vfx.FadeIn(duration / 3.0))
        effects.append(vfx.FadeOut(duration / 3.0))

    if effects:
        if hasattr(clip, "with_effects"):
            clip = clip.with_effects(effects)
        elif hasattr(clip, "fx"):
            for fx_func in effects:
                clip = clip.fx(fx_func)

    return cast(VideoClip, clip)
