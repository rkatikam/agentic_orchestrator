"""
from fastapi import FastAPI
from faster_whisper import WhisperModel
from pydantic import BaseModel
import edge_tts
import uvicorn
import os

app = FastAPI()

model = WhisperModel("small", device="cuda", compute_type="float16")

class TTSRequest(BaseModel):
    text: str
    output_path: str
    lang: str = "hi"

@app.post("/generate")
async def generate_audio(req: TTSRequest):
    # Map your LANGUAGES list to edge-tts voices
    voices = {"hi": "hi-IN-MadhurNeural", "te": "te-IN-MohanNeural", "fr": "fr-FR-EloiseNeural"}
    voice = voices.get(req.lang, "en-US-GuyNeural")
    
    communicate = edge_tts.Communicate(req.text, voice)
    await communicate.save(req.output_path)
    return {"status": "success", "path": req.output_path}


@app.post("/transcribe")
async def transcribe_audio(req: dict):
    # Path to the file the Jetson just extracted
    audio_path = "/mnt/jetson_share/AO/extracted_english_audio.wav"

    segments, info = model.transcribe(audio_path, beam_size=5)
    full_text = " ".join([segment.text for segment in segments])

    return {"text": full_text}

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=5050)
"""
import math
from fastapi import FastAPI
from pydantic import BaseModel
import edge_tts
from faster_whisper import WhisperModel
import uvicorn

app = FastAPI()

print("Loading Whisper Model...")
# Using 'small' model for speed. It is highly accurate for baseline English.
model = WhisperModel("small", device="cuda", compute_type="float16")
print("Whisper Ready.")

class TranscribeRequest(BaseModel):
    path: str

class TTSRequest(BaseModel):
    text: str
    output_path: str
    lang: str = "en"

def format_timestamp(seconds: float):
    """Converts raw seconds into strict SRT format: HH:MM:SS,mmm"""
    hours = math.floor(seconds / 3600)
    minutes = math.floor((seconds % 3600) / 60)
    secs = math.floor(seconds % 60)
    millis = math.floor((seconds - math.floor(seconds)) * 1000)
    return f"{hours:02d}:{minutes:02d}:{secs:02d},{millis:03d}"

@app.post("/transcribe")
async def transcribe_audio(req: TranscribeRequest):
    # Transcribe and force it to build an exact SRT structure
    segments, info = model.transcribe(req.path, beam_size=5)

    srt_content = ""
    for i, segment in enumerate(segments, start=1):
        start_time = format_timestamp(segment.start)
        end_time = format_timestamp(segment.end)
        srt_content += f"{i}\n{start_time} --> {end_time}\n{segment.text.strip()}\n\n"

    return {"text": srt_content.strip()}

@app.post("/generate")
async def generate_audio(req: TTSRequest):
    # Strip out the SRT timestamps/numbers before sending to TTS so it doesn't read them aloud
    import re
    clean_text = re.sub(r'\d+\n\d{2}:\d{2}:\d{2},\d{3} --> \d{2}:\d{2}:\d{2},\d{3}\n', '', req.text)
    clean_text = clean_text.replace('\n', ' ').strip()

    # Map your 5 languages to specific high-quality Edge-TTS neural voices
    voices = {
        "hi": "hi-IN-MadhurNeural",
        "te": "te-IN-MohanNeural",
        "fr": "fr-FR-HenriNeural",
        "es": "es-ES-AlvaroNeural",
        "de": "de-DE-KillianNeural",
        "en": "en-US-GuyNeural"
    }
    voice = voices.get(req.lang, "en-US-GuyNeural")

    communicate = edge_tts.Communicate(clean_text, voice)
    await communicate.save(req.output_path)
    return {"status": "success", "path": req.output_path}

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=5050)
