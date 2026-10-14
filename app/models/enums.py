import enum


class EstadoOnboarding(str, enum.Enum):
    """Estado del flujo de triage inicial."""
    EN_CURSO = "EN_CURSO"
    FINALIZADO = "FINALIZADO"


class ModoAtencion(str, enum.Enum):
    """Quién está atendiendo esta conversación ahora mismo."""
    IA = "ia"
    HUMANO = "humano"
    PAUSADO = "pausado"


class TipoMensaje(str, enum.Enum):
    """Quién envió este mensaje."""
    CLIENTE = "cliente"
    IA = "ia"
    HUMANO = "humano"
    SISTEMA = "sistema"


class TipoContenido(str, enum.Enum):
    """Qué tipo de contenido tiene el mensaje."""
    TEXTO = "texto"
    AUDIO = "audio"
    IMAGEN = "imagen"
    DOCUMENTO = "documento"


class CanalOrigen(str, enum.Enum):
    """De qué plataforma viene el mensaje."""
    TELEGRAM = "telegram"
    WHATSAPP = "whatsapp"
    FACEBOOK = "facebook"
    INSTAGRAM = "instagram"
    WEB = "web"
