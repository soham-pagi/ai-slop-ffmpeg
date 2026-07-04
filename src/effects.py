import os
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
from typing import cast, Optional


def create_ken_burns_clip(
    image_path: str,
    duration: float,
    effect_type: str = "zoom_in",
    target_size: tuple = (1920, 1080),
    fps: int = 60,
    transition_duration: float = 0.4,
    start_transition: str = "Cross-Dissolve (Hollywood Blend)",
    end_transition: str = "Cross-Dissolve (Hollywood Blend)",
    prev_image_path: Optional[str] = None,
    next_image_path: Optional[str] = None
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

    # Preload adjacent frames for Hollywood Cross-Dissolve without MoviePy composition
    prev_frame = None
    next_frame = None
    if prev_image_path and os.path.exists(prev_image_path) and start_transition == "Cross-Dissolve (Hollywood Blend)":
        try:
            p_img = Image.open(prev_image_path).convert('RGB').resize((target_w, target_h), Image.Resampling.BILINEAR)
            prev_frame = np.array(p_img, dtype=np.float32)
        except Exception:
            pass
    if next_image_path and os.path.exists(next_image_path) and end_transition == "Cross-Dissolve (Hollywood Blend)":
        try:
            n_img = Image.open(next_image_path).convert('RGB').resize((target_w, target_h), Image.Resampling.BILINEAR)
            next_frame = np.array(n_img, dtype=np.float32)
        except Exception:
            pass

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

        # Consistent aesthetic rate: constant speed per second regardless of clip duration!
        # This ensures a 2-second clip and a 10-second clip move at the exact same gentle, cinematic pace.
        z_rate = min(0.35, 0.035 * duration) # 3.5% zoom per second
        p_rate = min(0.80, 0.16 * duration)  # 16% pan per second

        if effect_type == "zoom_in":
            scale = 1.0 + z_rate * p
            pan_x = 0.0
            pan_y = 0.0
        elif effect_type == "zoom_out":
            scale = (1.0 + z_rate) - z_rate * p
            pan_x = 0.0
            pan_y = 0.0
        elif effect_type == "pan_right_zoom_in":
            scale = 1.05 + z_rate * p
            pan_x = -0.5 * p_rate + p_rate * p
            pan_y = 0.0
        elif effect_type == "pan_left_zoom_in":
            scale = 1.05 + z_rate * p
            pan_x = 0.5 * p_rate - p_rate * p
            pan_y = 0.0
        elif effect_type == "pan_up_zoom_in":
            scale = 1.05 + z_rate * p
            pan_x = 0.0
            pan_y = 0.5 * p_rate - p_rate * p
        elif effect_type == "pan_down_zoom_in":
            scale = 1.05 + z_rate * p
            pan_x = 0.0
            pan_y = -0.5 * p_rate + p_rate * p
        elif effect_type == "pan_right_zoom_out":
            scale = (1.05 + z_rate) - z_rate * p
            pan_x = -0.5 * p_rate + p_rate * p
            pan_y = 0.0
        elif effect_type == "pan_left_zoom_out":
            scale = (1.05 + z_rate) - z_rate * p
            pan_x = 0.5 * p_rate - p_rate * p
            pan_y = 0.0
        elif effect_type == "pan_up_right_zoom_in":
            scale = 1.08 + z_rate * p
            pan_x = -0.4 * p_rate + 0.8 * p_rate * p
            pan_y = 0.4 * p_rate - 0.8 * p_rate * p
        elif effect_type == "pan_down_left_zoom_in":
            scale = 1.08 + z_rate * p
            pan_x = 0.4 * p_rate - 0.8 * p_rate * p
            pan_y = -0.4 * p_rate + 0.8 * p_rate * p
        elif effect_type == "zoom_in_fast_slow":
            p_ease = 1.0 - (1.0 - p) ** 2  # Decelerating cinematic ease-out
            scale = 1.0 + z_rate * p_ease
            pan_x = 0.0
            pan_y = 0.0
        elif effect_type == "zoom_out_slow_fast":
            p_ease = p ** 2  # Accelerating cinematic ease-in
            scale = (1.0 + z_rate) - z_rate * p_ease
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

        # Apply sub-pixel affine transformation
        if use_gpu:
            try:
                tx = (2.0 * pan_x * max_shift_x) / W0
                ty = (2.0 * pan_y * max_shift_y) / H0
                theta = torch.tensor([[
                    [1.0 / scale, 0.0, tx],
                    [0.0, 1.0 / scale, ty]
                ]], dtype=torch.float32, device=img_gpu.device)
                grid = F.affine_grid(theta, size=(1, 3, target_h, target_w), align_corners=False)
                res_gpu = F.grid_sample(img_gpu, grid, mode='bilinear', padding_mode='reflection', align_corners=False)
                res_clamped = torch.clamp(res_gpu.squeeze(0).permute(1, 2, 0) * 255.0, 0, 255).to(torch.uint8)
                res = res_clamped.cpu().numpy()
            except Exception:
                res = None
        else:
            res = None

        if res is None and CV2_AVAILABLE:
            try:
                M = np.array([
                    [k, 0.0, left],
                    [0.0, k, top]
                ], dtype=np.float32)
                res = cv2.warpAffine(
                    img_np,
                    M,
                    (target_w, target_h),
                    flags=cv2.INTER_LINEAR | cv2.WARP_INVERSE_MAP,
                    borderMode=cv2.BORDER_REFLECT_101
                )
            except Exception:
                res = None

        if res is None:
            matrix = (k, 0.0, left, 0.0, k, top)
            resized = img.transform(
                target_size,
                Image.Transform.AFFINE,
                data=matrix,
                resample=Image.Resampling.BILINEAR
            )
            res = np.array(resized)

        # Bake flawless, zero-blackout transitions directly into RGB frame!
        half_dur = transition_duration / 2.0
        if half_dur > 0 and duration > half_dur * 2:
            res_float = res.astype(np.float32)
            if t < half_dur and start_transition != "Clean Cut (No Fade)":
                alpha = max(0.0, min(1.0, t / half_dur))
                if start_transition == "Cross-Dissolve (Hollywood Blend)" and prev_frame is not None:
                    res_float = res_float * (0.5 + 0.5 * alpha) + prev_frame * (0.5 * (1.0 - alpha))
                elif start_transition == "Flash / Dip to White":
                    res_float = res_float * alpha + 255.0 * (1.0 - alpha)
                elif start_transition == "Dip to Black":
                    res_float = res_float * alpha
                res = np.clip(res_float, 0, 255).astype(np.uint8)
            elif t > duration - half_dur and end_transition != "Clean Cut (No Fade)":
                alpha = max(0.0, min(1.0, (duration - t) / half_dur))
                if end_transition == "Cross-Dissolve (Hollywood Blend)" and next_frame is not None:
                    res_float = res_float * (0.5 + 0.5 * alpha) + next_frame * (0.5 * (1.0 - alpha))
                elif end_transition == "Flash / Dip to White":
                    res_float = res_float * alpha + 255.0 * (1.0 - alpha)
                elif end_transition == "Dip to Black":
                    res_float = res_float * alpha
                res = np.clip(res_float, 0, 255).astype(np.uint8)

        return res

    clip = VideoClip(make_frame, duration=duration)
    
    # In MoviePy v1 vs v2, set fps
    if hasattr(clip, "with_fps"):
        clip = clip.with_fps(fps)
    elif hasattr(clip, "set_fps"):
        clip = clip.set_fps(fps)
    else:
        setattr(clip, "fps", fps)

    return cast(VideoClip, clip)
