import pytest

from app.auth.passwords import hash_password, needs_rehash, verify_password

PASSWORD = "correct horse battery staple"


def test_hash_is_not_the_plain_password():
    password_hash = hash_password(PASSWORD)

    assert password_hash != PASSWORD
    assert PASSWORD not in password_hash
    assert password_hash.startswith("$argon2id$")


def test_verify_accepts_the_right_password():
    assert verify_password(hash_password(PASSWORD), PASSWORD) is True


def test_verify_rejects_a_wrong_password():
    assert verify_password(hash_password(PASSWORD), "wrong password") is False


@pytest.mark.parametrize("invalid_hash", ["", "not-a-hash", "$argon2id$broken"])
def test_verify_returns_false_for_an_invalid_hash(invalid_hash):
    assert verify_password(invalid_hash, PASSWORD) is False


def test_same_password_gets_a_different_hash_each_time():
    assert hash_password(PASSWORD) != hash_password(PASSWORD)


def test_fresh_hash_does_not_need_rehash():
    assert needs_rehash(hash_password(PASSWORD)) is False
