from app.config import Settings
from app.db.database import Database
from app.tools.backup import create_backup
from app.tools.export import export_records
from app.main import app
from fastapi.testclient import TestClient
import pytest


def test_environment_and_paper_invariants_fail_closed() -> None:
    assert Settings(app_env="paper-production").app_env == "paper-production"
    with pytest.raises(ValueError, match="app_env"):
        Settings(app_env="live")
    with pytest.raises(ValueError, match="trading mode"):
        Settings(trading_mode="live")
    with pytest.raises(ValueError, match="database_url"):
        Settings(database_url="postgresql://unsafe")


def test_sqlite_backup_is_readable_retained_and_exported(tmp_path) -> None:
    settings = Settings(database_url=f"sqlite:///{tmp_path / 'active.db'}", backup_retention_count=1)
    database = Database(settings)
    database.initialize()
    first = create_backup(database, 1)
    second = create_backup(database, 1)
    assert second.exists() and Database(Settings(database_url=f"sqlite:///{second}")).integrity_check() == "ok"
    assert len(list((tmp_path / "backups").glob("*.db"))) == 1
    exported = export_records("alerts", "json", database)
    assert exported.exists() and exported.parent.name == "exports"
    assert not first.exists()


def test_operational_endpoints_error_shape_and_correlation_header() -> None:
    with TestClient(app) as client:
        response = client.get("/api/system/live", headers={"X-Request-ID": "test-correlation"})
        assert response.status_code == 200 and response.headers["X-Request-ID"] == "test-correlation"
        assert client.get("/api/system/ready").status_code == 200
        assert client.get("/api/system/version").status_code == 200
        assert client.get("/api/system/diagnostics").status_code == 200
        assert client.get("/api/system/metrics").status_code == 200
        validation = client.get("/api/validation/status")
        assert validation.status_code == 200 and validation.json()["status"] in {"pass", "fail", "insufficient_data", "paused"}
        assert client.get("/api/validation/rules").status_code == 200
        assert client.get("/api/validation/history?limit=10&offset=0").status_code == 200
        research_export = client.get("/api/system/exports/backtest-summaries?format=csv")
        assert research_export.status_code == 200 and research_export.headers["content-type"].startswith("text/csv")
        invalid = client.get("/api/market/DOGEUSDT/candles")
        assert invalid.status_code == 404 and invalid.json()["error"]["code"] == "HTTP_ERROR"
        malformed_size = client.get("/api/system/live", headers={"Content-Length": "not-a-number"})
        assert malformed_size.status_code == 400 and malformed_size.json()["error"]["code"] == "INVALID_CONTENT_LENGTH"
