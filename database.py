from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base

# Aquí están los datos de tu bóveda: Usuario, Contraseña, Dirección (localhost) y el nombre de la Base (CrmDb)
# El "TrustServerCertificate=yes" es clave para que confíe en nuestra conexión local.
URL_BASE_DATOS = "mssql+pyodbc://sa:PasswordSeguro123!@127.0.0.1,1433/CrmDb?driver=ODBC+Driver+18+for+SQL+Server&TrustServerCertificate=yes"

# El "engine" (motor) es el que hace el trabajo pesado de conectarse a SQL
engine = create_engine(URL_BASE_DATOS)

# La sesión es como la "ventanilla" por donde enviaremos y pediremos datos
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# Base es el molde que usaremos más adelante para crear nuestras tablas (como Clientes o Mensajes)
Base = declarative_base()
SQLALCHEMY_DATABASE_URL = (
    "mssql+pyodbc://@TU_PC_O_SERVER/NOMBRE_DE_TU_BASE"
    "?driver=ODBC+Driver+18+for+SQL+Server"
    "&Trusted_Connection=yes"
    "&TrustServerCertificate=yes"
)