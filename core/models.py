class HardwareNode:
    def __init__(self, node_id: str, supported_compute_types: list):
        self.node_id = node_id
        # e.g., ["llm_heavy", "ai_inference_light", "io_bound"]
        self.supported_compute_types = supported_compute_types

class Task:
    def __init__(self, task_id: str, compute_type: str, deps: list = None, action_payload: dict = None, output_handlers: dict = None):
        self.task_id = task_id
        self.compute_type = compute_type
        self.deps = deps or []

        # The generic HTTP payload envelope. Domain logic (like target_lang) goes here.
        self.action_payload = action_payload or {}

        # Generic instructions for the orchestrator (where to save memory/files)
        self.output_handlers = output_handlers or {}
