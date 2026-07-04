import os
import argparse
from src.video_generator import generate_video


def parse_resolution(res_str: str) -> tuple:
    try:
        width, height = map(int, res_str.lower().split('x'))
        return (width, height)
    except Exception:
        raise argparse.ArgumentTypeError(f"Invalid resolution format: '{res_str}'. Expected format like '1920x1080'.")


def main():
    parser = argparse.ArgumentParser(
        description="Automated Video Generator with Ken Burns Effects & Audio Synchronization"
    )
    
    # Default paths matching project repository structure
    base_dir = os.path.dirname(os.path.abspath(__file__))
    default_script = os.path.join(base_dir, "scripts", "How Ancient Humans Used Salt.txt")
    default_audio = os.path.join(base_dir, "audio", "How Ancient Humans Used Salt.wav")
    default_images = os.path.join(base_dir, "images", "How Ancient Humans Used Salt")
    default_output = os.path.join(base_dir, "output_video", "How_Ancient_Humans_Used_Salt.mp4")

    parser.add_argument("--script", type=str, default=default_script,
                        help="Path to script text file with timestamps (optional, pass 'none' to omit)")
    parser.add_argument("--audio", type=str, default=default_audio,
                        help="Path to audio file (.wav, .mp3)")
    parser.add_argument("--images", type=str, default=default_images,
                        help="Path to directory containing images")
    parser.add_argument("--output", type=str, default=default_output,
                        help="Path for output video (.mp4)")
    parser.add_argument("--mapping", type=str, choices=["index", "sequential"], default="index",
                        help="Image mapping strategy: 'index' (group by number prefix) or 'sequential'")
    parser.add_argument("--res", type=parse_resolution, default=(1920, 1080),
                        help="Output resolution in WIDTHxHEIGHT format (default: 1920x1080)")
    parser.add_argument("--fps", type=int, default=60,
                        help="Frames per second for output video (default: 60)")
    parser.add_argument("--transition", type=float, default=0.4,
                        help="Transition fade duration in seconds (default: 0.4)")

    args = parser.parse_args()

    script_arg = None if (args.script is None or str(args.script).lower() == "none" or not str(args.script).strip()) else args.script

    generate_video(
        script_source=script_arg,
        audio_path=args.audio,
        images_source=args.images,
        output_path=args.output,
        mapping_mode=args.mapping,
        resolution=args.res,
        fps=args.fps,
        transition_duration=args.transition
    )


if __name__ == "__main__":
    main()
