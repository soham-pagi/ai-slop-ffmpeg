import re
from dataclasses import dataclass
from typing import List, Tuple, Optional
import os


@dataclass
class TimestampSegment:
    index: int          # 1-based index
    start_time: float   # in seconds
    end_time: float     # in seconds
    duration: float     # in seconds
    text: str           # narration text


def time_str_to_seconds(time_str: str) -> float:
    """
    Converts a time string in format MM:SS, HH:MM:SS, or MM:SS.sss into total seconds.
    """
    parts = time_str.strip().split(':')
    if len(parts) == 2:
        minutes, seconds = parts
        return int(minutes) * 60.0 + float(seconds)
    elif len(parts) == 3:
        hours, minutes, seconds = parts
        return int(hours) * 3600.0 + int(minutes) * 60.0 + float(seconds)
    else:
        try:
            return float(time_str)
        except ValueError:
            raise ValueError(f"Invalid time format: {time_str}")


def parse_script_text(content: str, default_title: str = "Video Project") -> Tuple[str, List[TimestampSegment]]:
    """
    Parses raw script text containing timestamps like [00:00 - 00:08] and narration text.
    Returns:
        title (str): The extracted title or default_title.
        segments (List[TimestampSegment]): Ordered list of parsed timestamp segments.
    """
    # Extract Title if present
    title_match = re.search(r'^TITLE:\s*(.+)$', content, re.MULTILINE | re.IGNORECASE)
    if title_match:
        title = title_match.group(1).strip()
    else:
        title = default_title

    # Match timestamp blocks: [00:00 - 00:08] or similar
    pattern = r'\[(\d{1,2}:\d{2}(?::\d{2})?(?:\.\d+)?)\s*-\s*(\d{1,2}:\d{2}(?::\d{2})?(?:\.\d+)?)\]'
    matches = list(re.finditer(pattern, content))

    segments = []
    for i, match in enumerate(matches):
        start_str = match.group(1)
        end_str = match.group(2)
        start_sec = time_str_to_seconds(start_str)
        end_sec = time_str_to_seconds(end_str)
        duration = max(0.1, end_sec - start_sec)  # Ensure positive duration

        # Extract text between this timestamp and the next timestamp (or end of content)
        text_start_idx = match.end()
        if i + 1 < len(matches):
            text_end_idx = matches[i + 1].start()
        else:
            text_end_idx = len(content)

        raw_text = content[text_start_idx:text_end_idx].strip()
        # Clean up multiline breaks into single spaces or clean paragraphs
        clean_text = ' '.join(line.strip() for line in raw_text.splitlines() if line.strip())

        segments.append(
            TimestampSegment(
                index=i + 1,
                start_time=start_sec,
                end_time=end_sec,
                duration=duration,
                text=clean_text
            )
        )

    return title, segments


def parse_script(file_path: str) -> Tuple[str, List[TimestampSegment]]:
    """
    Parses a script file from disk.
    """
    if not os.path.exists(file_path):
        raise FileNotFoundError(f"Script file not found: {file_path}")

    with open(file_path, 'r', encoding='utf-8') as f:
        content = f.read()

    default_title = os.path.splitext(os.path.basename(file_path))[0]
    return parse_script_text(content, default_title=default_title)
