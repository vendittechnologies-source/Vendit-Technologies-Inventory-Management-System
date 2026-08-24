"""JWT-based auth helpers for the Vendit Inventory app."""
import os
from datetime import datetime, timedelta, timezone
from functools import wraps

import jwt
from flask import request, jsonify, g

JWT_SECRET = os.environ.get("JWT_SECRET", "dev-secret-change-me")
JWT_ALGO = "HS256"
TOKEN_TTL_HOURS = 12


def generate_token(user_row):
    payload = {
        "sub": str(user_row["id"]),
        "username": user_row["username"],
        "role": user_row["role"],
        "full_name": user_row["full_name"],
        "exp": datetime.now(timezone.utc) + timedelta(hours=TOKEN_TTL_HOURS),
        "iat": datetime.now(timezone.utc),
    }
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGO)


def decode_token(token):
    return jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGO])


def _extract_token():
    header = request.headers.get("Authorization", "")
    if header.startswith("Bearer "):
        return header[7:]
    return None


def require_auth(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        token = _extract_token()
        if not token:
            return jsonify({"error": "Authentication required."}), 401
        try:
            payload = decode_token(token)
        except jwt.ExpiredSignatureError:
            return jsonify({"error": "Session expired. Please log in again."}), 401
        except jwt.InvalidTokenError:
            return jsonify({"error": "Invalid session. Please log in again."}), 401
        g.user = {
            "id": int(payload["sub"]),
            "username": payload["username"],
            "role": payload["role"],
            "full_name": payload["full_name"],
        }
        return f(*args, **kwargs)

    return wrapper


def require_role(*roles):
    def decorator(f):
        @wraps(f)
        def wrapper(*args, **kwargs):
            if not getattr(g, "user", None):
                return jsonify({"error": "Authentication required."}), 401
            if g.user["role"] not in roles:
                return jsonify({"error": "You don't have permission to do that."}), 403
            return f(*args, **kwargs)

        return wrapper

    return decorator
