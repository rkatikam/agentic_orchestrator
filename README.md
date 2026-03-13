# Agentic Video Localization Pipeline - Setup & Execution Guide

This file contains all setup and execution steps for the Windows Control Plane, RTX 5060 Ti Desktop, and Jetson Nano.



---

## Part 1: Requirements & Setup

### Machine 1: Windows Laptop (Control Plane)
1. Create a file named requirements.txt and add this line:
    aiohttp==3.9.3

2. Open Command Prompt and run:
    pip install -r requirements.txt

3. Ensure your Samba share is mapped to Z: and Sample.mp4 is inside Z:/AO/

### Machine 2: Linux RTX 5060 Ti Desktop (AI Node)
1. Open a terminal and install system dependencies:
    sudo apt update && sudo apt install ffmpeg

2. Create a file named requirements.txt and add these lines:
    fastapi==0.110.0
    uvicorn==0.27.1
    pydantic==2.6.3
    faster-whisper==1.0.1
    edge-tts==6.1.9
    pydub==0.25.1
    pysrt==1.1.2
    vllm==0.3.3

3. Install Python dependencies:
    pip install -r requirements.txt

4. Ensure the Samba share is mounted:
    ls -lh /mnt/jetson_share/AO/
    (If it hangs, fix it with: sudo umount -f -l /mnt/jetson_share && sudo mount -a)

### Machine 3: Jetson Nano Orin (Edge Node)
1. SSH into the Jetson and install system dependencies:
    sudo apt update && sudo apt install ffmpeg

2. Create a file named requirements.txt and add these lines:
    fastapi==0.110.0
    uvicorn==0.27.1

3. Install Python dependencies:
    pip install -r requirements.txt

---

## Part 2: Execution Order

You must start these in the exact order below across 4 separate terminal windows.

### Step 1: Start the Edge Worker (On Jetson Nano)
Run this command:
    python3 edge_worker.py

### Step 2: Start the LLM Engine (On RTX Desktop - Terminal 1)
Run this command (the 4096 max-model-len is strictly required):
    python3 -m vllm.entrypoints.openai.api_server --model /opt/huggingface/Meta-Llama-3.1-8B-Instruct-bnb-4bit --max-model-len 4096

### Step 3: Start the Audio/TTS Server (On RTX Desktop - Terminal 2)
Run this command:
    python3 runtime/tts_server.py

### Step 4: Dispatch the Job (On Windows Laptop)
Once the Jetson and RTX servers are all running, dispatch the DAG:
    python submit_job.py

---

## Part 3: Troubleshooting

* FFmpeg exit status 1 on final merge: The LLM dropped the sequence number 1 and the 00:00:00,000 timestamp. Check Z:/AO/subtitles_[lang].srt.
* Output is the wrong language: Use full language names (e.g., "Telugu") in your prompt instead of ISO codes like "te".
* Pipeline hangs at Tier 1: The Samba mount on the RTX desktop died. Remount it using the command in Part 1.
