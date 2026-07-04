import os
import re
from dataclasses import dataclass
from typing import List, Union, Optional, Any
from .timestamp_parser import TimestampSegment


@dataclass
class MappedClip:
    image_path: str
    duration: float
    segment_index: int
    text: str
    start_time: float
    end_time: float


def natural_sort_key(s: str):
    """
    Key for natural alphanumeric sorting (e.g. 1.png, 2.png, ... 9.png, 9.1.png, 10.png).
    """
    return [int(text) if text.isdigit() else text.lower()
            for text in re.split(r'(\d+)', s)]


def get_image_files(images_source: Union[str, List[str]]) -> List[str]:
    """
    Returns naturally sorted list of image file paths from either a directory path or list of file paths.
    """
    valid_exts = {'.png', '.jpg', '.jpeg', '.webp', '.bmp'}
    
    if isinstance(images_source, list):
        files = [
            f for f in images_source
            if os.path.splitext(f)[1].lower() in valid_exts and os.path.exists(f)
        ]
    elif isinstance(images_source, str):
        if not os.path.exists(images_source):
            raise FileNotFoundError(f"Images directory not found: {images_source}")
        files = [
            os.path.join(images_source, f) for f in os.listdir(images_source)
            if os.path.splitext(f)[1].lower() in valid_exts
        ]
    else:
        raise ValueError("images_source must be a directory path (str) or list of file paths.")

    files.sort(key=lambda x: natural_sort_key(os.path.basename(x)))
    return files


def map_images_to_timestamps(
    images_source: Union[str, List[str]],
    timestamps: Optional[List[TimestampSegment]] = None,
    mode: str = "index",
    audio_duration: Optional[float] = None
) -> List[MappedClip]:
    """
    Maps available images to the provided timestamp segments.
    If timestamps is None or empty, divides audio_duration equally among all images (or defaults to 5.0s per image).
    """
    image_paths = get_image_files(images_source)
    if not image_paths:
        raise ValueError(f"No valid image files found in {images_source}")

    mapped_clips = []

    if not timestamps:
        print(f"[ImageMapper] No script timestamps provided. Creating equal-duration timeline for {len(image_paths)} images...")
        dur = (audio_duration / len(image_paths)) if (audio_duration and audio_duration > 0) else 5.0
        curr_time = 0.0
        for i, path in enumerate(image_paths):
            mapped_clips.append(
                MappedClip(
                    image_path=path,
                    duration=dur,
                    segment_index=i + 1,
                    text=f"Image {i+1}",
                    start_time=curr_time,
                    end_time=curr_time + dur
                )
            )
            curr_time += dur
        return mapped_clips

    if mode == "index":
        # Group images by leading integer in filename
        segment_groups = {seg.index: [] for seg in timestamps}
        unmapped_images = []

        for path in image_paths:
            filename = os.path.basename(path)
            match = re.match(r'^(\d+)', filename)
            if match:
                idx = int(match.group(1))
                if idx in segment_groups:
                    segment_groups[idx].append(path)
                elif idx > len(timestamps) and len(timestamps) > 0:
                    print(f"[ImageMapper] Note: Image '{filename}' index ({idx}) > timestamp count ({len(timestamps)}). Assigning to final segment.")
                    segment_groups[len(timestamps)].append(path)
                else:
                    unmapped_images.append(path)
            else:
                unmapped_images.append(path)

        # Distribute any unmapped images across segments that have 0 images
        for seg in timestamps:
            if not segment_groups[seg.index] and unmapped_images:
                segment_groups[seg.index].append(unmapped_images.pop(0))

        # If still any segment has 0 images, reuse from previous segment
        last_valid_img = image_paths[0]
        for seg in timestamps:
            imgs = segment_groups[seg.index]
            if not imgs:
                print(f"[ImageMapper] Note: No image found for segment #{seg.index} [{seg.start_time}-{seg.end_time}s]. Reusing previous image.")
                imgs = [last_valid_img]
            else:
                last_valid_img = imgs[-1]

            # Divide duration among images in this segment
            sub_duration = seg.duration / len(imgs)
            curr_time = seg.start_time
            for img_path in imgs:
                mapped_clips.append(
                    MappedClip(
                        image_path=img_path,
                        duration=sub_duration,
                        segment_index=seg.index,
                        text=seg.text,
                        start_time=curr_time,
                        end_time=curr_time + sub_duration
                    )
                )
                curr_time += sub_duration

    elif mode == "sequential":
        # Distribute M images across N timestamps sequentially
        num_imgs = len(image_paths)
        num_segs = len(timestamps)

        for i, seg in enumerate(timestamps):
            img_idx = int((i / num_segs) * num_imgs)
            img_idx = min(img_idx, num_imgs - 1)
            mapped_clips.append(
                MappedClip(
                    image_path=image_paths[img_idx],
                    duration=seg.duration,
                    segment_index=seg.index,
                    text=seg.text,
                    start_time=seg.start_time,
                    end_time=seg.end_time
                )
            )
    else:
        raise ValueError(f"Unknown mapping mode: {mode}")

    return mapped_clips


def parse_time_str(val: Any) -> Optional[float]:
    if val is None or str(val).strip() == "" or "Please select" in str(val) or "Error:" in str(val):
        return None
    s = str(val).strip()
    if ":" in s:
        parts = s.split(":")
        try:
            if len(parts) == 2:
                return float(parts[0]) * 60 + float(parts[1])
            elif len(parts) == 3:
                return float(parts[0]) * 3600 + float(parts[1]) * 60 + float(parts[2])
        except ValueError:
            return None
    try:
        return float(s)
    except ValueError:
        return None


def find_matching_image(filename: str, image_paths: List[str], path_map: dict) -> str:
    if not filename:
        return image_paths[0]
    fname_clean = filename.strip()
    
    # 1. Exact match (case-sensitive)
    if fname_clean in path_map:
        return path_map[fname_clean]
        
    # 2. Case-insensitive exact match
    for base, full in path_map.items():
        if base.lower() == fname_clean.lower():
            return full
            
    # 3. Substring match (e.g. user typed "dog" for "my_dog_photo.png" or "1.png" for "prefix_1.png")
    for base, full in path_map.items():
        if fname_clean.lower() in base.lower():
            return full
            
    # 4. Numeric / Index match (e.g. user typed "1", "2", "3" or "#1", "image 1")
    import re
    nums = re.findall(r'\d+', fname_clean)
    if nums:
        try:
            idx = int(nums[0]) - 1 # 1-based to 0-based
            if 0 <= idx < len(image_paths):
                return image_paths[idx]
        except Exception:
            pass
            
    # 5. Fallback to first image
    print(f"[Warning] Could not find exact match for image '{filename}'. Defaulting to first image: {os.path.basename(image_paths[0])}")
    return image_paths[0]


def create_custom_timeline(
    images_source: Union[str, List[str]],
    timeline_rows: Any,
    audio_duration: float = 0.0
) -> List[MappedClip]:
    """
    Creates a MappedClip timeline from manual Dataframe rows.
    Supports both legacy format: [[order, filename, duration], ...]
    and new format: [[preview_html, filename, start_timestamp, duration], ...]
    """
    image_paths = get_image_files(images_source)
    if not image_paths:
        raise ValueError(f"No valid image files found in {images_source}")
        
    path_map = {os.path.basename(p): p for p in image_paths}
    
    if hasattr(timeline_rows, "values"):
        timeline_rows = timeline_rows.values.tolist()
    elif hasattr(timeline_rows, "to_numpy"):
        timeline_rows = timeline_rows.to_numpy().tolist()
    elif isinstance(timeline_rows, dict) and "data" in timeline_rows:
        timeline_rows = timeline_rows["data"]
    
    # 1. Parse rows into structured list: (filename, start_val, dur_val)
    parsed_items = []
    for row in timeline_rows:
        if not row or not isinstance(row, (list, tuple)) or len(row) < 2:
            continue
            
        if len(row) == 3:
            # Check if column 0 is HTML preview or integer order
            if isinstance(row[0], str) and "<img" in str(row[0]):
                # [preview, filename, start_or_duration]
                filename = str(row[1]).strip()
                start_val = parse_time_str(row[2])
                dur_val = None
            else:
                # Legacy [order, filename, duration]
                filename = str(row[1]).strip()
                start_val = None
                dur_val = parse_time_str(row[2])
        elif len(row) >= 4:
            # [preview, filename, start_timestamp, duration]
            filename = str(row[1]).strip()
            start_val = parse_time_str(row[2])
            dur_val = parse_time_str(row[3])
        else:
            continue
            
        if not filename or "Please select" in filename or "Error:" in filename:
            continue
            
        parsed_items.append((filename, start_val, dur_val))
        
    if not parsed_items:
        raise ValueError("Custom timeline resulted in 0 valid rows. Please check table data.")

    # 2. Compute start_time for each row
    start_times = []
    curr_t = 0.0
    for i, (fname, s_val, d_val) in enumerate(parsed_items):
        if s_val is not None and s_val >= 0:
            start_times.append(s_val)
            curr_t = s_val
        else:
            start_times.append(curr_t)
            # If dur_val provided, advance curr_t for next fallback
            if d_val is not None and d_val > 0:
                curr_t += d_val
            else:
                curr_t += 5.0

    # 3. Compute duration for each row and build MappedClips
    mapped_clips = []
    num_items = len(parsed_items)
    for i, (fname, s_val, d_val) in enumerate(parsed_items):
        st = start_times[i]
        
        # Determine duration
        if d_val is not None and d_val > 0:
            dur = d_val
        elif i + 1 < num_items and start_times[i+1] > st:
            dur = start_times[i+1] - st
        elif i == num_items - 1 and audio_duration > st:
            dur = audio_duration - st
        else:
            dur = 5.0
            
        if dur <= 0:
            dur = 5.0
            
        img_path = find_matching_image(fname, image_paths, path_map)
        mapped_clips.append(
            MappedClip(
                image_path=img_path,
                duration=dur,
                segment_index=i + 1,
                text=f"Manual Segment {i+1}",
                start_time=st,
                end_time=st + dur
            )
        )
        
    return mapped_clips
