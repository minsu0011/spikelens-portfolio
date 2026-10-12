import argparse
import hashlib
import random
import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import select

from app.db.session import SessionLocal
from app.models import Event
from app.providers.demo import DemoAnalysisProvider
from app.schemas.events import EventInput

SEED = 271013
RECIPE = "spikelens-synthetic-v1"


def synthetic_events(count=10000):
    rng = random.Random(SEED)
    start = datetime(2025, 1, 2, 9, tzinfo=UTC)
    for index in range(count):
        price = round(rng.uniform(5, 450), 4)
        drift = rng.uniform(-0.12, 0.12)
        path = [
            round(price * (1 + drift * step / 29 + rng.uniform(-0.005, 0.005)), 4)
            for step in range(30)
        ]
        yield EventInput(
            ticker=f"SYN{rng.randrange(1, 151):03d}",
            event_time=start + timedelta(minutes=index * 13),
            session=rng.choice(["PREMARKET", "RTH", "RTH", "AFTERHOURS"]),
            event_type=rng.choice(["PRICE_SPIKE", "VOLUME_SURGE", "VOLATILITY"]),
            p0_price=price,
            t5_price=path[-1],
            volume=rng.randint(100, 3000000),
            price_path=path,
        )


def seed(count: int):
    engine = DemoAnalysisProvider()
    inserted = 0
    with SessionLocal() as db:
        existing = set(db.scalars(select(Event.source_key).where(Event.is_public.is_(True))))
        for index, data in enumerate(synthetic_events(count)):
            key = hashlib.sha256(f"{RECIPE}|{SEED}|{index}".encode()).hexdigest()
            if key in existing:
                continue
            scored = engine.process(data, row_index=index)
            db.add(
                Event(
                    id=uuid.uuid5(uuid.NAMESPACE_URL, key),
                    **data.model_dump(),
                    anomaly_score=scored["anomaly_score"],
                    data_quality_score=scored["data_quality_score"],
                    model_version=engine.version,
                    is_public=True,
                    is_synthetic=True,
                    source_key=key,
                )
            )
            inserted += 1
            if inserted % 1000 == 0:
                db.flush()
        db.commit()
    print({"recipe": RECIPE, "seed": SEED, "requested": count, "inserted": inserted})


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--count", type=int, default=10000)
    args = parser.parse_args()
    if not 1 <= args.count <= 20000:
        parser.error("count must be between 1 and 20000")
    seed(args.count)
