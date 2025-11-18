import json
import logging
import pathlib
import re
import unicodedata
import urllib.parse

import httpx
from bs4 import BeautifulSoup

BASE_URL = 'https://www.camarapoa.rs.gov.br'
OUTPUT_DIR = pathlib.Path('data')
PDF_DIR = OUTPUT_DIR / 'pdfs'
JSON_FILE = OUTPUT_DIR / 'projects.json'

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    datefmt='%H:%M:%S',
)
logger = logging.getLogger(__name__)


class CamaraScraper:
    def __init__(self):
        self.client = httpx.Client(
            timeout=30.0,
            follow_redirects=True,
            headers={
                'User-Agent': 'Mozilla/5.0 (compatible; VozCivicaBot/0.1; +https://github.com/mdfguerra)',
                'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
            },
        )
        self.results: list[dict] = []
        self._setup_directories()

    def _setup_directories(self):
        PDF_DIR.mkdir(parents=True, exist_ok=True)

    def _extract_sjr_html(self, text: str) -> str:
        """Extracts HTML embedded in Rails SJR (JavaScript) responses."""
        if match := re.search(r"\.html\(['\"](.*?)['\"]\)", text, re.DOTALL):
            return (
                match.group(1)
                .replace("\\'", "'")
                .replace('\\"', '"')
                .replace('\\n', '\n')
                .replace('\\/', '/')
            )
        return text

    def _to_snake_case(self, text: str) -> str:
        """Converts text to snake_case (e.g., 'Data de Criação' -> 'data_de_criacao')."""
        # Normalize unicode (remove accents, e.g., ã -> a)
        text = (
            unicodedata.normalize('NFKD', text)
            .encode('ascii', 'ignore')
            .decode('utf-8')
        )
        # Lowercase and replace non-alphanumeric chars with underscore
        text = re.sub(r'[^a-z0-9]', '_', text.lower())
        # Remove repeated underscores and strip edges
        return re.sub(r'_+', '_', text).strip('_')

    def _get_soup(self, url: str, params: dict | None = None) -> BeautifulSoup:
        resp = self.client.get(url, params=params)
        resp.raise_for_status()

        content = resp.text
        if 'text/javascript' in resp.headers.get('content-type', ''):
            content = self._extract_sjr_html(content)

        return BeautifulSoup(content, 'html.parser')

    def get_project_links(self, limit: int = 3) -> list[str]:
        """Fetches project URLs from the search page."""
        logger.info('Searching for PLL projects...')
        search_url = f'{BASE_URL}/processos'
        params = {'utf8': '✓', 'by_tipo': 'PLL', 'commit': 'Pesquisar'}

        try:
            soup = self._get_soup(search_url, params)
            links = set()

            for a in soup.find_all('a', href=re.compile(r'/processos/\d+$')):
                if 'PLL' in a.get_text(strip=True).upper():
                    links.add(urllib.parse.urljoin(BASE_URL, a['href']))

            links = list(links)[:limit]
            logger.info(f'Found {len(links)} projects to process.')
            return links
        except httpx.RequestError as e:
            logger.error(f'Search failed: {e}')
            return []

    def process_project(self, url: str):
        """Extracts metadata and downloads PDFs for a single project."""
        try:
            logger.info(f'Processing: {url}')
            soup = self._get_soup(url)

            # 1. Extract Metadata
            data = {'url': url, 'id': url.split('/')[-1], 'metadata': {}}

            if id_container := soup.find('div', attrs={'data-tab': 'dados'}):
                for dt in id_container.select('dl.dados dt'):
                    raw_key = dt.get_text(strip=True)
                    key = self._to_snake_case(raw_key)

                    if dd := dt.find_next_sibling('dd'):
                        data['metadata'][key] = dd.get_text(strip=True)

            # 2. Check Tabs
            data['has_votacoes'] = bool(
                soup.find('div', attrs={'data-tab': 'votacoes'})
            )
            data['has_tramitacoes'] = bool(
                soup.find('div', attrs={'data-tab': 'tramitacoes'})
            )
            data['files'] = []

            # 3. Download Documents
            if docs_container := soup.find('div', attrs={'data-tab': 'documentos'}):
                project_pdf_dir = PDF_DIR / data['id']
                project_pdf_dir.mkdir(exist_ok=True)

                for link in docs_container.find_all(
                    'a', href=re.compile(r'\.pdf', re.IGNORECASE)
                ):
                    file_url = urllib.parse.urljoin(BASE_URL, link['href'])
                    name_text = link.get_text(strip=True) or 'document'

                    filename = re.sub(r'[\\/*?:"<>|]', '', name_text).strip() + '.pdf'
                    save_path = project_pdf_dir / filename

                    with self.client.stream('GET', file_url) as r:
                        r.raise_for_status()
                        with open(save_path, 'wb') as f:
                            for chunk in r.iter_bytes():
                                f.write(chunk)

                    data['files'].append(
                        {
                            'name': name_text,
                            'local_path': str(save_path),
                            'remote_url': file_url,
                        }
                    )

            self.results.append(data)

        except Exception as e:
            logger.error(f'Failed to process {url}: {e}')

    def save_json(self):
        """Saves collected data to JSON."""
        with open(JSON_FILE, 'w', encoding='utf-8') as f:
            json.dump(self.results, f, ensure_ascii=False, indent=2)
        logger.info(f'Data saved to {JSON_FILE}')

    def close(self):
        self.client.close()


if __name__ == '__main__':
    scraper = CamaraScraper()
    try:
        links = scraper.get_project_links(limit=3)
        for link in links:
            scraper.process_project(link)
        scraper.save_json()
    finally:
        scraper.close()
