"""Manage a private, socket-only PostgreSQL cluster for local development."""
import argparse
import getpass
import json
from pathlib import Path
import re
import shlex
import shutil
import subprocess
from uuid import uuid4

import psycopg
from psycopg.conninfo import make_conninfo

from application.config import LOCAL_CONFIG, PROJECT_ROOT
from database.manage import bootstrap_household, grant_app_role, migrate

APP_ROLE = "menuagent_app"
DATABASE_NAME = "menuagent_dev"


def pg_command(name):
    found = shutil.which(name)
    if found:
        return found
    raise RuntimeError(f"Install PostgreSQL and put {name} on PATH.")


def run_pg(args, **kwargs):
    result = subprocess.run(args, capture_output=True, text=True, **kwargs)
    if result.returncode:
        raise RuntimeError("PostgreSQL command failed. Check the private cluster's server.log.")
    return result


def start(data_dir, socket_dir, port):
    if subprocess.run([pg_command('pg_ctl'), '-D', str(data_dir), 'status'], capture_output=True).returncode == 0:
        return
    options = shlex.join(['-p', str(port), '-k', str(socket_dir), '-h', ''])
    run_pg([pg_command('pg_ctl'), '-D', str(data_dir), '-l', str(data_dir / 'server.log'), '-o', options, '-w', 'start'])


def setup(data_dir: Path, port=55432):
    if LOCAL_CONFIG.exists():
        saved = json.loads(LOCAL_CONFIG.read_text())
        if Path(saved['data_dir']) != data_dir or saved['port'] != port:
            raise ValueError("A local configuration already exists for another cluster. Use its start/stop commands.")
    admin_user = getpass.getuser()
    if not re.fullmatch(r'[A-Za-z_][A-Za-z0-9_-]*', admin_user):
        raise ValueError("The local operating-system username cannot be mapped to PostgreSQL peer access.")
    marker = data_dir / '.menuagent-managed'
    if data_dir.exists() and not marker.exists():
        raise ValueError("Choose a new directory; this path is not a managed MenuAgent cluster.")
    if not data_dir.exists():
        data_dir.parent.mkdir(parents=True, exist_ok=True)
        run_pg([pg_command('initdb'), '-D', str(data_dir), '--encoding=UTF8', '--locale=C', '--auth-local=peer', '--auth-host=reject'])
        marker.write_text('MenuAgent local development cluster\n')
        hba = data_dir / 'pg_hba.conf'
        hba.write_text('local all all peer map=menuagent_local\n' + hba.read_text())
        with (data_dir / 'pg_ident.conf').open('a') as mapping:
            mapping.write(f'\nmenuagent_local {admin_user} {admin_user}\nmenuagent_local {admin_user} {APP_ROLE}\n')
    socket_dir = data_dir.parent / 'socket'
    socket_dir.mkdir(mode=0o700, exist_ok=True)
    socket_dir.chmod(0o700)
    start(data_dir, socket_dir, port)
    admin_base = make_conninfo(host=str(socket_dir), port=port, user=admin_user, dbname='postgres')
    with psycopg.connect(admin_base, autocommit=True) as conn:
        if not conn.execute('SELECT 1 FROM pg_roles WHERE rolname = %s', (APP_ROLE,)).fetchone():
            conn.execute('CREATE ROLE menuagent_app LOGIN NOSUPERUSER NOBYPASSRLS NOCREATEDB NOCREATEROLE')
        if not conn.execute('SELECT 1 FROM pg_database WHERE datname = %s', (DATABASE_NAME,)).fetchone():
            conn.execute('CREATE DATABASE menuagent_dev')
    admin = make_conninfo(admin_base, dbname=DATABASE_NAME)
    app = make_conninfo(admin, user=APP_ROLE)
    migrate(admin)
    grant_app_role(admin, APP_ROLE)
    household_id = json.loads(LOCAL_CONFIG.read_text())['household_id'] if LOCAL_CONFIG.exists() else str(uuid4())
    bootstrap_household(admin, household_id, 'My household', 'local-editor')
    LOCAL_CONFIG.parent.mkdir(mode=0o700, exist_ok=True)
    LOCAL_CONFIG.parent.chmod(0o700)
    config = {'database_url': app, 'household_id': household_id, 'access_mode': 'local', 'local_editor_subject': 'local-editor',
              'data_dir': str(data_dir), 'socket_dir': str(socket_dir), 'port': port}
    LOCAL_CONFIG.write_text(json.dumps(config, indent=2) + '\n')
    LOCAL_CONFIG.chmod(0o600)
    return admin, app


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=['setup', 'start', 'stop', 'status'])
    parser.add_argument('--data-dir', type=Path, default=PROJECT_ROOT / '.local' / 'postgres')
    parser.add_argument('--port', type=int, default=55432)
    parser.add_argument('--backend', choices=['auto', 'native', 'docker'], default='auto')
    args = parser.parse_args()
    try:
        if args.command == 'setup':
            backend = args.backend
            if backend == 'auto':
                if LOCAL_CONFIG.is_file():
                    backend = json.loads(LOCAL_CONFIG.read_text()).get('backend', 'native')
                else:
                    backend = 'docker' if shutil.which('docker') and subprocess.run(['docker', 'info', '--format', '{{.ServerVersion}}'], capture_output=True).returncode == 0 else 'native'
            if backend == 'docker':
                from database.docker_local import setup as docker_setup
                docker_setup(args.port)
            else:
                setup(args.data_dir.resolve(), args.port)
            print('Local database ready. Restart or reload Streamlit to use the saved household.')
            return
        if not LOCAL_CONFIG.is_file():
            raise ValueError('Run setup first.')
        saved = json.loads(LOCAL_CONFIG.read_text())
        if saved.get('backend') == 'docker':
            from database.docker_local import control
            control(args.command, saved)
            return
        data_dir = Path(saved['data_dir'])
        if not (data_dir / '.menuagent-managed').is_file():
            raise ValueError('The configured directory is not a managed MenuAgent cluster.')
        if args.command == 'start':
            start(data_dir, Path(saved['socket_dir']), saved['port'])
        elif args.command == 'stop':
            run_pg([pg_command('pg_ctl'), '-D', str(data_dir), '-m', 'fast', '-w', 'stop'])
        else:
            result = subprocess.run([pg_command('pg_ctl'), '-D', str(data_dir), 'status'], capture_output=True, text=True)
            print('Local PostgreSQL is running.' if result.returncode == 0 else 'Local PostgreSQL is stopped.')
    except (RuntimeError, ValueError, psycopg.Error) as error:
        parser.exit(1, f'Local database setup failed ({type(error).__name__}). {str(error) if not isinstance(error, psycopg.Error) else "Check the private server log."}\n')


if __name__ == '__main__':
    main()
