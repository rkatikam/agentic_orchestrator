from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
import subprocess
import os
import json
import shutil

app = FastAPI()

SHARED_DRIVE_PATH = "/mnt/shared_storage"
INPUT_DIR = os.path.join(SHARED_DRIVE_PATH, "inputs")
OUTPUT_DIR = os.path.join(SHARED_DRIVE_PATH, "outputs")

os.makedirs(INPUT_DIR, exist_ok=True)
os.makedirs(OUTPUT_DIR, exist_ok=True)

class TaskPayload(BaseModel):
    action: str
    input_file: str = "source_video.mp4"
    target_lang: str = None
    llm_text_data: str = None

@app.post("/execute")
def execute_edge_task(payload: TaskPayload):
    print(f"\n[Edge Worker] Received Action: {payload.action}")
    
    try:
        # 1. AUDIO EXTRACTION
        if payload.action == "extract_audio":
            input_video_path = os.path.join(INPUT_DIR, payload.input_file)
            output_audio_path = os.path.join(OUTPUT_DIR, "extracted_english_audio.wav")
            
            command = [
                "ffmpeg", "-y", "-i", input_video_path,
                "-vn", "-acodec", "pcm_s16le", "-ar", "16000", "-ac", "1",
                output_audio_path
            ]
            print(f"  -> Running FFmpeg extraction...")
            subprocess.run(command, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            return {"status": "success", "output_pointer": output_audio_path}

        # 2. SUBTITLE FORMATTING
        elif payload.action.startswith("format_srt_"):
            output_srt_path = os.path.join(OUTPUT_DIR, f"subtitles_{payload.target_lang}.srt")
            print(f"  -> Generating SRT file at: {output_srt_path}")
            
            translations = [{"start": "00:00:01,000", "end": "00:00:05,000", "text": f"Simulated {payload.target_lang} subtitle"}]

            with open(output_srt_path, "w", encoding="utf-8") as srt_file:
                for idx, block in enumerate(translations, start=1):
                    srt_file.write(f"{idx}\n")
                    srt_file.write(f"{block.get('start')} --> {block.get('end')}\n")
                    srt_file.write(f"{block.get('text', '')}\n\n")

            return {"status": "success", "output_pointer": output_srt_path}

        # 3. TEXT-TO-SPEECH (MOCKED)
        elif payload.action.startswith("tts_"):
            # Mocking the AI TTS by duplicating the extracted audio so FFmpeg has a file to use
            src_audio = os.path.join(OUTPUT_DIR, "extracted_english_audio.wav")
            output_audio = os.path.join(OUTPUT_DIR, f"audio_{payload.target_lang}.wav")
            print(f"  -> Generating mocked TTS audio at: {output_audio}")
            
            if os.path.exists(src_audio):
                shutil.copy(src_audio, output_audio)
            else:
                with open(output_audio, "wb") as f: f.write(b"") # Empty file fallback

            return {"status": "success", "output_pointer": output_audio}

        # 4. FINAL VIDEO MERGING
        elif payload.action.startswith("merge_video_"):
            input_video = os.path.join(INPUT_DIR, payload.input_file)
            input_audio = os.path.join(OUTPUT_DIR, f"audio_{payload.target_lang}.wav")
            input_srt = os.path.join(OUTPUT_DIR, f"subtitles_{payload.target_lang}.srt")
            output_video = os.path.join(OUTPUT_DIR, f"final_{payload.target_lang}.mp4")

            print(f"  -> Muxing final video: {output_video}")
            
            # Merges Original Video + New Audio + New Subtitles
            command = [
                "ffmpeg", "-y",
                "-i", input_video,
                "-i", input_audio,
                "-i", input_srt,
                "-map", "0:v:0", "-map", "1:a:0", "-map", "2:s:0",
                "-c:v", "copy",
                "-c:a", "aac",
                "-c:s", "mov_text",
                output_video
            ]
            subprocess.run(command, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            return {"status": "success", "output_pointer": output_video}

        else:
            raise ValueError(f"Action '{payload.action}' is not supported.")

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
