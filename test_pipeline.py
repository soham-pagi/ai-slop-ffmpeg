import os
from src.timestamp_parser import parse_script
from src.image_mapper import map_images_to_timestamps
from src.effects import create_ken_burns_clip
from moviepy import AudioFileClip


def test_pipeline():
    print("=== Testing Timestamp Parser ===")
    script_path = "scripts/How Ancient Humans Used Salt.txt"
    title, timestamps = parse_script(script_path)
    print(f"Title: {title}")
    print(f"Total Segments Parsed: {len(timestamps)}")
    assert len(timestamps) == 13, f"Expected 13 segments, got {len(timestamps)}"
    print(f"Segment 1: [{timestamps[0].start_time}-{timestamps[0].end_time}s] -> '{timestamps[0].text[:40]}...'")
    print("Timestamp Parser: PASSED\n")

    print("=== Testing Image Mapper (Index Mode) ===")
    images_dir = "images/How Ancient Humans Used Salt"
    mapped_clips = map_images_to_timestamps(images_dir, timestamps, mode="index")
    print(f"Total Mapped Clips: {len(mapped_clips)}")
    assert len(mapped_clips) > 0, "No clips were mapped!"
    print(f"First Clip: {os.path.basename(mapped_clips[0].image_path)} (Duration: {mapped_clips[0].duration}s)")
    print("Image Mapper (Index Mode): PASSED\n")

    print("=== Testing Image Mapper (Sequential Mode) ===")
    mapped_seq = map_images_to_timestamps(images_dir, timestamps, mode="sequential")
    print(f"Total Sequential Clips: {len(mapped_seq)}")
    print("Image Mapper (Sequential Mode): PASSED\n")

    print("=== Testing Image Mapper (No Script / Optional Timestamps) ===")
    mapped_no_script = map_images_to_timestamps(images_dir, timestamps=None, audio_duration=60.0)
    print(f"Total Clips Without Script: {len(mapped_no_script)}")
    assert len(mapped_no_script) > 0, "No clips generated for no-script mode!"
    assert round(mapped_no_script[0].duration * len(mapped_no_script), 1) == 60.0, "Audio duration not divided equally!"
    print("Image Mapper (No Script): PASSED\n")

    print("=== Testing Image Mapper (Custom Manual Timeline Table) ===")
    from src.image_mapper import create_custom_timeline
    custom_rows = [[1, "1.png", 10.0], [2, "2.png", 15.0]]
    mapped_custom = create_custom_timeline(images_dir, custom_rows)
    print(f"Total Custom Clips: {len(mapped_custom)}")
    assert len(mapped_custom) == 2, f"Expected 2 custom clips, got {len(mapped_custom)}"
    assert mapped_custom[0].duration == 10.0 and mapped_custom[1].duration == 15.0, "Custom durations mismatch!"

    # Test 4-column format with HTML preview and Start Timestamps
    smart_rows = [
        ["<img src='...'>", "1", "0:00", ""],
        ["<img src='...'>", "2", "0:08", ""],
        ["<img src='...'>", "3", "0:15", ""]
    ]
    mapped_smart = create_custom_timeline(images_dir, smart_rows, audio_duration=30.0)
    assert len(mapped_smart) == 3, f"Expected 3 smart clips, got {len(mapped_smart)}"
    assert mapped_smart[0].duration == 8.0, f"Expected 8.0s, got {mapped_smart[0].duration}"
    assert mapped_smart[1].duration == 7.0, f"Expected 7.0s, got {mapped_smart[1].duration}"
    assert mapped_smart[2].duration == 15.0, f"Expected 15.0s, got {mapped_smart[2].duration}"
    print("Image Mapper (Custom Timeline Table & Smart Timestamps): PASSED\n")

    print("=== Testing Ken Burns Animation & Frame Generator ===")
    sample_clip = mapped_clips[0]
    clip = create_ken_burns_clip(
        image_path=sample_clip.image_path,
        duration=sample_clip.duration,
        effect_type="zoom_in",
        target_size=(1280, 720),
        fps=24,
        transition_duration=0.2
    )
    frame = clip.get_frame(0.0)
    print(f"Frame Shape at t=0.0: {frame.shape}, Dtype: {frame.dtype}")
    assert frame.shape == (720, 1280, 3), f"Expected shape (720, 1280, 3), got {frame.shape}"
    print("Ken Burns Animation: PASSED\n")

    print("=== Testing Audio File Loading ===")
    audio_path = "audio/How Ancient Humans Used Salt.wav"
    audio = AudioFileClip(audio_path)
    print(f"Audio Loaded Successfully! Duration: {audio.duration:.2f}s")
    print("Audio Loader: PASSED\n")

    print("=========================================")
    print("   ALL PIPELINE UNIT TESTS PASSED!       ")
    print("=========================================")


if __name__ == "__main__":
    test_pipeline()
