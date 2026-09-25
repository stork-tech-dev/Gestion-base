"""Motor, sesión y base declarativa de SQLAlchemy."""
from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from config import settings

# Todas las columnas son TIMESTAMP sin zona en hora del negocio: la conexión
# fija la zona para que now() sea coherente en cualquier servidor. Se comparte
# (DRY, Principio 2) con migrations/env.py, que abre su propio engine online.
OPCIONES_CONEXION = {"options": f"-c timezone={settings.TIMEZONE}"}

engine = create_engine(
    settings.DATABASE_URL,
    pool_pre_ping=True,
    echo=settings.DEBUG and settings.APP_ENV == "development",
    connect_args=OPCIONES_CONEXION,
)

SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


def get_db():
    """Dependency de FastAPI: una sesión por request."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
