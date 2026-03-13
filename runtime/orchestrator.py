import asyncio
import aiohttp
import os
import re

class ExecutionEngine:
    def __init__(self, node_endpoints: dict):
        self.node_endpoints = node_endpoints
        self.shared_memory = {}
        self.pipeline_failed = False

    def _resolve_payload(self, payload_template: dict):
        """Recursively injects shared_memory dependencies into the payload template."""
        resolved = {}
        for k, v in payload_template.items():
            if isinstance(v, str):
                # Regex find-and-replace for ANY {dep:task_id} inside the string
                matches = re.findall(r'\{dep:(.*?)\}', v)
                resolved_str = v
                for dep_key in matches:
                    memory_val = str(self.shared_memory.get(dep_key, ""))
                    resolved_str = resolved_str.replace(f"{{dep:{dep_key}}}", memory_val)
                resolved[k] = resolved_str

            elif isinstance(v, list):
                resolved_list = []
                for item in v:
                    if isinstance(item, dict):
                        resolved_list.append(self._resolve_payload(item))
                    else:
                        resolved_list.append(item)
                resolved[k] = resolved_list
            elif isinstance(v, dict):
                resolved[k] = self._resolve_payload(v)
            else:
                resolved[k] = v
        return resolved

    def _extract_json_path(self, data, path: str):
        """Extracts nested data using dot notation (e.g., 'choices.0.message.content')."""
        keys = path.split('.')
        val = data
        try:
            for key in keys:
                if key.isdigit() and isinstance(val, list):
                    val = val[int(key)]
                else:
                    val = val[key]
            return str(val).strip()
        except (KeyError, IndexError, TypeError):
            return str(data)

    async def dispatch_task(self, session: aiohttp.ClientSession, task: dict):
        if self.pipeline_failed: return

        task_id = task.get("task_id")
        target_node = task.get("target_node")

        # 1. Generic Endpoint Resolution
        action_payload = task.get("action_payload", {})
        override_node = action_payload.pop("override_endpoint", target_node)
        endpoint_suffix = action_payload.pop("endpoint_suffix", "")

        base_url = self.node_endpoints.get(override_node)
        actual_url = f"{base_url}{endpoint_suffix}"

        print(f"  -> [Dispatching] '{task_id}' to {override_node}")

        # 2. Dependency Injection
        payload = self._resolve_payload(action_payload)

        # 3. Execution Block
        try:
            async with session.post(actual_url, json=payload, timeout=300) as response:
                if response.status == 200:
                    result = await response.json()
                    handlers = task.get("output_handlers", {})

                    # Generic Response Parsing
                    json_path = handlers.get("json_path", "")
                    extracted_value = self._extract_json_path(result, json_path) if json_path else str(result)

                    memory_key = handlers.get("memory_key", task_id)
                    self.shared_memory[memory_key] = extracted_value

                    # Generic File I/O
                    for key, file_path in handlers.items():
                        if key.startswith("save_file"):
                            try:
                                with open(file_path, "w", encoding="utf-8") as f:
                                    f.write(extracted_value)
                            except Exception as io_err:
                                print(f"  [!] Disk IO Error on {file_path}: {io_err}")

                    print(f"  <- [Finished] '{task_id}'")
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
                    print(f"\n[!] Aborting Tier {tier_plan['tier']} due to previous failures.")
                    break

                print(f"\n=== Executing Tier {tier_plan['tier']} ===")
                coroutines = [self.dispatch_task(session, task) for task in tier_plan["parallel_tasks"]]
                await asyncio.gather(*coroutines)

            if not self.pipeline_failed:
                print("\n[Orchestrator] All workflow tiers executed successfully.")
