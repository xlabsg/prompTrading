"""TradingView Trending Strategies Scraper.

This module scrapes trending Pine Scripts and Trading Ideas from TradingView.
It includes rate limiting, user agent rotation, and quality scoring.
"""

import json
import time
import random
import logging
from concurrent.futures import ThreadPoolExecutor
from typing import Literal, List, Dict, Any, Optional
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

from .symbol_detector import detect_symbols, detect_markets

logger = logging.getLogger(__name__)

# User agents for rotation to avoid blocking
USER_AGENTS = [
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.1 Safari/605.1.15",
]


class TradingViewTrendingScraper:
    """Scraper for TradingView trending strategies (scripts and ideas)."""

    def __init__(
        self,
        rate_limit_delay: float = 0.5,
        max_retries: int = 3,
        timeout: int = 30,
    ):
        """
        Initialize the scraper.

        Args:
            rate_limit_delay: Delay between requests in seconds (reduced for parallel scraping)
            max_retries: Maximum number of retries for failed requests
            timeout: Request timeout in seconds
        """
        self.rate_limit_delay = rate_limit_delay
        self.max_retries = max_retries
        self.timeout = timeout
        self.session = requests.Session()

    def scrape_trending_parallel(
        self,
        source_types: List[Literal["scripts", "ideas"]],
        max_count: int = 50,
        filter_crypto: bool = False,
    ) -> List[Dict[str, Any]]:
        """
        Scrape trending strategies from TradingView in parallel.

        Args:
            source_types: List of source types to scrape
            max_count: Maximum number of strategies to scrape per source
            filter_crypto: Only include strategies that mention crypto symbols

        Returns:
            List of strategy dictionaries from all sources
        """
        logger.info(f"Parallel scraping TradingView sources: {source_types}, max_count={max_count}")

        def scrape_single_source(st: str) -> List[Dict[str, Any]]:
            """Scrape a single source type."""
            if st == "scripts":
                return self._scrape_scripts(max_count, filter_crypto)
            elif st == "ideas":
                return self._scrape_ideas(max_count, filter_crypto)
            else:
                logger.error(f"Unknown source_type: {st}")
                return []

        # Use ThreadPoolExecutor to scrape sources in parallel
        with ThreadPoolExecutor(max_workers=len(source_types)) as executor:
            futures = [executor.submit(scrape_single_source, st) for st in source_types]
            results = [f.result() for f in futures]

        # Flatten results
        all_strategies = []
        for strategies in results:
            all_strategies.extend(strategies)

        logger.info(f"Parallel scrape complete: {len(all_strategies)} total strategies")
        return all_strategies

    def scrape_trending(
        self,
        source_type: Literal["scripts", "ideas"],
        max_count: int = 50,
        filter_crypto: bool = False,
    ) -> List[Dict[str, Any]]:
        """
        Scrape trending strategies from TradingView.

        Args:
            source_type: "scripts" or "ideas"
            max_count: Maximum number of strategies to scrape
            filter_crypto: Only include strategies that mention crypto symbols

        Returns:
            List of strategy dictionaries
        """
        logger.info(f"Scraping TradingView {source_type}, max_count={max_count}, filter_crypto={filter_crypto}")

        if source_type == "scripts":
            return self._scrape_scripts(max_count, filter_crypto)
        elif source_type == "ideas":
            return self._scrape_ideas(max_count, filter_crypto)
        else:
            logger.error(f"Unknown source_type: {source_type}")
            return []

    def _scrape_scripts(self, max_count: int, filter_crypto: bool = False) -> List[Dict[str, Any]]:
        """Scrape TradingView scripts list (open-source strategies only).

        We intentionally scrape from the "Indicators and strategies" publications feed using the
        `script_type=strategies` filter and keep only public/open scripts so we can later fetch source.
        """
        url = "https://www.tradingview.com/scripts/?script_type=strategies&script_access=open"
        strategies = []

        try:
            headers = {
                "User-Agent": random.choice(USER_AGENTS),
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
                "Accept-Language": "en-US,en;q=0.9",
                "Accept-Encoding": "gzip, deflate, br",
                "DNT": "1",
                "Connection": "keep-alive",
                "Upgrade-Insecure-Requests": "1",
            }

            next_url: str | None = url
            page = 0
            max_pages = max(1, (max_count + 23) // 24) + 2  # allow a bit of slack
            seen_ids: set[str] = set()

            while next_url and len(strategies) < max_count and page < max_pages:
                logger.info(f"Fetching {next_url}")
                response = self._make_request(next_url, headers=headers)
                if not response:
                    break

                extracted = self._extract_publications_feed(response.text)
                if extracted:
                    items, next_rel = extracted
                    for raw in items:
                        if len(strategies) >= max_count:
                            break
                        strategy = self._normalize_publication_item(raw, rank=len(strategies) + 1)
                        if strategy is None:
                            continue

                        tv_id = strategy.get("tradingview_id") or ""
                        if tv_id in seen_ids:
                            continue
                        seen_ids.add(tv_id)

                        # Detect symbols and markets
                        text = f"{strategy['title']} {strategy.get('description', '')}"
                        symbols = detect_symbols(text)
                        strategy["detected_symbols"] = symbols
                        strategy["detected_markets"] = detect_markets(symbols)

                        if filter_crypto and "crypto" not in strategy["detected_markets"]:
                            continue

                        strategies.append(strategy)

                    next_url = urljoin("https://www.tradingview.com", next_rel) if next_rel else None
                else:
                    # Fallback: parse HTML cards if JSON extraction fails.
                    soup = BeautifulSoup(response.content, "lxml")
                    script_cards = self._find_script_cards(soup)
                    logger.info(f"Found {len(script_cards)} script cards (HTML fallback)")
                    for i, card in enumerate(script_cards):
                        if len(strategies) >= max_count:
                            break
                        try:
                            strategy = self._parse_script_card(card, rank=len(strategies) + 1)
                            tv_id = strategy.get("tradingview_id") or ""
                            if tv_id in seen_ids:
                                continue
                            seen_ids.add(tv_id)

                            text = f"{strategy['title']} {strategy.get('description', '')}"
                            symbols = detect_symbols(text)
                            strategy["detected_symbols"] = symbols
                            strategy["detected_markets"] = detect_markets(symbols)
                            if filter_crypto and "crypto" not in strategy["detected_markets"]:
                                continue

                            strategies.append(strategy)
                        except Exception as e:
                            logger.error(f"Error parsing script card {i}: {e}")
                            continue

                    next_url = None

                page += 1
                time.sleep(self.rate_limit_delay)

        except Exception as e:
            logger.error(f"Error scraping scripts: {e}")

        logger.info(f"Scraped {len(strategies)} strategies from scripts")
        return strategies

    def _scrape_ideas(self, max_count: int, filter_crypto: bool = False) -> List[Dict[str, Any]]:
        """Scrape trending Trading Ideas from TradingView."""
        url = "https://www.tradingview.com/ideas/"
        strategies = []

        try:
            headers = {
                "User-Agent": random.choice(USER_AGENTS),
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
                "Accept-Language": "en-US,en;q=0.9",
            }

            logger.info(f"Fetching {url}")
            response = self._make_request(url, headers=headers)
            if not response:
                return strategies

            soup = BeautifulSoup(response.content, "lxml")

            # Try to find idea cards
            idea_cards = self._find_idea_cards(soup)

            logger.info(f"Found {len(idea_cards)} idea cards")

            for i, card in enumerate(idea_cards[:max_count]):
                try:
                    strategy = self._parse_idea_card(card, rank=i + 1)

                    # Detect symbols and markets
                    text = f"{strategy['title']} {strategy.get('description', '')}"
                    symbols = detect_symbols(text)
                    strategy["detected_symbols"] = symbols
                    strategy["detected_markets"] = detect_markets(symbols)

                    # Only include crypto-related strategies if filter_crypto is enabled
                    if filter_crypto and "crypto" not in strategy["detected_markets"]:
                        logger.debug(f"Skipping non-crypto idea: {strategy['title']}")
                        continue

                    strategies.append(strategy)
                    logger.info(f"Scraped idea: {strategy['title']}")

                    # Rate limiting
                    time.sleep(self.rate_limit_delay)

                except Exception as e:
                    logger.error(f"Error parsing idea card {i}: {e}")
                    continue

        except Exception as e:
            logger.error(f"Error scraping ideas: {e}")

        logger.info(f"Scraped {len(strategies)} crypto strategies from ideas")
        return strategies

    def _find_script_cards(self, soup: BeautifulSoup) -> List[Any]:
        """Find script cards in the HTML."""
        # Prefer selecting anchors that link to actual script pages.
        # TradingView frequently changes CSS class names; href structure is more stable.
        cards: list[Any] = []
        seen: set[str] = set()
        for a in soup.select("a[href*='/script/']"):
            href = a.get("href") or ""
            if not href:
                continue
            key = href
            if key in seen:
                continue
            seen.add(key)
            container = a.find_parent("article") or a
            cards.append(container)
        if cards:
            return cards
        return soup.find_all("article")

    def _extract_publications_feed(self, html: str) -> Optional[tuple[list[dict[str, Any]], Optional[str]]]:
        """Extract publication feed items from TradingView embedded JSON.

        TradingView renders the list server-side and embeds a JSON blob containing:
          { "state": { ... "feed": { "items": [...], "next": "/scripts/page-2/" } ... }, ... }
        This is far more stable than scraping dynamic class names.
        """
        soup = BeautifulSoup(html, "lxml")
        best_items: list[dict[str, Any]] = []
        best_next: str | None = None

        for script in soup.find_all("script"):
            t = (script.get("type") or "").lower()
            if "json" not in t:
                continue
            raw = (script.string or "").strip()
            if not raw:
                continue
            # Quick filter to avoid parsing unrelated JSON payloads (menus, locale links, etc.).
            if "/scripts/page" not in raw and "\"script_type\"" not in raw and "\"feed\"" not in raw:
                continue
            try:
                obj = json.loads(raw)
            except Exception:
                continue
            if not isinstance(obj, dict):
                continue

            candidate = self._find_feed_container(obj)
            if not candidate:
                continue
            items, next_rel = candidate
            if len(items) > len(best_items):
                best_items = items
                best_next = next_rel

        if not best_items:
            return None
        return best_items, best_next

    def _find_feed_container(self, obj: Any) -> Optional[tuple[list[dict[str, Any]], Optional[str]]]:
        """Find a dict containing a feed-like structure: {'items': [...], 'next': ...}."""
        best_items: list[dict[str, Any]] = []
        best_next: str | None = None

        stack = [obj]
        while stack:
            cur = stack.pop()
            if isinstance(cur, dict):
                items = cur.get("items")
                if isinstance(items, list) and items and all(isinstance(x, dict) for x in items):
                    # Heuristic: publication items typically include script flags/types.
                    score = sum(1 for x in items if "script_type" in x or "is_script" in x or "script_access" in x)
                    if score > 0 and len(items) > len(best_items):
                        best_items = items  # type: ignore[assignment]
                        nxt = cur.get("next")
                        best_next = nxt if isinstance(nxt, str) else None
                stack.extend(cur.values())
            elif isinstance(cur, list):
                stack.extend(cur)

        if not best_items:
            return None
        return best_items, best_next

    def _normalize_publication_item(self, item: dict[str, Any], *, rank: int) -> Optional[Dict[str, Any]]:
        """Map TradingView feed item to our normalized TrendingStrategy dict.

        Filters:
        - strategies only
        - open/public only (so Pine source can be fetched later)
        """
        if not isinstance(item, dict):
            return None

        script_type = str(item.get("script_type") or item.get("scriptType") or "").lower()
        if script_type and script_type != "strategy":
            return None

        # Only keep truly public/visible publications.
        if item.get("is_public") is False or item.get("is_visible") is False:
            return None

        # "script_access" appears to be numeric; 1 == open-source (public).
        script_access = item.get("script_access", item.get("scriptAccess"))
        if script_access is not None:
            try:
                access_int = int(script_access)
            except Exception:
                access_int = None
            if access_int is not None and access_int != 1:
                return None
            if isinstance(script_access, str) and script_access.lower() not in {"open", "1"}:
                return None

        url = item.get("chart_url") or item.get("url") or item.get("link") or item.get("path") or ""
        if isinstance(url, str) and url.startswith("/"):
            url = urljoin("https://www.tradingview.com", url)
        if not isinstance(url, str) or "/script/" not in url:
            return None

        title = item.get("title") or item.get("name") or ""
        if not isinstance(title, str) or not title.strip():
            return None

        description = item.get("description") or item.get("text") or item.get("content") or ""
        if not isinstance(description, str):
            description = ""

        user = item.get("user") or {}
        author = user.get("username") if isinstance(user, dict) else None
        author_url = f"https://www.tradingview.com/u/{author}/" if author else ""

        likes = int(item.get("likes_count") or item.get("likes") or 0)
        views = int(item.get("views_count") or item.get("views") or 0)
        comments = int(item.get("comments_count") or item.get("comments") or 0)

        # Extract script ID from URL
        script_id = None
        parts = url.split("/script/")
        if len(parts) > 1:
            # Prefer the stable id-part (first segment before any slug).
            raw_id = parts[1].split("/")[0] or ""
            script_id = raw_id.split("-", 1)[0] or None
        if not script_id:
            # TradingView feed includes the id-part in `image_url` as a short token.
            image_id = item.get("image_url")
            if isinstance(image_id, str) and image_id:
                script_id = image_id

        image_url = None
        image = item.get("image") or {}
        if isinstance(image, dict):
            image_url = image.get("middle") or image.get("big") or None

        return {
            "source_type": "script",
            "tradingview_id": script_id or url,
            "title": title.strip(),
            "description": description[:500],
            "author": author,
            "author_url": author_url,
            "likes": likes,
            "views": views,
            "comments": comments,
            "content_preview": description[:500] if description else "",
            "image_url": image_url,
            "script_id": script_id,
            "url": url,
            "trending_rank": rank,
            "trending_category": "trending",
        }

    def _find_idea_cards(self, soup: BeautifulSoup) -> List[Any]:
        """Find idea cards in the HTML. May need adjustment based on actual structure."""
        selectors = [
            "div.tv-widget-idea",
            "article.tv-widget-idea",
            "div.idea-card",
            "div[data-widget-type='idea']",
        ]

        for selector in selectors:
            cards = soup.select(selector)
            if cards:
                return cards

        all_divs = soup.find_all("div", class_=lambda x: x and any(s in str(x).lower() for s in ["idea", "card"]))
        return all_divs if all_divs else []

    def _parse_script_card(self, card, rank: int) -> Dict[str, Any]:
        """Parse a script card HTML element into a strategy dictionary."""
        # TradingView uses dynamic class names, so we use partial matches
        title_selectors = [
            "a[class*='title']",
        ]

        description_selectors = [
            "a[class*='paragraph']",
        ]

        # Metrics are loaded via JavaScript and may not be available in static HTML
        # We'll use placeholder values for now
        likes_selectors = []
        views_selectors = []
        comments_selectors = []

        link_selectors = [
            "a[href*='/script/']",
        ]

        def extract_text(selectors: List[str]) -> str:
            for sel in selectors:
                elem = card.select_one(sel)
                if elem:
                    text = elem.get_text(strip=True)
                    if text:
                        return text
            return ""

        def extract_number(selectors: List[str]) -> int:
            for sel in selectors:
                elem = card.select_one(sel)
                if elem:
                    text = elem.get_text(strip=True)
                    # Extract number (handle K, M suffixes)
                    text = text.upper().replace("K", "000").replace("M", "000000").replace(",", "")
                    text = "".join(c for c in text if c.isdigit())
                    if text:
                        return int(text)
            return 0

        def extract_url(selectors: List[str]) -> str:
            for sel in selectors:
                elem = card.select_one(sel)
                if elem and elem.get("href"):
                    return urljoin("https://www.tradingview.com", elem["href"])
            return ""

        def extract_image() -> Optional[str]:
            img = card.find("img")
            if img and img.get("src"):
                return img["src"]
            return None

        # Extract fields
        title = extract_text(title_selectors) or "Unknown Title"
        description = extract_text(description_selectors) or ""
        likes = extract_number(likes_selectors) if likes_selectors else 0
        views = extract_number(views_selectors) if views_selectors else 0
        comments = extract_number(comments_selectors) if comments_selectors else 0
        url = extract_url(link_selectors)

        # Extract script ID from URL
        script_id = None
        if url and "/script/" in url:
            parts = url.split("/script/")
            if parts and len(parts) > 1:
                raw_id = parts[1].split("/")[0]
                script_id = raw_id.split("-", 1)[0] if raw_id else None

        # Try to extract author from the URL or page title
        # For now, use placeholder
        author = "TradingView Community"
        author_url = ""

        return {
            "source_type": "script",
            "tradingview_id": script_id or url,
            "title": title,
            "description": description[:500],  # Limit description length
            "author": author,
            "author_url": author_url,
            "likes": likes,
            "views": views,
            "comments": comments,
            "content_preview": description[:500] if description else "",
            "image_url": extract_image(),
            "script_id": script_id,
            "url": url,
            "trending_rank": rank,
            "trending_category": "trending",
        }

    def _parse_idea_card(self, card, rank: int) -> Dict[str, Any]:
        """Parse an idea card HTML element into a strategy dictionary."""
        # Similar to script card parsing
        return self._parse_script_card(card, rank)

    def _make_request(self, url: str, headers: Dict[str, str] = None) -> Optional[requests.Response]:
        """Make HTTP request with retries."""
        for attempt in range(self.max_retries):
            try:
                response = self.session.get(
                    url,
                    headers=headers or {},
                    timeout=self.timeout,
                )
                response.raise_for_status()
                return response
            except requests.RequestException as e:
                logger.warning(f"Request failed (attempt {attempt + 1}/{self.max_retries}): {e}")
                if attempt < self.max_retries - 1:
                    time.sleep(2 ** attempt)  # Exponential backoff
                else:
                    logger.error(f"Max retries exceeded for {url}")
                    return None
        return None
