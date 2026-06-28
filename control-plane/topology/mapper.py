from typing import List
from dataclasses import dataclass

try:
    from herdmaster.config import AclRole, AclConfig
except ImportError:
    # Mock fallback for typing if herdmaster is not in PYTHONPATH
    @dataclass
    class AclRole:
        name: str
        agents: List[str]
        can_send_to: List[str]
        can_receive_from: List[str]
        can_dispatch_tasks: bool = False
        can_reassign_tasks: bool = False

    @dataclass
    class AclConfig:
        default_policy: str
        roles: List[AclRole]

@dataclass
class CanvasNode:
    id: str
    role: str # "orchestrator" (Tech-Lead), "worker", "peer_reviewer"

@dataclass
class CanvasEdge:
    source: str
    target: str

class TopologyValidator:
    @staticmethod
    def validate(nodes: List[CanvasNode], edges: List[CanvasEdge]):
        if len(nodes) <= 1:
            return
            
        connected_nodes = set()
        for e in edges:
            connected_nodes.add(e.source)
            connected_nodes.add(e.target)
            
        for n in nodes:
            if n.role == "worker" and n.id not in connected_nodes:
                raise ValueError(f"Invalid topology: worker {n.id} is unreachable")

class TopologyMapper:
    @staticmethod
    def map_to_acl(nodes: List[CanvasNode], edges: List[CanvasEdge]) -> AclConfig:
        TopologyValidator.validate(nodes, edges)
        
        roles_list = []
        # Create a specific role per node to respect precise canvas edges
        for node in nodes:
            can_send_to = []
            can_receive_from = []
            for edge in edges:
                if edge.source == node.id:
                    can_send_to.append(edge.target)
                if edge.target == node.id:
                    can_receive_from.append(edge.source)
                    
            role_name = f"role_{node.id}_{node.role}"
            is_tl = (node.role == "orchestrator")
            
            roles_list.append(AclRole(
                name=role_name,
                agents=[node.id],
                can_send_to=can_send_to,
                can_receive_from=can_receive_from,
                can_dispatch_tasks=is_tl,
                can_reassign_tasks=is_tl
            ))
            
        return AclConfig(
            default_policy="deny",
            roles=roles_list
        )
