import asyncio
import logging
import json
from typing import Dict, Set, Optional
from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Query

logger = logging.getLogger("websocket.manager")

class ConnectionManager:
    """
    Stateful real-time connection broker managing massive concurrent WebSockets, 
    isolating channels via Rooms, Tenants, and targeted User IDs.
    """
    def __init__(self):
        # Central metadata mapping: WebSocket -> {user_id, tenant_id, set(rooms)}
        self.active_connections: Dict[WebSocket, dict] = {}
        
        # Granular indices for extremely fast message routing O(1) lookups
        self.tenants: Dict[str, Set[WebSocket]] = {}
        self.users: Dict[str, Set[WebSocket]] = {}
        self.rooms: Dict[str, Set[WebSocket]] = {
            "provisioning": set(),
            "topology": set(),
            "health": set()
        }

    async def connect(self, websocket: WebSocket, user_id: str, tenant_id: str):
        """Initializes and scopes a new inbound real-time connection."""
        await websocket.accept()
        
        # Initialize central metadata map
        self.active_connections[websocket] = {
            "user_id": user_id,
            "tenant_id": tenant_id,
            "rooms": set()
        }
        
        # Index strictly by tenant
        if tenant_id not in self.tenants:
            self.tenants[tenant_id] = set()
        self.tenants[tenant_id].add(websocket)
        
        # Index strictly by user
        if user_id not in self.users:
            self.users[user_id] = set()
        self.users[user_id].add(websocket)
        
        logger.debug(f"User {user_id} (Tenant: {tenant_id}) connected via WebSocket.")

    def disconnect(self, websocket: WebSocket):
        """Prunes a dropped or closed connection efficiently across all lookup graphs."""
        if websocket not in self.active_connections:
            return
            
        metadata = self.active_connections.pop(websocket)
        user_id = metadata["user_id"]
        tenant_id = metadata["tenant_id"]
        rooms = metadata["rooms"]
        
        # Unlink from tenant index
        if tenant_id in self.tenants:
            self.tenants[tenant_id].discard(websocket)
            if not self.tenants[tenant_id]:
                del self.tenants[tenant_id]
                
        # Unlink from user index
        if user_id in self.users:
            self.users[user_id].discard(websocket)
            if not self.users[user_id]:
                del self.users[user_id]
                
        # Unlink cleanly from active rooms
        for room in rooms:
            if room in self.rooms:
                self.rooms[room].discard(websocket)

        logger.debug(f"WebSocket closed gracefully for User {user_id}.")

    async def subscribe_to_room(self, websocket: WebSocket, room: str):
        """Opt-in mechanism binding a connection to a broadcast channel."""
        if websocket not in self.active_connections:
            return
            
        # Dynamically instantiate room if not rigidly predefined
        if room not in self.rooms:
            self.rooms[room] = set()
            
        self.rooms[room].add(websocket)
        self.active_connections[websocket]["rooms"].add(room)
        logger.debug(f"Socket securely bound to room target: {room}")

    async def unsubscribe_from_room(self, websocket: WebSocket, room: str):
        """Opt-out mechanism tearing down channel bindings."""
        if websocket in self.active_connections:
            self.active_connections[websocket]["rooms"].discard(room)
        if room in self.rooms:
            self.rooms[room].discard(websocket)

    async def _safe_dispatch(self, sockets: Set[WebSocket], payload: str):
        """Internal helper firing async pushes whilst pruning silently dead peers."""
        dead_sockets = set()
        
        # Copy to list to avoid runtime mutation exceptions while iterating
        for ws in list(sockets):
            try:
                await ws.send_text(payload)
            except Exception:
                dead_sockets.add(ws)
                
        # Safely evict zombies bypassing disconnect graph tracking constraints
        for ws in dead_sockets:
            self.disconnect(ws)

    async def broadcast(self, message: dict, room: Optional[str] = None):
        """
        Dispatches payload globally, or scopes the payload heavily to a specific room.
        Rooms commonly utilized: 'provisioning', 'topology', 'health'.
        """
        payload = json.dumps(message)
        targets = self.rooms.get(room, set()) if room else set(self.active_connections.keys())
        await self._safe_dispatch(targets, payload)

    async def send_to_tenant(self, tenant_id: str, message: dict):
        """Dispatches payload targeted strictly at users authenticated to a tenant scope."""
        if tenant_id not in self.tenants:
            return
            
        payload = json.dumps(message)
        await self._safe_dispatch(self.tenants[tenant_id], payload)

    async def send_to_user(self, user_id: str, message: dict):
        """Dispatches a highly localized direct payload to a specific user session."""
        if user_id not in self.users:
            return
            
        payload = json.dumps(message)
        await self._safe_dispatch(self.users[user_id], payload)


# Instantiate centralized Singleton broker
manager = ConnectionManager()
router = APIRouter(prefix="/ws", tags=["websocket"])

@router.websocket("/events")
async def websocket_endpoint(
    websocket: WebSocket, 
    user_id: str = Query(..., description="The requesting user identity binding"), 
    tenant_id: str = Query(..., description="The logical tenant grouping isolation boundary")
):
    """
    Main WebSocket ingestion terminus mapping bidirectional logic.
    Supports in-flight `subscribe` channels and maintains `ping` health checks natively.
    """
    await manager.connect(websocket, user_id, tenant_id)
    
    try:
        while True:
            # Non-blocking yield awaiting client directives
            data = await websocket.receive_text()
            
            try:
                payload = json.loads(data)
                action = payload.get("action")
                
                # Bi-directional control logic routing
                if action == "subscribe":
                    room = payload.get("room")
                    if room:
                        await manager.subscribe_to_room(websocket, room)
                        await websocket.send_text(json.dumps({"event": "subscribed", "room": room}))
                
                elif action == "unsubscribe":
                    room = payload.get("room")
                    if room:
                        await manager.unsubscribe_from_room(websocket, room)
                        
                elif action == "ping":
                    # Connection keep-alive heartbeat logic
                    await websocket.send_text(json.dumps({"event": "pong"}))
                    
            except json.JSONDecodeError:
                # Silently drop invalid malformed JSON frames to prevent thread panics
                logger.debug(f"Dropped malformed WebSocket frame from {user_id}")
                pass
                
    except WebSocketDisconnect:
        manager.disconnect(websocket)
    except Exception as e:
        logger.error(f"WebSocket fatal execution abort for {user_id}: {e}")
        manager.disconnect(websocket)
