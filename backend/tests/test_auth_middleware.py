from fastapi import HTTPException

from app.middleware.auth import create_access_token, decode_token


def test_create_and_decode_access_token(user_id):
    token, expires_in = create_access_token(user_id, "user@example.com")

    parsed = decode_token(token)

    assert parsed.user_id == user_id
    assert parsed.email == "user@example.com"
    assert expires_in > 0


def test_decode_token_invalid_raises_401():
    try:
        decode_token("not-a-jwt")
        raise AssertionError("expected HTTPException")
    except HTTPException as exc:
        assert exc.status_code == 401
