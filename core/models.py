from dataclasses import dataclass, field
from typing import List

@dataclass
class Task:
    id: str
    compute_type: str  
    deps: List[str] = field(default_factory=list)
    target_lang: str = None  

@dataclass
class HardwareNode:
    id: str
    supported_types: List[str]
    is_available: bool = True
