import os
import argparse
import logging
from typing import List, Optional

# Alembic & SQLAlchemy integrations
from alembic.config import Config
from alembic import command
from alembic.script import ScriptDirectory
from alembic.runtime.migration import MigrationContext
from sqlalchemy import create_engine

logger = logging.getLogger("migration.manager")

class MigrationManager:
    """
    Programmatic Python wrapper driving Alembic execution safely 
    within the runtime application lifecycle and CI/CD pipelines.
    """
    
    def __init__(self, alembic_ini_path: str = "alembic.ini", database_url: Optional[str] = None):
        """
        Initializes the Alembic configuration context. Overrides the statically
        compiled INI target if dynamic database parameters are provided.
        """
        self.alembic_cfg = Config(alembic_ini_path)
        
        if database_url:
            self.alembic_cfg.set_main_option("sqlalchemy.url", database_url)
            self.database_url = database_url
        else:
            self.database_url = self.alembic_cfg.get_main_option("sqlalchemy.url")

    def run_upgrade(self, revision: str = "head"):
        """Run transactional database migrations to upgrade the schema."""
        logger.info(f"Upgrading database schema to revision boundary: {revision}")
        command.upgrade(self.alembic_cfg, revision)
        logger.info("Database schema upgrade applied successfully.")

    def run_downgrade(self, revision: str = "-1"):
        """Revert database migrations sequentially to a prior bounded state."""
        logger.warning(f"Downgrading database schema to revision boundary: {revision}")
        command.downgrade(self.alembic_cfg, revision)
        logger.info("Database schema downgrade applied successfully.")

    def create_migration(self, message: str, autogenerate: bool = True):
        """Generate a new sequential migration schema script."""
        logger.info(f"Generating schema revision: '{message}' (Autogenerate Map: {autogenerate})")
        command.revision(self.alembic_cfg, message=message, autogenerate=autogenerate)
        logger.info("Migration script generated and indexed successfully.")

    def _get_migration_context(self):
        """Helper establishing a synchronous connection block for interrogating Alembic state."""
        # Alembic natively leverages sync connections to perform structural graph queries
        engine = create_engine(self.database_url)
        return engine, MigrationContext.configure(engine.connect())

    def get_current_revision(self) -> Optional[str]:
        """Fetch the exact hash string of the currently applied database schema."""
        engine, context = self._get_migration_context()
        try:
            return context.get_current_revision()
        finally:
            engine.dispose()

    def get_pending_migrations(self) -> List[str]:
        """Calculates precisely which structural migrations are waiting in queue to be applied."""
        engine, context = self._get_migration_context()
        try:
            script = ScriptDirectory.from_config(self.alembic_cfg)
            heads = script.get_revisions(script.get_heads())
            current_rev = context.get_current_revision()
            
            pending = []
            for head in heads:
                # Walk down the revision tree traversing from HEAD back to our current state
                for rev in script.iterate_revisions(head.revision, current_rev):
                    pending.append(rev.revision)
                    
            return pending
        finally:
            engine.dispose()

    def check_health(self) -> dict:
        """
        Exposes a structural health check payload. Emits critical warnings if 
        the container application bootups but detects pending out-of-sync migrations.
        """
        try:
            pending = self.get_pending_migrations()
            current = self.get_current_revision()
            
            if pending:
                logger.warning(f"Health Warning: Application running with {len(pending)} pending migrations!")
                return {
                    "status": "warning", 
                    "message": f"Database desync detected. There are {len(pending)} unapplied migrations.",
                    "current_revision": current,
                    "pending_count": len(pending)
                }
                
            return {
                "status": "healthy",
                "message": "Database schema is perfectly synchronized.",
                "current_revision": current,
                "pending_count": 0
            }
        except Exception as e:
            logger.error(f"Migration health probe completely failed: {e}")
            return {
                "status": "error",
                "message": str(e)
            }


def main():
    """CLI sub-routine exposing internal programmatic commands to terminal operations."""
    parser = argparse.ArgumentParser(description="AOP Schema Database Migration Manager")
    
    subparsers = parser.add_subparsers(dest="command", required=True, help="Available structural commands")
    
    # upgrade wrapper
    upgrade_parser = subparsers.add_parser("upgrade", help="Apply pending database migrations forwards")
    upgrade_parser.add_argument("--revision", default="head", help="Target revision limit (default: head)")
    
    # downgrade wrapper
    downgrade_parser = subparsers.add_parser("downgrade", help="Revert applied database migrations backwards")
    downgrade_parser.add_argument("--revision", default="-1", help="Target revision limit (default: -1)")
    
    # create wrapper
    create_parser = subparsers.add_parser("create", help="Scaffold a new migration structural script")
    create_parser.add_argument("-m", "--message", required=True, help="Contextual description of changes")
    create_parser.add_argument("--no-auto", action="store_true", help="Disable SQLAlchemy model autogeneration")
    
    # status wrapper
    subparsers.add_parser("status", help="Inspect current structural migration synchronization state")
    
    args = parser.parse_args()
    
    # Safely extract dynamic configuration from ENV over INI 
    database_url = os.getenv("DB_DSN", "postgresql://localhost/aop")
    manager = MigrationManager(alembic_ini_path="alembic.ini", database_url=database_url)
    
    # Route to handlers
    if args.command == "upgrade":
        manager.run_upgrade(revision=args.revision)
    elif args.command == "downgrade":
        manager.run_downgrade(revision=args.revision)
    elif args.command == "create":
        manager.create_migration(message=args.message, autogenerate=not args.no_auto)
    elif args.command == "status":
        health = manager.check_health()
        print("--- AOP MIGRATION STATUS ---")
        print(f"Status:           {health['status'].upper()}")
        print(f"Message:          {health['message']}")
        print(f"Current Revision: {health['current_revision']}")
        print(f"Pending Count:    {health['pending_count']}")
        print("----------------------------")

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    main()
