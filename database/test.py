"""Run the full suite against an isolated database using private local config."""
import json
import os
import subprocess
import sys

from application.config import LOCAL_CONFIG
from database.docker_local import PRIVATE_ADMIN
from psycopg.conninfo import make_conninfo


def main():
    if not LOCAL_CONFIG.is_file():
        raise SystemExit('Run python -m database.local setup first.')
    saved = json.loads(LOCAL_CONFIG.read_text())
    if saved.get('backend') == 'docker':
        admin = json.loads(PRIVATE_ADMIN.read_text())['admin_database_url']
    else:
        import getpass
        admin = make_conninfo(saved['database_url'], user=getpass.getuser())
    environment = dict(os.environ, MENUAGENT_TEST_ADMIN_DATABASE_URL=admin, MENUAGENT_TEST_DATABASE_URL=saved['database_url'])
    # Connection credentials stay in process memory, never command arguments.
    result = subprocess.run([sys.executable, '-m', 'unittest', 'discover', '-s', 'tests', '-v'], env=environment)
    raise SystemExit(result.returncode)


if __name__ == '__main__':
    main()
