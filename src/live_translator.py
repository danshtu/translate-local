from queue import Empty, Full, Queue
from threading import Thread

import mlx_whisper
import numpy as np
import sounddevice as sd

# Audio settings
SAMPLE_RATE = 16_000
CHUNK_DURATION = 3.0
OVERLAP_DURATION = 1.0
BUFFER_SIZE = int(SAMPLE_RATE * CHUNK_DURATION)
OVERLAP_SIZE = int(SAMPLE_RATE * OVERLAP_DURATION)


class LiveTranslator:
    """Capture microphone audio and produce local English captions."""

    def __init__(
        self,
        translation_backend="whisper",
        input_device=None,
        source_language="uk",
    ):
        if translation_backend not in {"whisper", "argos"}:
            raise ValueError("translation_backend must be 'whisper' or 'argos'")
        if source_language not in {"uk", "ru"}:
            raise ValueError("source_language must be 'uk' or 'ru'")

        self.translation_backend = translation_backend
        self.input_device = input_device
        self.source_language = source_language
        self.model_path = "mlx-community/whisper-large-v3-mlx"
        self.translator = None

        if translation_backend == "argos":
            self._setup_argos()

        # Keep the callback non-blocking. If transcription falls behind, stale
        # microphone blocks are discarded instead of growing latency forever.
        self.audio_queue = Queue(maxsize=16)
        self.text_queue = Queue()
        self.running = False
        self.worker = None
        self.stream = None
        self.last_transcription = ""
        self.silence_threshold = 0.005

        self._warm_up_model()

    def _warm_up_model(self):
        """Load the model into mlx-whisper's cache before recording starts."""
        print("Loading and warming up Whisper model...")
        mlx_whisper.transcribe(
            np.zeros(SAMPLE_RATE, dtype=np.float32),
            path_or_hf_repo=self.model_path,
            language=self.source_language,
            task=(
                "translate"
                if self.translation_backend == "whisper"
                else "transcribe"
            ),
            condition_on_previous_text=False,
            no_speech_threshold=0.5,
            temperature=0.0,
            verbose=None,
        )

    def _setup_argos(self):
        """Install the selected Argos-to-English package only when missing."""
        import argostranslate.package
        import argostranslate.translate

        print("Setting up Argos translation...")
        installed = argostranslate.package.get_installed_packages()
        source_to_english = next(
            (
                p
                for p in installed
                if p.from_code == self.source_language and p.to_code == "en"
            ),
            None,
        )

        if source_to_english is None:
            argostranslate.package.update_package_index()
            available = argostranslate.package.get_available_packages()
            source_to_english = next(
                (
                    p
                    for p in available
                    if p.from_code == self.source_language and p.to_code == "en"
                ),
                None,
            )
            if source_to_english is None:
                raise RuntimeError(
                    f"No Argos {self.source_language}-to-English package is available"
                )
            argostranslate.package.install_from_path(source_to_english.download())

        self.translator = argostranslate.translate.get_translation_from_codes(
            self.source_language, "en"
        )

    def audio_callback(self, indata, frames, time_info, status):
        if status:
            print(f"Audio status: {status}")
        if not self.running:
            return

        chunk = indata.copy()
        try:
            self.audio_queue.put_nowait(chunk)
        except Full:
            # Real-time captions should skip stale audio rather than drift
            # farther and farther behind the speaker.
            try:
                self.audio_queue.get_nowait()
            except Empty:
                pass
            try:
                self.audio_queue.put_nowait(chunk)
            except Full:
                pass

    def _transcribe(self, audio):
        task = "translate" if self.translation_backend == "whisper" else "transcribe"
        return mlx_whisper.transcribe(
            audio,
            path_or_hf_repo=self.model_path,
            language=self.source_language,
            task=task,
            condition_on_previous_text=False,
            no_speech_threshold=0.5,
            temperature=0.0,
            verbose=None,
        )["text"].strip()

    def transcribe_worker(self):
        buffer = np.empty(0, dtype=np.float32)

        while self.running:
            try:
                chunk = self.audio_queue.get(timeout=0.1)
            except Empty:
                continue

            buffer = np.concatenate((buffer, chunk.reshape(-1)))
            if len(buffer) < BUFFER_SIZE:
                continue

            audio = buffer[:BUFFER_SIZE]
            buffer = buffer[BUFFER_SIZE - OVERLAP_SIZE :]
            audio_level = float(np.abs(audio).mean())
            print(f"Audio level: {audio_level:.6f}")

            if audio_level < self.silence_threshold:
                print("Skipping - too quiet")
                continue

            text = self._transcribe(audio)
            if not text:
                continue

            if self.translation_backend == "whisper":
                original_text = ""
                english_text = text
                print(f"Translated (English): '{english_text}'")
            else:
                original_text = text
                english_text = self.translator.translate(original_text).strip()
                print(f"Transcribed ({self.source_language}): '{original_text}'")
                print(f"Translated (English): '{english_text}'")

            normalized = " ".join(english_text.casefold().split())
            if normalized == self.last_transcription:
                print("Skipping - duplicate caption")
                continue

            self.text_queue.put(
                {"original": original_text, "translated": english_text}
            )
            self.last_transcription = normalized

    def start(self):
        if self.running:
            return

        self.stream = sd.InputStream(
            device=self.input_device,
            samplerate=SAMPLE_RATE,
            channels=1,
            dtype=np.float32,
            callback=self.audio_callback,
            blocksize=int(SAMPLE_RATE * 0.5),
        )
        self.running = True
        self.worker = Thread(target=self.transcribe_worker, daemon=True)
        self.worker.start()
        try:
            self.stream.start()
        except Exception:
            self.stop()
            raise

    def stop(self):
        if not self.running:
            return

        self.running = False
        if self.stream is not None:
            self.stream.stop()
            self.stream.close()
            self.stream = None
        if self.worker is not None:
            self.worker.join(timeout=2)
            self.worker = None
