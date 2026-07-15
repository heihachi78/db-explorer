from typing import Any

import oracledb

from .connection import OracleCredentials, connect_read_only


CATALOG_VIEWS = (
    "ALL_OBJECTS",
    "ALL_DEPENDENCIES",
    "ALL_CONSTRAINTS",
    "ALL_CONS_COLUMNS",
    "ALL_TRIGGERS",
    "ALL_INDEXES",
    "ALL_SYNONYMS",
)


def _can_select(cursor: oracledb.Cursor, view_name: str) -> bool:
    try:
        cursor.execute(f"SELECT 1 FROM {view_name} WHERE 1 = 0")
        return True
    except oracledb.Error:
        return False


def discover_capabilities(credentials: OracleCredentials) -> dict[str, Any]:
    connection = connect_read_only(credentials)
    try:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT
                    SYS_CONTEXT('USERENV', 'DB_NAME'),
                    SYS_CONTEXT('USERENV', 'CON_NAME'),
                    SYS_CONTEXT('USERENV', 'CURRENT_SCHEMA')
                FROM dual
                """
            )
            database_name, container_name, current_schema = cursor.fetchone()

            readable_views = [view for view in CATALOG_VIEWS if _can_select(cursor, view)]
            missing_views = [view for view in CATALOG_VIEWS if view not in readable_views]

            schemas: list[str] = []
            if "ALL_OBJECTS" in readable_views:
                cursor.execute(
                    """
                    SELECT DISTINCT owner
                    FROM all_objects
                    WHERE owner NOT IN (
                        'SYS', 'SYSTEM', 'XDB', 'MDSYS', 'CTXSYS', 'ORDSYS',
                        'DBSNMP', 'OUTLN', 'AUDSYS', 'GSMADMIN_INTERNAL'
                    )
                    ORDER BY owner
                    """
                )
                schemas = [row[0] for row in cursor]

                cursor.execute(
                    "SELECT DISTINCT object_type FROM all_objects ORDER BY object_type"
                )
                object_types = [row[0] for row in cursor]
            else:
                object_types = []

        warnings = [f"Catalog view is not readable: {view}" for view in missing_views]
        return {
            "oracleVersion": connection.version,
            "databaseName": database_name,
            "containerName": container_name,
            "currentSchema": current_schema,
            "driverMode": credentials.mode,
            "schemas": schemas,
            "readableViews": readable_views,
            "missingViews": missing_views,
            "objectTypes": object_types,
            "warnings": warnings,
        }
    finally:
        connection.close()
