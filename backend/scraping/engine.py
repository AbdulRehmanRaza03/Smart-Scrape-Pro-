"""
SmartScrape Pro — Core Scraping Engine
Playwright (primary) → Selenium (fallback) → BeautifulSoup
Anti-bot handling, proxy support, pagination
"""
import asyncio
import json
import time
from typing import Any, Optional
from datetime import datetime
from backend.utils.logger import logger


class ScrapingResult:
    def __init__(self):
        self.records: list[dict] = []
        self.pages_scraped: int = 0
        self.errors: list[str] = []
        self.duration_seconds: float = 0.0
        self.source_url: str = ""


class PlaywrightEngine:
    """Primary scraping engine using Playwright (handles JS-heavy sites)."""

    async def scrape(
        self,
        url: str,
        selectors: dict,
        headers: dict = None,
        cookies: list = None,
        proxy: dict = None,
        pagination: dict = None,
        timeout: int = 30,
    ) -> ScrapingResult:
        result = ScrapingResult()
        result.source_url = url
        start_time = time.time()

        try:
            from playwright.async_api import async_playwright

            async with async_playwright() as p:
                # Browser launch config
                launch_args = {
                    "headless": True,
                    "args": [
                        "--no-sandbox",
                        "--disable-setuid-sandbox",
                        "--disable-dev-shm-usage",
                        "--disable-gpu",
                        "--window-size=1920,1080",
                    ]
                }

                if proxy and proxy.get("server"):
                    launch_args["proxy"] = {
                        "server": proxy["server"],
                        "username": proxy.get("username"),
                        "password": proxy.get("password"),
                    }

                browser = await p.chromium.launch(**launch_args)

                # Context with anti-bot settings
                context_args = {
                    "viewport": {"width": 1920, "height": 1080},
                    "user_agent": self._get_random_user_agent(),
                    "locale": "en-US",
                    "timezone_id": "America/New_York",
                    "extra_http_headers": headers or {},
                }

                context = await browser.new_context(**context_args)

                if cookies:
                    await context.add_cookies(cookies)

                page = await context.new_page()

                # Anti-detection scripts
                await page.add_init_script("""
                    Object.defineProperty(navigator, 'webdriver', {get: () => undefined});
                    Object.defineProperty(navigator, 'plugins', {get: () => [1, 2, 3, 4, 5]});
                    window.chrome = {runtime: {}};
                """)

                # Scrape with pagination
                current_url = url
                page_num = 1
                max_pages = pagination.get("max_pages", 1) if pagination else 1

                while current_url and page_num <= max_pages:
                    try:
                        logger.info(f"Scraping page {page_num}: {current_url}")

                        await page.goto(
                            current_url,
                            wait_until="domcontentloaded",
                            timeout=timeout * 1000
                        )

                        # Random human-like delay
                        await asyncio.sleep(1.5 + (page_num * 0.3))

                        # Extract data using selectors
                        page_data = await self._extract_data(page, selectors)
                        result.records.extend(page_data)
                        result.pages_scraped += 1

                        # Handle pagination
                        current_url = None
                        if pagination and page_num < max_pages:
                            current_url = await self._get_next_page_url(
                                page, current_url or url, pagination, page_num
                            )
                        page_num += 1

                    except Exception as e:
                        error_msg = f"Page {page_num} error: {str(e)[:200]}"
                        result.errors.append(error_msg)
                        logger.warning(error_msg)
                        break

                await browser.close()

        except Exception as e:
            result.errors.append(f"Playwright engine error: {str(e)[:300]}")
            logger.error(f"Playwright scraping failed for {url}: {e}")

        result.duration_seconds = round(time.time() - start_time, 2)
        return result

    async def _extract_data(self, page, selectors: dict) -> list[dict]:
        """Extract data from page using CSS selectors."""
        if not selectors:
            # Smart auto-extraction for 'No Selector' jobs (Makes Excel/JSON readable)
            records = []
            
            title = await page.title()
            records.append({"Extracted_Type": "Page Info", "Primary_Text": "Page Title", "Target_URL_or_Source": title})
            
            # Extract common elements
            elements = await page.query_selector_all("h1, h2, h3, a[href], img[src]")
            for el in elements[:100]:  # Limit to 100 to avoid massive files
                tag = await el.evaluate("el => el.tagName.toLowerCase()")
                
                if tag in ['h1', 'h2', 'h3']:
                    text = await el.inner_text()
                    if text.strip():
                        records.append({"Extracted_Type": f"Heading ({tag.upper()})", "Primary_Text": text.strip(), "Target_URL_or_Source": ""})
                
                elif tag == 'a':
                    text = await el.inner_text()
                    href = await el.get_attribute("href")
                    if text.strip() and href and not href.startswith("javascript:"):
                        records.append({"Extracted_Type": "Web Link", "Primary_Text": text.strip()[:100], "Target_URL_or_Source": href})
                        
                elif tag == 'img':
                    alt = await el.get_attribute("alt") or "Image"
                    src = await el.get_attribute("src")
                    if src and not src.startswith("data:"):
                        records.append({"Extracted_Type": "Image / Photo", "Primary_Text": alt.strip()[:100], "Target_URL_or_Source": src})
                        
            return records

        records = []

        # Check if we're scraping a list (multiple items) or a single page
        # Convention: if any selector starts with "@", it's a container selector
        container_selector = selectors.get("@container")

        if container_selector:
            # List scraping mode
            containers = await page.query_selector_all(container_selector)
            for container in containers:
                record = {}
                for field, selector in selectors.items():
                    if field.startswith("@"):
                        continue
                    try:
                        el = await container.query_selector(selector)
                        if el:
                            tag = await el.get_attribute("type") or await el.evaluate("el => el.tagName.toLowerCase()")
                            if tag == "img":
                                record[field] = await el.get_attribute("src") or ""
                            elif tag == "a":
                                record[field] = await el.get_attribute("href") or await el.inner_text()
                            else:
                                record[field] = (await el.inner_text()).strip()
                        else:
                            record[field] = None
                    except Exception:
                        record[field] = None
                if any(v for v in record.values()):
                    records.append(record)
        else:
            # Single record mode
            record = {}
            for field, selector in selectors.items():
                try:
                    el = await page.query_selector(selector)
                    if el:
                        record[field] = (await el.inner_text()).strip()
                    else:
                        record[field] = None
                except Exception:
                    record[field] = None
            records.append(record)

        return records

    async def _get_next_page_url(self, page, current_url: str, pagination: dict, page_num: int) -> Optional[str]:
        """Get next page URL based on pagination config."""
        pagination_type = pagination.get("type", "url")

        if pagination_type == "url":
            # URL pattern like: ?page=2, ?page=3
            pattern = pagination.get("pattern", "?page={}")
            return current_url.split("?")[0] + pattern.replace("{}", str(page_num + 1))

        elif pagination_type == "next_button":
            # Click next button
            next_selector = pagination.get("selector", "a[rel='next']")
            try:
                next_btn = await page.query_selector(next_selector)
                if next_btn:
                    href = await next_btn.get_attribute("href")
                    return href
            except Exception:
                pass

        return None

    def _get_random_user_agent(self) -> str:
        """Return a realistic user agent string."""
        agents = [
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
            "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:125.0) Gecko/20100101 Firefox/125.0",
        ]
        import random
        return random.choice(agents)


class BeautifulSoupEngine:
    """Lightweight scraping engine for static HTML sites."""

    async def scrape(
        self,
        url: str,
        selectors: dict,
        headers: dict = None,
        **kwargs
    ) -> ScrapingResult:
        result = ScrapingResult()
        result.source_url = url
        start_time = time.time()

        try:
            import httpx
            from bs4 import BeautifulSoup

            default_headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                "Accept-Language": "en-US,en;q=0.5",
            }
            if headers:
                default_headers.update(headers)

            async with httpx.AsyncClient(headers=default_headers, timeout=30, follow_redirects=True) as client:
                response = await client.get(url)
                response.raise_for_status()

                soup = BeautifulSoup(response.text, "lxml")

                if not selectors:
                    records = []
                    
                    title_tag = soup.title
                    title = title_tag.get_text(strip=True) if title_tag else "No Title Found"
                    records.append({"Extracted_Type": "Page Info", "Primary_Text": "Page Title", "Target_URL_or_Source": title})
                    
                    for el in soup.find_all(['h1', 'h2', 'h3', 'a', 'img'])[:100]:
                        tag = el.name.lower()
                        
                        if tag in ['h1', 'h2', 'h3']:
                            text = el.get_text(strip=True)
                            if text:
                                records.append({"Extracted_Type": f"Heading ({tag.upper()})", "Primary_Text": text, "Target_URL_or_Source": ""})
                                
                        elif tag == 'a' and el.has_attr('href'):
                            text = el.get_text(strip=True)
                            href = el['href']
                            if text and not href.startswith('javascript:'):
                                records.append({"Extracted_Type": "Web Link", "Primary_Text": text[:100], "Target_URL_or_Source": href})
                                
                        elif tag == 'img' and el.has_attr('src'):
                            alt = el.get('alt', 'Image').strip()
                            src = el['src']
                            if src and not src.startswith('data:'):
                                records.append({"Extracted_Type": "Image / Photo", "Primary_Text": alt[:100], "Target_URL_or_Source": src})
                                
                    result.records = records
                else:
                    container_selector = selectors.get("@container")

                    if container_selector:
                        containers = soup.select(container_selector)
                        for container in containers:
                            record = {}
                            for field, selector in selectors.items():
                                if field.startswith("@"):
                                    continue
                                el = container.select_one(selector)
                                if el:
                                    if el.name == "img":
                                        record[field] = el.get("src", "")
                                    elif el.name == "a":
                                        record[field] = el.get("href") or el.get_text(strip=True)
                                    else:
                                        record[field] = el.get_text(strip=True)
                                else:
                                    record[field] = None
                            if any(v for v in record.values()):
                                result.records.append(record)
                    else:
                        record = {}
                        for field, selector in selectors.items():
                            el = soup.select_one(selector)
                            record[field] = el.get_text(strip=True) if el else None
                        result.records.append(record)

                result.pages_scraped = 1

        except Exception as e:
            result.errors.append(f"BeautifulSoup engine error: {str(e)[:300]}")
            logger.error(f"BS4 scraping failed for {url}: {e}")

        result.duration_seconds = round(time.time() - start_time, 2)
        return result


class ScrapingEngine:
    """
    Main scraping orchestrator.
    Auto-selects engine based on job config.
    Falls back gracefully: Playwright → BeautifulSoup
    """

    def __init__(self):
        self.playwright = PlaywrightEngine()
        self.bs4 = BeautifulSoupEngine()

    async def run(self, job_config: dict) -> ScrapingResult:
        """
        Run a scraping job.

        job_config keys:
            - url: str
            - engine: "playwright" | "beautifulsoup" | "auto"
            - selectors: dict
            - headers: dict
            - cookies: list
            - proxy: dict
            - pagination: dict
            - timeout: int
        """
        url = job_config.get("url", "")
        engine = job_config.get("engine", "auto")
        selectors = job_config.get("selectors", {})
        headers = job_config.get("headers", {})
        cookies = job_config.get("cookies", [])
        proxy = job_config.get("proxy", {})
        pagination = job_config.get("pagination", {})
        timeout = job_config.get("timeout", 30)

        logger.info(f"Starting scrape job: {url} (engine: {engine})")

        if engine == "beautifulsoup":
            return await self.bs4.scrape(url, selectors, headers)

        elif engine == "playwright":
            return await self.playwright.scrape(
                url, selectors, headers, cookies, proxy, pagination, timeout
            )

        elif engine == "auto":
            # Try Playwright first (handles JS sites)
            try:
                result = await self.playwright.scrape(
                    url, selectors, headers, cookies, proxy, pagination, timeout
                )
                if result.records or not result.errors:
                    return result
                logger.warning("Playwright returned no results, trying BeautifulSoup")
            except Exception as e:
                logger.warning(f"Playwright failed: {e}, falling back to BeautifulSoup")

            # Fallback to BeautifulSoup
            return await self.bs4.scrape(url, selectors, headers)

        else:
            result = ScrapingResult()
            result.errors = [f"Unknown engine: {engine}"]
            return result


# Module-level singleton
scraping_engine = ScrapingEngine()
