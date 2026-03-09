import asyncio
import aiohttp

class ExecutionEngine:
    def __init__(self, node_endpoints: dict):
        self.node_endpoints = node_endpoints
        self.shared_memory = {} 

    async def dispatch_task(self, session: aiohttp.ClientSession, task: dict):
        task_id = task["task_id"]
        compute_type = task["compute_type"]
        target_node = task["target_node"]
        endpoint_url = self.node_endpoints.get(target_node)

        print(f"  -> [Dispatching] '{task_id}' to {target_node}")

        if compute_type in ["llm_heavy", "ai_inference_light"]:
            transcript = self.shared_memory.get("transcribe_eng", "[Simulated English Transcript]")
            payload = {
                "model": "meta-llama/Llama-3-8b-instruct",
                "prompt": f"<system>Translate to {task.get('target_lang')}</system>\n<text>{transcript}</text>",
                "max_tokens": 1024
            }
        else:
            # Edge Node Payload (Requires target_lang and input_file)
            payload = {
                "action": task_id,
                "input_file": "source_video.mp4",
                "target_lang": task.get("target_lang"),
                "llm_text_data": self.shared_memory.get(f"translate_{task.get('target_lang')}", "dummy_data")
            }

        try:
            # IN PRODUCTION:
            # async with session.post(endpoint_url, json=payload) as response:
            #     result = await response.json()
            
            await asyncio.sleep(1.5) 
            self.shared_memory[task_id] = f"Completed output of {task_id}"
            print(f"  <- [Finished] '{task_id}' on {target_node}")
            
        except Exception as e:
            print(f"  [!] Task '{task_id}' failed: {e}")

    async def execute_manifest(self, manifest: dict):
        async with aiohttp.ClientSession() as session:
            for tier_plan in manifest.get("execution_plan", []):
                tier_idx = tier_plan["tier"]
                print(f"\n=== Executing Tier {tier_idx} ===")
                
                coroutines = [self.dispatch_task(session, task) for task in tier_plan["parallel_tasks"]]
                await asyncio.gather(*coroutines)
                
            print("\n[Orchestrator] All workflow tiers executed successfully.")
