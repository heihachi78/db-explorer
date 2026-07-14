from dataclasses import dataclass
from threading import Lock

import oracledb

from app.config import Settings
from app.errors import AppError


_thick_mode_lock = Lock()
_thick_mode_initialized = False


@dataclass(frozen=True, slots=True)
class OracleCredentials:
    user: str
    password: str
    dsn: str
    mode: str


def credentials_from_settings(settings: Settings) -> OracleCredentials:
    if not settings.oracle_configured:
        raise AppError(
            "ORACLE_NOT_CONFIGURED",
            "Oracle connection settings are incomplete.",
            status_code=503,
            details={"required": ["ORACLE_USER", "ORACLE_PASSWORD", "ORACLE_DSN"]},
        )
    return OracleCredentials(
        user=settings.oracle_user or "",
        password=settings.oracle_password or "",
        dsn=settings.oracle_dsn or "",
        mode=settings.oracle_mode,
    )


def _initialize_thick_mode() -> None:
    global _thick_mode_initialized
    with _thick_mode_lock:
        if not _thick_mode_initialized:
            oracledb.init_oracle_client()
            _thick_mode_initialized = True


def connect_read_only(credentials: OracleCredentials) -> oracledb.Connection:
    """Open an Oracle connection and enforce read-only transactions."""
    try:
        if credentials.mode == "thick":
            _initialize_thick_mode()
        connection = oracledb.connect(
            user=credentials.user,
            password=credentials.password,
            dsn=credentials.dsn,
        )
        connection.call_timeout = 30_000
        with connection.cursor() as cursor:
            cursor.execute("SET TRANSACTION READ ONLY")
        return connection
    except oracledb.Error as error:
        error_object = error.args[0] if error.args else None
        code = getattr(error_object, "code", None)
        message = getattr(error_object, "message", str(error)).strip()
        raise AppError(
            "ORACLE_CONNECTION_FAILED",
            "Could not connect to Oracle with the configured read-only account.",
            status_code=502,
            details={"oracleCode": code, "oracleMessage": message},
        ) from error
    except OSError as error:
        raise AppError(
            "ORACLE_NETWORK_ERROR",
            "The Oracle host cannot be reached from the application container.",
            status_code=502,
            details={
                "networkError": type(error).__name__,
                "networkMessage": str(error),
                "hint": (
                    "Check the host name in ORACLE_DSN and ensure it is resolvable "
                    "and reachable from Docker. For a database on the host machine, "
                    "use host.docker.internal instead of localhost."
                ),
            },
        ) from error
