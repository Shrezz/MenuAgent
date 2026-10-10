"""Durable queue in PostgreSQL; one local daemon thread processes a job at a time."""
import argparse
from threading import Lock, Thread

from agent.runtime import PlanningAgent
from agent.state import PlanningBudgetExceeded
from application.repositories.menus import PlanningCancelled
from database.connection import StorageUnavailable, AccessDenied

_worker_lock = Lock()


def run_job(repository, job_id, agent=None):
    snapshot = repository.claim(job_id)
    if snapshot is None:
        return
    try:
        runtime = agent or PlanningAgent()
        status, message = runtime.run(snapshot, lambda message:repository.progress(job_id,message),
                                     lambda document:repository.save_candidate(job_id,document))
        repository.finish(job_id,status,message)
    except PlanningCancelled:
        return
    except PlanningBudgetExceeded:
        repository.finish(job_id,'needs_input','Execution limit reached. Review any saved candidate or generate a new draft.')
    except (ValueError, RuntimeError, TypeError, KeyError, OverflowError):
        # Raw model/HTTP/database exceptions may contain private household data.
        repository.finish(job_id,'failed','Planning could not finish. Check Ollama and the recipe inputs, then generate a new draft. Any saved candidate is retained.')


def dispatch(repository, job_id):
    if not _worker_lock.acquire(blocking=False):
        return
    def execute():
        try:
            run_job(repository,job_id)
        except (StorageUnavailable, AccessDenied, PlanningCancelled):
            pass  # A revoked editor cannot write a job result or see its inputs.
        finally:
            _worker_lock.release()
    try:
        Thread(target=execute,name='menuagent-planner',daemon=True).start()
    except RuntimeError:
        _worker_lock.release()
        raise


def main():
    parser = argparse.ArgumentParser(description='Run queued jobs for the configured local household.')
    parser.add_argument('--once', action='store_true', help='Process at most one queued job.')
    args = parser.parse_args()
    from application.config import RuntimeConfig
    from application.repositories.households import HouseholdRepository
    from application.repositories.menus import MenuRepository
    from database.connection import Database, EditorContext
    config = RuntimeConfig.load()
    if config.mode != 'postgres' or config.access_mode != 'local':
        parser.error('Configure the local PostgreSQL household before using this worker.')
    repository = MenuRepository(HouseholdRepository(Database(config.database_url),EditorContext(config.household_id,config.local_editor_subject)))
    for job in reversed(repository.list()):
        if job['status'] == 'queued':
            run_job(repository,job['id'])
            if args.once:
                break


if __name__ == '__main__':
    main()
