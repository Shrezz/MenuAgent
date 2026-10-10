"""Application queue facade; model work runs outside Streamlit's request thread."""
from application.repositories.menus import MenuRepository
from application.domain.recipes import STATES
from workers.planning import dispatch

DEFAULT_OPTIONS = {'web':True,'new_recipes':True,'vegetarian':True,'allow_shopping':True,'cuisine':'South Indian','stock_states':{}}


def clean_options(options):
    result = dict(DEFAULT_OPTIONS, **(options or {}))
    if set(result) != set(DEFAULT_OPTIONS) or any(not isinstance(result[k],bool) for k in ('web','new_recipes','vegetarian','allow_shopping')):
        raise ValueError('Choose supported planning options.')
    if not isinstance(result['cuisine'],str) or not result['cuisine'].strip() or len(result['cuisine']) > 120:
        raise ValueError('Choose a cuisine focus of up to 120 characters.')
    states = result['stock_states']
    if not isinstance(states,dict) or len(states) > 1000 or any(not isinstance(k,str) or len(k) > 300 or v not in STATES for k,v in states.items()):
        raise ValueError('Review supported stock preparation states.')
    return result


class MenuPlanner:
    def __init__(self, owner):
        self.owner = owner
        self.repository = MenuRepository(owner.repository)

    def start(self, options=None, source_event=None, force=False):
        options = clean_options(options)
        job_id = self.repository.start(self.owner.week_start,self.owner.household_version,options,source_event,force)
        dispatch(self.repository,job_id)
        return job_id

    def jobs(self, week=None):
        rows = self.repository.list(week)
        queued = next((j for j in reversed(rows) if j['status'] == 'queued'),None)
        if queued:
            dispatch(self.repository,queued['id'])
        return rows
