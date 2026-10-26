import argparse
import uuid

from faker import Faker
import psycopg

from passwords import PasswordService


TENANT_NAMESPACE = uuid.UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")


def generate_rows(total: int, seed: int):
    faker = Faker("id_ID")
    Faker.seed(seed)
    passwords = PasswordService()
    for number in range(1, total + 1):
        tenant_number = ((number - 1) % 10) + 1
        tenant_id = uuid.uuid5(TENANT_NAMESPACE, f"tenant:{tenant_number}")
        yield (
            tenant_id,
            faker.name(),
            faker.unique.email(),
            faker.phone_number(),
            f"9999{number:012d}",
            passwords.hash(f"Dummy-Only-{number:08d}"),
        )


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dsn", required=True)
    parser.add_argument("--rows", type=int, default=10_000)
    parser.add_argument("--seed", type=int, default=2026)
    args = parser.parse_args()
    with psycopg.connect(args.dsn) as connection:
        with connection.cursor() as cursor:
            with cursor.copy(
                """
                COPY lab_v1.customers (
                    tenant_id, full_name, email, phone, national_id, password_hash
                ) FROM STDIN
                """
            ) as copy:
                for row in generate_rows(args.rows, args.seed):
                    copy.write_row(row)


if __name__ == "__main__":
    main()

