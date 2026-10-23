import os

from alembic import context
from dotenv import load_dotenv
from sqlalchemy import create_engine

from app.models import Base

load_dotenv()
target_metadata = Base.metadata


def run():
    url = os.getenv("MIGRATION_DATABASE_URL") or os.environ["DATABASE_URL"]
    if context.is_offline_mode():
        context.configure(url=url, target_metadata=target_metadata, literal_binds=True)
        with context.begin_transaction():
            context.run_migrations()
    else:
        engine = create_engine(url, hide_parameters=True)
        with engine.connect() as connection:
            context.configure(connection=connection, target_metadata=target_metadata, compare_type=True)
            with context.begin_transaction():
                context.run_migrations()


run()
