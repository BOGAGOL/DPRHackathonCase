from passwords import PasswordService


def test_password_round_trip():
    service = PasswordService(pepper="lab-pepper")
    stored = service.hash("correct horse battery staple")
    valid, _ = service.verify(stored, "correct horse battery staple")
    invalid, _ = service.verify(stored, "wrong")
    assert valid is True
    assert invalid is False

