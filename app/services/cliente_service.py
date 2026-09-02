from sqlalchemy.orm import Session
from app.models.cliente import Cliente
from app.schemas.cliente import ClienteCrear, ClienteActualizar


class ClienteService:
    """Operaciones CRUD sobre clientes."""

    def __init__(self, db: Session):
        self.db = db

    def listar(self, solo_activos: bool = True) -> list[Cliente]:
        query = self.db.query(Cliente)
        if solo_activos:
            query = query.filter(Cliente.activo == True)
        return query.order_by(Cliente.fecha_creacion.desc()).all()

    def obtener(self, cliente_id: int) -> Cliente | None:
        return self.db.query(Cliente).get(cliente_id)

    def crear(self, datos: ClienteCrear) -> Cliente:
        cliente = Cliente(**datos.model_dump(exclude_unset=True))
        self.db.add(cliente)
        self.db.commit()
        self.db.refresh(cliente)
        return cliente

    def actualizar(self, cliente_id: int, datos: ClienteActualizar) -> Cliente | None:
        cliente = self.obtener(cliente_id)
        if not cliente:
            return None

        for campo, valor in datos.model_dump(exclude_unset=True).items():
            setattr(cliente, campo, valor)

        self.db.commit()
        self.db.refresh(cliente)
        return cliente
