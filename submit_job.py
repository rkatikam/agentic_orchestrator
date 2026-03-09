import asyncio
import json
from core.models import Task, HardwareNode
from core.compiler import AgenticCompiler
from runtime.orchestrator import ExecutionEngine

CLUSTER = [
    HardwareNode("rtx_5060ti", ["llm_heavy", "ai_inference_light"]),
    HardwareNode("intel_b60", ["llm_heavy", "ai_inference_light"]),
    HardwareNode("jetson_nano_1", ["io_bound", "cpu_scalar"]),
    HardwareNode("jetson_nano_2", ["io_bound", "cpu_scalar"])
]

ENDPOINTS = {
    "rtx_5060ti": "http://192.168.1.100:8000/v1/completions",
    "intel_b60": "http://192.168.1.101:8000/v1/completions",
    "jetson_nano_1": "http://192.168.1.102:5000/execute",
    "jetson_nano_2": "http://192.168.1.103:5000/execute"
}

# Base Extraction
WORKFLOW = {
    "extract_audio": Task("extract_audio", "io_bound"),
    "transcribe_eng": Task("transcribe_eng", "ai_inference_light", deps=["extract_audio"]),
}

# Generate branches for all 5 languages
LANGUAGES = ["hi", "te", "fr", "es", "de"]

for lang in LANGUAGES:
    # LLM Translation
    WORKFLOW[f"translate_{lang}"] = Task(f"translate_{lang}", "llm_heavy", deps=["transcribe_eng"], target_lang=lang)
    
    # Text Processing (Subtitles)
    WORKFLOW[f"format_srt_{lang}"] = Task(f"format_srt_{lang}", "cpu_scalar", deps=[f"translate_{lang}"], target_lang=lang)
    
    # Audio Processing (TTS - routed to edge for our mock)
    WORKFLOW[f"tts_{lang}"] = Task(f"tts_{lang}", "cpu_scalar", deps=[f"translate_{lang}"], target_lang=lang)
    
    # Final Video Merge (Waits for both Audio and Subtitles to finish)
    WORKFLOW[f"merge_video_{lang}"] = Task(f"merge_video_{lang}", "io_bound", deps=[f"format_srt_{lang}", f"tts_{lang}"], target_lang=lang)


if __name__ == "__main__":
    compiler = AgenticCompiler(hardware_registry=CLUSTER)
    manifest = compiler.compile(WORKFLOW)
    
    print("Compiled Manifest Output generated...")
    
    engine = ExecutionEngine(node_endpoints=ENDPOINTS)
    asyncio.run(engine.execute_manifest(manifest))
