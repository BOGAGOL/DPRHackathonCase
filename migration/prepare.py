"""Explicit admin phase; runtime migration never uses the target admin credential."""

import os

import psycopg
from psycopg import sql

from infra.protected.apply import admin_parameters, inspect_schema, load_profile, provision
from infra.protected.credentials import ROLES, role_password
from infra.security import external_directory
from .model import MigrationError
from .runner import PAIRS


def prepare(target: str, profile_path, *, create_local_credentials: bool = False) -> dict:
    if target not in PAIRS.values():
        raise MigrationError("invalid_prepare_target")
    profile = load_profile(profile_path)
    root = external_directory(os.environ.get("DPR_SECRETS_DIR"))
    # CREATE DATABASE is executed against template1, never against either source.
    params = admin_parameters(root,"template1")
    with psycopg.connect(**params,autocommit=True) as connection:
        version, admin, identity = connection.execute("SELECT current_setting('server_version_num')::int,current_user,system_identifier::text FROM pg_control_system()").fetchone()
        if version//10000!=18:
            raise MigrationError("wrong_database_or_version")
        if not connection.execute("SELECT 1 FROM pg_database WHERE datname=%s",(target,)).fetchone():
            connection.execute(sql.SQL("CREATE DATABASE {} TEMPLATE template0").format(sql.Identifier(target)))
    passwords = {role:role_password(root,role,create=create_local_credentials) for role in ROLES}
    provision(os.environ.get("DPR_POSTGRES_CONTAINER","pg-dpr"),target,admin,passwords,profile,system_identifier=identity)
    result = inspect_schema({**params,"dbname":target},profile)
    if not result["passed"]:
        raise MigrationError("schema_inspection_failed")
    return {**result,"target":target,"data_migrated":False}
