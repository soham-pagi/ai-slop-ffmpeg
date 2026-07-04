import numpy as np
from PIL import Image
try:
    import torch
    import torch.nn.functional as F
    TORCH_AVAILABLE = True
except ImportError:
    TORCH_AVAILABLE = False

try:
    import cv2
    CV2_AVAILABLE = True
except ImportError:
    CV2_AVAILABLE = False

try:
    from moviepy import VideoClip
    import moviepy.video.fx as vfx
    MOVIEPY_V2 = True
except ImportError:
    from moviepy.editor import VideoClip, vfx
    MOVIEPY_V2 = False
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
    Uses PyTorch GPU acceleration when available (Kaggle T4 / RTX 3050), or OpenCV/PIL fallback.
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

    use_gpu = TORCH_AVAILABLE and torch.cuda.is_available()
    if use_gpu:
        try:
            # Load image onto GPU VRAM! Uses GPU and System RAM!
            img_np = np.array(img)
            img_gpu = torch.from_numpy(img_np).permute(2, 0, 1).unsqueeze(0).float().cuda() / 255.0
        except Exception:
            use_gpu = False
            
    if not use_gpu and CV2_AVAILABLE:
        img_np = np.array(img)

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

        if use_gpu:
            l_idx = int(max(0, left))
            t_idx = int(max(0, top))
            r_idx = int(min(W0, right))
            b_idx = int(min(H0, bottom))
            if r_idx <= l_idx or b_idx <= t_idx:
                l_idx, t_idx, r_idx, b_idx = 0, 0, W0, H0
            crop_gpu = img_gpu[:, :, t_idx:b_idx, l_idx:r_idx]
            res_gpu = F.interpolate(crop_gpu, size=(target_h, target_w), mode='bilinear', align_corners=False)
            return (res_gpu.squeeze(0).permute(1, 2, 0) * 255.0).byte().cpu().numpy()
        elif CV2_AVAILABLE:
            l_idx = int(max(0, left))
            t_idx = int(max(0, top))
            r_idx = int(min(W0, right))
            b_idx = int(min(H0, bottom))
            if r_idx <= l_idx or b_idx <= t_idx:
                l_idx, t_idx, r_idx, b_idx = 0, 0, W0, H0
            cropped = img_np[t_idx:b_idx, l_idx:r_idx]
            return cv2.resize(cropped, (target_w, target_h), interpolation=cv2.INTER_LINEAR)
        else:
            cropped = img.crop((left, top, right, bottom))
            resized = cropped.resize(target_size, Image.Resampling.BICUBIC)
            return np.array(resized)

    clip = VideoClip(make_frame, duration=duration)
    
    # In MoviePy v1 vs v2, set fps and apply fade effects
    if hasattr(clip, "with_fps"):
        clip = clip.with_fps(fps)
    elif hasattr(clip, "set_fps"):
        clip = clip.set_fps(fps)
    else:
        setattr(clip, "fps", fps)

    # Apply smooth cinematic fade in/out transitions (compatible with MoviePy 1.x and 2.x)
    fade_dur = 0.0
    if transition_duration > 0 and duration > transition_duration * 2:
        fade_dur = transition_duration
    elif transition_duration > 0 and duration > transition_duration:
        fade_dur = duration / 3.0

    if fade_dur > 0:
        if MOVIEPY_V2 and hasattr(vfx, "FadeIn"):
            effects = [vfx.FadeIn(fade_dur), vfx.FadeOut(fade_dur)]
            if hasattr(clip, "with_effects"):
                clip = clip.with_effects(effects)
            elif hasattr(clip, "fx"):
                for fx_func in effects:
                    clip = clip.fx(fx_func)
        else:
            # MoviePy 1.x fallback
            if hasattr(clip, "fadein"):
                clip = clip.fadein(fade_dur)
            if hasattr(clip, "fadeout"):
                clip = clip.fadeout(fade_dur)

    return cast(VideoClip, clip)
