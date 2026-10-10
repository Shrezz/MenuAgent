"""Persistent development PostgreSQL in an isolated Docker container."""
from hashlib import sha256
import json
import os
from pathlib import Path
import secrets
import subprocess
import time
from uuid import uuid4

import psycopg
from psycopg import sql
from psycopg.conninfo import make_conninfo

from application.config import LOCAL_CONFIG, PROJECT_ROOT
from database.manage import bootstrap_household, grant_app_role, migrate

PRIVATE_ADMIN = PROJECT_ROOT / '.local' / 'postgres-admin.json'
APP_ROLE = 'menuagent_app'


def private_json(path, value):
    path.parent.mkdir(mode=0o700, exist_ok=True)
    path.parent.chmod(0o700)
    # Create with private permissions before writing credentials.
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(descriptor, 'w') as output:
        json.dump(value, output, indent=2)
        output.write('\n')
    path.chmod(0o600)


def docker(*args, env=None, check=True):
    result = subprocess.run(['docker', *args], env=env, capture_output=True, text=True)
    if check and result.returncode:
        raise RuntimeError('Docker operation failed. Check Docker is running and the local database port is available.')
    return result


def container_name():
    return 'menuagent-postgres-' + sha256(str(PROJECT_ROOT).encode()).hexdigest()[:10]


def setup(port=55432):
    name = container_name()
    if LOCAL_CONFIG.is_file():
        saved = json.loads(LOCAL_CONFIG.read_text())
        if saved.get('backend') != 'docker' or saved['port'] != port:
            raise ValueError('A different local database is already configured. Use its start/stop commands.')
    if PRIVATE_ADMIN.is_file():
        credentials = json.loads(PRIVATE_ADMIN.read_text())
    else:
        credentials = {'admin_password': secrets.token_urlsafe(32), 'app_password': secrets.token_urlsafe(32)}
        private_json(PRIVATE_ADMIN, credentials)
    inspected = docker('inspect', '--format', '{{index .Config.Labels "menuagent.managed"}}', name, check=False)
    if inspected.returncode == 0:
        if inspected.stdout.strip() != str(PROJECT_ROOT):
            raise ValueError('The container name belongs to another project.')
        docker('start', name)
    else:
        environment = dict(os.environ, POSTGRES_PASSWORD=credentials['admin_password'])
        docker('run', '--detach', '--name', name, '--label', f'menuagent.managed={PROJECT_ROOT}',
               '--publish', f'127.0.0.1:{port}:5432', '--mount', f'type=volume,source={name}-data,target=/var/lib/postgresql/data',
               '--env', 'POSTGRES_PASSWORD', '--env', 'POSTGRES_INITDB_ARGS=--auth-host=scram-sha-256', 'postgres:17', env=environment)
    admin_base = make_conninfo(host='127.0.0.1', port=port, user='postgres', dbname='postgres', password=credentials['admin_password'])
    deadline = time.monotonic() + 30
    while True:
        try:
            with psycopg.connect(admin_base, connect_timeout=2):
                break
        except psycopg.OperationalError:
            if time.monotonic() >= deadline:
                raise RuntimeError('The local PostgreSQL container did not become ready.') from None
            time.sleep(0.25)
    with psycopg.connect(admin_base, autocommit=True) as conn:
        if not conn.execute('SELECT 1 FROM pg_roles WHERE rolname = %s', (APP_ROLE,)).fetchone():
            conn.execute(sql.SQL('CREATE ROLE {} LOGIN NOSUPERUSER NOBYPASSRLS NOCREATEDB NOCREATEROLE PASSWORD {}')
                         .format(sql.Identifier(APP_ROLE), sql.Literal(credentials['app_password'])))
        if not conn.execute("SELECT 1 FROM pg_database WHERE datname = 'menuagent_dev'").fetchone():
            conn.execute('CREATE DATABASE menuagent_dev')
    admin = make_conninfo(admin_base, dbname='menuagent_dev')
    app = make_conninfo(admin, user=APP_ROLE, password=credentials['app_password'])
    migrate(admin)
    grant_app_role(admin, APP_ROLE)
    household_id = json.loads(LOCAL_CONFIG.read_text())['household_id'] if LOCAL_CONFIG.exists() else str(uuid4())
    bootstrap_household(admin, household_id, 'My household', 'local-editor')
    private_json(LOCAL_CONFIG, {'backend': 'docker', 'container': name, 'port': port, 'database_url': app,
                               'household_id': household_id, 'access_mode': 'local', 'local_editor_subject': 'local-editor'})
    private_json(PRIVATE_ADMIN, dict(credentials, admin_database_url=admin))
    return admin, app


def control(command, saved):
    name = saved['container']
    inspected = docker('inspect', '--format', '{{index .Config.Labels "menuagent.managed"}}', name)
    if inspected.stdout.strip() != str(PROJECT_ROOT):
        raise ValueError('The configured container belongs to another project.')
    if command == 'status':
        state = docker('inspect', '--format', '{{.State.Running}}', name).stdout.strip()
        print('Local PostgreSQL is running.' if state == 'true' else 'Local PostgreSQL is stopped.')
    else:
        docker(command, name)
