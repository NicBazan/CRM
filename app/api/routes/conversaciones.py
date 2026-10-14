from fastapi import APIRouter, Depends, HTTPException, WebSocket, WebSocketDisconnect
from sqlalchemy.orm import Session
from app.api.deps import get_db
from app.models.conversacion import Conversacion
from app.models.mensaje import Mensaje
from app.models.enums import ModoAtencion, TipoMensaje, TipoContenido, CanalOrigen
from app.schemas.conversacion import ConversacionResponse, HandoffRequest, RespuestaHumana
from app.schemas.mensaje import MensajeResponse
from app.channels.dispatcher import dispatcher
from app.channels.whatsapp import FueraDeVentana24HorasError
from app.channels.base import MensajeSaliente
from app.services.notificacion_service import manager, NotificacionService

router = APIRouter(prefix="/conversaciones", tags=["Conversaciones"])


@router.get("/", response_model=list[ConversacionResponse])
def listar_conversaciones(db: Session = Depends(get_db)):
    """Lista todas las conversaciones activas, ordenadas por último mensaje."""
    return (
        db.query(Conversacion)
        .filter(Conversacion.activa == True)
        .order_by(Conversacion.fecha_ultimo_mensaje.desc())
        .all()
    )


@router.get("/{conv_id}", response_model=ConversacionResponse)
def obtener_conversacion(conv_id: int, db: Session = Depends(get_db)):
    """Obtiene los datos de una conversación."""
    conv = db.query(Conversacion).get(conv_id)
    if not conv:
        raise HTTPException(status_code=404, detail="Conversación no encontrada")
    return conv


@router.get("/{conv_id}/mensajes", response_model=list[MensajeResponse])
def ver_mensajes(conv_id: int, db: Session = Depends(get_db)):
    """Obtiene el historial completo de mensajes de una conversación."""
    return (
        db.query(Mensaje)
        .filter(Mensaje.conversacion_id == conv_id)
        .order_by(Mensaje.fecha_creacion.asc())
        .all()
    )


# ================================================
# HANDOFF: Tomar o devolver el control
# ================================================
@router.put("/{conv_id}/handoff")
async def cambiar_modo_atencion(
    conv_id: int,
    request: HandoffRequest,
    db: Session = Depends(get_db),
):
    """
    Cambia quién atiende la conversación.
    - modo: "ia" → la IA retoma el control
    - modo: "humano" → el gerente toma el control
    - modo: "pausado" → nadie responde
    """
    conv = db.query(Conversacion).get(conv_id)
    if not conv:
        raise HTTPException(status_code=404, detail="Conversación no encontrada")

    modo_anterior = conv.modo_atencion
    conv.modo_atencion = request.modo
    db.commit()

    # Notificar cambio por WebSocket
    notificacion = NotificacionService()
    await notificacion.handoff_cambio(
        conv_id,
        modo_anterior=modo_anterior.value,
        modo_nuevo=request.modo.value,
    )

    return {
        "status": "ok",
        "modo_anterior": modo_anterior.value,
        "modo_atencion": request.modo.value,
    }


# ================================================
# RESPONDER MANUALMENTE (como humano)
# ================================================
@router.post("/{conv_id}/responder")
async def responder_como_humano(
    conv_id: int,
    respuesta: RespuestaHumana,
    db: Session = Depends(get_db),
):
    """
    Permite al gerente enviar un mensaje manual al cliente.
    El mensaje se guarda en la DB y se envía por el canal correspondiente.
    """
    conv = db.query(Conversacion).get(conv_id)
    if not conv:
        raise HTTPException(status_code=404, detail="Conversación no encontrada")

    # Guardar en DB
    msg = Mensaje(
        conversacion_id=conv_id,
        tipo_mensaje=TipoMensaje.HUMANO,
        tipo_contenido=TipoContenido.TEXTO,
        contenido=respuesta.texto,
    )
    db.add(msg)
    db.commit()
    db.refresh(msg)

    # Enviar al cliente a través del Dispatcher multicanal
    try:
        enviado = await dispatcher.dispatch_saliente(
            canal=conv.canal,
            mensaje=MensajeSaliente(id_destino=conv.id_externo, texto=respuesta.texto),
        )
        if not enviado:
            raise HTTPException(
                status_code=502,
                detail=f"No se pudo despachar el mensaje al canal {conv.canal.value}",
            )
    except FueraDeVentana24HorasError as e:
        raise HTTPException(
            status_code=409,
            detail={
                "code": "VENTANA_24H_EXPIRADA",
                "message": str(e),
            },
        )

    # Notificar al panel React
    notificacion = NotificacionService()
    await notificacion.nuevo_mensaje(conv_id, msg)

    return {"status": "enviado", "mensaje_id": msg.id}


# ================================================
# WEBSOCKET: Conexión en tiempo real
# ================================================
@router.websocket("/ws")
async def websocket_global(websocket: WebSocket):
    """WebSocket global — recibe notificaciones de TODAS las conversaciones."""
    await manager.connect(websocket)
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        manager.disconnect(websocket)


@router.websocket("/ws/{conv_id}")
async def websocket_conversacion(websocket: WebSocket, conv_id: int):
    """WebSocket por conversación — recibe notificaciones de UNA conversación."""
    await manager.connect(websocket, conv_id)
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        manager.disconnect(websocket, conv_id)
