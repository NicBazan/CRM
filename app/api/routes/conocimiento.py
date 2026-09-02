from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from app.api.deps import get_db
from app.models.documento_conocimiento import DocumentoConocimiento
from app.schemas.mensaje import (
    DocumentoConocimientoCrear,
    DocumentoConocimientoActualizar,
    DocumentoConocimientoResponse,
)

router = APIRouter(prefix="/conocimiento", tags=["Knowledge Base"])


@router.get("/", response_model=list[DocumentoConocimientoResponse])
def listar_documentos(db: Session = Depends(get_db)):
    """Lista todos los documentos de conocimiento del negocio."""
    return (
        db.query(DocumentoConocimiento)
        .order_by(DocumentoConocimiento.categoria, DocumentoConocimiento.titulo)
        .all()
    )


@router.post("/", response_model=DocumentoConocimientoResponse, status_code=201)
def crear_documento(datos: DocumentoConocimientoCrear, db: Session = Depends(get_db)):
    """
    Agrega un nuevo documento de conocimiento.
    Este conocimiento será inyectado automáticamente en el prompt del agente IA.
    """
    doc = DocumentoConocimiento(**datos.model_dump())
    db.add(doc)
    db.commit()
    db.refresh(doc)
    return doc


@router.patch("/{doc_id}", response_model=DocumentoConocimientoResponse)
def actualizar_documento(
    doc_id: int,
    datos: DocumentoConocimientoActualizar,
    db: Session = Depends(get_db),
):
    """Actualiza un documento de conocimiento existente."""
    doc = db.query(DocumentoConocimiento).get(doc_id)
    if not doc:
        raise HTTPException(status_code=404, detail="Documento no encontrado")

    for campo, valor in datos.model_dump(exclude_unset=True).items():
        setattr(doc, campo, valor)

    db.commit()
    db.refresh(doc)
    return doc


@router.delete("/{doc_id}")
def eliminar_documento(doc_id: int, db: Session = Depends(get_db)):
    """Elimina (soft delete) un documento de conocimiento."""
    doc = db.query(DocumentoConocimiento).get(doc_id)
    if not doc:
        raise HTTPException(status_code=404, detail="Documento no encontrado")

    doc.activo = False
    db.commit()
    return {"status": "eliminado", "id": doc_id}
