# Local Ukrainian and Russian live subtitles

This app captures Ukrainian or Russian speech and shows an English subtitle
overlay. It runs transcription and translation locally on Apple Silicon with
MLX Whisper. The model is downloaded on the first run and can be used offline
afterward.

## Run

```sh
uv sync
uv run python src/main.py
```

The default backend uses Whisper `large-v3` to translate Ukrainian speech
directly into English. To use Ukrainian transcription followed by Argos
translation instead:

```sh
uv run python src/main.py --backend argos
```

Use Russian as the spoken source language with:

```sh
uv run python src/main.py --language ru
```

Russian also works with the optional Argos backend:

```sh
uv run python src/main.py --language ru --backend argos
```

The overlay starts near the bottom of the primary display. Drag it with the
mouse to reposition it. Press Escape or `q` to quit.

## Choose an audio input

List the CoreAudio devices visible to the app:

```sh
uv run python src/main.py --list-devices
```

Select a device by ID or name:

```sh
uv run python src/main.py --device 2
uv run python src/main.py --device "BlackHole 2ch"
```

For a person speaking near the Mac, use the built-in or an external
microphone. To subtitle audio playing on the Mac, route that audio into a
CoreAudio loopback input such as BlackHole or Loopback, then pass that input to
`--device`.

macOS may request microphone access for Terminal, your IDE, or Python the first
time the app records audio.
