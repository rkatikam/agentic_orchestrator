class AgenticCompiler:
    def __init__(self, hardware_registry: list):
        self.hardware_registry = hardware_registry

    def _assign_node(self, compute_type: str) -> str:
        """Finds the first available node that supports the required compute_type."""
        for node in self.hardware_registry:
            if compute_type in node.supported_compute_types:
                return node.node_id
        raise ValueError(f"No hardware node available for compute_type: {compute_type}")

    def compile(self, workflow: dict) -> dict:
        """Transforms a raw workflow dictionary into a structured execution manifest."""
        in_degree = {task_id: 0 for task_id in workflow}
        adj_list = {task_id: [] for task_id in workflow}

        # Build graph and count in-degrees
        for task_id, task in workflow.items():
            for dep in task.deps:
                adj_list[dep].append(task_id)
                in_degree[task_id] += 1

        # Kahn's Algorithm for Topological Sort into Tiers
        queue = [t_id for t_id in workflow if in_degree[t_id] == 0]
        execution_plan = []
        tier_idx = 0

        while queue:
            next_queue = []
            tier_tasks = []

            for task_id in queue:
                task = workflow[task_id]

                # Hardware routing assignment
                assigned_node = self._assign_node(task.compute_type)

                # Convert the object into a pure dictionary for the Orchestrator
                tier_tasks.append({
                    "task_id": task.task_id,
                    "compute_type": task.compute_type,
                    "target_node": assigned_node,
                    "action_payload": task.action_payload,
                    "output_handlers": task.output_handlers
                })

                for neighbor in adj_list[task_id]:
                    in_degree[neighbor] -= 1
                    if in_degree[neighbor] == 0:
                        next_queue.append(neighbor)

            execution_plan.append({
                "tier": tier_idx,
                "parallel_tasks": tier_tasks
            })
            queue = next_queue
            tier_idx += 1

        if sum(in_degree.values()) > 0:
            raise ValueError("Circular dependency detected in workflow graph.")

        return {"execution_plan": execution_plan}
