"""PineScript scraper for TradingView scripts."""

import json
import logging
import os
import re
from typing import Any, Dict, Optional

import requests
from bs4 import BeautifulSoup
from requests.exceptions import RequestException

from tradingview_scraper.utils import generate_user_agent

logger = logging.getLogger(__name__)


class PineScriptScraper:
    """Scrape PineScript source code and metadata from TradingView.

    Supports multiple extraction methods:
    1. Direct API access (if available)
    2. HTML parsing with embedded JSON
    3. Page structure analysis
    """

    def __init__(self, cookie: Optional[str] = None):
        """Initialize the scraper.

        Args:
            cookie: Optional TradingView session cookie to bypass captcha
        """
        self.headers = {
            "user-agent": generate_user_agent(),
            "accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "accept-language": "en-US,en;q=0.9",
        }

        # Add cookie if provided
        if cookie:
            self.headers["cookie"] = cookie
        elif os.getenv("TRADINGVIEW_COOKIE"):
            self.headers["cookie"] = os.getenv("TRADINGVIEW_COOKIE")

    def get_script(self, script_url: str) -> Dict[str, Any]:
        """Scrape PineScript from a TradingView script URL.

        Args:
            script_url: Full URL to the TradingView script page
                       Example: "https://www.tradingview.com/script/jXvqrU4q-OBV-MACD-Indicator/"

        Returns:
            Dictionary containing:
            - id: Script ID
            - name: Script name
            - description: Script description
            - author: Author username
            - source: PineScript source code (if available)
            - url: Original URL
            - error: Error message if scraping failed

        Raises:
            ValueError: If the URL format is invalid
        """
        logger.info(f"Starting to scrape TradingView script: {script_url}")

        script_id = self._extract_script_id(script_url)
        if not script_id:
            logger.error(f"Invalid TradingView script URL (no script ID found): {script_url}")
            raise ValueError(f"Invalid TradingView script URL: {script_url}")

        logger.info(f"Extracted script ID from URL: {script_id}")
        result = None

        # Try API endpoint first
        try:
            logger.info("Attempting to fetch via API endpoint...")
            result = self._fetch_via_api(script_id, script_url)
            if result and result.get("source"):
                logger.info(f"✓ Successfully fetched script via API: {script_id}")
                logger.info(f"  Script name: {result.get('scriptName', result.get('name', 'Unknown'))}")
                logger.info(f"  Source code length: {len(result.get('source', ''))} characters")
                return result
            else:
                logger.warning("API method returned no source code")
        except Exception as e:
            logger.warning(f"API method failed with exception: {type(e).__name__}: {e}")

        # Fallback to HTML parsing
        try:
            logger.info("Attempting to fetch via HTML parsing...")
            result = self._fetch_via_html(script_url, script_id)
            if result and result.get("source"):
                logger.info(f"✓ Successfully fetched script via HTML: {script_id}")
                logger.info(f"  Script name: {result.get('scriptName', result.get('name', 'Unknown'))}")
                logger.info(f"  Source code length: {len(result.get('source', ''))} characters")
                return result
            else:
                logger.warning("HTML method returned no source code")
        except Exception as e:
            logger.warning(f"HTML method failed with exception: {type(e).__name__}: {e}")

        # Return error if all methods failed
        if not result:
            error_msg = "Unable to fetch script. The script may be private or require authentication."
            logger.error(f"✗ All scraping methods failed for script: {script_url}")
            logger.error(f"  Error: {error_msg}")
            result = {
                "id": script_id,
                "url": script_url,
                "error": error_msg,
            }

        return result

    def _extract_script_id(self, url: str) -> Optional[str]:
        """Extract script ID from TradingView URL.

        Args:
            url: TradingView script URL

        Returns:
            Script ID if found, None otherwise
        """
        pattern = r"/script/([a-zA-Z0-9]+)"
        match = re.search(pattern, url)
        return match.group(1) if match else None

    def _extract_real_script_id(self, script_url: str) -> Optional[str]:
        """Extract the real script ID (PUB;xxx format) from the page HTML.

        Args:
            script_url: Full script URL

        Returns:
            Real script ID if found, None otherwise
        """
        try:
            logger.info(f"Fetching page HTML to extract real script ID from: {script_url}")
            response = requests.get(script_url, headers=self.headers, timeout=10)

            if response.status_code != 200:
                logger.error(f"Failed to fetch page HTML: HTTP {response.status_code}")
                return None

            html_content = response.text
            logger.debug(f"Fetched HTML page, length: {len(html_content)} characters")

            # Pattern 1: Look for scriptIdPart in JSON data
            # Try both snake_case and camelCase (TradingView uses snake_case in HTML)
            patterns = [
                r'"script_id_part"\s*:\s*"([^"]+)"',  # snake_case (actual HTML format)
                r'"scriptIdPart"\s*:\s*"([^"]+)"',      # camelCase (fallback)
                r'"id"\s*:\s*"(PUB;[a-f0-9]+)"',
                r'"scriptId"\s*:\s*"(PUB;[a-f0-9]+)"',
                r'PUB%3B([a-f0-9]+)',  # URL encoded format
            ]

            for i, pattern in enumerate(patterns, 1):
                logger.debug(f"Trying pattern {i}/{len(patterns)}: {pattern}")
                match = re.search(pattern, html_content)
                if match:
                    script_id = match.group(1)
                    logger.info(f"✓ Pattern {i} matched! Raw value: {script_id}")

                    # Decode if URL encoded
                    if '%3B' in script_id:
                        import urllib.parse
                        script_id = urllib.parse.unquote(script_id)
                        logger.info(f"  Decoded from URL encoding: {script_id}")
                    elif ';' not in script_id and len(script_id) == 32:
                        # If we only got the hex part, add PUB; prefix
                        script_id = f"PUB;{script_id}"
                        logger.info(f"  Added PUB; prefix: {script_id}")

                    logger.info(f"✓ Successfully extracted real script ID: {script_id}")
                    return script_id

            logger.warning("Could not extract real script ID from HTML using any pattern")
            logger.debug(f"HTML snippet (first 500 chars): {html_content[:500]}")
            return None

        except Exception as e:
            logger.error(f"Failed to extract real script ID: {type(e).__name__}: {e}")
            import traceback
            logger.debug(f"Traceback: {traceback.format_exc()}")
            return None

    def _fetch_via_api(self, script_id: str, script_url: str) -> Optional[Dict[str, Any]]:
        """Try to fetch script data via TradingView API endpoints.

        Args:
            script_id: Script ID
            script_url: Full script URL

        Returns:
            Script data if successful, None otherwise
        """
        logger.info("=" * 60)
        logger.info("ATTEMPTING API FETCH METHOD")
        logger.info("=" * 60)

        # First, try to get the real script ID from the page HTML
        real_script_id = self._extract_real_script_id(script_url)

        if real_script_id:
            logger.info(f"Using real script ID: {real_script_id}")
            # Try the pine-facade API with the real script ID
            try:
                # URL encode the script ID (e.g., "PUB;xxx" -> "PUB%3Bxxx")
                import urllib.parse
                encoded_id = urllib.parse.quote(real_script_id, safe='')
                logger.info(f"URL encoded script ID: {encoded_id}")

                # Try different versions
                versions = ['1', '0', 'latest']
                for version in versions:
                    endpoint = f"https://pine-facade.tradingview.com/pine-facade/get/{encoded_id}/{version}?no_4xx=true"

                    # Update headers for this request
                    headers = self.headers.copy()
                    headers.update({
                        'Accept': 'application/json',
                        'Referer': 'https://www.tradingview.com/',
                        'Origin': 'https://www.tradingview.com',
                    })

                    logger.info(f"Trying pine-facade API with version '{version}':")
                    logger.info(f"  Endpoint: {endpoint}")
                    logger.info(f"  Headers: {dict(headers)}")

                    response = requests.get(endpoint, headers=headers, timeout=10)
                    logger.info(f"  Response status: {response.status_code}")

                    if response.status_code == 200:
                        try:
                            data = response.json()
                            logger.info(f"  Response JSON keys: {list(data.keys())}")

                            if data and data.get("source"):
                                source_preview = data["source"][:200] if len(data["source"]) > 200 else data["source"]
                                logger.info(f"  ✓ Found source code! Length: {len(data['source'])} characters")
                                logger.info(f"  Source preview: {source_preview}...")
                                logger.info(f"✓ Successfully fetched via pine-facade API (version {version})")
                                return self._normalize_response(data, script_id, script_url)
                            else:
                                logger.warning("  Response has no 'source' field")
                        except Exception as e:
                            logger.error(f"  Failed to parse JSON response: {type(e).__name__}: {e}")
                            logger.debug(f"  Response text (first 500 chars): {response.text[:500]}")
                    else:
                        logger.warning(f"  Failed with HTTP {response.status_code}")
                        logger.debug(f"  Response text (first 500 chars): {response.text[:500]}")

            except Exception as e:
                logger.error(f"Pine-facade API failed: {type(e).__name__}: {e}")
                import traceback
                logger.debug(f"Traceback: {traceback.format_exc()}")
        else:
            logger.warning("Could not extract real script ID, skipping pine-facade API")

        # Fallback to old API endpoints
        logger.info("\nTrying fallback API endpoints...")
        api_endpoints = [
            f"https://www.tradingview.com/pine_perm/modify/?id={script_id}",
            f"https://www.tradingview.com/script/get-source/{script_id}/",
        ]

        for i, endpoint in enumerate(api_endpoints, 1):
            try:
                logger.info(f"Fallback endpoint {i}/{len(api_endpoints)}: {endpoint}")
                response = requests.get(endpoint, headers=self.headers, timeout=10)
                logger.info(f"  Response status: {response.status_code}")

                if response.status_code == 200:
                    data = response.json()
                    logger.info(f"  Response JSON keys: {list(data.keys())}")
                    if data and ("source" in data or "scriptSource" in data):
                        logger.info("  ✓ Found source code in response!")
                        return self._normalize_response(data, script_id, script_url)
                    else:
                        logger.warning("  No source code in response")
            except Exception as e:
                logger.warning(f"  Endpoint failed: {type(e).__name__}: {e}")
                continue

        logger.error("All API methods failed to retrieve source code")
        return None

    def _fetch_via_html(self, script_url: str, script_id: str) -> Optional[Dict[str, Any]]:
        """Fetch script data by parsing HTML page.

        Args:
            script_url: Full script URL
            script_id: Script ID

        Returns:
            Script data if successful, None otherwise
        """
        try:
            response = requests.get(script_url, headers=self.headers, timeout=10)
            if response.status_code != 200:
                logger.error(f"HTTP {response.status_code}: Failed to fetch {script_url}")
                return None

            # Check for captcha
            if "<title>Captcha Challenge</title>" in response.text:
                logger.error("Captcha encountered. Set TRADINGVIEW_COOKIE environment variable.")
                return None

            html_content = response.text

            # Try extracting from window.__INITIAL_STATE__
            result = self._extract_from_initial_state(html_content, script_id, script_url)
            if result and result.get("source"):
                return result

            # Try extracting from script tags with JSON
            result = self._extract_from_script_tags(html_content, script_id, script_url)
            if result and result.get("source"):
                return result

            # Fallback: extract metadata only
            return self._extract_metadata_only(html_content, script_id, script_url)

        except RequestException as e:
            logger.error(f"Network request failed: {e}")
            return None
        except Exception as e:
            logger.error(f"Unexpected error: {e}")
            return None

    def _extract_from_initial_state(
        self, html: str, script_id: str, script_url: str
    ) -> Optional[Dict[str, Any]]:
        """Extract script data from window.__INITIAL_STATE__ or similar."""
        patterns = [
            r"window\.__INITIAL_STATE__\s*=\s*({.+?});",
            r"window\.__PINE_SCRIPT_DATA__\s*=\s*({.+?});",
            r"window\.__SCRIPT_DATA__\s*=\s*({.+?});",
        ]

        for pattern in patterns:
            try:
                match = re.search(pattern, html, re.DOTALL)
                if match:
                    json_str = match.group(1)
                    data = json.loads(json_str)

                    # Search for script data in nested structure
                    script_data = self._find_script_in_data(data)
                    if script_data:
                        return self._normalize_response(script_data, script_id, script_url)
            except Exception as e:
                logger.debug(f"Failed to parse pattern {pattern}: {e}")
                continue

        return None

    def _extract_from_script_tags(
        self, html: str, script_id: str, script_url: str
    ) -> Optional[Dict[str, Any]]:
        """Extract script data from <script type='application/json'> tags."""
        soup = BeautifulSoup(html, "html.parser")

        for script_tag in soup.find_all("script", type="application/json"):
            try:
                data = json.loads(script_tag.string)
                script_data = self._find_script_in_data(data)
                if script_data:
                    return self._normalize_response(script_data, script_id, script_url)
            except Exception as e:
                logger.debug(f"Failed to parse script tag: {e}")
                continue

        return None

    def _extract_metadata_only(
        self, html: str, script_id: str, script_url: str
    ) -> Dict[str, Any]:
        """Extract basic metadata from HTML structure (without source code)."""
        soup = BeautifulSoup(html, "html.parser")

        result = {
            "id": script_id,
            "url": script_url,
            "source": None,
            "error": "Source code not available. Script may be private or protected.",
        }

        # Try to extract metadata
        title_tag = soup.find("h1")
        if title_tag:
            result["name"] = title_tag.get_text(strip=True)

        meta_desc = soup.find("meta", property="og:description")
        if meta_desc:
            result["description"] = meta_desc.get("content", "")

        return result

    def _find_script_in_data(
        self, data: Any, depth: int = 0, max_depth: int = 10
    ) -> Optional[Dict[str, Any]]:
        """Recursively search for script data containing 'source' or 'scriptSource'."""
        if depth > max_depth:
            return None

        if isinstance(data, dict):
            # Check if this dict contains script source
            if "source" in data or "scriptSource" in data:
                return data

            # Recursively search nested dicts
            for value in data.values():
                result = self._find_script_in_data(value, depth + 1, max_depth)
                if result:
                    return result

        elif isinstance(data, list):
            # Search in lists
            for item in data:
                result = self._find_script_in_data(item, depth + 1, max_depth)
                if result:
                    return result

        return None

    def _normalize_response(
        self, data: Dict[str, Any], script_id: str, script_url: str
    ) -> Dict[str, Any]:
        """Normalize API/HTML response to standard format."""
        source = (
            data.get("source")
            or data.get("scriptSource")
            or data.get("content")
            or data.get("pineSource")
            or ""
        )

        author = data.get("author", {})
        if isinstance(author, dict):
            author_name = author.get("username", "") or author.get("name", "")
        else:
            author_name = str(author) if author else ""

        return {
            "id": data.get("scriptIdPart", script_id),
            "url": script_url,
            "name": data.get("name", "") or data.get("title", ""),
            "description": data.get("description", ""),
            "author": author_name,
            "source": source,
            "access_level": data.get("access", 0),
            "script_type": data.get("scriptType", "") or data.get("type", ""),
            "published_at": data.get("publishedAt", "") or data.get("created", ""),
            "updated_at": data.get("updatedAt", "") or data.get("modified", ""),
            "views": data.get("views", 0),
            "likes": data.get("likes", 0),
        }


def get_pinescript(script_url: str, cookie: Optional[str] = None) -> Dict[str, Any]:
    """Convenience function to scrape a PineScript by URL.

    Args:
        script_url: Full URL to the TradingView script
        cookie: Optional TradingView session cookie

    Returns:
        Dictionary with script data including source code (if available)

    Example:
        >>> data = get_pinescript("https://www.tradingview.com/script/jXvqrU4q-OBV-MACD-Indicator/")
        >>> print(data['name'])
        'OBV MACD Indicator'
        >>> if data['source']:
        ...     print("PineScript code found!")
    """
    scraper = PineScriptScraper(cookie=cookie)
    return scraper.get_script(script_url)
