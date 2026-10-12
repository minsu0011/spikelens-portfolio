from app.providers.base import AnalysisProvider
from app.providers.demo import DemoAnalysisProvider
from tests.test_unit import event


def test_fixtures_do_not_depend_on_financial_inputs():
    provider: AnalysisProvider = DemoAnalysisProvider()
    first = provider.process(event(), row_index=2)
    changed = provider.process(event(ticker="OTHER", p0_price=3, t5_price=900, volume=1, price_path=[3, 30, 100, 900]), row_index=2)
    assert first == changed
    assert first["metrics"]["fixture_only"] is True
    assert "DEMO/FIXTURE" in first["event_summary"]


def test_public_provider_records_only_generic_quality_counts():
    output = DemoAnalysisProvider().process(event(price_path=[100, 110]))
    assert output["metrics"] == {"fixture_only": True, "validated_rows": 1, "missing_fields": 0, "path_points": 2}
    assert output["data_quality_score"] == 100
    assert output["model_version"] == "synthetic-fixture-v1"


def test_fixture_position_is_repeatable_for_job_recovery():
    provider = DemoAnalysisProvider()
    assert provider.process(event(), row_index=0) == provider.process(event(), row_index=6)
    assert provider.process(event(), row_index=0)["anomaly_score"] != provider.process(event(), row_index=1)["anomaly_score"]
