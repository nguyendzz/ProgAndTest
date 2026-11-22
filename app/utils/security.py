import re
import secrets
import bcrypt


class SecurityService:
    PASSWORD_PATTERN = re.compile(r"^(?=.*[A-Za-z])(?=.*\d).{6,}$")

    @staticmethod
    def hash_password(plain_password: str) -> str:
        salt = bcrypt.gensalt(rounds=12)
        return bcrypt.hashpw(plain_password.encode("utf-8"), salt).decode("utf-8")

    @staticmethod
    def verify_password(plain_password: str, password_hash: str) -> bool:
        if not plain_password or not password_hash:
            return False
        try:
            return bcrypt.checkpw(
                plain_password.encode("utf-8"), password_hash.encode("utf-8")
            )
        except ValueError:
            return False

    @classmethod
    def validate_password_complexity(cls, password: str) -> tuple[bool, str]:
        if not password or len(password) < 6:
            return False, "Password must be at least 6 characters long."
        if not cls.PASSWORD_PATTERN.match(password):
            return False, "Password must include at least one letter and one number."
        return True, ""

    @staticmethod
    def generate_reset_token() -> str:
        return secrets.token_urlsafe(32)

    @staticmethod
    def generate_csrf_token() -> str:
        return secrets.token_hex(32)
