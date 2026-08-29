import argparse

import sounddevice as sd

from caption_display import CaptionDisplay
from live_translator import LiveTranslator


def parse_args():
    parser = argparse.ArgumentParser(
        description="Show local Ukrainian/Russian-to-English subtitles on macOS."
    )
    parser.add_argument(
        "--backend",
        choices=("whisper", "argos"),
        default="whisper",
        help="Use direct Whisper translation (default) or Whisper plus Argos.",
    )
    parser.add_argument(
        "--language",
        choices=("uk", "ru"),
        default="uk",
        help="Spoken source language: Ukrainian (uk, default) or Russian (ru).",
    )
    parser.add_argument(
        "--device",
        help="Input device name or numeric ID (use --list-devices to discover it).",
    )
    parser.add_argument(
        "--list-devices",
        action="store_true",
        help="List audio devices and exit.",
    )
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    if args.list_devices:
        print(sd.query_devices())
        raise SystemExit(0)

    device = (
        int(args.device) if args.device and args.device.isdigit() else args.device
    )
    translator = LiveTranslator(
        translation_backend=args.backend,
        input_device=device,
        source_language=args.language,
    )
    display = CaptionDisplay(translator)
    display.run()
