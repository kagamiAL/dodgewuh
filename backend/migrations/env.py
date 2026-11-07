"""Use the same secret-aware configuration as the coordinator."""
from alembic import context
from app.db.connection import make_engine
from app.db.models import Base

# Offline mode emits SQL without opening a connection or requiring credentials.
if context.is_offline_mode():
    context.configure(dialect_name="postgresql", target_metadata=Base.metadata, literal_binds=True)
    with context.begin_transaction():
        context.run_migrations()
else:
    # Online migrations use the same PG variables and password-file rules as the API.
    engine = make_engine()
    with engine.connect() as connection:
        context.configure(connection=connection, target_metadata=Base.metadata)
        with context.begin_transaction():
            context.run_migrations()
    engine.dispose()
