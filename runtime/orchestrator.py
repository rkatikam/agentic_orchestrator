import asyncio
import aiohttp
import os

class ExecutionEngine:
    def __init__(self, node_endpoints: dict):
        self.node_endpoints = node_endpoints
        self.shared_memory = {} 

        # Windows Laptop view of the Jetson Samba Share
        self.SAMBA_PATH = "Z:/AO"

        # Linux RTX view of the Jetson Samba Share
        self.RTX_MOUNT_PATH = "/mnt/jetson_share/AO"

        self.pipeline_failed = False

    async def dispatch_task(self, session: aiohttp.ClientSession, task: dict):
        if self.pipeline_failed:
            return

        task_id = task.get("task_id")
        compute_type = task.get("compute_type")
        target_node = task.get("target_node")

        target_lang = task.get("target_lang")
        if target_lang is None:
            target_lang = "en"

        base_endpoint = self.node_endpoints.get(target_node)
        actual_url = base_endpoint
        payload = {}

        print(f"  -> [Dispatching] '{task_id}' to {target_node}")

        # --- 1. TRANSCRIBE (Whisper on RTX:5050) ---
        if task_id == "transcribe_eng":
            actual_url = "http://192.168.20.58:5050/transcribe"
            payload = {"path": f"{self.RTX_MOUNT_PATH}/extracted_english_audio.wav"}

        # --- 2. TRANSLATE & FORMAT SRT (Llama 3.1 via vLLM on RTX:8000) ---
        elif compute_type in ["llm_heavy", "ai_inference_light"] and ("translate" in task_id or "format_srt" in task_id):
            # Auto-fix URL from completions to chat/completions for Llama 3.1 Instruct
            if "v1/completions" in actual_url:
                actual_url = actual_url.replace("v1/completions", "v1/chat/completions")

            if "format_srt" in task_id:
                context = self.shared_memory.get(f"translate_{target_lang}", "Text missing")
            else:
                context = self.shared_memory.get("transcribe_eng", "Transcript missing")

            # --- AUTO-DETECT vLLM MODEL NAME ---
            if "vllm_active_model" not in self.shared_memory:
                try:
                    # Extract base URL (e.g., http://192.168.20.58:8000) to fetch models
                    base_vllm_url = actual_url.split("/v1/")[0]
                    async with session.get(f"{base_vllm_url}/v1/models") as m_resp:
                        if m_resp.status == 200:
                            m_data = await m_resp.json()
                            self.shared_memory["vllm_active_model"] = m_data["data"][0]["id"]
                            print(f"    [System] Auto-detected vLLM model: {self.shared_memory['vllm_active_model']}")
                        else:
                            self.shared_memory["vllm_active_model"] = "default-model"
                except Exception as e:
                    print(f"    [!] Failed to auto-detect model: {e}")
                    self.shared_memory["vllm_active_model"] = "default-model"

            # Llama 3.1 Chat API format
            payload = {
                "model": self.shared_memory.get("vllm_active_model", "default-model"),
                "messages": [
                    {"role": "system", "content": "You are a professional subtitle translator. Translate the provided SRT text. Keep all timestamps and sequence numbers exactly the same. Output ONLY the valid SRT format. No commentary."},
                    {"role": "user", "content": f"Translate this SRT into {target_lang}:\n\n{context}"}
                ],
                "max_tokens": 550,
                "temperature": 0.1
            }

        # --- 3. TEXT TO SPEECH (Edge-TTS on RTX:5050) ---
        elif "tts" in task_id:
            actual_url = "http://192.168.20.58:5050/generate"
            payload = {
                "text": self.shared_memory.get(f"translate_{target_lang}", "Text missing"),
                "lang": target_lang,
                "output_path": f"{self.RTX_MOUNT_PATH}/audio_{target_lang}.wav"
            }

        # --- 4. JETSON NANO IO (Merge & Extract on Jetson:5000) ---
        else:
            payload = {
                "action": task_id,
                "input_file": "Sample.mp4",
                "target_lang": target_lang,
                "llm_text_data": self.shared_memory.get(f"translate_{target_lang}", "")
            }

        # --- EXECUTION BLOCK ---
        try:
            async with session.post(actual_url, json=payload, timeout=300) as response:
                if response.status == 200:
                    result = await response.json()

                    if task_id == "transcribe_eng":
                        text_output = result.get("text", "").strip()
                        self.shared_memory[task_id] = text_output

                        debug_path = os.path.join(self.SAMBA_PATH, "debug_transcript_eng.txt")
                        try:
                            with open(debug_path, "w", encoding="utf-8") as f:
                                f.write(text_output)
                            print(f"    [DEBUG] Saved Base English SRT to {debug_path}")
                        except Exception as io_err:
                            print(f"    [!] Failed to write debug file: {io_err}")

                    elif "translate" in task_id or "format_srt" in task_id:
                        # Extract from OpenAI Chat API response format
                        text_output = result.get("choices", [{}])[0].get("message", {}).get("content", "").strip()
                        self.shared_memory[task_id] = text_output

                        if "translate" in task_id:
                            debug_path = os.path.join(self.SAMBA_PATH, f"debug_translation_{target_lang}.txt")
                            try:
                                with open(debug_path, "w", encoding="utf-8") as f:
                                    f.write(text_output)
                                print(f"    [DEBUG] Saved {target_lang} translated SRT to {debug_path}")
                            except Exception as io_err:
                                pass

                        elif "format_srt" in task_id:
                            srt_path = os.path.join(self.SAMBA_PATH, f"subtitles_{target_lang}.srt")
                            try:
                                with open(srt_path, "w", encoding="utf-8") as f:
                                    f.write(text_output)
                            except Exception as io_err:
                                print(f"  [!] Failed to write {srt_path}: {io_err}")

                    elif "tts" in task_id:
                        self.shared_memory[task_id] = result.get("path", "success")

                    else:
                        self.shared_memory[task_id] = result.get("output_pointer", "success")

                    print(f"  <- [Finished] '{task_id}' on {target_node}")
                else:
                    error_data = await response.text()
                    print(f"  [!] Task '{task_id}' FAILED on {target_node} ({response.status}): {error_data}")
                    self.pipeline_failed = True

        except Exception as e:
            print(f"  [!] Network/Execution Error on '{task_id}': {e}")
            self.pipeline_failed = True

    async def execute_manifest(self, manifest: dict):
        async with aiohttp.ClientSession() as session:
            for tier_plan in manifest.get("execution_plan", []):
                if self.pipeline_failed:
                    print(f"\n[!] Aborting Tier {tier_plan['tier']} due to critical failure in previous sequence.")
                    break

                tier_idx = tier_plan["tier"]
                print(f"\n=== Executing Tier {tier_idx} ===")
                
                coroutines = [self.dispatch_task(session, task) for task in tier_plan["parallel_tasks"]]
                await asyncio.gather(*coroutines)

            if not self.pipeline_failed:
                print("\n[Orchestrator] All workflow tiers executed successfully.")
            else:
                print("\n[Orchestrator] Pipeline execution HALTED due to errors.")
