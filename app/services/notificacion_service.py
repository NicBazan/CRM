import json
from fastapi import WebSocket


class ConnectionManager:
    """
    Gestiona conexiones WebSocket agrupadas por conversación.
    Permite push en tiempo real al panel de React.
    """

    def __init__(self):
        # { conv_id: [websocket1, websocket2, ...] }
        self.active_connections: dict[int, list[WebSocket]] = {}
        # Conexiones globales (escuchan todas las conversaciones)
        self.global_connections: list[WebSocket] = []

    async def connect(self, websocket: WebSocket, conv_id: int | None = None):
        """Acepta una conexión WebSocket, opcionalmente asociada a una conversación."""
        await websocket.accept()
        if conv_id is not None:
            if conv_id not in self.active_connections:
                self.active_connections[conv_id] = []
            self.active_connections[conv_id].append(websocket)
        else:
            self.global_connections.append(websocket)

    def disconnect(self, websocket: WebSocket, conv_id: int | None = None):
        """Remueve una conexión WebSocket."""
        if conv_id is not None and conv_id in self.active_connections:
            self.active_connections[conv_id] = [
                ws for ws in self.active_connections[conv_id] if ws != websocket
            ]
        elif websocket in self.global_connections:
            self.global_connections.remove(websocket)

    async def broadcast(self, conv_id: int, data: dict):
        """Envía un mensaje a todas las conexiones escuchando esta conversación + globales."""
        mensaje_json = json.dumps(data, default=str)

        # Enviar a conexiones de esta conversación específica
        connections = self.active_connections.get(conv_id, [])
        for ws in connections.copy():
            try:
                await ws.send_text(mensaje_json)
            except Exception:
                self.disconnect(ws, conv_id)

        # Enviar a conexiones globales
        for ws in self.global_connections.copy():
            try:
                await ws.send_text(mensaje_json)
            except Exception:
                self.disconnect(ws)


# Instancia global (singleton)
manager = ConnectionManager()


class NotificacionService:
    """Servicio para notificar al panel React sobre nuevos mensajes y cambios."""

    async def nuevo_mensaje(self, conv_id: int, mensaje):
        """Notifica que llegó un nuevo mensaje en una conversación."""
        await manager.broadcast(conv_id, {
            "tipo": "mensaje",
            "conversacion_id": conv_id,
            "mensaje": {
                "id": mensaje.id,
                "tipo_mensaje": mensaje.tipo_mensaje.value,
                "tipo_contenido": mensaje.tipo_contenido.value,
                "contenido": mensaje.contenido,
                "fecha_creacion": str(mensaje.fecha_creacion),
            },
        })

    async def handoff_cambio(self, conv_id: int, modo_anterior: str, modo_nuevo: str):
        """Notifica que cambió el modo de atención de una conversación."""
        await manager.broadcast(conv_id, {
            "tipo": "handoff",
            "conversacion_id": conv_id,
            "modo_anterior": modo_anterior,
            "modo_nuevo": modo_nuevo,
        })
