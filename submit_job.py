import asyncio
import urllib.request
import json
from core.models import Task, HardwareNode
from core.compiler import AgenticCompiler
from runtime.orchestrator import ExecutionEngine

DESKTOP_IP = "192.168.20.58"
JETSON_IP = "192.168.20.143"
SAMBA_PATH = "Z:/AO"
RTX_MOUNT_PATH = "/mnt/jetson_share/AO"

CLUSTER = [
    HardwareNode("rtx_5060ti", ["llm_heavy", "ai_inference_light"]),
    HardwareNode("jetson_nano_1", ["io_bound"])
]

ENDPOINTS = {
    "rtx_5060ti": f"http://{DESKTOP_IP}:8000",
    "rtx_5060ti_services": f"http://{DESKTOP_IP}:5050",
    "jetson_nano_1": f"http://{JETSON_IP}:5000/execute",
}

def get_vllm_model(base_url):
    try:
        req = urllib.request.Request(f"{base_url}/v1/models")
        with urllib.request.urlopen(req, timeout=5) as response:
            data = json.loads(response.read().decode())
            return data["data"][0]["id"]
    except Exception as e:
        print(f"[!] Could not auto-detect vLLM model: {e}")
        return "/opt/huggingface/Meta-Llama-3.1-8B-Instruct-bnb-4bit"

ACTIVE_VLLM_MODEL = get_vllm_model(ENDPOINTS["rtx_5060ti"])
print(f"[System] Registered Model for DAG: {ACTIVE_VLLM_MODEL}")

WORKFLOW = {}

WORKFLOW["extract_audio"] = Task(
    task_id="extract_audio", compute_type="io_bound",
    action_payload={"action": "extract_audio", "target_lang": "en"},
    output_handlers={"memory_key": "extract_audio", "json_path": "output_pointer"}
)

WORKFLOW["transcribe_eng"] = Task(
    task_id="transcribe_eng", compute_type="ai_inference_light", deps=["extract_audio"],
    action_payload={
        "override_endpoint": "rtx_5060ti_services",
        "endpoint_suffix": "/transcribe",
        "path": f"{RTX_MOUNT_PATH}/extracted_english_audio.wav"
    },
    output_handlers={
        "memory_key": "transcribe_eng",
        "json_path": "text",
        "save_file_1": f"{SAMBA_PATH}/debug_transcript_eng.srt"
    }
)

# Map short codes to full language names to stop LLM hallucination
LANGUAGE_MAP = {
    "hi": "Hindi",
    "te": "Telugu",
    "fr": "French",
    "es": "Spanish",
    "de": "German"
}

for lang_code, lang_name in LANGUAGE_MAP.items():
    WORKFLOW[f"translate_{lang_code}"] = Task(
        task_id=f"translate_{lang_code}", compute_type="llm_heavy", deps=["transcribe_eng"],
        action_payload={
            "endpoint_suffix": "/v1/chat/completions",
            "model": ACTIVE_VLLM_MODEL,
            "messages": [
                {
                    "role": "system",
                    "content": (
                        "You are a programmatic translation API. You receive SRT formatted subtitles. "
                        "You MUST obey these constraints: "
                        "<constraints>\n"
                        f"1. Translate ONLY the spoken text into {lang_name}. Do not translate timestamps.\n"
                        "2. You MUST return the EXACT SAME number of sequence blocks as the input.\n"
                        "3. Do not merge, combine, or skip any lines.\n"
                        "4. Output absolutely nothing except the final SRT file.\n"
                        "5. Your output MUST start with the number 1, followed by the first timestamp. DO NOT skip the first block's metadata.\n"
                        "</constraints>"
                    )
                },
                {"role": "user", "content": f"Translate this SRT into {lang_name}:\n\n{{dep:transcribe_eng}}"}
            ],
            "max_tokens": 1500, # Increased back to 1500 to prevent truncation
            "temperature": 0.1
        },
        output_handlers={
            "memory_key": f"translate_{lang_code}",
            "json_path": "choices.0.message.content",
            "save_file_1": f"{SAMBA_PATH}/debug_translation_{lang_code}.txt",
            "save_file_2": f"{SAMBA_PATH}/subtitles_{lang_code}.srt"
        }
    )

    WORKFLOW[f"tts_{lang_code}"] = Task(
        task_id=f"tts_{lang_code}", compute_type="ai_inference_light", deps=[f"translate_{lang_code}"],
        action_payload={
            "override_endpoint": "rtx_5060ti_services",
            "endpoint_suffix": "/generate",
            "text": f"{{dep:translate_{lang_code}}}",
            "lang": lang_code,
            "output_path": f"{RTX_MOUNT_PATH}/audio_{lang_code}.wav"
        },
        output_handlers={"memory_key": f"tts_{lang_code}", "json_path": "path"}
    )

    WORKFLOW[f"merge_video_{lang_code}"] = Task(
        task_id=f"merge_video_{lang_code}", compute_type="io_bound", deps=[f"translate_{lang_code}", f"tts_{lang_code}"],
        action_payload={
            "action": f"merge_video_{lang_code}",
            "input_file": "Sample.mp4",
            "target_lang": lang_code,
            "llm_text_data": f"{{dep:translate_{lang_code}}}"
        },
        output_handlers={"memory_key": f"merge_video_{lang_code}", "json_path": "output_pointer"}
    )

if __name__ == "__main__":
    print("Compiling Agentic Workflow DAG...")
    compiler = AgenticCompiler(hardware_registry=CLUSTER)
    manifest = compiler.compile(WORKFLOW)

    print("Initializing Task-Agnostic Engine...")
    engine = ExecutionEngine(node_endpoints=ENDPOINTS)
    asyncio.run(engine.execute_manifest(manifest))
