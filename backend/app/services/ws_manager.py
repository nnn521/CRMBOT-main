from fastapi import WebSocket
from typing import Dict, List
import logging
from datetime import datetime, timezone
from uuid import uuid4

logger = logging.getLogger(__name__)

class ConnectionManager:
    def __init__(self):
        # session_id -> list of connected websockets
        self.active_connections: Dict[str, List[WebSocket]] = {}

    async def connect(self, websocket: WebSocket, session_id: str):
        await websocket.accept()
        if session_id not in self.active_connections:
            self.active_connections[session_id] = []
        self.active_connections[session_id].append(websocket)
        logger.info("[WS-CONNECT] session=%s total=%s clients_here=%s",
                    session_id, len(self.active_connections), len(self.active_connections[session_id]))

    def disconnect(self, websocket: WebSocket, session_id: str):
        # safe remove with try/except for ValueError
        if session_id in self.active_connections:
            try:
                self.active_connections[session_id].remove(websocket)
            except ValueError:
                pass  # already disconnected
            if not self.active_connections[session_id]:
                del self.active_connections[session_id]

    async def _send_to_all(self, connections: List[WebSocket], session_id: str, event: dict) -> None:
        """发送事件并清理发送失败的陈旧连接。"""
        stale = []
        for ws in connections:
            try:
                await ws.send_json(event)
            except Exception as e:
                stale.append(ws)
                logger.warning("[WS] send failed: %s", e)
        for ws in stale:
            self.disconnect(ws, session_id)

    async def broadcast_to_session(self, session_id: str, message: dict):
        """Send message to all clients watching this session"""
        event = {
            "event_id": message.get("event_id") or str(uuid4()),
            "timestamp": message.get("timestamp") or datetime.now(timezone.utc).isoformat(),
            **message,
        }
        connections = list(self.active_connections.get(session_id, []))
        logger.info(
            "[WS-BROADCAST] channel=%s type=%s message_id=%s clients=%s",
            session_id,
            event.get("type"),
            (event.get("message") or {}).get("id"),
            len(connections),
        )
        await self._send_to_all(connections, session_id, event)

    async def broadcast_event(self, event_type: str, data: dict):
        """Broadcast to ALL connected clients (for session list updates)."""
        # 快照遍历 + 失败清理（修复：不再遗留死连接）
        for session_id, connections in list(self.active_connections.items()):
            event = {"type": event_type, **data}
            await self._send_to_all(list(connections), session_id, event)

manager = ConnectionManager()
