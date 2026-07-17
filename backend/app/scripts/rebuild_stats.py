from app.core.config import get_settings
from app.db.session import SessionLocal
from app.services.stats import StatsService


def main() -> None:
    with SessionLocal() as db:
        rebuilt = StatsService(db, get_settings()).rebuild_aggregates()
    print(f"Rebuilt aggregate and non-Medic DPM data from {rebuilt} player-match rows.")


if __name__ == "__main__":
    main()
