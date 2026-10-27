"""Resumable keyset batches with atomic checkpoints and full, in-memory validation."""

from collections import Counter
from datetime import datetime, timezone
import hashlib
import json

from psycopg import sql

from .model import MigrationError, canonical_value, compare_batch, protect_batch, source_bytes, target_columns
from dprcrypto import normalize
from infra.targets import MIGRATION_DATASETS, MIGRATION_PAIRS


PAIRS = MIGRATION_PAIRS
LOCK = 734100018


def check_pair(source: str, target: str) -> None:
    if PAIRS.get(source)!=target:
        raise MigrationError("invalid_source_target_pair")


def expected_source_rows(source: str, override: int | None = None) -> int:
    if source not in MIGRATION_DATASETS:
        raise MigrationError("invalid_source_target_pair")
    expected = MIGRATION_DATASETS[source]["expected_rows"] if override is None else override
    if type(expected) is not int or not 0<=expected<=9223372036854775807:
        raise MigrationError("invalid_expected_row_count")
    return expected


def source_page(connection, columns: list[str], after, size: int) -> list[dict]:
    query = sql.SQL("SELECT {} FROM public.anggota WHERE (%s::bigint IS NULL OR id>%s) ORDER BY id LIMIT %s").format(
        sql.SQL(",").join(map(sql.Identifier,["id",*columns])))
    return connection.execute(query,(after,after,size)).fetchall()


def source_summary(connection, profile: dict) -> dict:
    columns = list(profile["columns"])
    digest = hashlib.sha256()
    count, after = 0, None
    nulls = Counter({column:0 for column in columns})
    # Only normalized lookup values live in memory, never emitted or persisted.
    unique = {column:set() for column,field in profile["columns"].items() if field["bidx"]}
    nonnull = Counter()
    while rows := source_page(connection,columns,after,1000):
        for row in rows:
            if type(row["id"]) is not int:
                raise MigrationError("invalid_source_id")
            digest.update(source_bytes(row,columns))
            for column in columns: nulls[column] += row[column] is None
            for column,values in unique.items():
                if row[column] is not None:
                    values.add(normalize(column,canonical_value(row[column])))
                    nonnull[column] += 1
        after = rows[-1]["id"]
        count += len(rows)
    return {"rows":count,"sha256":digest.hexdigest(),"nulls":dict(nulls),
            "bidx_unique":{column:len(values)==nonnull[column] for column,values in unique.items()}}


def check_connections(source, target, source_name: str, target_name: str) -> str:
    check_pair(source_name,target_name)
    for connection,name in ((source,source_name),(target,target_name)):
        metadata = connection.execute("SELECT current_database() AS name,current_setting('server_version_num')::int AS version").fetchone()
        if metadata["name"]!=name or metadata["version"]//10000!=18:
            raise MigrationError("wrong_database_or_version")
    role = target.execute("SELECT current_user AS name,rolsuper,rolcreatedb,rolcreaterole,rolreplication,rolbypassrls FROM pg_roles WHERE rolname=current_user").fetchone()
    if role["name"]!="migration_user" or any(role[key] for key in ("rolsuper","rolcreatedb","rolcreaterole","rolreplication","rolbypassrls")):
        raise MigrationError("unsafe_target_role")
    identity = source.execute("SELECT oid::text AS oid FROM pg_database WHERE datname=current_database()").fetchone()["oid"]
    return json.dumps([source.info.host,source.info.port,source_name,identity],separators=(",",":"))


def open_job(target, source_name: str, identity: str, profile_hash: str, summary: dict,
             compatible_profile_hashes: tuple[str,...] = ()) -> dict:
    with target.transaction():
        job = target.execute("SELECT * FROM public.migration_jobs WHERE job_id=1 FOR UPDATE").fetchone()
        state = target.execute("SELECT count(*) AS rows,max(legacy_row_id) AS last FROM public.anggota_protected").fetchone()
        if job is None:
            if state["rows"]:
                raise MigrationError("target_not_fresh")
            job = target.execute("""INSERT INTO public.migration_jobs(job_id,source_database,source_identity,profile_sha256,
                source_sha256,source_rows,status) VALUES(1,%s,%s,%s,%s,%s,'running') RETURNING *""",
                (source_name,identity,profile_hash,summary["sha256"],summary["rows"])).fetchone()
        expected = (source_name,identity,profile_hash,summary["sha256"],summary["rows"])
        actual = tuple(job[key] for key in ("source_database","source_identity","profile_sha256","source_sha256","source_rows"))
        if (actual[:2]+actual[3:]!=expected[:2]+expected[3:]
                or job["profile_sha256"] not in {profile_hash,*compatible_profile_hashes}):
            raise MigrationError("source_or_profile_changed")
        if state["rows"]!=job["migrated_rows"] or state["last"]!=job["last_legacy_id"]:
            raise MigrationError("target_checkpoint_mismatch")
        return job


def write_batch(target, rows: list[dict], profile: dict, client, previous: dict) -> dict:
    protected = []
    for start in range(0,len(rows),100):
        protected.extend(protect_batch(rows[start:start+100],profile,client))
    columns = target_columns(profile)
    query = sql.SQL("INSERT INTO public.anggota_protected({}) VALUES({})").format(
        sql.SQL(",").join(map(sql.Identifier,columns)),sql.SQL(",").join(sql.Placeholder() for _ in columns))
    with target.transaction():
        job = target.execute("SELECT * FROM public.migration_jobs WHERE job_id=1 FOR UPDATE").fetchone()
        if job["migrated_rows"]!=previous["migrated_rows"] or job["last_legacy_id"]!=previous["last_legacy_id"]:
            raise MigrationError("concurrent_checkpoint_change")
        with target.cursor() as cursor:
            cursor.executemany(query,([row[column] for column in columns] for row in protected))
        # Commit checkpoint and rows together. No ON CONFLICT that hides mismatches.
        return target.execute("""UPDATE public.migration_jobs SET migrated_rows=migrated_rows+%s,last_legacy_id=%s,
            batch_count=batch_count+1,status='running',validated_at=NULL,updated_at=clock_timestamp()
            WHERE job_id=1 RETURNING *""",(len(rows),rows[-1]["id"])).fetchone()


def validate_all(source, target, profile: dict, summary: dict, client) -> dict:
    columns = target_columns(profile)
    after, count = None, 0
    nulls = Counter({column:0 for column in profile["columns"]})
    target.execute("UPDATE public.migration_jobs SET status='validating',validated_at=NULL,updated_at=clock_timestamp() WHERE job_id=1")
    with target.transaction():
        # Exclude concurrent writers during comparison; source remains READ ONLY.
        target.execute("LOCK TABLE public.anggota_protected IN SHARE MODE")
        for_source = list(profile["columns"])
        while rows := source_page(source,for_source,after,100):
            query = sql.SQL("SELECT {} FROM public.anggota_protected WHERE legacy_row_id=ANY(%s) ORDER BY legacy_row_id").format(sql.SQL(",").join(map(sql.Identifier,columns)))
            protected = target.execute(query,([row["id"] for row in rows],)).fetchall()
            nulls.update(compare_batch(rows,protected,profile,client))
            count += len(rows)
            after = rows[-1]["id"]
        actual = target.execute("SELECT count(*) AS rows FROM public.anggota_protected").fetchone()["rows"]
        if actual!=summary["rows"] or count!=summary["rows"] or dict(nulls)!=summary["nulls"]:
            raise MigrationError("validation_totals_or_nulls")
        uniqueness = {}
        for column,field in profile["columns"].items():
            if field["bidx"]:
                counts = target.execute(sql.SQL("SELECT count({0}) AS nonnull,count(DISTINCT {0}) AS distinct_values FROM public.anggota_protected").format(sql.Identifier(field["bidx_column"]))).fetchone()
                unique = counts["nonnull"]==counts["distinct_values"]
                uniqueness[column] = {"source_normalized_unique":summary["bidx_unique"][column],"target_unique":unique}
                if summary["bidx_unique"][column] and not unique:
                    raise MigrationError("validation_index_uniqueness")
        # The caller also checks the source in a fresh snapshot before marking success.
    return {"passed":True,"rows_compared":count,"comparison":"all_rows_all_fields",
            "null_counts":dict(nulls),"blind_index_uniqueness":uniqueness}


def execute(source, target, *, source_name: str, target_name: str, profile: dict, profile_hash: str,
            migration_client, validation_client, batch_size: int = 1000, max_batches: int | None = None,
            validate_only: bool = False, expected_rows: int | None = None,
            compatible_profile_hashes: tuple[str,...] = ()) -> dict:
    if type(batch_size) is not int or not 1<=batch_size<=1000 or (max_batches is not None and (type(max_batches) is not int or max_batches<1)):
        raise MigrationError("invalid_batch_bound")
    if expected_rows is not None and (type(expected_rows) is not int or expected_rows<0):
        raise MigrationError("invalid_expected_row_count")
    identity = check_connections(source,target,source_name,target_name)
    validation_client.require_policy("svc-app")
    if not validate_only:
        migration_client.require_policy("svc-migration")
        if migration_client.authorization_scope()[0].split(":")[0]==validation_client.authorization_scope()[0].split(":")[0]:
            raise MigrationError("validation_identity_not_separate")
    if not target.execute("SELECT pg_try_advisory_lock(%s) AS locked",(LOCK,)).fetchone()["locked"]:
        raise MigrationError("migration_already_running")
    try:
        with source.transaction():
            source.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY")
            summary = source_summary(source,profile)
            if expected_rows is not None and summary["rows"]!=expected_rows:
                raise MigrationError("unexpected_source_row_count")
            job = open_job(target,source_name,identity,profile_hash,summary,compatible_profile_hashes)
            if validate_only and job["migrated_rows"]!=summary["rows"]:
                raise MigrationError("migration_incomplete")
            batches = 0
            while not validate_only and (rows := source_page(source,list(profile["columns"]),job["last_legacy_id"],batch_size)):
                job = write_batch(target,rows,profile,migration_client,job)
                batches += 1
                if max_batches is not None and batches>=max_batches and job["migrated_rows"]<summary["rows"]:
                    target.execute("UPDATE public.migration_jobs SET status='paused',updated_at=clock_timestamp() WHERE job_id=1")
                    return {"passed":False,"complete":False,"status":"paused","migrated_rows":job["migrated_rows"],"source_rows":summary["rows"]}
        # Persist invalidation before the validating transaction: rollback must
        # never leave a previous successful marker on data that failed recheck.
        target.execute("UPDATE public.migration_jobs SET status='validating',validated_at=NULL,updated_at=clock_timestamp() WHERE job_id=1")
        with target.transaction():
            target.execute("LOCK TABLE public.anggota_protected IN SHARE MODE")
            with source.transaction():
                source.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY")
                if source_summary(source,profile)!=summary:
                    raise MigrationError("source_changed_during_migration")
                result = validate_all(source,target,profile,summary,validation_client)
            # Check a fresh snapshot again while target writers remain excluded.
            with source.transaction():
                source.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY")
                if source_summary(source,profile)!=summary:
                    raise MigrationError("source_changed_during_migration")
            target.execute("UPDATE public.migration_jobs SET status='validated',validated_at=clock_timestamp(),updated_at=clock_timestamp() WHERE job_id=1")
        return {**result,"complete":True,"status":"validated","source":source_name,"target":target_name,
                "expected_rows":expected_rows,
                "source_rows":summary["rows"],"migrated_rows":job["migrated_rows"],"profile_sha256":job["profile_sha256"],
                "profile_canonical_sha256":profile_hash,
                "source_sha256":summary["sha256"],"checked_at_utc":datetime.now(timezone.utc).isoformat()}
    finally:
        target.execute("SELECT pg_advisory_unlock(%s)",(LOCK,))
