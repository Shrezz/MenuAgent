"""Household-scoped durable jobs, immutable input snapshots and checked candidates."""
from datetime import date
from hashlib import sha256
import json
from uuid import UUID, uuid4
from psycopg.types.json import Jsonb

from database.connection import AccessDenied, ConcurrentChange


class PlanningCancelled(RuntimeError):
    pass


class MenuRepository:
    def __init__(self, household_repository):
        self.households = household_repository
        self.database, self.context = household_repository.database, household_repository.context

    def _household(self, conn):
        row = conn.execute('SELECT * FROM menuagent.households WHERE id = %s FOR SHARE', (self.context.household_id,)).fetchone()
        if row is None:
            raise AccessDenied('This editor does not have access to the configured household.')
        return row

    def start(self, week_start, expected_version, options, source_event=None, force=False):
        week = date.fromisoformat(str(week_start))
        if week.weekday() != 0:
            raise ValueError('Choose a week starting on Monday.')
        with self.database.transaction(self.context) as conn:
            household = self._household(conn)
            if household['version'] != expected_version:
                raise ConcurrentChange('Household inputs changed. Reload saved household data before planning.')
            # All inputs are read in this one repeatable-read transaction.
            members = conn.execute('SELECT id, name, kind, age_group, targets, dislikes, restrictions FROM menuagent.members WHERE household_id = %s ORDER BY id', (self.context.household_id,)).fetchall()
            for member in members:
                member['id'] = str(member['id'])
            stock = conn.execute('SELECT name AS "Item", location AS "Location", quantity AS "Quantity", unit AS "Unit", status AS "Status" FROM menuagent.inventory_items WHERE household_id = %s ORDER BY position', (self.context.household_id,)).fetchall()
            recipes = conn.execute('SELECT DISTINCT ON (recipe_id) document FROM menuagent.recipe_versions WHERE household_id = %s ORDER BY recipe_id, revision DESC', (self.context.household_id,)).fetchall()
            history = conn.execute("""SELECT DISTINCT ON (j.week_start) c.document FROM menuagent.menu_candidates c
                JOIN menuagent.planning_jobs j ON j.household_id = c.household_id AND j.id = c.job_id
                WHERE j.household_id = %s AND j.status = 'draft_ready' AND j.week_start < %s
                ORDER BY j.week_start DESC, c.created_at DESC LIMIT 4""", (self.context.household_id, week)).fetchall()
            prior = conn.execute('''SELECT c.document FROM menuagent.menu_candidates c
                JOIN menuagent.planning_jobs j ON j.household_id = c.household_id AND j.id = c.job_id
                WHERE j.household_id = %s AND j.week_start = %s ORDER BY c.created_at DESC LIMIT 1''',
                (self.context.household_id,week)).fetchone()
            pending = {rid:prior['document']['recipes'][rid] for rid in prior['document'].get('unreviewed_ids',[]) if rid in prior['document']['recipes']} if prior else {}
            snapshot = {'week_start': week.isoformat(), 'input_version': expected_version, 'members': members, 'inventory': stock,
                        'recipes': {r['document']['id']: r['document'] for r in recipes},
                        'settings': {k: household[k] for k in ('cuisines','cooking_effort','meal_prep','busy_days')},
                        'options': options, 'proposal_recipes':pending,
                        'history_families': [r['dish_family'] for h in history for r in h['document'].get('recipes', {}).values()]}
            identity = {'week': week.isoformat(), 'version': expected_version, 'options': options,
                        'source': source_event, 'nonce': str(uuid4()) if force else None}
            key = sha256(json.dumps(identity, sort_keys=True).encode()).hexdigest()
            job_id = str(uuid4())
            conn.execute('INSERT INTO menuagent.planning_jobs (household_id,id,week_start,input_version,request_key,snapshot) VALUES (%s,%s,%s,%s,%s,%s) ON CONFLICT DO NOTHING',
                         (self.context.household_id, job_id, week, expected_version, key, Jsonb(snapshot)))
            row = conn.execute('SELECT id FROM menuagent.planning_jobs WHERE household_id = %s AND request_key = %s', (self.context.household_id, key)).fetchone()
        return str(row['id'])

    def list(self, week_start=None):
        with self.database.transaction(self.context) as conn:
            self._household(conn)
            # A request interrupted by a dead app process remains inspectable.
            conn.execute("UPDATE menuagent.planning_jobs SET status = 'failed', progress = 'Worker stopped. Generate a new draft to retry.', updated_at = now() WHERE household_id = %s AND status = 'running' AND updated_at < now() - interval '12 minutes'", (self.context.household_id,))
            rows = conn.execute('SELECT id, week_start, input_version, status, progress, created_at FROM menuagent.planning_jobs WHERE household_id = %s AND (%s::date IS NULL OR week_start = %s) ORDER BY created_at DESC LIMIT 30', (self.context.household_id, week_start, week_start)).fetchall()
        return [dict(r, id=str(r['id'])) for r in rows]

    def claim(self, job_id):
        with self.database.transaction(self.context) as conn:
            self._household(conn)
            row = conn.execute("UPDATE menuagent.planning_jobs SET status = 'running', progress = 'Reading household inputs', updated_at = now() WHERE household_id = %s AND id = %s AND status = 'queued' RETURNING snapshot", (self.context.household_id, str(UUID(job_id)))).fetchone()
        return row['snapshot'] if row else None

    def progress(self, job_id, message):
        with self.database.transaction(self.context) as conn:
            changed = conn.execute("UPDATE menuagent.planning_jobs SET progress = %s, updated_at = now() WHERE household_id = %s AND id = %s AND status = 'running'", (message[:500], self.context.household_id, job_id))
            if not changed.rowcount:
                raise PlanningCancelled('Planning was cancelled or stopped.')

    def cancel(self, job_id):
        with self.database.transaction(self.context) as conn:
            self._household(conn)
            conn.execute("UPDATE menuagent.planning_jobs SET status = 'cancelled', progress = 'Cancelled by the household editor', updated_at = now() WHERE household_id = %s AND id = %s AND status IN ('queued','running')", (self.context.household_id, job_id))

    def finish(self, job_id, status, message):
        if status not in ('draft_ready', 'needs_input', 'failed'):
            raise ValueError('Unsupported planning result.')
        with self.database.transaction(self.context) as conn:
            household = self._household(conn)
            job = conn.execute("SELECT input_version, status FROM menuagent.planning_jobs WHERE household_id = %s AND id = %s FOR UPDATE", (self.context.household_id, job_id)).fetchone()
            if not job or job['status'] != 'running':
                raise PlanningCancelled('Planning was cancelled or stopped.')
            if household['version'] != job['input_version']:
                status, message = 'needs_input', 'Inputs changed during planning. Reload the household and generate a new draft.'
            if status == 'draft_ready':
                checked = conn.execute('SELECT document FROM menuagent.menu_candidates WHERE household_id = %s AND job_id = %s ORDER BY created_at DESC LIMIT 1', (self.context.household_id,job_id)).fetchone()
                if not checked or not checked['document']['report']['ready']:
                    raise ValueError('A ready job requires its latest saved candidate to pass validation.')
            conn.execute('UPDATE menuagent.planning_jobs SET status = %s, progress = %s, updated_at = now() WHERE household_id = %s AND id = %s', (status, message[:500], self.context.household_id, job_id))

    def save_candidate(self, job_id, document):
        # The worker validates each candidate. Recompute here to bind the saved
        # report to its exact menu and immutable job inputs, not a supplied flag.
        from agent.runtime import assess_candidate
        with self.database.transaction(self.context) as conn:
            household = self._household(conn)
            # Serialize saving/finalizing with cancellation: a cancelled job
            # cannot be revived or receive a later candidate from another session.
            job = conn.execute('SELECT snapshot, status FROM menuagent.planning_jobs WHERE household_id = %s AND id = %s FOR UPDATE', (self.context.household_id, job_id)).fetchone()
            if not job or job['status'] != 'running':
                raise PlanningCancelled('Planning was cancelled or stopped.')
            originals = job['snapshot']['recipes']
            if any(rid in originals and recipe != originals[rid] for rid,recipe in document['recipes'].items()):
                raise ValueError('Saved recipe snapshots cannot be changed by the planner.')
            if any(rid not in originals and rid not in document['unreviewed_ids'] for rid in document['recipes']):
                raise ValueError('New recipes must be marked for review.')
            report = assess_candidate(job['snapshot'], document['menu'], document['recipes'], document['unreviewed_ids'])
            document = dict(document, report=report, members=job['snapshot']['members'], settings=job['snapshot']['settings'])
            if household['version'] != job['snapshot']['input_version']:
                report['ready'] = False
                report['issues'].append({'code':'stale_inputs','severity':'required','message':'Household inputs changed during planning. Generate a new draft.','slot_id':None})
            conn.execute('INSERT INTO menuagent.menu_candidates (household_id,id,job_id,document) VALUES (%s,%s,%s,%s)', (self.context.household_id, document['menu']['version_id'], job_id, Jsonb(document)))
        return document

    def candidate(self, job_id):
        with self.database.transaction(self.context) as conn:
            self._household(conn)
            row = conn.execute('SELECT document FROM menuagent.menu_candidates WHERE household_id = %s AND job_id = %s ORDER BY created_at DESC LIMIT 1', (self.context.household_id, job_id)).fetchone()
        return row['document'] if row else None
