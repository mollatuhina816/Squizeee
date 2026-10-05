"""Create the local app database using an existing PostgreSQL administrator."""
from pathlib import Path
import secrets
import psycopg
from psycopg import sql


def main():
    env_path = Path(__file__).with_name('.env')
    if env_path.exists():
        raise SystemExit('Existing backend/.env preserved; configure the database manually.')
    password = secrets.token_hex(32)
    with psycopg.connect('host=localhost port=5432 dbname=postgres user=postgres connect_timeout=3', autocommit=True) as db:
        if db.execute("SELECT 1 FROM pg_roles WHERE rolname = 'quizeee'").fetchone():
            raise SystemExit('Existing quizeee role preserved; configure its credentials manually.')
        database_exists = db.execute("SELECT 1 FROM pg_database WHERE datname = 'quizeee'").fetchone()
        db.execute(sql.SQL('CREATE ROLE quizeee LOGIN PASSWORD {}').format(sql.Literal(password)))
        if not database_exists:
            db.execute('CREATE DATABASE quizeee OWNER quizeee')
        db.execute('GRANT CONNECT ON DATABASE quizeee TO quizeee')
    with psycopg.connect('host=localhost port=5432 dbname=quizeee user=postgres connect_timeout=3', autocommit=True) as db:
        db.execute('GRANT USAGE, CREATE ON SCHEMA public TO quizeee')
        db.execute('GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO quizeee')
        db.execute('GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO quizeee')
    env_path.write_text(
        f'DATABASE_URL=postgresql+psycopg://quizeee:{password}@localhost:5432/quizeee\n'
        'REDIS_URL=redis://127.0.0.1:6379/0\n'
        f'JWT_SECRET={secrets.token_hex(32)}\n'
        'APP_ORIGIN=http://localhost:3000\nENVIRONMENT=development\n', encoding='utf-8')
    print('Configured quizeee role/database and backend/.env; existing data preserved and credentials not printed.')


if __name__ == '__main__':
    main()
