import json
from importlib.resources import files

from app.schemas.events import EventInput

PROVIDER_VERSION = "synthetic-fixture-v1"
FIXTURES = json.loads(files("app.providers").joinpath("fixtures.json").read_text())


class DemoAnalysisProvider:
    """Return published display fixtures, never a prediction or financial feature.

    Input is already validated by EventInput. Only generic row/path counts are
    recorded. Display values depend on row position, not prices, ticker or volume.
    """

    version = PROVIDER_VERSION

    def process(self, event: EventInput, *, row_index: int = 0) -> dict:
        fixture = FIXTURES[row_index % len(FIXTURES)]
        return {
            "anomaly_score": fixture["display_value"],
            "data_quality_score": 100.0,
            "event_summary": "DEMO/FIXTURE: validated row stored; prediction is not available.",
            "model_version": self.version,
            "metrics": {
                "fixture_only": True,
                "validated_rows": 1,
                "missing_fields": 0,
                "path_points": len(event.price_path),
            },
        }
