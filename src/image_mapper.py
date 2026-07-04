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


def create_custom_timeline(
    images_source: Union[str, List[str]],
    timeline_rows: List[List[Any]]
) -> List[MappedClip]:
    """
    Creates a MappedClip timeline from manual Dataframe rows: [[order, filename, duration], ...].
    """
    image_paths = get_image_files(images_source)
    if not image_paths:
        raise ValueError(f"No valid image files found in {images_source}")
        
    # Build lookup map from filename to full path
    path_map = {os.path.basename(p): p for p in image_paths}
    
    mapped_clips = []
    curr_time = 0.0
    
    for i, row in enumerate(timeline_rows):
        if not row or len(row) < 3:
            continue
        filename = str(row[1]).strip()
        try:
            duration = float(row[2])
        except (ValueError, TypeError):
            duration = 5.0
            
        if duration <= 0:
            continue
            
        # Find matching image path (or fallback to first image if deleted/renamed)
        img_path = path_map.get(filename, image_paths[0])
        
        mapped_clips.append(
            MappedClip(
                image_path=img_path,
                duration=duration,
                segment_index=i + 1,
                text=f"Manual Segment {i+1}",
                start_time=curr_time,
                end_time=curr_time + duration
            )
        )
        curr_time += duration
        
    if not mapped_clips:
        raise ValueError("Custom timeline resulted in 0 valid clips. Please check table durations.")
        
    return mapped_clips
