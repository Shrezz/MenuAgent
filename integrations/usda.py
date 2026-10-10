"""Fixed-host USDA lookup; every match requires household review."""
from datetime import datetime, timezone
from hashlib import sha256
import json
import os
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import urlopen

from application.domain.recipes import clean_food, normalize_name

CATALOG = Path(__file__).parent / 'data' / 'usda_foods.json'
NUTRIENT_IDS = {'protein': 1003, 'fat': 1004, 'carbs': 1005}


def parse_food(raw, state, aliases=(), retrieved_at=None):
    """FDC full detail or search nutrient records; never label serving totals."""
    fdc_id = int(raw['fdcId'])
    values = {}
    for entry in raw.get('foodNutrients', []):
        nutrient = entry.get('nutrient', {})
        amount = entry.get('amount', entry.get('value'))
        identifier = nutrient.get('id', entry.get('nutrientId'))
        unit = nutrient.get('unitName', entry.get('unitName', ''))
        if isinstance(amount, (int, float)) and not isinstance(amount, bool):
            values[identifier] = (amount, str(unit).casefold())
    nutrients = {key: values.get(identifier, (None, ''))[0] if values.get(identifier, (None, ''))[1] == 'g' else None
                 for key, identifier in NUTRIENT_IDS.items()}
    # Energy (kcal), with USDA's newer general/specific Atwater kcal fields.
    nutrients['kcal'] = next((values[i][0] for i in (1008, 2047, 2048) if i in values and values[i][1] == 'kcal'), None)
    return clean_food({'id': f'fdc:{fdc_id}', 'fdc_id': fdc_id, 'name': raw['description'], 'state': state,
                       'aliases': list(aliases), 'nutrients': nutrients,
                       'source_url': f'https://fdc.nal.usda.gov/food-details/{fdc_id}/nutrients',
                       'retrieved_at': retrieved_at or datetime.now(timezone.utc).isoformat(),
                       'source_hash': sha256(json.dumps(raw, sort_keys=True, separators=(',', ':')).encode()).hexdigest(),
                       'data_type': raw.get('dataType', 'Unknown')})


def bundled_foods():
    return {food['id']: clean_food(food) for food in json.loads(CATALOG.read_text())}


def match_candidates(foods, name, state=None):
    query = normalize_name(name)
    return [food for food in foods.values() if (state is None or food['state'] == state)
            and query in [normalize_name(food['name']), *food['aliases']]]


class USDAUnavailable(ValueError):
    pass


class USDAClient:
    def _get(self, path, parameters=None):
        key = os.environ.get('MENUAGENT_USDA_API_KEY')
        if not key:
            raise USDAUnavailable('Live USDA lookup needs MENUAGENT_USDA_API_KEY in the backend environment. The bundled source foods work without a key.')
        url = 'https://api.nal.usda.gov/fdc/v1/' + path + '?' + urlencode(dict(parameters or {}, api_key=key))
        try:
            with urlopen(url, timeout=15) as response:
                payload = response.read(5_000_001)
                if len(payload) > 5_000_000:
                    raise USDAUnavailable('The USDA response is too large. Try a narrower lookup.')
                return json.loads(payload)
        except (HTTPError, URLError, TimeoutError, OSError, ValueError):
            raise USDAUnavailable('USDA lookup is unavailable. Check backend configuration or try again later.') from None

    def search(self, query):
        if not query.strip():
            raise USDAUnavailable('Enter a food to search.')
        data = self._get('foods/search', {'query': query.strip(), 'pageSize': 10, 'dataType': 'Foundation,SR Legacy'})
        return [{'fdc_id': int(row['fdcId']), 'name': row['description'], 'data_type': row.get('dataType', '')} for row in data.get('foods', [])]

    def detail(self, fdc_id, state, aliases=()):
        identifier = int(fdc_id)
        if identifier <= 0:
            raise USDAUnavailable('Choose a valid USDA food identifier.')
        try:
            return parse_food(self._get(f'food/{identifier}'), state, aliases)
        except (KeyError, TypeError, ValueError) as error:
            if isinstance(error, USDAUnavailable):
                raise
            raise USDAUnavailable('The USDA record is incomplete or unsupported; it was not saved.') from None
