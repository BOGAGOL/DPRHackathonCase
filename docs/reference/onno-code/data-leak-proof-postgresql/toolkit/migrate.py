import argparse
import base64
import os
import random
import time
import uuid

import psycopg
from psycopg.errors import DeadlockDetected, SerializationFailure

from blind_index import blind_index, normalize_email, normalize_phone
from crypto_codec import AESGCMCodec, build_aad


CUSTOMER_NAMESPACE = uuid.UUID("bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb")
MAX_RETRIES = 5


def migrate_batch(connection, codec, index_key, key_version, batch_size):
    with connection.transaction():
        rows = connection.execute(
            """
            SELECT customer_id, tenant_id, full_name, email, phone,
                   national_id, password_hash
            FROM lab_v1.customers AS source
            WHERE NOT EXISTS (
              SELECT 1 FROM protected_v2.customers_secure AS target
              WHERE target.source_customer_id = source.customer_id
            )
            ORDER BY customer_id
            FOR UPDATE OF source SKIP LOCKED
            LIMIT %s
            """,
            (batch_size,),
        ).fetchall()

        for source_id, tenant_id, full_name, email, phone, national_id, password_hash in rows:
            customer_id = uuid.uuid5(CUSTOMER_NAMESPACE, f"{tenant_id}:{source_id}")
            email_value = normalize_email(email)
            phone_value = normalize_phone(phone) if phone else None

            def protect(column, value):
                if value is None:
                    return None
                aad = build_aad(tenant_id, "customers_secure", column, customer_id)
                return codec.encrypt(value.encode("utf-8"), aad, key_version)

            connection.execute(
                """
                INSERT INTO protected_v2.customers_secure (
                  customer_id, source_customer_id, tenant_id, full_name_token,
                  email_payload, email_bidx, phone_payload, phone_bidx,
                  national_id_payload, password_hash, protection_version,
                  key_version, migrated_at
                ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,1,%s,now())
                ON CONFLICT DO NOTHING
                """,
                (
                    customer_id,
                    source_id,
                    tenant_id,
                    f"customer-{customer_id}",
                    protect("email", email_value),
                    blind_index("email", email_value, index_key),
                    protect("phone", phone_value),
                    blind_index("phone", phone_value, index_key) if phone_value else None,
                    protect("national_id", national_id),
                    password_hash,
                    key_version,
                ),
            )

        connection.execute(
            """
            UPDATE migration_control.jobs
            SET rows_completed = rows_completed + %s,
                updated_at = now(), last_error_code = NULL
            WHERE job_name = 'customers_v1_to_v2'
            """,
            (len(rows),),
        )
    return len(rows)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dsn", required=True)
    parser.add_argument("--batch-size", type=int, default=100)
    parser.add_argument("--key-version", type=int, default=1)
    parser.add_argument("--max-batches", type=int)
    args = parser.parse_args()

    codec = AESGCMCodec({args.key_version: base64.b64decode(os.environ["AES_KEY_B64"], validate=True)})
    index_key = base64.b64decode(os.environ["BLIND_INDEX_KEY_B64"], validate=True)
    completed_batches = 0

    with psycopg.connect(args.dsn) as connection:
        while True:
            paused = connection.execute(
                "SELECT paused FROM migration_control.jobs WHERE job_name='customers_v1_to_v2'"
            ).fetchone()[0]
            if paused:
                print("migration_paused=true")
                return

            for attempt in range(MAX_RETRIES):
                try:
                    processed = migrate_batch(
                        connection, codec, index_key, args.key_version, args.batch_size
                    )
                    break
                except (DeadlockDetected, SerializationFailure):
                    connection.rollback()
                    if attempt == MAX_RETRIES - 1:
                        raise
                    time.sleep(min(8.0, 0.25 * (2**attempt)) + random.uniform(0, 0.2))

            print(f"processed={processed}")
            if processed == 0:
                return
            completed_batches += 1
            if args.max_batches is not None and completed_batches >= args.max_batches:
                return
            time.sleep(0.1)


if __name__ == "__main__":
    main()

