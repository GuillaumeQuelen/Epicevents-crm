"""Create every table in the database (run once)."""

from database import engine
from models import Base

Base.metadata.create_all(engine)
print("Tables créées.")