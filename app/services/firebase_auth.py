import logging
from datetime import datetime, timezone

from flask import current_app

logger = logging.getLogger(__name__)


class TokenError(ValueError):
    pass


def _firebase_ready():
    return bool(current_app.config.get("FIREBASE_PROJECT_ID"))


def init_firebase_admin():
    if not _firebase_ready():
        raise TokenError("Google sign-in is not available.")
    import firebase_admin
    from firebase_admin import credentials

    if firebase_admin._apps:
        return firebase_admin.get_app()
    project_id = current_app.config["FIREBASE_PROJECT_ID"]
    cred_path = current_app.config.get("GOOGLE_APPLICATION_CREDENTIALS")
    emulator = current_app.config.get("FIREBASE_AUTH_EMULATOR_HOST")
    options = {"projectId": project_id}
    if emulator:
        return firebase_admin.initialize_app(options=options)
    if cred_path:
        cred = credentials.Certificate(cred_path)
        return firebase_admin.initialize_app(cred, options)
    return firebase_admin.initialize_app(options=options)


def verify_id_token(id_token, require_recent=False):
    if not id_token or not isinstance(id_token, str):
        raise TokenError("Google sign-in failed.")
    try:
        init_firebase_admin()
        from firebase_admin import auth as fb_auth

        claims = fb_auth.verify_id_token(
            id_token,
            check_revoked=False,
        )
    except TokenError:
        raise
    except Exception:
        logger.warning("Google sign-in token rejected.")
        raise TokenError("Google sign-in failed.") from None

    project_id = current_app.config["FIREBASE_PROJECT_ID"]
    audience = claims.get("aud")
    if audience != project_id:
        logger.warning("Google sign-in token rejected.")
        raise TokenError("Google sign-in failed.")
    if not claims.get("email_verified"):
        raise TokenError("Google sign-in failed.")
    email = (claims.get("email") or "").strip().lower()
    uid = claims.get("uid") or claims.get("sub")
    if not email or not uid:
        raise TokenError("Google sign-in failed.")
    if require_recent:
        auth_time = claims.get("auth_time")
        if not auth_time:
            raise TokenError("Google sign-in failed.")
        signed = datetime.fromtimestamp(int(auth_time), tz=timezone.utc)
        age = datetime.now(timezone.utc) - signed
        if age.total_seconds() > 300:
            raise TokenError("Google sign-in failed.")
    return {"uid": uid, "email": email, "auth_time": claims.get("auth_time")}


def delete_firebase_user(uid):
    try:
        init_firebase_admin()
        from firebase_admin import auth as fb_auth

        fb_auth.delete_user(uid)
    except Exception:
        logger.warning("Could not delete remote sign-in account.")
        raise TokenError("Could not delete the account.") from None
