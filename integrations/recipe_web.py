"""Bounded search on a vegetarian publisher, with retained recipe provenance."""
from hashlib import sha256
from html import unescape
from html.parser import HTMLParser
import json
from urllib.parse import urlencode, urlsplit
from urllib.request import Request, HTTPRedirectHandler, ProxyHandler, build_opener
from xml.etree import ElementTree as ET
from uuid import uuid4
import re

from application.domain.recipes import clean_recipe

HOST = 'www.vegrecipesofindia.com'


class RecipeWebUnavailable(RuntimeError):
    pass


def checked_url(url):
    parsed = urlsplit(url)
    if parsed.scheme != 'https' or parsed.hostname != HOST or parsed.username or parsed.password or parsed.port not in (None, 443):
        raise ValueError('Use an HTTPS recipe from www.vegrecipesofindia.com.')
    return url


class PublisherRedirects(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        checked_url(newurl)
        return super().redirect_request(req, fp, code, msg, headers, newurl)


class RecipeScripts(HTMLParser):
    def __init__(self):
        super().__init__()
        self.active, self.current, self.scripts = False, [], []

    def handle_starttag(self, tag, attrs):
        if tag == 'script' and dict(attrs).get('type') == 'application/ld+json':
            self.active, self.current = True, []

    def handle_data(self, data):
        if self.active:
            self.current.append(data)

    def handle_endtag(self, tag):
        if tag == 'script' and self.active:
            self.scripts.append(''.join(self.current))
            self.active = False


class RecipeLinks(HTMLParser):
    def __init__(self):
        super().__init__()
        self.url, self.parts, self.links = None, [], []

    def handle_starttag(self, tag, attrs):
        if tag == 'a':
            url = dict(attrs).get('href','')
            try:
                checked_url(url)
                if urlsplit(url).path.count('/') == 2 and urlsplit(url).path not in ('/about/','/contact/','/recipes/','/privacy-policy/','/dassana-cookbook/'):
                    self.url, self.parts = url, []
            except ValueError:
                pass

    def handle_data(self, data):
        if self.url:
            self.parts.append(data)

    def handle_endtag(self, tag):
        if tag == 'a' and self.url:
            title = ' '.join(' '.join(self.parts).split())
            if title and len(title) <= 200:
                self.links.append({'title':title,'url':self.url})
            self.url = None


def plain(value):
    class TextOnly(HTMLParser):
        def __init__(self):
            super().__init__()
            self.parts = []
        def handle_data(self, text):
            self.parts.append(text)
    parser = TextOnly()
    parser.feed(str(value))
    return ' '.join(unescape(' '.join(parser.parts)).split())


def parse_recipe_page(payload, url):
    checked_url(url)
    parser = RecipeScripts()
    parser.feed(payload.decode('utf-8', errors='replace'))
    queue = []
    for script in parser.scripts:
        try:
            queue.append(json.loads(script))
        except ValueError:
            continue
    for _ in range(10000):
        if not queue:
            break
        node = queue.pop()
        if isinstance(node, list):
            queue.extend(node)
        elif isinstance(node, dict):
            types = node.get('@type', [])
            types = [types] if isinstance(types, str) else types
            if 'Recipe' in types:
                steps = []
                pending = list(node.get('recipeInstructions', [])) if isinstance(node.get('recipeInstructions'), list) else [node.get('recipeInstructions', '')]
                while pending and len(steps) < 100:
                    step = pending.pop(0)
                    if isinstance(step, dict):
                        if step.get('text'):
                            steps.append(plain(step['text']))
                        pending.extend(step.get('itemListElement', []))
                    elif isinstance(step, str) and step.strip():
                        steps.append(plain(step))
                ingredients = node.get('recipeIngredient', [])
                if not isinstance(ingredients, list) or not ingredients or not steps:
                    raise RecipeWebUnavailable('This page has no usable structured recipe. Open the source to review it.')
                return {'title': plain(node.get('name', 'Recipe'))[:200], 'url': url,
                        'ingredients': [plain(x)[:500] for x in ingredients[:100]],
                        'instructions': [x[:2000] for x in steps], 'yield': str(node.get('recipeYield', ''))[:200],
                        'category': str(node.get('recipeCategory', ''))[:300],
                        'cuisine': str(node.get('recipeCuisine', ''))[:300], 'source_hash': sha256(payload).hexdigest()}
            queue.extend(v for v in node.values() if isinstance(v, (dict, list)))
    raise RecipeWebUnavailable('This page does not expose a structured recipe. The source link remains available.')


class RecipeWebClient:
    def __init__(self):
        self.opener = build_opener(ProxyHandler({}), PublisherRedirects())

    def _fetch(self, url):
        checked_url(url)
        try:
            with self.opener.open(Request(url, headers={'User-Agent':'MenuAgent/0.5 (personal recipe planning)'}), timeout=12) as response:
                checked_url(response.url)
                data = response.read(3_000_001)
            if len(data) > 3_000_000:
                raise RecipeWebUnavailable('The recipe page is too large to import.')
            return data
        except (OSError, ValueError):
            raise RecipeWebUnavailable('The recipe website is unavailable or blocked this request. Source links can still be reviewed manually.') from None

    def search(self, query='south indian', limit=12):
        if not isinstance(query, str) or not query.strip() or len(query) > 160:
            raise ValueError('Enter a recipe search of up to 160 characters.')
        if 'south indian' in query.casefold():
            data = self._fetch('https://' + HOST + '/recipes/south-indian-recipes/')
            parser = RecipeLinks()
            parser.feed(data.decode('utf-8', errors='replace'))
            seen, links = set(), []
            for link in parser.links:
                if link['url'] not in seen:
                    seen.add(link['url'])
                    links.append(link)
            return links[:min(limit,20)]
        data = self._fetch('https://' + HOST + '/?' + urlencode({'s': query.strip(), 'feed':'rss2'}))
        try:
            root = ET.fromstring(data)
            results, seen = [], set()
            for item in root.findall('./channel/item'):
                url, title = item.findtext('link'), plain(item.findtext('title') or '')
                if not url or not title or url in seen:
                    continue
                checked_url(url)
                seen.add(url)
                results.append({'title':title[:200], 'url':url})
            return results[:min(limit, 20)]
        except (ET.ParseError, ValueError):
            raise RecipeWebUnavailable('The recipe search returned unreadable results.') from None

    def read(self, url):
        return parse_recipe_page(self._fetch(url), url)


def source_to_draft(source, meal_type='Dinner'):
    """Import source text without guessing cup weights or nutrient matches."""
    lines = []
    for original in source['ingredients']:
        grams = re.match(r'^\s*(\d+(?:\.\d+)?)\s*(?:g|grams?)\b\s*(.*)', original, re.I)
        name = grams.group(2).strip(' -–') if grams else original
        lines.append({'name':name[:200], 'quantity':float(grams.group(1)) if grams else None,
            'unit':'g', 'state':'as sold', 'component':'Main dish', 'food':None,
            'source_ingredient_text':original, 'grams_per_unit':None,'conversion_note':''})
    yield_number = re.fullmatch(r"\[?['\"]?(\d+(?:\.\d+)?)['\"]?\]?", source.get('yield','').strip())
    servings = float(yield_number.group(1)) if yield_number else 4
    return clean_recipe({'id':str(uuid4()),'revision':0,'name':source['title'],'dish_family':source['title'],
        'meal_type':meal_type,'cuisine':'South Indian','servings':servings,
        'source_label':'Web import; review serving yield, ingredient states, quantities and dietary details',
        'source_url':source['url'],'source_hash':source['source_hash'],'source_yield':source.get('yield',''),
        'source_ingredients':source['ingredients'],
        'effort':None,'active_minutes':None,'equipment':[],
        'ingredients':lines,'instructions':source['instructions'],'restriction_reviewed':False,
        'allergens':[],'dietary_tags':[]})
