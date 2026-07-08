"""
SmartScrape Pro — Proxy Manager
Rotate proxies, validate, format for Playwright/httpx
"""
import random
import asyncio
from typing import Optional
from backend.utils.logger import logger


class ProxyManager:
    """
    Manages proxy pool for scraping jobs.
    Supports: HTTP, HTTPS, SOCKS5 proxies.
    """

    def __init__(self):
        self._proxies: list[dict] = []
        self._failed: set[str] = set()

    def add_proxy(self, server: str, username: str = None, password: str = None):
        """Add proxy to pool."""
        self._proxies.append({
            "server": server,
            "username": username,
            "password": password,
        })

    def add_proxies_from_list(self, proxy_list: list[str]):
        """
        Add multiple proxies from string list.
        Format: "http://user:pass@host:port" or "host:port"
        """
        for p in proxy_list:
            parsed = self._parse_proxy_string(p)
            if parsed:
                self._proxies.append(parsed)

    def _parse_proxy_string(self, proxy_str: str) -> Optional[dict]:
        """Parse proxy string into dict."""
        try:
            proxy_str = proxy_str.strip()
            if "://" not in proxy_str:
                proxy_str = "http://" + proxy_str

            from urllib.parse import urlparse
            parsed = urlparse(proxy_str)

            return {
                "server": f"{parsed.scheme}://{parsed.hostname}:{parsed.port}",
                "username": parsed.username,
                "password": parsed.password,
            }
        except Exception as e:
            logger.warning(f"Invalid proxy string '{proxy_str}': {e}")
            return None

    def get_random(self) -> Optional[dict]:
        """Get random working proxy from pool."""
        available = [p for p in self._proxies
                     if p["server"] not in self._failed]
        if not available:
            return None
        return random.choice(available)

    def mark_failed(self, proxy: dict):
        """Mark proxy as failed — skip in future rotations."""
        if proxy and proxy.get("server"):
            self._failed.add(proxy["server"])
            logger.warning(f"Proxy marked failed: {proxy['server']}")

    def get_for_playwright(self) -> Optional[dict]:
        """Get proxy formatted for Playwright browser context."""
        proxy = self.get_random()
        if not proxy:
            return None
        result = {"server": proxy["server"]}
        if proxy.get("username"):
            result["username"] = proxy["username"]
        if proxy.get("password"):
            result["password"] = proxy["password"]
        return result

    def get_for_httpx(self) -> Optional[dict]:
        """Get proxy formatted for httpx client."""
        proxy = self.get_random()
        if not proxy:
            return None
        server = proxy["server"]
        if proxy.get("username") and proxy.get("password"):
            from urllib.parse import urlparse, urlunparse
            parsed = urlparse(server)
            server = urlunparse(parsed._replace(
                netloc=f"{proxy['username']}:{proxy['password']}@{parsed.netloc}"
            ))
        return {"http://": server, "https://": server}

    @property
    def pool_size(self) -> int:
        return len(self._proxies)

    @property
    def active_size(self) -> int:
        return len([p for p in self._proxies if p["server"] not in self._failed])

    def reset_failed(self):
        """Clear failed proxy list — retry all proxies."""
        self._failed.clear()

    def stats(self) -> dict:
        return {
            "total": self.pool_size,
            "active": self.active_size,
            "failed": len(self._failed),
        }


async def validate_proxy(proxy: dict, test_url: str = "https://httpbin.org/ip") -> bool:
    """Test if proxy works by making a test request."""
    try:
        import httpx
        proxies = {
            "http://": proxy["server"],
            "https://": proxy["server"],
        }
        async with httpx.AsyncClient(proxies=proxies, timeout=10) as client:
            res = await client.get(test_url)
            return res.status_code == 200
    except Exception:
        return False


# Module-level singleton
proxy_manager = ProxyManager()
