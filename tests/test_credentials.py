import string

from ja import credentials


def test_generate_password_meets_common_complexity_rules():
    for _ in range(20):
        pwd = credentials.generate_password()
        assert len(pwd) == 16
        assert any(c.islower() for c in pwd)
        assert any(c.isupper() for c in pwd)
        assert any(c.isdigit() for c in pwd)
        assert any(c in "!@#$%^&*" for c in pwd)


def test_generate_password_varies():
    passwords = {credentials.generate_password() for _ in range(10)}
    assert len(passwords) == 10  # no collisions in 10 tries


def test_get_or_create_is_idempotent_per_hostname(tmp_path):
    root = str(tmp_path)
    login1, pw1 = credentials.get_or_create(root, "careers.acme.icims.com", "me@example.com")
    login2, pw2 = credentials.get_or_create(root, "careers.acme.icims.com", "me@example.com")
    assert (login1, pw1) == (login2, pw2)


def test_get_or_create_is_isolated_per_hostname(tmp_path):
    # Two different companies both hosted on *.icims.com must never share a
    # login -- each is a separate candidate database despite the shared
    # underlying platform.
    root = str(tmp_path)
    _, pw_a = credentials.get_or_create(root, "careers-acme.icims.com", "me@example.com")
    _, pw_b = credentials.get_or_create(root, "careers-other.icims.com", "me@example.com")
    assert pw_a != pw_b


def test_credentials_persist_to_disk(tmp_path):
    root = str(tmp_path)
    credentials.get_or_create(root, "example.icims.com", "me@example.com")
    reloaded = credentials.load_credentials(root)
    assert "example.icims.com" in reloaded
    assert reloaded["example.icims.com"]["login"] == "me@example.com"


def test_hostname_for_extracts_netloc():
    assert credentials.hostname_for("https://careers-acme.icims.com/jobs/1/apply") == "careers-acme.icims.com"
