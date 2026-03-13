import math
import os
import tempfile
import subprocess
from fastapi import FastAPI
from pydantic import BaseModel
import edge_tts
from faster_whisper import WhisperModel
import uvicorn
import pysrt
from pydub import AudioSegment

app = FastAPI()

print("Loading Whisper Model...")
model = WhisperModel("small", device="cuda", compute_type="float16")
print("Whisper Ready.")

class TranscribeRequest(BaseModel):
    path: str

class TTSRequest(BaseModel):
    text: str
    output_path: str
    lang: str = "en"

def format_timestamp(seconds: float):
    hours = math.floor(seconds / 3600)
    minutes = math.floor((seconds % 3600) / 60)
    secs = math.floor(seconds % 60)
    millis = math.floor((seconds - math.floor(seconds)) * 1000)
    return f"{hours:02d}:{minutes:02d}:{secs:02d},{millis:03d}"

@app.post("/transcribe")
async def transcribe_audio(req: TranscribeRequest):
    segments, info = model.transcribe(req.path, beam_size=5)

    srt_content = ""
    for i, segment in enumerate(segments, start=1):
        start_time = format_timestamp(segment.start)
        end_time = format_timestamp(segment.end)
        srt_content += f"{i}\n{start_time} --> {end_time}\n{segment.text.strip()}\n\n"

    return {"text": srt_content.strip()}

@app.post("/generate")
async def generate_audio(req: TTSRequest):
    voices = {
        "hi": "hi-IN-MadhurNeural", "te": "te-IN-MohanNeural",
        "fr": "fr-FR-HenriNeural", "es": "es-ES-AlvaroNeural",
        "de": "de-DE-KillianNeural", "en": "en-US-GuyNeural"
    }
    voice = voices.get(req.lang, "en-US-GuyNeural")

    with tempfile.NamedTemporaryFile(delete=False, suffix=".srt", mode="w", encoding="utf-8") as temp_srt:
        temp_srt.write(req.text)
        srt_path = temp_srt.name

    subs = pysrt.open(srt_path)

    if subs:
        total_duration_ms = subs[-1].end.ordinal + 2000
    else:
        total_duration_ms = 1000

    master_audio = AudioSegment.silent(duration=total_duration_ms)

    for sub in subs:
        text_to_speak = sub.text.replace('\n', ' ').strip()
        if not text_to_speak:
            continue

        temp_wav = f"{srt_path}_{sub.index}.wav"

        communicate = edge_tts.Communicate(text_to_speak, voice)
        await communicate.save(temp_wav)

        if os.path.exists(temp_wav):
            speech_segment = AudioSegment.from_file(temp_wav)
            actual_duration_ms = len(speech_segment)
            target_duration_ms = sub.end.ordinal - sub.start.ordinal

            # AUDIO SYNC FIX: Stretch the audio if it exceeds the SRT subtitle window
            if actual_duration_ms > target_duration_ms and target_duration_ms > 0:
                speed_factor = actual_duration_ms / target_duration_ms
                fast_wav = f"{temp_wav}_fast.wav"

                cmd = f'ffmpeg -y -i "{temp_wav}" -filter:a "atempo={speed_factor}" "{fast_wav}"'
                subprocess.run(cmd, shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

                speech_segment = AudioSegment.from_file(fast_wav)
                os.remove(fast_wav)

            # Overlay at the exact start timestamp
            start_time_ms = sub.start.ordinal
            master_audio = master_audio.overlay(speech_segment, position=start_time_ms)
            os.remove(temp_wav)

    master_audio.export(req.output_path, format="wav")
    os.remove(srt_path)

    return {"status": "success", "path": req.output_path}

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=5050)
