from typing import List, Dict, Set
from .models import Task, HardwareNode

class AgenticCompiler:
    def __init__(self, hardware_registry: List[HardwareNode]):
        self.hardware_registry = hardware_registry

    def _extract_parallel_tiers(self, tasks: Dict[str, Task]) -> List[List[str]]:
        resolved: Set[str] = set()
        tiers: List[List[str]] = []
        remaining: Set[str] = set(tasks.keys())
        
        while remaining:
            current_tier = []
            for task_id in remaining:
                if all(dep in resolved for dep in tasks[task_id].deps):
                    current_tier.append(task_id)
            
            if not current_tier:
                raise ValueError("Cycle detected in Agent DAG! Deadlock imminent.")
                
            tiers.append(current_tier)
            resolved.update(current_tier)
            remaining.difference_update(current_tier)
            
        return tiers

    def compile(self, tasks: Dict[str, Task]) -> Dict:
        parallel_tiers = self._extract_parallel_tiers(tasks)
        manifest = {"execution_plan": []}
        
        for tier_index, tier_task_ids in enumerate(parallel_tiers):
            scheduled_tasks = []
            
            # Reset hardware availability for the new tier
            for node in self.hardware_registry:
                node.is_available = True

            for task_id in tier_task_ids:
                task = tasks[task_id]
                
                # Find first available compatible node
                assigned_node = next(
                    (n.id for n in self.hardware_registry if n.is_available and task.compute_type in n.supported_types),
                    None
                )
                
                if not assigned_node:
                    raise RuntimeError(f"No hardware found for task '{task_id}'")
                    
                # Mark node as busy
                for node in self.hardware_registry:
                    if node.id == assigned_node:
                        node.is_available = False
                        break

                scheduled_tasks.append({
                    "task_id": task.id,
                    "compute_type": task.compute_type,
                    "target_node": assigned_node,
                    "target_lang": task.target_lang
                })
                
            manifest["execution_plan"].append({
                "tier": tier_index,
                "parallel_tasks": scheduled_tasks
            })
            
        return manifest
