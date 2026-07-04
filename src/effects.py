import numpy as np
from PIL import Image
try:
    import torch  # type: ignore
    import torch.nn.functional as F  # type: ignore
    TORCH_AVAILABLE = True
except Exception:
    TORCH_AVAILABLE = False

try:
    import cv2  # type: ignore
    CV2_AVAILABLE = True
except Exception:
    CV2_AVAILABLE = False

try:
    from moviepy import VideoClip
    import moviepy.video.fx as vfx
    MOVIEPY_V2 = True
except ImportError:
    from moviepy.editor import VideoClip, vfx  # type: ignore
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

    use_gpu = False
    if TORCH_AVAILABLE:
        try:
            if torch.cuda.is_available():
                img_np_copy = np.array(img).copy()
                img_gpu = torch.from_numpy(img_np_copy).permute(2, 0, 1).unsqueeze(0).float().cuda() / 255.0
                use_gpu = True
        except Exception:
            use_gpu = False

    if CV2_AVAILABLE:
        try:
            img_np = np.array(img).copy()
        except Exception:
            pass

    def make_frame(t):
        p = min(1.0, max(0.0, t / duration)) if duration > 0 else 0.0

        if effect_type == "zoom_in":
            scale = 1.0 + 0.20 * p
            pan_x = 0.0
            pan_y = 0.0
        elif effect_type == "zoom_out":
            scale = 1.20 - 0.20 * p
            pan_x = 0.0
            pan_y = 0.0
        elif effect_type == "pan_right_zoom_in":
            scale = 1.10 + 0.15 * p  # Zoom in 15% to create generous margin for smooth panning
            pan_x = -0.85 + 1.70 * p # Pan smoothly across 85% of available width from left to right
            pan_y = 0.0
        elif effect_type == "pan_left_zoom_in":
            scale = 1.10 + 0.15 * p  # Zoom in 15%
            pan_x = 0.85 - 1.70 * p  # Pan smoothly across 85% of available width from right to left
            pan_y = 0.0
        elif effect_type == "pan_up_zoom_in":
            scale = 1.10 + 0.15 * p
            pan_x = 0.0
            pan_y = 0.85 - 1.70 * p  # Pan smoothly from bottom to top
        elif effect_type == "pan_down_zoom_in":
            scale = 1.10 + 0.15 * p
            pan_x = 0.0
            pan_y = -0.85 + 1.70 * p # Pan smoothly from top to bottom
        elif effect_type == "pan_right_zoom_out":
            scale = 1.25 - 0.15 * p  # Start zoomed in, zoom out smoothly
            pan_x = -0.85 + 1.70 * p
            pan_y = 0.0
        elif effect_type == "pan_left_zoom_out":
            scale = 1.25 - 0.15 * p
            pan_x = 0.85 - 1.70 * p
            pan_y = 0.0
        elif effect_type == "pan_up_right_zoom_in":
            scale = 1.15 + 0.15 * p
            pan_x = -0.70 + 1.40 * p # Diagonal pan left-to-right
            pan_y = 0.70 - 1.40 * p  # Diagonal pan bottom-to-top
        elif effect_type == "pan_down_left_zoom_in":
            scale = 1.15 + 0.15 * p
            pan_x = 0.70 - 1.40 * p  # Diagonal pan right-to-left
            pan_y = -0.70 + 1.40 * p # Diagonal pan top-to-bottom
        elif effect_type == "zoom_in_fast_slow":
            p_ease = 1.0 - (1.0 - p) ** 2  # Decelerating cinematic ease-out
            scale = 1.0 + 0.22 * p_ease
            pan_x = 0.0
            pan_y = 0.0
        elif effect_type == "zoom_out_slow_fast":
            p_ease = p ** 2  # Accelerating cinematic ease-in
            scale = 1.22 - 0.22 * p_ease
            pan_x = 0.0
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
        
        # Sub-pixel affine scale ratio from output frame pixel to input image pixel
        k = w_crop / target_w

        if use_gpu:
            try:
                # Sub-pixel bilinear grid sampling on NVIDIA GPU VRAM (eliminates texture vibration)
                tx = (2.0 * pan_x * max_shift_x) / W0
                ty = (2.0 * pan_y * max_shift_y) / H0
                theta = torch.tensor([[
                    [1.0 / scale, 0.0, tx],
                    [0.0, 1.0 / scale, ty]
                ]], dtype=torch.float32, device=img_gpu.device)
                grid = F.affine_grid(theta, size=(1, 3, target_h, target_w), align_corners=False)
                res_gpu = F.grid_sample(img_gpu, grid, mode='bilinear', padding_mode='reflection', align_corners=False)
                res_clamped = torch.clamp(res_gpu.squeeze(0).permute(1, 2, 0) * 255.0, 0, 255).to(torch.uint8)
                return res_clamped.cpu().numpy()
            except Exception:
                pass

        if CV2_AVAILABLE:
            try:
                # 2x3 floating-point Affine matrix for sub-pixel inverse mapping
                M = np.array([
                    [k, 0.0, left],
                    [0.0, k, top]
                ], dtype=np.float32)
                return cv2.warpAffine(
                    img_np,
                    M,
                    (target_w, target_h),
                    flags=cv2.INTER_LINEAR | cv2.WARP_INVERSE_MAP,
                    borderMode=cv2.BORDER_REFLECT_101
                )
            except Exception:
                pass

        # Sub-pixel affine transformation fallback using PIL
        matrix = (k, 0.0, left, 0.0, k, top)
        resized = img.transform(
            target_size,
            Image.Transform.AFFINE,
            data=matrix,
            resample=Image.Resampling.BILINEAR
        )
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
