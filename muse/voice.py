"""Deliberate, bounded voice input. Exact allowlist; no LLM executes commands."""
import io
import json
import os
import re
import wave
from pathlib import Path

PHRASES = {
    "play": "play", "resume": "play", "resume music": "play", "play music": "play",
    "pause": "pause", "pause music": "pause", "stop": "pause", "stop music": "pause",
    "next": "next", "next song": "next", "next track": "next", "skip": "next", "skip song": "next",
    "previous": "previous", "previous song": "previous", "previous track": "previous",
    "volume up": "volume_up", "louder": "volume_up", "volume down": "volume_down", "quieter": "volume_down",
    "skip forward": "forward", "skip back": "back", "shuffle": "shuffle", "repeat": "repeat",
    "what is playing": "now_playing", "what s playing": "now_playing", "song name": "now_playing",
    "cancel": "cancel"
}


def parse(text):
    clean = re.sub(r"[^a-z0-9 ]", " ", str(text).lower())
    clean = " ".join(clean.split())
    for prefix in ("muse ", "please "):
        if clean.startswith(prefix):
            clean = clean[len(prefix):]
    return PHRASES.get(clean)


def pcm16_mono(wav_bytes):
    import numpy as np
    with wave.open(io.BytesIO(wav_bytes), "rb") as wav:
        if wav.getsampwidth() != 2 or wav.getnchannels() not in {1, 2}:
            raise ValueError("Voice input needs mono/stereo PCM16 WAV")
        rate, channels = wav.getframerate(), wav.getnchannels()
        frames = wav.getnframes()
        if rate <= 0 or frames / rate > 8:
            raise ValueError("Voice clip must be at most eight seconds")
        samples = np.frombuffer(wav.readframes(frames), dtype="<i2").astype(np.float64)
    if channels == 2:
        samples = samples.reshape(-1, 2).mean(axis=1)
    if rate != 16000 and len(samples):
        count = int(len(samples) * 16000 / rate)
        samples = np.interp(np.arange(count) * rate / 16000, np.arange(len(samples)), samples)
    return np.clip(samples, -32768, 32767).astype("<i2").tobytes()


class Transcriber:
    def __init__(self, config):
        self.config = config
        self.model = None

    def recognize(self, wav_bytes):
        if len(wav_bytes) > 2_000_000:
            raise ValueError("Voice input too large")
        backend = self.config.get("voice_backend", "typed")
        pcm = pcm16_mono(wav_bytes)  # validate duration/format before any upload
        if backend == "vosk":
            from vosk import Model, KaldiRecognizer
            path = Path(self.config.get("vosk_model_path", ""))
            if not (path / "am").is_dir():
                raise ValueError("Configure an extracted, compatible Vosk model directory")
            if self.model is None:
                self.model = Model(str(path))
            recognizer = KaldiRecognizer(self.model, 16000)
            recognizer.AcceptWaveform(pcm)
            return json.loads(recognizer.FinalResult()).get("text", "")
        if backend == "openai":
            if self.config.get("cloud_voice_consent") is not True:
                raise ValueError("Enable cloud_voice_consent only after reviewing audio sharing")
            key = os.environ.get("OPENAI_API_KEY")
            if not key:
                raise ValueError("OPENAI_API_KEY is not configured on this device")
            import requests
            response = requests.post("https://api.openai.com/v1/audio/transcriptions",
                headers={"Authorization": "Bearer " + key}, data={"model": "whisper-1", "language": "en"},
                files={"file": ("command.wav", wav_bytes, "audio/wav")}, timeout=20)
            if not response.ok:
                raise ValueError(f"Speech service returned HTTP {response.status_code}")
            return response.json().get("text", "")
        raise ValueError("Select typed, vosk, or consented openai voice mode")
