import os
import subprocess
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

app = FastAPI()

# Single Source of Truth: The Samba Share Root
SHARED_PATH = "/home/lyptus/LyptusShare/AO"

class TaskPayload(BaseModel):
    action: str
    input_file: str = "Sample.mp4"
    target_lang: str = None

@app.post("/execute")
def execute_edge_task(payload: TaskPayload):
    print(f"\n[Jetson Worker] Action Received: {payload.action}")

    # Define paths directly in the shared folder
    video_path = os.path.join(SHARED_PATH, payload.input_file)
    eng_audio = os.path.join(SHARED_PATH, "extracted_english_audio.wav")

    try:
        # 1. AUDIO EXTRACTION (Only happens ONCE at the start)
        if payload.action == "extract_audio":
            if not os.path.exists(video_path):
                raise FileNotFoundError(f"Input video not found: {video_path}")

            command = [
                "ffmpeg", "-y", "-i", video_path,
                "-vn", "-acodec", "pcm_s16le", "-ar", "16000", "-ac", "1",
                eng_audio
            ]
            subprocess.run(command, check=True, capture_output=True)
            return {"status": "success", "output": eng_audio}

        # 2. FINAL VIDEO MERGING (Happens AFTER RTX Desktop finishes its job)
        elif payload.action.startswith("merge_video_"):
            lang = payload.target_lang
            lang_audio = os.path.join(SHARED_PATH, f"audio_{lang}.wav")
            lang_srt = os.path.join(SHARED_PATH, f"subtitles_{lang}.srt")
            final_out = os.path.join(SHARED_PATH, f"final_{lang}.mp4")

            # Check if RTX Desktop actually finished the files
            if not os.path.exists(lang_audio) or not os.path.exists(lang_srt):
                raise FileNotFoundError(f"Missing translated assets for {lang} in {SHARED_PATH}")

            command = [
                "ffmpeg", "-y", "-i", video_path, "-i", lang_audio, "-i", lang_srt,
                "-map", "0:v:0", "-map", "1:a:0", "-map", "2:s:0",
                "-c:v", "copy", "-c:a", "aac", "-c:s", "mov_text",
                final_out
            ]
            subprocess.run(command, check=True, capture_output=True)
            return {"status": "success", "output": final_out}

        else:
            raise ValueError(f"Action '{payload.action}' is handled by the RTX Desktop, not Jetson.")

    except Exception as e:
        print(f"ERROR: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

if __name__=="__main__":
    import uvicorn
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=5000)
    args = parser.parse_args()
    uvicorn.run(app, host="0.0.0.0", port=args.port)

