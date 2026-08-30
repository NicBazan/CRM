from sqlalchemy import Column, Integer, String, DateTime
from datetime import datetime
from database import Base

# Creamos el molde para la tabla de clientes
class Cliente(Base):
    __tablename__ = "clientes"

    id = Column(Integer, primary_key=True, index=True)
    telefono = Column(String(50), unique=True, index=True)
    nombre = Column(String(100), nullable=True) # Puede ser nulo hasta que nos digan su nombre
    ultimo_mensaje = Column(String(500), nullable=True)
    
    # Estados útiles para el CRM: 'nuevo', 'presupuesto_enviado', 'lentes_en_proceso', 'listo_para_retirar'
    estado = Column(String(50), default="nuevo") 
    
    fecha_actualizacion = Column(DateTime, default=datetime.utcnow)