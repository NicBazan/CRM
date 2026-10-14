from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from app.api.deps import get_db, get_current_user
from app.schemas.cliente import ClienteCrear, ClienteActualizar, ClienteResponse
from app.services.cliente_service import ClienteService

router = APIRouter(prefix="/clientes", tags=["Clientes"], dependencies=[Depends(get_current_user)])


@router.get("/", response_model=list[ClienteResponse])
def listar_clientes(db: Session = Depends(get_db)):
    """Lista todos los clientes activos."""
    servicio = ClienteService(db)
    return servicio.listar()


@router.get("/{cliente_id}", response_model=ClienteResponse)
def obtener_cliente(cliente_id: int, db: Session = Depends(get_db)):
    """Obtiene un cliente por su ID."""
    servicio = ClienteService(db)
    cliente = servicio.obtener(cliente_id)
    if not cliente:
        raise HTTPException(status_code=404, detail="Cliente no encontrado")
    return cliente


@router.post("/", response_model=ClienteResponse, status_code=201)
def crear_cliente(datos: ClienteCrear, db: Session = Depends(get_db)):
    """Crea un nuevo cliente."""
    servicio = ClienteService(db)
    return servicio.crear(datos)


@router.patch("/{cliente_id}", response_model=ClienteResponse)
def actualizar_cliente(
    cliente_id: int,
    datos: ClienteActualizar,
    db: Session = Depends(get_db),
):
    """Actualiza los datos de un cliente existente."""
    servicio = ClienteService(db)
    cliente = servicio.actualizar(cliente_id, datos)
    if not cliente:
        raise HTTPException(status_code=404, detail="Cliente no encontrado")
    return cliente
