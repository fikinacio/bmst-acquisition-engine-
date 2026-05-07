"""
HTTP scraper for Angolan job board sources.

Target sources (all scraped by scrape_all_sources):
  - emprego.co.ao
  - jobartis.com/ao
  - angoemprego.co.ao

Rate limiting: minimum 2 seconds between requests to the same domain.

HIGH_FRICTION_KEYWORDS and MEDIUM_FRICTION_KEYWORDS are imported by classifier.py.

Public API
----------
scrape_source(url) -> list[dict]
    Scrape a single URL. Return list of raw listing dicts.
    Each dict: { company_name, job_title, description, url, source }

scrape_all_sources() -> list[dict]
    Call scrape_source for every configured source; return merged list.
"""

import time
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup
from loguru import logger

# ── Friction keyword lists (PRD Section 7) ────────────────────────────────────
# Used by classifier.py for fast pre-filtering before the LLM call.

HIGH_FRICTION_KEYWORDS: list[str] = [
    # Portuguese — direct signals
    "entrada de dados",
    "registo manual",
    "arquivo fisico",
    "arquivo manual",
    "controlo manual",
    "folha de calculo",
    "processamento de facturas",
    "emissao de facturas",
    "facturacao manual",
    "processamento manual",
    "reconciliacao bancaria",
    "reconciliacao contabilistica",
    "gestao de stock manual",
    "controlo de stock",
    "inventario manual",
    "processamento de salarios",
    "folha de pagamento",
    "controlo de ponto manual",
    "relatorios manuais",
    "elaboracao de relatorios",
    "controlo de documentos",
    "arquivo documental",
    "processamento de pedidos",
    "tratamento de encomendas",
    "controlo de despesas",
    "gestao de despesas manual",
    "controlo de caixa manual",
    "lancamentos contabilisticos",
    "digitacao",
    # English equivalents
    "data entry",
    "manual processing",
    "manual data",
    "invoice processing",
    "manual reconciliation",
    "spreadsheet management",
    "manual reporting",
    "document control",
    "order processing",
    "manual inventory",
    "manual payroll",
    "manual filing",
    "paper-based",
    "paper based",
]

MEDIUM_FRICTION_KEYWORDS: list[str] = [
    # Portuguese — operational roles implying manual work
    "assistente administrativo",
    "assistente operacional",
    "assistente de escritorio",
    "auxiliar administrativo",
    "tecnico administrativo",
    "coordenador",
    "supervisor operacional",
    "responsavel operacional",
    "gestor operacional",
    "aprovisionamento",
    "compras",
    "logistica",
    "expedicao",
    "distribuicao",
    "armazem",
    "stock",
    "atendimento ao cliente",
    "servico ao cliente",
    "gestao de contratos",
    "operacoes",
    "back office",
    "back-office",
    "controller",
    "controlling",
    "facturacao",
    "contabilidade",
    "financas",
    "tesouraria",
    "recursos humanos",
    "gestao de pessoal",
    "secretaria",
    "secretariado",
    # English
    "administrative assistant",
    "operations coordinator",
    "logistics coordinator",
    "procurement",
    "supply chain",
    "warehouse",
    "customer service",
    "contract management",
    "back office",
    "accounting clerk",
    "finance assistant",
    "hr assistant",
    "office administrator",
    "data coordinator",
]

# ── Source configuration ───────────────────────────────────────────────────────

_SOURCES: list[dict] = [
    {
        "name": "emprego.co.ao",
        "url": "https://www.emprego.co.ao/empregos",
        "selectors": {
            "listing": ["article.job", "div.job-item", "li.job-listing", "div.vaga", ".job"],
            "title": ["h2", "h3", ".job-title", ".titulo", ".title"],
            "company": [".company", ".empresa", ".company-name", "span.company"],
            "description": [".description", ".descricao", "p.summary", ".job-description"],
            "link": ["a"],
        },
    },
    {
        "name": "jobartis.com",
        "url": "https://www.jobartis.com/ao/empregos",
        "selectors": {
            "listing": ["article", "div.job-card", "div.job-item", ".job-listing", "li.result"],
            "title": ["h2", "h3", ".job-title", ".position"],
            "company": [".company", ".employer", ".empresa", "span.company-name"],
            "description": [".description", "p.summary", ".job-desc", ".overview"],
            "link": ["a"],
        },
    },
    {
        "name": "angoemprego.co.ao",
        "url": "https://www.angoemprego.co.ao/vagas",
        "selectors": {
            "listing": ["div.vaga", "article.emprego", "li.job", "div.job-listing", ".listing"],
            "title": ["h2", "h3", ".title", ".vaga-titulo", ".job-title"],
            "company": [".empresa", ".company", ".empregador", "span.company"],
            "description": [".descricao", ".description", "p", ".summary"],
            "link": ["a"],
        },
    },
]

_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "pt-PT,pt;q=0.9,en;q=0.8",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}

_last_request_time: dict[str, float] = {}
_MIN_INTERVAL_SECONDS = 2.0


# ── Helpers ───────────────────────────────────────────────────────────────────

def _extract_domain(url: str) -> str:
    return urlparse(url).netloc.lower().lstrip("www.")


def _rate_limit(domain: str) -> None:
    last = _last_request_time.get(domain, 0.0)
    elapsed = time.time() - last
    if elapsed < _MIN_INTERVAL_SECONDS:
        time.sleep(_MIN_INTERVAL_SECONDS - elapsed)
    _last_request_time[domain] = time.time()


def _first_text(soup: BeautifulSoup, selectors: list[str]) -> str:
    for sel in selectors:
        tag = soup.select_one(sel)
        if tag and tag.get_text(strip=True):
            return tag.get_text(strip=True)
    return ""


def _first_href(soup: BeautifulSoup, base_url: str) -> str:
    tag = soup.find("a", href=True)
    if tag:
        href = tag["href"]
        if href.startswith("http"):
            return href
        return urljoin(base_url, href)
    return base_url


def _parse_listings(
    html: str,
    source_config: dict,
    base_url: str,
) -> list[dict]:
    soup = BeautifulSoup(html, "html.parser")
    sel = source_config["selectors"]
    results: list[dict] = []

    # Try each listing selector until we find hits
    containers = []
    for listing_sel in sel["listing"]:
        containers = soup.select(listing_sel)
        if containers:
            break

    # Fallback: use article or section tags
    if not containers:
        containers = soup.find_all(["article", "section"], limit=50)

    for container in containers[:50]:
        title = _first_text(container, sel["title"])
        company = _first_text(container, sel["company"])
        description = _first_text(container, sel["description"])
        link = _first_href(container, base_url)

        # Skip entries with no title
        if not title:
            continue

        results.append({
            "company_name": company or "Desconhecido",
            "job_title": title,
            "description": description[:500],
            "url": link,
            "source": source_config["name"],
        })

    return results


# ── Public API ────────────────────────────────────────────────────────────────

def scrape_source(url: str, source_config: dict | None = None) -> list[dict]:
    """Scrape a single job board URL. Return list of raw listing dicts."""
    domain = _extract_domain(url)
    _rate_limit(domain)

    # Find source config by URL if not provided
    if source_config is None:
        source_config = next(
            (s for s in _SOURCES if domain in s["url"]),
            {"name": domain, "selectors": {
                "listing": ["article", "li.job", "div.job", ".listing"],
                "title": ["h2", "h3", ".title"],
                "company": [".company", ".employer"],
                "description": ["p", ".description"],
                "link": ["a"],
            }},
        )

    logger.info(f"Scraping {url}")
    try:
        response = requests.get(url, headers=_HEADERS, timeout=15)
        response.raise_for_status()
    except requests.RequestException as exc:
        logger.warning(f"Failed to fetch {url}: {exc}")
        return []

    listings = _parse_listings(response.text, source_config, url)
    logger.info(f"Found {len(listings)} raw listings from {domain}")
    return listings


def scrape_all_sources() -> list[dict]:
    """Scrape all configured Angolan job board sources. Return merged listings."""
    all_listings: list[dict] = []
    for source in _SOURCES:
        try:
            listings = scrape_source(source["url"], source_config=source)
            all_listings.extend(listings)
        except Exception as exc:
            logger.error(f"Unexpected error scraping {source['name']}: {exc}")

    logger.info(f"Total raw listings across all sources: {len(all_listings)}")
    return all_listings
