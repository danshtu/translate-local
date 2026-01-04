import sounddevice as sd
import numpy as np
import mlx_whisper
import argostranslate.package
import argostranslate.translate
from queue import Queue
from threading import Thread

# Audio settings
SAMPLE_RATE = 16000
CHUNK_DURATION = 3  # seconds per chunk
BUFFER_SIZE = SAMPLE_RATE * CHUNK_DURATION

class LiveTranslator:
    def __init__(self):
        # Load Whisper model (use "large-v3" for best Ukrainian accuracy)
        print("Loading Whisper model...")
        self.model_path = "mlx-community/whisper-large-v3-mlx"
        mlx_whisper.load_models.load_model(path_or_hf_repo=self.model_path)

        # Install and load Argos translation (Ukrainian → English)
        self._setup_argos()

        self.audio_queue = Queue()
        self.text_queue = Queue()
        self.running = False
        self.last_transcription = ""
        self.silence_threshold = 0.005  # Skip transcription if audio level below this

    def _setup_argos(self):
        print("Setting up translation...")
        argostranslate.package.update_package_index()
        available = argostranslate.package.get_available_packages()

        # Find Ukrainian → English package
        uk_en = next((p for p in available
                      if p.from_code == "uk" and p.to_code == "en"), None)
        if uk_en:
            argostranslate.package.install_from_path(uk_en.download())

        self.translator = argostranslate.translate.get_translation_from_codes("uk", "en")

    def audio_callback(self, indata, frames, time, status):
        if status:
            print(f"Audio status: {status}")
        self.audio_queue.put(indata.copy())

    def transcribe_worker(self):
        buffer = np.array([], dtype=np.float32)

        while self.running:
            if not self.audio_queue.empty():
                chunk = self.audio_queue.get()
                buffer = np.append(buffer, chunk.flatten())

                # Process when buffer is full
                if len(buffer) >= BUFFER_SIZE:
                    # Check audio level
                    audio_level = np.abs(buffer[:BUFFER_SIZE]).mean()
                    print(f"Audio level: {audio_level:.6f}")

                    # Skip if too quiet (likely silence/hallucination)
                    if audio_level < self.silence_threshold:
                        print("Skipping - too quiet")
                        buffer = buffer[BUFFER_SIZE // 2:]
                        continue

                    result = mlx_whisper.transcribe(
                        buffer[:BUFFER_SIZE],
                        path_or_hf_repo=self.model_path,
                        language="uk",
                    )

                    ukrainian_text = result["text"].strip()
                    print(f"Transcribed (Ukrainian): '{ukrainian_text}'")

                    # Skip if same as last transcription (avoid repeats)
                    if ukrainian_text and ukrainian_text != self.last_transcription:
                        english_text = self.translator.translate(ukrainian_text)
                        print(f"Translated (English): '{english_text}'")
                        self.text_queue.put({
                            "original": ukrainian_text,
                            "translated": english_text
                        })
                        self.last_transcription = ukrainian_text
                    elif ukrainian_text == self.last_transcription:
                        print("Skipping - duplicate transcription")

                    # Keep overlap for continuity
                    buffer = buffer[BUFFER_SIZE // 2:]

    def start(self):
        self.running = True

        # Start transcription thread
        Thread(target=self.transcribe_worker, daemon=True).start()

        # Start audio stream
        self.stream = sd.InputStream(
            samplerate=SAMPLE_RATE,
            channels=1,
            dtype=np.float32,
            callback=self.audio_callback,
            blocksize=int(SAMPLE_RATE * 0.5)  # 500ms blocks
        )
        self.stream.start()

    def stop(self):
        self.running = False
        self.stream.stop()
