"""
Endpoints de desarrollo y testing.
Permite probar el flujo completo del agente IA sin necesidad de Telegram/Ngrok.

⚠️ Estos endpoints son SOLO para desarrollo. En producción deben deshabilitarse.
"""
import logging
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from pydantic import BaseModel
from app.api.deps import get_db
from app.core.config import get_settings
from app.models.documento_conocimiento import DocumentoConocimiento
from app.models.conversacion import Conversacion
from app.models.cliente import Cliente
from app.models.mensaje import Mensaje
from app.models.enums import (
    ModoAtencion,
    CanalOrigen,
    TipoMensaje,
    TipoContenido,
)
from app.services.agente_ia_service import AgenteIAService
from app.services.conocimiento_service import ConocimientoService

logger = logging.getLogger(__name__)
settings = get_settings()

router = APIRouter(prefix="/dev", tags=["🔧 Desarrollo"])


# =====================================================
# 1. Probar el agente IA directamente
# =====================================================
class TestIARequest(BaseModel):
    """Request para probar el agente IA desde Swagger."""
    mensaje: str
    conversacion_id: int | None = None


class TestIAResponse(BaseModel):
    respuesta_ia: str
    conversacion_id: int
    contexto_rag_preview: str
    llm_provider: str


@router.post("/test-ia", response_model=TestIAResponse)
async def test_agente_ia(req: TestIARequest, db: Session = Depends(get_db)):
    """
    🧪 Prueba el agente IA directamente sin necesidad de Telegram.

    - Si no envías `conversacion_id`, crea una conversación de prueba.
    - Devuelve la respuesta de la IA y un preview del contexto RAG utilizado.
    """
    # Obtener o crear conversación de prueba
    if req.conversacion_id:
        conversacion = db.query(Conversacion).get(req.conversacion_id)
        if not conversacion:
            # Crear una nueva
            conversacion = None
    else:
        conversacion = None

    if not conversacion:
        # Crear cliente y conversación de prueba
        cliente = Cliente(nombre="Tester Swagger")
        db.add(cliente)
        db.flush()

        conversacion = Conversacion(
            cliente_id=cliente.id,
            canal=CanalOrigen.WEB,
            id_externo="swagger-test",
            modo_atencion=ModoAtencion.IA,
        )
        db.add(conversacion)
        db.commit()
        db.refresh(conversacion)

    # Guardar mensaje del "cliente" en la DB
    msg_cliente = Mensaje(
        conversacion_id=conversacion.id,
        tipo_mensaje=TipoMensaje.CLIENTE,
        tipo_contenido=TipoContenido.TEXTO,
        contenido=req.mensaje,
    )
    db.add(msg_cliente)
    db.commit()

    # Generar respuesta
    agente = AgenteIAService(db)
    conocimiento = ConocimientoService(db)

    contexto_rag = conocimiento.obtener_contexto_relevante(req.mensaje)
    respuesta = await agente.generar_respuesta(
        conversacion=conversacion,
        mensaje_actual=req.mensaje,
    )

    # Guardar respuesta de la IA
    msg_ia = Mensaje(
        conversacion_id=conversacion.id,
        tipo_mensaje=TipoMensaje.IA,
        tipo_contenido=TipoContenido.TEXTO,
        contenido=respuesta,
    )
    db.add(msg_ia)
    db.commit()

    return TestIAResponse(
        respuesta_ia=respuesta,
        conversacion_id=conversacion.id,
        contexto_rag_preview=contexto_rag[:500] + "..." if len(contexto_rag) > 500 else contexto_rag,
        llm_provider=settings.LLM_PROVIDER,
    )


# =====================================================
# 2. Seed de conocimiento del negocio
# =====================================================
DATOS_NEGOCIO = [
    {
        "titulo": "Servicios de Aire Acondicionado",
        "categoria": "servicios",
        "contenido": (
            "Ofrecemos los siguientes servicios de climatización:\n"
            "- Mantenimiento preventivo de aire acondicionado (limpieza de filtros, "
            "verificación de presiones, limpieza de serpentinas): desde $15.000.\n"
            "- Carga de gas refrigerante R410a: desde $25.000 (incluye diagnóstico).\n"
            "- Instalación de equipo split (hasta 4500 frigorías): desde $45.000 "
            "(no incluye el equipo).\n"
            "- Desinstalación y reinstalación (mudanza): desde $35.000.\n"
            "- Reparaciones varias (plaquetas, motores, compresores): presupuesto "
            "según diagnóstico.\n"
            "Duración estimada del mantenimiento: 1.5 a 2 horas por equipo."
        ),
    },
    {
        "titulo": "Servicios de Plomería",
        "categoria": "servicios",
        "contenido": (
            "Servicios de plomería general:\n"
            "- Destapaciones simples (baño, cocina): desde $8.000.\n"
            "- Destapaciones con máquina: desde $15.000.\n"
            "- Reparación de pérdidas de agua: desde $10.000.\n"
            "- Cambio de griferías y válvulas: desde $12.000 (mano de obra, "
            "materiales aparte).\n"
            "- Colocación de termotanques: desde $20.000.\n"
            "Todos los trabajos incluyen garantía de 90 días sobre la mano de obra."
        ),
    },
    {
        "titulo": "Horarios de Atención",
        "categoria": "operativa",
        "contenido": (
            "Horarios de atención al público:\n"
            "- Lunes a Viernes: 9:00 a 18:00 hs.\n"
            "- Sábados: 9:00 a 13:00 hs.\n"
            "- Domingos y feriados: NO trabajamos.\n"
            "- Emergencias fuera de horario: se puede coordinar con recargo "
            "del 50% sobre el valor del servicio.\n"
            "Los turnos se agendan con al menos 24 horas de anticipación."
        ),
    },
    {
        "titulo": "Zonas de Cobertura",
        "categoria": "operativa",
        "contenido": (
            "Zonas donde prestamos servicio:\n"
            "- CABA (Capital Federal): todas las zonas.\n"
            "- GBA Norte: Vicente López, San Isidro, San Fernando, Tigre.\n"
            "- GBA Oeste: Morón, Ituzaingó, Merlo, Moreno.\n"
            "- GBA Sur: consultar disponibilidad.\n"
            "Para zonas fuera de cobertura, podemos derivar a un técnico asociado."
        ),
    },
    {
        "titulo": "Métodos de Pago",
        "categoria": "operativa",
        "contenido": (
            "Formas de pago aceptadas:\n"
            "- Efectivo.\n"
            "- Transferencia bancaria / Mercado Pago.\n"
            "- Tarjeta de débito (en el domicilio con posnet).\n"
            "- Tarjeta de crédito: hasta 3 cuotas sin interés, "
            "6 y 12 cuotas con interés.\n"
            "El pago se realiza al finalizar el trabajo, "
            "una vez que el cliente confirme que está conforme."
        ),
    },
    {
        "titulo": "Política de Garantía",
        "categoria": "politicas",
        "contenido": (
            "Todos nuestros trabajos tienen 90 días de garantía sobre la mano de obra.\n"
            "La garantía cubre:\n"
            "- Defectos en la instalación o reparación realizada.\n"
            "- Revisión sin cargo si el problema persiste.\n"
            "La garantía NO cubre:\n"
            "- Daños por mal uso del equipo.\n"
            "- Problemas eléctricos del domicilio (baja tensión, etc.).\n"
            "- Desgaste natural de piezas.\n"
            "Para hacer uso de la garantía, contactarnos por este mismo chat "
            "o llamar al número que figura en la factura."
        ),
    },
    {
        "titulo": "Preguntas Frecuentes",
        "categoria": "faq",
        "contenido": (
            "P: ¿Cada cuánto hay que hacer mantenimiento al aire acondicionado?\n"
            "R: Se recomienda al menos 1 vez al año, idealmente antes del verano.\n\n"
            "P: ¿El técnico lleva los repuestos?\n"
            "R: Sí, los técnicos llevan los repuestos más comunes. Para piezas "
            "especiales, se coordina una segunda visita sin costo de viático.\n\n"
            "P: ¿Se puede agendar para un horario específico?\n"
            "R: Sí, manejamos turnos de mañana (9-13) y tarde (13-18). "
            "Se confirma franja horaria el día anterior.\n\n"
            "P: ¿Hacen presupuesto sin compromiso?\n"
            "R: El diagnóstico tiene un costo de $5.000 que se descuenta "
            "del valor del trabajo si se acepta el presupuesto."
        ),
    },
]


class SeedResponse(BaseModel):
    documentos_creados: int
    documentos_existentes: int
    total: int


@router.post("/seed-conocimiento", response_model=SeedResponse)
def seed_conocimiento_negocio(db: Session = Depends(get_db)):
    """
    🌱 Carga los datos de conocimiento del negocio de Ciclo Confort.

    Solo crea documentos que no existan (por título). Es seguro llamarlo múltiples veces.
    """
    creados = 0
    existentes = 0

    for dato in DATOS_NEGOCIO:
        existe = (
            db.query(DocumentoConocimiento)
            .filter(DocumentoConocimiento.titulo == dato["titulo"])
            .first()
        )
        if existe:
            existentes += 1
            continue

        doc = DocumentoConocimiento(**dato)
        db.add(doc)
        creados += 1

    db.commit()

    total = db.query(DocumentoConocimiento).filter(DocumentoConocimiento.activo == True).count()

    logger.info("Seed completado: %d creados, %d ya existían, %d total", creados, existentes, total)

    return SeedResponse(
        documentos_creados=creados,
        documentos_existentes=existentes,
        total=total,
    )


# =====================================================
# 3. Ver estado de la configuración
# =====================================================
@router.get("/config-status")
def ver_configuracion():
    """
    🔍 Muestra el estado de la configuración del sistema (sin exponer secretos).
    """
    return {
        "database_url": settings.DATABASE_URL.split("@")[-1] if "@" in settings.DATABASE_URL else settings.DATABASE_URL,
        "llm_provider": settings.LLM_PROVIDER,
        "gemini_api_key_configurada": bool(settings.GEMINI_API_KEY),
        "gemini_model": settings.GEMINI_MODEL,
        "openai_api_key_configurada": bool(settings.OPENAI_API_KEY),
        "openai_model": settings.OPENAI_MODEL,
        "telegram_token_configurado": bool(settings.TELEGRAM_BOT_TOKEN),
        "cors_origins": settings.CORS_ORIGINS,
    }
