import importlib
import sys

from cryptography.fernet import Fernet
from fastapi.testclient import TestClient

from garmin_api.store import Account


class FakeGarmin:
    def __init__(self, payload):
        self.payload = payload
        self.calls = []

    def get_activities(self, start, limit, activity_type=None):
        self.calls.append((start, limit, activity_type))
        return self.payload


def load_api(monkeypatch, tmp_path):
    monkeypatch.setenv("GARMIN_API_STORAGE", str(tmp_path / "storage"))
    monkeypatch.setenv("GARMIN_API_DATABASE", str(tmp_path / "garmin_api.sqlite3"))
    monkeypatch.setenv("GARMIN_API_ENCRYPTION_KEY", Fernet.generate_key().decode())
    monkeypatch.setenv("GARMIN_API_ALLOWED_HOSTS", "testserver,localhost,127.0.0.1")
    sys.modules.pop("garmin_api.main", None)
    return importlib.import_module("garmin_api.main")


def test_latest_activity_returns_first_garmin_activity(monkeypatch, tmp_path):
    main = load_api(monkeypatch, tmp_path)
    account = Account(
        id="account-1",
        label=None,
        email_encrypted="email",
        password_encrypted="password",
        api_key_hash="hash",
        is_cn=False,
    )
    fake_garmin = FakeGarmin([{"activityId": 24108314422, "activityName": "Natação em piscina"}])

    main.app.dependency_overrides[main.current_account] = lambda: account
    monkeypatch.setattr(main.service, "get_garmin", lambda _account: fake_garmin)
    monkeypatch.setattr(
        main.service,
        "cached_call",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("cache used")),
    )

    response = TestClient(main.app).get("/activities/latest?fresh=true")

    assert response.status_code == 200
    assert response.json()["cached"] is False
    assert response.json()["data"] == {
        "activityId": 24108314422,
        "activityName": "Natação em piscina",
    }
    assert fake_garmin.calls == [(0, 1, None)]


def test_latest_activity_returns_null_when_garmin_has_no_activity(monkeypatch, tmp_path):
    main = load_api(monkeypatch, tmp_path)
    account = Account(
        id="account-1",
        label=None,
        email_encrypted="email",
        password_encrypted="password",
        api_key_hash="hash",
        is_cn=False,
    )
    fake_garmin = FakeGarmin([])

    main.app.dependency_overrides[main.current_account] = lambda: account
    monkeypatch.setattr(main.service, "get_garmin", lambda _account: fake_garmin)

    response = TestClient(main.app).get("/activities/latest?fresh=true")

    assert response.status_code == 200
    assert response.json()["data"] is None
    assert fake_garmin.calls == [(0, 1, None)]


def test_latest_activity_can_use_regular_cache(monkeypatch, tmp_path):
    main = load_api(monkeypatch, tmp_path)
    account = Account(
        id="account-1",
        label=None,
        email_encrypted="email",
        password_encrypted="password",
        api_key_hash="hash",
        is_cn=False,
    )

    main.app.dependency_overrides[main.current_account] = lambda: account
    monkeypatch.setattr(
        main.service,
        "cached_call",
        lambda _account, cache_key, _load: ({"activityId": "cached"}, cache_key == ("activities-latest",)),
    )

    response = TestClient(main.app).get("/activities/latest?fresh=false")

    assert response.status_code == 200
    assert response.json()["cached"] is True
    assert response.json()["data"] == {"activityId": "cached"}
