"""WebSocket connection manager for the AI Native game engine."""

from fastapi import WebSocket, WebSocketDisconnect
from typing import Dict, Any, Optional
import logging

# Import websockets exception for graceful handling of abrupt disconnections
try:
    from websockets.exceptions import ConnectionClosedError, ConnectionClosedOK
except ImportError:
    # Fallback if websockets is not installed (shouldn't happen with starlette)
    ConnectionClosedError = Exception
    ConnectionClosedOK = Exception

logger = logging.getLogger(__name__)


class WebSocketManager:
    """Manager for WebSocket connections."""
    
    def __init__(self):
        """Initialize the WebSocket manager."""
        self.player_connections: Dict[str, WebSocket] = {}

    async def connect(self, websocket: WebSocket, player_id: str):
        """Connect a WebSocket.
        
        Args:
            websocket (WebSocket): The WebSocket to connect.
            player_id (str): The ID of the player.
        """
        self.player_connections[player_id] = websocket
        logger.info(f"New WebSocket connection for player {player_id}. Total connections: {len(self.player_connections)}")

    def disconnect(self, player_id: str):
        """Disconnect a WebSocket.
        
        Args:
            player_id (str): The ID of the player to disconnect.
        """
        if player_id in self.player_connections:
            del self.player_connections[player_id]
            logger.info(f"WebSocket for player {player_id} disconnected. Remaining connections: {len(self.player_connections)}")

    async def broadcast_to_session(
        self, 
        session_id: str, 
        message: Dict[str, Any], 
        player_sessions: Dict[str, Any], 
        exclude_player_id: Optional[str] = None
    ):
        """Broadcast a message to all players in a specific session.
        
        Args:
            session_id: The session to broadcast to.
            message: The message to send.
            player_sessions: Dict mapping player IDs to session data.
            exclude_player_id: Optional player ID to exclude from broadcast.
        """
        for player_id, session_data in player_sessions.items():
            if session_data.get("session_id") == session_id and player_id != exclude_player_id:
                websocket = self.player_connections.get(player_id)
                if websocket:
                    if websocket.client_state == 2:  # WebSocketState.DISCONNECTED
                        continue
                    try:
                        await websocket.send_json(message)
                    except (RuntimeError, WebSocketDisconnect, ConnectionClosedError, ConnectionClosedOK) as e:
                        logger.debug(f"Failed to send message to player {player_id} (disconnected): {e}")
                    except Exception as e:
                        logger.warning(f"Failed to send message to player {player_id}: {e}")

    async def broadcast_to_all(self, message: Dict[str, Any]):
        """Broadcast a message to all connected WebSockets.
        
        Args:
            message: The message to send.
        """
        for websocket in self.player_connections.values():
            if websocket.client_state == 2:  # WebSocketState.DISCONNECTED
                continue
            try:
                await websocket.send_json(message)
            except (RuntimeError, WebSocketDisconnect, ConnectionClosedError, ConnectionClosedOK) as e:
                logger.debug(f"Failed to send message to a WebSocket (disconnected): {e}")
            except Exception as e:
                logger.warning(f"Failed to send message to a WebSocket: {e}")

    async def send_to_player(self, player_id: str, message: Dict[str, Any]) -> bool:
        """Send a message to a specific player.
        
        Args:
            player_id: The player to send to.
            message: The message to send.
            
        Returns:
            True if sent successfully, False otherwise.
        """
        websocket = self.player_connections.get(player_id)
        if websocket and websocket.client_state != 2:
            try:
                await websocket.send_json(message)
                return True
            except (RuntimeError, WebSocketDisconnect, ConnectionClosedError, ConnectionClosedOK) as e:
                logger.debug(f"Failed to send message to player {player_id} (disconnected): {e}")
            except Exception as e:
                logger.warning(f"Error sending message to player {player_id}: {e}")
        return False

    def get_websocket(self, player_id: str) -> Optional[WebSocket]:
        """Get the WebSocket for a player.
        
        Args:
            player_id: The player ID.
            
        Returns:
            The WebSocket if connected, None otherwise.
        """
        return self.player_connections.get(player_id)

    def is_connected(self, player_id: str) -> bool:
        """Check if a player is connected.
        
        Args:
            player_id: The player ID.
            
        Returns:
            True if connected, False otherwise.
        """
        websocket = self.player_connections.get(player_id)
        return websocket is not None and websocket.client_state != 2

