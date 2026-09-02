"""
Servicio de conocimiento del negocio para RAG.

V1 (actual): Carga TODOS los documentos activos y los inyecta en el prompt.
    Funciona bien con <50 documentos cortos.

V2 (futuro): Embeddings vectoriales + búsqueda por similitud con pgvector.
"""
from sqlalchemy.orm import Session
from app.models.documento_conocimiento import DocumentoConocimiento


class ConocimientoService:
    def __init__(self, db: Session):
        self.db = db

    def obtener_contexto_relevante(self, consulta: str) -> str:
        """
        Devuelve el conocimiento del negocio formateado para inyectar en el prompt.

        Args:
            consulta: El texto del mensaje del cliente (para futuro filtrado por relevancia).

        Returns:
            Texto formateado con todos los documentos activos del negocio.
        """
        documentos = (
            self.db.query(DocumentoConocimiento)
            .filter(DocumentoConocimiento.activo == True)
            .order_by(DocumentoConocimiento.categoria)
            .all()
        )

        if not documentos:
            return "(No hay información del negocio cargada aún. Respondé de forma general.)"

        bloques = []
        for doc in documentos:
            categoria = f" [{doc.categoria}]" if doc.categoria else ""
            bloques.append(f"### {doc.titulo}{categoria}\n{doc.contenido}")

        return "\n\n".join(bloques)
