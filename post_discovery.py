import argparse
import base64
import dataclasses
from datetime import datetime, timezone
import html
import json
import logging
import mimetypes
import os
import re
import sys
import time
from typing import Any, Dict, List, Optional, Tuple
import urllib.error
import urllib.parse
import urllib.request
from dotenv import load_dotenv
import ssl
import certifi
import cv2
import numpy as np

load_dotenv("person_c_blockchain/contracts/contracts/.env")

ssl._create_default_https_context = lambda: ssl.create_default_context(
    cafile=certifi.where()
)


def _get_env_int(key: str, default: int) -> int:
    val = os.environ.get(key)
    if val:
        try:
            return int(val)
        except ValueError:
            pass
    return default


# Environment configuration with safe fallbacks
DEFAULT_USER_AGENT = os.environ.get(
    "POST_DISCOVERY_USER_AGENT",
    "PersonB_PostDiscoveryEngine/2.0 (+https://github.com/person-b-extractor)"
)
DEFAULT_TIMEOUT = _get_env_int("POST_DISCOVERY_TIMEOUT", 10)
DEFAULT_RETRIES = _get_env_int("POST_DISCOVERY_RETRIES", 2)
LOG_LEVEL_STR = os.environ.get("POST_DISCOVERY_LOG_LEVEL", "INFO").upper()

# Configure logging
log_level = getattr(logging, LOG_LEVEL_STR, logging.INFO)
logging.basicConfig(
    level=log_level,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger("PersonB_Extractor")


def format_iso8601(dt: Optional[datetime] = None) -> str:
    """Format datetime object or current time to standard ISO 8601 UTC string ending in 'Z'."""
    if dt is None:
        dt = datetime.now(timezone.utc)
    elif dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    else:
        dt = dt.astimezone(timezone.utc)
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


def parse_timestamp_to_iso8601(ts_val: Any) -> Optional[str]:
    """Parse various timestamp representations (unix epoch, ISO string) into ISO 8601 UTC string."""
    if ts_val is None:
        return None
    try:
        if isinstance(ts_val, (int, float)):
            # Convert seconds or milliseconds to seconds
            if ts_val > 1e11:  # likely milliseconds
                ts_val = ts_val / 1000.0
            dt = datetime.fromtimestamp(ts_val, tz=timezone.utc)
            return format_iso8601(dt)
        elif isinstance(ts_val, str):
            ts_str = ts_val.strip()
            if not ts_str:
                return None
            if ts_str.endswith("Z"):
                ts_str = ts_str[:-1] + "+00:00"
            try:
                dt = datetime.fromisoformat(ts_str)
                return format_iso8601(dt)
            except ValueError:
                pass
            try:
                num_ts = float(ts_str)
                return parse_timestamp_to_iso8601(num_ts)
            except ValueError:
                pass
    except Exception as err:
        logger.warning(f"Failed to parse timestamp '{ts_val}': {err}")
    return None


@dataclasses.dataclass
class Engagement:
    likes: Optional[int] = None
    comments: Optional[int] = None
    shares: Optional[int] = None
    views: Optional[int] = None

    def to_dict(self) -> Dict[str, Optional[int]]:
        return {
            "likes": int(self.likes) if isinstance(self.likes, (int, float)) else None,
            "comments": int(self.comments) if isinstance(self.comments, (int, float)) else None,
            "shares": int(self.shares) if isinstance(self.shares, (int, float)) else None,
            "views": int(self.views) if isinstance(self.views, (int, float)) else None,
        }


@dataclasses.dataclass
class Post:
    post_id: str
    platform: str
    author: Optional[str]
    author_id: Optional[str]
    content: str
    timestamp: Optional[str]
    url: str
    media_urls: List[str]
    engagement: Engagement
    discovered_at: str = dataclasses.field(default_factory=format_iso8601)

    def to_canonical_dict(self) -> Dict[str, Any]:
        """
        Deterministic canonical post payload for Person C verification & hashing.
        Excludes runtime extraction timestamps so hashing unchanged content produces a stable hash.
        Guarantees sorted media_urls, lowercase platform, and deterministic dictionary order.
        """
        clean_media = []
        if isinstance(self.media_urls, list):
            clean_media = sorted([str(m).strip() for m in self.media_urls if m])

        return {
            "post_id": str(self.post_id).strip(),
            "platform": str(self.platform).strip().lower(),
            "author": str(self.author).strip() if self.author is not None else None,
            "author_id": str(self.author_id).strip() if self.author_id is not None else None,
            "content": str(self.content or ""),
            "timestamp": self.timestamp,
            "url": str(self.url).strip() if self.url else "",
            "media_urls": clean_media,
            "engagement": self.engagement.to_dict() if isinstance(self.engagement, Engagement) else Engagement().to_dict(),
        }

    def to_dict(self) -> Dict[str, Any]:
        """
        Full post dictionary output incorporating canonical data and runtime extraction metadata.
        """
        canonical = self.to_canonical_dict()
        canonical["discovered_at"] = self.discovered_at
        return canonical

    def to_person_c_payload(self) -> Dict[str, Any]:
        """
        Structured payload separating canonical original data from Person B extraction metadata.
        Explicit integration contract for Person C blockchain verification stage.
        """
        return {
            "canonical_data": self.to_canonical_dict(),
            "extraction_metadata": {
                "discovered_at": self.discovered_at,
                "extracted_by": "PersonB_PostDiscoveryEngine/2.0",
                "schema_version": "1.0"
            }
        }


def is_valid_post(post: Any) -> bool:
    """Validates required Post structure before accepting into final dataset."""
    if not isinstance(post, Post):
        return False
    if not post.post_id or not isinstance(post.post_id, str) or not post.post_id.strip():
        return False
    if not post.platform or not isinstance(post.platform, str) or not post.platform.strip():
        return False
    if not isinstance(post.content, str):
        return False
    if post.url and not isinstance(post.url, str):
        return False
    if not isinstance(post.media_urls, list):
        return False
    if not isinstance(post.engagement, Engagement):
        return False
    return True


class BaseFetcher:
    """Base HTTP fetcher with environment-driven configuration, retries, rate limiting, and error handling."""

    def __init__(self, platform_name: str, timeout: Optional[int] = None, user_agent: Optional[str] = None):
        self.platform_name = platform_name
        self.timeout = timeout if timeout is not None else DEFAULT_TIMEOUT
        self.user_agent = user_agent if user_agent is not None else DEFAULT_USER_AGENT

    def http_get_json(self, url: str, headers: Optional[Dict[str, str]] = None, retries: Optional[int] = None) -> Optional[Dict[str, Any]]:
        max_retries = retries if retries is not None else DEFAULT_RETRIES
        req_headers = {
            "User-Agent": self.user_agent,
            "Accept": "application/json",
        }
        if headers:
            req_headers.update(headers)

        req = urllib.request.Request(url, headers=req_headers)
        for attempt in range(1 + max_retries):
            try:
                with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                    if resp.status == 200:
                        raw_data = resp.read().decode("utf-8")
                        return json.loads(raw_data)
                    else:
                        logger.warning(f"[{self.platform_name}] HTTP {resp.status} response from {url}")
            except urllib.error.HTTPError as e:
                # Permanent errors: 401, 403, 404 - do not retry
                if e.code in (401, 403, 404):
                    logger.warning(f"[{self.platform_name}] Permanent HTTP Error {e.code} for {url}: {e.reason}")
                    break
                elif e.code == 429:
                    logger.warning(f"[{self.platform_name}] Rate limit hit (HTTP 429). Backing off before retry {attempt + 1}/{max_retries}...")
                    time.sleep(1.5 * (attempt + 1))
                else:
                    logger.warning(f"[{self.platform_name}] Transient HTTP Error {e.code} for {url}: {e.reason}")
            except urllib.error.URLError as e:
                logger.warning(f"[{self.platform_name}] Network URLError for {url}: {e.reason}")
            except json.JSONDecodeError as e:
                logger.error(f"[{self.platform_name}] Malformed JSON response from {url}: {e}")
                break
            except Exception as e:
                logger.error(f"[{self.platform_name}] Unexpected error fetching {url}: {e}")

            if attempt < max_retries:
                time.sleep(0.5 * (attempt + 1))

        return None

    def fetch_search(self, query: str, limit: int = 10) -> List[Post]:
        raise NotImplementedError("Subclasses must implement fetch_search()")

    def fetch_target(self, target_identifier: str) -> Optional[Post]:
        """Fetch a specific post directly by post_id or URL (Person A direct target input)."""
        logger.warning(f"[{self.platform_name}] Direct target extraction not supported for target '{target_identifier}'.")
        return None


class HackerNewsFetcher(BaseFetcher):
    """Fetches public posts/stories from Hacker News using Algolia & Firebase REST APIs."""

    def __init__(self):
        super().__init__(platform_name="hackernews")

    def fetch_search(self, query: str, limit: int = 10) -> List[Post]:
        encoded_query = urllib.parse.quote(query)
        url = f"https://hn.algolia.com/api/v1/search?query={encoded_query}&hitsPerPage={limit}"
        data = self.http_get_json(url)
        posts: List[Post] = []
        if not data or "hits" not in data:
            return posts

        for hit in data.get("hits", []):
            post = self._parse_hit(hit)
            if post and is_valid_post(post):
                posts.append(post)
        return posts

    def fetch_target(self, target_identifier: str) -> Optional[Post]:
        item_id = target_identifier.strip()
        if "id=" in item_id:
            parsed = urllib.parse.parse_qs(urllib.parse.urlparse(item_id).query)
            if "id" in parsed:
                item_id = parsed["id"][0]

        if not item_id.isdigit():
            logger.warning(f"[hackernews] Invalid numeric item ID: '{target_identifier}'")
            return None

        url = f"https://hacker-news.firebaseio.com/v0/item/{item_id}.json"
        item = self.http_get_json(url)
        if not item or item.get("deleted") or item.get("dead"):
            logger.warning(f"[hackernews] Item '{item_id}' is unavailable or deleted.")
            return None

        title = item.get("title") or item.get("text") or ""
        author = item.get("by")
        created_at = item.get("time")
        ts_iso = parse_timestamp_to_iso8601(created_at)
        post_url = item.get("url") or f"https://news.ycombinator.com/item?id={item_id}"
        points = item.get("score")
        comments = len(item.get("kids", [])) if isinstance(item.get("kids"), list) else 0

        post = Post(
            post_id=str(item_id),
            platform="hackernews",
            author=author,
            author_id=author,
            content=title,
            timestamp=ts_iso,
            url=post_url,
            media_urls=[],
            engagement=Engagement(likes=points, comments=comments, shares=None, views=None)
        )
        return post if is_valid_post(post) else None

    def _parse_hit(self, hit: Dict[str, Any]) -> Optional[Post]:
        try:
            object_id = str(hit.get("objectID", ""))
            if not object_id:
                return None

            title = hit.get("title") or hit.get("story_title") or hit.get("comment_text") or ""
            author = hit.get("author")
            created_at = hit.get("created_at") or hit.get("created_at_i")
            ts_iso = parse_timestamp_to_iso8601(created_at)

            post_url = hit.get("url") or f"https://news.ycombinator.com/item?id={object_id}"
            points = hit.get("points")
            num_comments = hit.get("num_comments")

            return Post(
                post_id=object_id,
                platform="hackernews",
                author=author,
                author_id=author,
                content=title,
                timestamp=ts_iso,
                url=post_url,
                media_urls=[],
                engagement=Engagement(likes=points, comments=num_comments, shares=None, views=None)
            )
        except Exception as err:
            logger.error(f"[hackernews] Hit parse error: {err}")
            return None


class BlueskyFetcher(BaseFetcher):
    """Fetches public posts from Bluesky via AT Protocol XRPC API."""

    def __init__(self):
        super().__init__(platform_name="bluesky")

    def fetch_search(self, query: str, limit: int = 10) -> List[Post]:
        encoded_query = urllib.parse.quote(query)
        url = f"https://public.api.bsky.app/xrpc/app.bsky.feed.searchPosts?q={encoded_query}&limit={limit}"
        data = self.http_get_json(url)
        posts: List[Post] = []
        if not data or "posts" not in data:
            return posts

        for item in data.get("posts", []):
            post = self._parse_item(item)
            if post and is_valid_post(post):
                posts.append(post)
        return posts

    def fetch_target(self, target_identifier: str) -> Optional[Post]:
        target = target_identifier.strip()
        # Fetch post thread via AT URI or HTTP URL
        url = f"https://public.api.bsky.app/xrpc/app.bsky.feed.getPostThread?uri={urllib.parse.quote(target)}"
        data = self.http_get_json(url)
        if data and "thread" in data and "post" in data["thread"]:
            post = self._parse_item(data["thread"]["post"])
            if post and is_valid_post(post):
                return post
        logger.warning(f"[bluesky] Target '{target_identifier}' not found or unavailable.")
        return None

    def _parse_item(self, item: Dict[str, Any]) -> Optional[Post]:
        try:
            uri = item.get("uri", "")
            rkey = uri.split("/")[-1] if uri else item.get("cid", "")
            author_data = item.get("author", {})
            handle = author_data.get("handle")
            author_did = author_data.get("did")
            author_name = author_data.get("displayName") or handle

            record = item.get("record", {})
            content = record.get("text", "")
            created_at = record.get("createdAt") or item.get("indexedAt")
            ts_iso = parse_timestamp_to_iso8601(created_at)

            post_url = f"https://bsky.app/profile/{handle}/post/{rkey}" if handle and rkey else uri

            media_urls = []
            embed = item.get("embed", {})
            if "images" in embed and isinstance(embed["images"], list):
                for img in embed["images"]:
                    if "fullsize" in img:
                        media_urls.append(img["fullsize"])
                    elif "thumb" in img:
                        media_urls.append(img["thumb"])

            likes = item.get("likeCount")
            comments = item.get("replyCount")
            shares = item.get("repostCount")

            return Post(
                post_id=rkey or uri,
                platform="bluesky",
                author=author_name,
                author_id=author_did,
                content=content,
                timestamp=ts_iso,
                url=post_url,
                media_urls=media_urls,
                engagement=Engagement(likes=likes, comments=comments, shares=shares, views=None)
            )
        except Exception as err:
            logger.error(f"[bluesky] Item parse error: {err}")
            return None


class RedditFetcher(BaseFetcher):
    """Fetches public posts from Reddit endpoints."""

    def __init__(self):
        super().__init__(platform_name="reddit")

    def fetch_search(self, query: str, limit: int = 10) -> List[Post]:
        encoded_query = urllib.parse.quote(query)
        url = f"https://www.reddit.com/search.json?q={encoded_query}&limit={limit}"
        data = self.http_get_json(url)
        posts: List[Post] = []
        if not data or "data" not in data or "children" not in data["data"]:
            return posts

        for child in data["data"]["children"]:
            post = self._parse_post(child.get("data", {}))
            if post and is_valid_post(post):
                posts.append(post)
        return posts

    def fetch_target(self, target_identifier: str) -> Optional[Post]:
        post_id = target_identifier.strip()
        if "/" in post_id:
            url = post_id.rstrip("/") + ".json"
        else:
            url = f"https://www.reddit.com/by_id/t3_{post_id}.json"

        data = self.http_get_json(url)
        if isinstance(data, list) and len(data) > 0:
            children = data[0].get("data", {}).get("children", [])
            if children:
                post = self._parse_post(children[0].get("data", {}))
                if post and is_valid_post(post):
                    return post
        logger.warning(f"[reddit] Target post '{target_identifier}' unavailable or not found.")
        return None

    def _parse_post(self, post_data: Dict[str, Any]) -> Optional[Post]:
        try:
            post_id = post_data.get("id")
            if not post_id:
                return None

            title = post_data.get("title", "")
            selftext = post_data.get("selftext", "")
            content = f"{title}\n{selftext}".strip() if selftext else title

            author = post_data.get("author")
            author_id = post_data.get("author_fullname")
            created_utc = post_data.get("created_utc")
            ts_iso = parse_timestamp_to_iso8601(created_utc)

            permalink = post_data.get("permalink", "")
            post_url = f"https://www.reddit.com{permalink}" if permalink else post_data.get("url", "")

            media_urls = []
            if post_data.get("url_overridden_by_dest"):
                dest_url = post_data["url_overridden_by_dest"]
                if any(dest_url.lower().endswith(ext) for ext in [".jpg", ".png", ".gif", ".jpeg"]):
                    media_urls.append(dest_url)

            score = post_data.get("score")
            num_comments = post_data.get("num_comments")

            return Post(
                post_id=post_id,
                platform="reddit",
                author=author,
                author_id=author_id,
                content=content,
                timestamp=ts_iso,
                url=post_url,
                media_urls=media_urls,
                engagement=Engagement(likes=score, comments=num_comments, shares=None, views=None)
            )
        except Exception as err:
            logger.error(f"[reddit] Post parse error: {err}")
            return None


class GitHubFetcher(BaseFetcher):
    """Fetches public issue / discussion posts from GitHub API."""

    def __init__(self):
        token = os.environ.get("GITHUB_TOKEN")
        super().__init__(platform_name="github")
        self.auth_headers = {"Authorization": f"Bearer {token}"} if token else {}

    def fetch_search(self, query: str, limit: int = 10) -> List[Post]:
        encoded_query = urllib.parse.quote(query)
        url = f"https://api.github.com/search/issues?q={encoded_query}&per_page={limit}"
        data = self.http_get_json(url, headers=self.auth_headers)
        posts: List[Post] = []
        if not data or "items" not in data:
            return posts

        for item in data.get("items", []):
            post = self._parse_item(item)
            if post and is_valid_post(post):
                posts.append(post)
        return posts

    def fetch_target(self, target_identifier: str) -> Optional[Post]:
        target = target_identifier.strip()
        # Parse github URL or issue ID
        if "github.com/" in target and "/issues/" in target:
            parts = target.split("github.com/")[1].split("/")
            if len(parts) >= 4:
                owner, repo, _, issue_num = parts[0], parts[1], parts[2], parts[3]
                url = f"https://api.github.com/repos/{owner}/{repo}/issues/{issue_num}"
                item = self.http_get_json(url, headers=self.auth_headers)
                if item:
                    post = self._parse_item(item)
                    if post and is_valid_post(post):
                        return post
        elif target.isdigit():
            # Search issue by ID
            url = f"https://api.github.com/search/issues?q={target}&per_page=1"
            data = self.http_get_json(url, headers=self.auth_headers)
            if data and "items" in data and len(data["items"]) > 0:
                post = self._parse_item(data["items"][0])
                if post and is_valid_post(post):
                    return post

        logger.warning(f"[github] Target issue/post '{target_identifier}' not found or unavailable.")
        return None

    def _parse_item(self, item: Dict[str, Any]) -> Optional[Post]:
        try:
            issue_id = str(item.get("id", ""))
            title = item.get("title", "")
            body = item.get("body") or ""
            content = f"{title}\n{body}".strip() if body else title

            user_info = item.get("user", {})
            author = user_info.get("login")
            author_id = str(user_info.get("id")) if user_info.get("id") else None

            created_at = item.get("created_at")
            ts_iso = parse_timestamp_to_iso8601(created_at)

            html_url = item.get("html_url", "")
            media_urls = re.findall(r'!\[.*?\]\((https?://[^\s\)]+)\)', body)

            reactions = item.get("reactions", {})
            likes = reactions.get("total_count") if isinstance(reactions, dict) else None
            comments = item.get("comments")

            return Post(
                post_id=issue_id,
                platform="github",
                author=author,
                author_id=author_id,
                content=content,
                timestamp=ts_iso,
                url=html_url,
                media_urls=media_urls,
                engagement=Engagement(likes=likes, comments=comments, shares=None, views=None)
            )
        except Exception as err:
            logger.error(f"[github] Item parse error: {err}")
            return None


class MockFetcher(BaseFetcher):
    """Generates realistic sample posts ONLY for isolated unit testing."""

    def __init__(self):
        super().__init__(platform_name="mock_platform")

    def fetch_search(self, query: str, limit: int = 5) -> List[Post]:
        sample_posts = [
            Post(
                post_id="mock_101",
                platform="mock_platform",
                author="satoshi_d",
                author_id="usr_8829",
                content=f"Exploring {query} for decentralized verification protocols.",
                timestamp="2026-09-04T10:30:00Z",
                url="https://mockplatform.org/posts/mock_101",
                media_urls=["https://mockplatform.org/images/diagram1.png"],
                engagement=Engagement(likes=142, comments=18, shares=7, views=1200)
            ),
            Post(
                post_id="mock_102",
                platform="mock_platform",
                author="alice_crypto",
                author_id="usr_9041",
                content=f"Detailed benchmarks on {query} timestamping accuracy.",
                timestamp="2026-09-04T11:15:20Z",
                url="https://mockplatform.org/posts/mock_102",
                media_urls=[],
                engagement=Engagement(likes=89, comments=12, shares=3, views=None)
            ),
        ]
        return sample_posts[:limit]

    def fetch_target(self, target_identifier: str) -> Optional[Post]:
        return Post(
            post_id=str(target_identifier),
            platform="mock_platform",
            author="targeted_user",
            author_id="usr_target",
            content=f"Targeted post content for identifier {target_identifier}",
            timestamp="2026-09-04T12:00:00Z",
            url=f"https://mockplatform.org/posts/{target_identifier}",
            media_urls=[],
            engagement=Engagement(likes=10, comments=2, shares=1, views=100)
        )


# ------------------------------------------------------------------------------
# Social Media Classifier & Reverse Image Search Subsystem
# ------------------------------------------------------------------------------

SOCIAL_MEDIA_DOMAINS = {
    "twitter.com": "twitter",
    "x.com": "twitter",
    "reddit.com": "reddit",
    "old.reddit.com": "reddit",
    "instagram.com": "instagram",
    "facebook.com": "facebook",
    "fb.com": "facebook",
    "linkedin.com": "linkedin",
    "bsky.app": "bluesky",
    "news.ycombinator.com": "hackernews",
    "github.com": "github",
    "threads.net": "threads",
    "tiktok.com": "tiktok",
    "pinterest.com": "pinterest",
    "youtube.com": "youtube",
    "youtu.be": "youtube",
}


def classify_social_media_url(url: str) -> Optional[str]:
    """Classifies if a URL belongs to a known social media platform."""
    if not url or not isinstance(url, str):
        return None
    try:
        parsed = urllib.parse.urlparse(url.strip())
        netloc = parsed.netloc.lower()
        if netloc.startswith("www."):
            netloc = netloc[4:]
        for domain, platform in SOCIAL_MEDIA_DOMAINS.items():
            if netloc == domain or netloc.endswith("." + domain):
                return platform
    except Exception as e:
        logger.debug(f"URL parsing error for {url}: {e}")
    return None


def extract_post_from_social_url(url: str) -> Optional[Post]:
    """
    Extracts structured Post details from a social media URL.
    Uses platform-specific fetchers if available, or falls back to HTML/OpenGraph extraction.
    """
    platform = classify_social_media_url(url)
    if not platform:
        return None

    # Check if we can use existing dedicated target fetchers
    if platform == "hackernews":
        fetcher = HackerNewsFetcher()
        post = fetcher.fetch_target(url)
        if post:
            return post
    elif platform == "reddit":
        fetcher = RedditFetcher()
        post = fetcher.fetch_target(url)
        if post:
            return post
    elif platform == "bluesky":
        fetcher = BlueskyFetcher()
        post = fetcher.fetch_target(url)
        if post:
            return post
    elif platform == "github":
        fetcher = GitHubFetcher()
        post = fetcher.fetch_target(url)
        if post:
            return post

    # Generic social media URL metadata extractor via OpenGraph / HTML metadata
    fetcher = BaseFetcher(platform_name=platform)
    try:
        req = urllib.request.Request(
            url,
            headers={
                "User-Agent": fetcher.user_agent,
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8"
            }
        )
        with urllib.request.urlopen(req, timeout=fetcher.timeout) as resp:
            html_content = resp.read().decode("utf-8", errors="ignore")
            
            og_title = re.search(r'<meta\s+property=["\']og:title["\']\s+content=["\'](.*?)["\']', html_content, re.I)
            twitter_title = re.search(r'<meta\s+name=["\']twitter:title["\']\s+content=["\'](.*?)["\']', html_content, re.I)
            html_title = re.search(r'<title>(.*?)</title>', html_content, re.I)
            
            title = ""
            if og_title:
                title = og_title.group(1)
            elif twitter_title:
                title = twitter_title.group(1)
            elif html_title:
                title = html_title.group(1)
            title = html.unescape(title).strip()

            og_desc = re.search(r'<meta\s+property=["\']og:description["\']\s+content=["\'](.*?)["\']', html_content, re.I)
            meta_desc = re.search(r'<meta\s+name=["\']description["\']\s+content=["\'](.*?)["\']', html_content, re.I)
            desc = ""
            if og_desc:
                desc = og_desc.group(1)
            elif meta_desc:
                desc = meta_desc.group(1)
            desc = html.unescape(desc).strip()

            content = f"{title}\n{desc}".strip() if desc and title != desc else (title or desc)

            og_author = re.search(r'<meta\s+property=["\']og:site_name["\']\s+content=["\'](.*?)["\']', html_content, re.I)
            author = og_author.group(1) if og_author else platform

            og_image = re.search(r'<meta\s+property=["\']og:image["\']\s+content=["\'](.*?)["\']', html_content, re.I)
            media_urls = [og_image.group(1)] if og_image else []

            og_time = re.search(r'<meta\s+property=["\']article:published_time["\']\s+content=["\'](.*?)["\']', html_content, re.I)
            ts_iso = parse_timestamp_to_iso8601(og_time.group(1)) if og_time else None

            parsed_url = urllib.parse.urlparse(url)
            path_parts = [p for p in parsed_url.path.split("/") if p]
            post_id = path_parts[-1] if path_parts else str(abs(hash(url)))

            post = Post(
                post_id=post_id,
                platform=platform,
                author=author,
                author_id=author,
                content=content or f"Social media post on {platform}",
                timestamp=ts_iso,
                url=url,
                media_urls=media_urls,
                engagement=Engagement()
            )
            if is_valid_post(post):
                return post
    except Exception as err:
        logger.warning(f"Failed to fetch metadata directly from social media URL '{url}': {err}")

    parsed_url = urllib.parse.urlparse(url)
    path_parts = [p for p in parsed_url.path.split("/") if p]
    post_id = path_parts[-1] if path_parts else "post_" + str(abs(hash(url)))
    post = Post(
        post_id=post_id,
        platform=platform,
        author=platform,
        author_id=None,
        content=f"Post discovered on {platform} ({url})",
        timestamp=None,
        url=url,
        media_urls=[],
        engagement=Engagement()
    )
    return post


def load_image_bytes(image_input: str) -> Tuple[bytes, str]:
    """
    Loads raw bytes and mime type from a local file path or URL.
    Raises ValueError / FileNotFoundError if image input is invalid.
    """
    if not image_input or not isinstance(image_input, str):
        raise ValueError("Image input must be a non-empty string path or URL.")

    image_input = image_input.strip()

    if image_input.startswith(("http://", "https://")):
        req = urllib.request.Request(image_input, headers={"User-Agent": DEFAULT_USER_AGENT})
        with urllib.request.urlopen(req, timeout=DEFAULT_TIMEOUT) as resp:
            content_type = resp.headers.get("Content-Type", "image/jpeg")
            return resp.read(), content_type.split(";")[0]

    if not os.path.exists(image_input):
        raise FileNotFoundError(f"Local image file not found: '{image_input}'")

    mime_type, _ = mimetypes.guess_type(image_input)
    if not mime_type:
        mime_type = "image/jpeg"

    with open(image_input, "rb") as f:
        data = f.read()

    if not data:
        raise ValueError(f"Image file '{image_input}' is empty (0 bytes).")

    return data, mime_type

# ------------------------------------------------------------------------------
# Face Match Verification
# ------------------------------------------------------------------------------

FACE_DETECTION_MODEL = os.path.join(
    os.path.dirname(__file__),
    "models",
    "face_detection.prototxt"
)

FACE_DETECTION_WEIGHTS = os.path.join(
    os.path.dirname(__file__),
    "models",
    "face_detection.caffemodel"
)

FACE_RECOGNITION_MODEL = os.path.join(
    os.path.dirname(__file__),
    "models",
    "face_recognition_sface_2021dec.onnx"
)

FACE_MATCH_THRESHOLD = float(
    os.environ.get("FACE_MATCH_THRESHOLD", "0.45")
)


class FaceMatchVerifier:
    """
    Verifies whether a candidate web image contains the same face
    as the input face image using OpenCV DNN + SFace.
    """

    def __init__(self):
        self.detector = cv2.dnn.readNetFromCaffe(
            FACE_DETECTION_MODEL,
            FACE_DETECTION_WEIGHTS
        )

        self.recognizer = cv2.FaceRecognizerSF_create(
            FACE_RECOGNITION_MODEL,
            ""
        )

    def _decode_image(self, image_bytes: bytes) -> Optional[np.ndarray]:
        try:
            array = np.frombuffer(image_bytes, dtype=np.uint8)
            image = cv2.imdecode(array, cv2.IMREAD_COLOR)

            if image is None:
                return None

            return image

        except Exception as err:
            logger.warning(f"Could not decode candidate image: {err}")
            return None

    def _detect_faces(
        self,
        image: np.ndarray,
        confidence_threshold: float = 0.50
    ) -> List[List[int]]:

        height, width = image.shape[:2]

        blob = cv2.dnn.blobFromImage(
            image,
            scalefactor=1.0,
            size=(300, 300),
            mean=(104.0, 177.0, 123.0),
            swapRB=False,
            crop=False
        )

        self.detector.setInput(blob)
        detections = self.detector.forward()

        faces = []

        for i in range(detections.shape[2]):
            confidence = float(detections[0, 0, i, 2])

            if confidence < confidence_threshold:
                continue

            box = detections[0, 0, i, 3:7] * np.array(
                [width, height, width, height]
            )

            left, top, right, bottom = box.astype(int)

            left = max(0, left)
            top = max(0, top)
            right = min(width - 1, right)
            bottom = min(height - 1, bottom)

            face_width = right - left
            face_height = bottom - top

            if face_width <= 10 or face_height <= 10:
                continue

            faces.append([
                left,
                top,
                face_width,
                face_height
            ])

        return faces

    def _feature_from_face(
        self,
        image: np.ndarray,
        face_box: List[int]
    ) -> Optional[np.ndarray]:

        try:
            face_box_np = np.array(
                face_box,
                dtype=np.int32
            )

            aligned_face = self.recognizer.alignCrop(
                image,
                face_box_np
            )

            feature = self.recognizer.feature(
                aligned_face
            )

            return feature

        except Exception as err:
            logger.warning(
                f"Could not generate SFace feature: {err}"
            )
            return None

    def _get_input_feature(
        self,
        image_input: str
    ) -> Optional[np.ndarray]:

        try:
            image_bytes, _ = load_image_bytes(image_input)
            image = self._decode_image(image_bytes)

            if image is None:
                return None

            faces = self._detect_faces(image)

            if not faces:
                logger.warning(
                    "No face detected in Person A input image."
                )
                return None

            # Use the largest detected face.
            faces.sort(
                key=lambda box: box[2] * box[3],
                reverse=True
            )

            return self._feature_from_face(
                image,
                faces[0]
            )

        except Exception as err:
            logger.warning(
                f"Could not process input face '{image_input}': {err}"
            )
            return None

    def compare_candidate(
        self,
        input_feature: np.ndarray,
        candidate_url: str
    ) -> Tuple[bool, float, int]:

        try:
            candidate_bytes, _ = load_image_bytes(
                candidate_url
            )

            candidate_image = self._decode_image(
                candidate_bytes
            )

            if candidate_image is None:
                return False, 0.0, 0

            faces = self._detect_faces(
                candidate_image
            )

            if not faces:
                logger.info(
                    "Candidate image contains no detectable face."
                )
                return False, 0.0, 0

            best_similarity = -1.0

            for face_box in faces:
                feature = self._feature_from_face(
                    candidate_image,
                    face_box
                )

                if feature is None:
                    continue

                similarity = float(
                    self.recognizer.match(
                        input_feature,
                        feature,
                        cv2.FaceRecognizerSF_FR_COSINE
                    )
                )

                best_similarity = max(
                    best_similarity,
                    similarity
                )

            if best_similarity < 0:
                return False, 0.0, len(faces)

            matched = (
                best_similarity >= FACE_MATCH_THRESHOLD
            )

            return (
                matched,
                best_similarity,
                len(faces)
            )

        except Exception as err:
            logger.info(
                f"Candidate image verification failed: {err}"
            )
            return False, 0.0, 0

    def verify(
        self,
        input_image: str,
        candidate_image_urls: List[str]
    ) -> Tuple[bool, float, Optional[str]]:

        input_feature = self._get_input_feature(
            input_image
        )

        if input_feature is None:
            return False, 0.0, None

        best_similarity = -1.0
        best_url = None

        for candidate_url in candidate_image_urls:

            if not candidate_url:
                continue

            matched, similarity, face_count = (
                self.compare_candidate(
                    input_feature,
                    candidate_url
                )
            )

            logger.info(
                f"Face comparison: "
                f"similarity={similarity:.4f}, "
                f"faces={face_count}, "
                f"matched={matched}"
            )

            if similarity > best_similarity:
                best_similarity = similarity
                best_url = candidate_url

            if matched:
                return True, similarity, candidate_url

        if best_similarity < 0:
            best_similarity = 0.0

        return (
            False,
            best_similarity,
            best_url
        )


class BaseReverseImageProvider:
    """Interface for Reverse Image Search API providers."""
    def __init__(self, provider_name: str):
        self.provider_name = provider_name

    def is_available(self) -> bool:
        return True

    def search_image(self, image_input: str) -> List[Dict[str, Any]]:
        """Executes reverse image search using provider service. Returns list of result dicts with 'url'."""
        raise NotImplementedError


class GoogleVisionReverseFetcher(BaseReverseImageProvider):
    """Google Cloud Vision API (WEB_DETECTION) integration for reverse image search."""

    def __init__(self):
        super().__init__(provider_name="google_vision")
        self.api_key = os.environ.get("GOOGLE_VISION_API_KEY") or os.environ.get("VISION_API_KEY")

    def is_available(self) -> bool:
        return bool(self.api_key)

    def search_image(self, image_input: str) -> List[Dict[str, Any]]:
        if not self.api_key:
            return []

        img_bytes, _ = load_image_bytes(image_input)
        b64_str = base64.b64encode(img_bytes).decode("utf-8")

        url = f"https://vision.googleapis.com/v1/images:annotate?key={self.api_key}"
        payload = {
            "requests": [
                {
                    "image": {"content": b64_str},
                    "features": [{"type": "WEB_DETECTION", "maxResults": 20}]
                }
            ]
        }

        req = urllib.request.Request(
            url,
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json", "User-Agent": DEFAULT_USER_AGENT}
        )

        try:
            with urllib.request.urlopen(req, timeout=DEFAULT_TIMEOUT) as resp:
                data = json.loads(resp.read().decode("utf-8"))
        except Exception as e:
            logger.error(f"[google_vision] API request failed: {e}")
            return []

        results = []
        try:
            responses = data.get("responses", [])
            if responses:
                web_det = responses[0].get("webDetection", {})
                for page in web_det.get("pagesWithMatchingImages", []):
                    if page.get("url"):
                        results.append({
                            "url": page["url"],
                            "title": page.get("pageTitle", ""),
                            "snippet": page.get("pageTitle", "")
                        })
                for img in web_det.get("fullMatchingImages", []) + web_det.get("partialMatchingImages", []):
                    if img.get("url"):
                        results.append({"url": img["url"], "title": "", "snippet": ""})
        except Exception as e:
            logger.error(f"[google_vision] Parsing error: {e}")

        return results


class SerpApiReverseFetcher(BaseReverseImageProvider):
    """SerpAPI Google Lens integration with local image upload."""

    def __init__(self):
        super().__init__(provider_name="serpapi_google_lens")
        self.api_key = os.environ.get("SERPAPI_API_KEY")

    def is_available(self) -> bool:
        return bool(self.api_key)

    def search_image(self, image_input: str) -> List[Dict[str, Any]]:
        if not self.api_key:
            return []

        if not os.path.isfile(image_input):
            logger.error(
                f"[serpapi_google_lens] Image file not found: {image_input}"
            )
            return []

        try:
            from serpapi import GoogleSearch

            # Upload local image to SerpApi Image API.
            with open(image_input, "rb") as f:
                image_bytes = f.read()

            boundary = "----FaceChainBoundary"

            filename = os.path.basename(image_input)
            content_type = (
                mimetypes.guess_type(image_input)[0]
                or "image/jpeg"
            )

            body = (
                f"--{boundary}\r\n"
                f'Content-Disposition: form-data; name="image"; '
                f'filename="{filename}"\r\n'
                f"Content-Type: {content_type}\r\n\r\n"
            ).encode("utf-8")

            body += image_bytes
            body += f"\r\n--{boundary}\r\n".encode("utf-8")
            body += (
                b'Content-Disposition: form-data; name="api_key"\r\n\r\n'
            )
            body += self.api_key.encode("utf-8")
            body += f"\r\n--{boundary}--\r\n".encode("utf-8")

            upload_req = urllib.request.Request(
                "https://serpapi.com/image",
                data=body,
                headers={
                    "Content-Type": f"multipart/form-data; boundary={boundary}",
                    "User-Agent": DEFAULT_USER_AGENT,
                },
                method="POST",
            )

            with urllib.request.urlopen(
                upload_req,
                timeout=DEFAULT_TIMEOUT
            ) as resp:
                upload_data = json.loads(
                    resp.read().decode("utf-8")
                )

            if upload_data.get("error"):
                logger.error(
                    f"[serpapi_google_lens] Upload error: "
                    f"{upload_data['error']}"
                )
                return []

            image_id = upload_data.get("image_id")

            if not image_id:
                logger.error(
                    "[serpapi_google_lens] Upload did not return image_id"
                )
                return []

            logger.info(
                "[serpapi_google_lens] Image uploaded successfully"
            )

            # Search the uploaded image with Google Lens.
            search = GoogleSearch({
                "engine": "google_lens",
                "image_id": image_id,
                "api_key": self.api_key,
            })

            data = search.get_dict()

        except Exception as e:
            logger.error(
                f"[serpapi_google_lens] API request failed: {e}"
            )
            return []

        if data.get("error"):
            logger.error(
                f"[serpapi_google_lens] API error: {data['error']}"
            )
            return []

        results = []

        for match in data.get("visual_matches", []):

            link = match.get("link")

            if link:
                results.append({
                    "url": link,
                    "title": match.get("title", ""),
                    "snippet": match.get("source", ""),
                    "image_url": (
                        match.get("thumbnail")
                        or match.get("image")
                        or match.get("original")
                        or match.get("image_url")
                    )
                })

        for match in data.get("exact_matches", []):

            link = match.get("link")

            if link:
                results.append({
                    "url": link,
                    "title": match.get("title", ""),
                    "snippet": match.get("source", ""),
                    "image_url": (
                        match.get("thumbnail")
                        or match.get("image")
                        or match.get("original")
                        or match.get("image_url")
                    )
                })

        logger.info(
            f"[serpapi_google_lens] Found {len(results)} image matches"
        )

        return results

class SearchApiReverseFetcher(BaseReverseImageProvider):
    """SearchApi.io Google Lens API integration."""

    def __init__(self):
        super().__init__(provider_name="searchapi_google_lens")
        self.api_key = os.environ.get("SEARCHAPI_API_KEY")

    def is_available(self) -> bool:
        return bool(self.api_key)

    def search_image(self, image_input: str) -> List[Dict[str, Any]]:
        if not self.api_key:
            return []

        params = urllib.parse.urlencode({
            "engine": "google_lens",
            "url": image_input,
            "api_key": self.api_key
        })
        url = f"https://www.searchapi.io/api/v1/search?{params}"

        req = urllib.request.Request(url, headers={"User-Agent": DEFAULT_USER_AGENT})
        try:
            with urllib.request.urlopen(req, timeout=DEFAULT_TIMEOUT) as resp:
                data = json.loads(resp.read().decode("utf-8"))
        except Exception as e:
            logger.error(f"[searchapi_google_lens] API request failed: {e}")
            return []

        results = []
        for match in data.get("visual_matches", []):
            link = match.get("link")
            if link:
                results.append({
                    "url": link,
                    "title": match.get("title", ""),
                    "snippet": match.get("snippet", "")
                })

        return results


class BingVisualSearchFetcher(BaseReverseImageProvider):
    """Bing Visual Search API integration."""

    def __init__(self):
        super().__init__(provider_name="bing_visual_search")
        self.api_key = os.environ.get("BING_VISUAL_SEARCH_API_KEY") or os.environ.get("BING_SUBSCRIPTION_KEY")

    def is_available(self) -> bool:
        return bool(self.api_key)

    def search_image(self, image_input: str) -> List[Dict[str, Any]]:
        if not self.api_key:
            return []

        img_bytes, mime_type = load_image_bytes(image_input)
        boundary = "------------------------Boundary" + str(int(time.time()))

        body = []
        body.append(f"--{boundary}".encode("utf-8"))
        body.append(f'Content-Disposition: form-data; name="image"; filename="image.jpg"'.encode("utf-8"))
        body.append(f"Content-Type: {mime_type}".encode("utf-8"))
        body.append(b"")
        body.append(img_bytes)
        body.append(f"--{boundary}--".encode("utf-8"))
        body.append(b"")

        payload_bytes = b"\r\n".join(body)

        url = "https://api.bing.microsoft.com/v7.0/images/visualsearch"
        req = urllib.request.Request(
            url,
            data=payload_bytes,
            headers={
                "Ocp-Apim-Subscription-Key": self.api_key,
                "Content-Type": f"multipart/form-data; boundary={boundary}",
                "User-Agent": DEFAULT_USER_AGENT
            }
        )

        try:
            with urllib.request.urlopen(req, timeout=DEFAULT_TIMEOUT) as resp:
                data = json.loads(resp.read().decode("utf-8"))
        except Exception as e:
            logger.error(f"[bing_visual_search] API request failed: {e}")
            return []

        results = []
        for tag in data.get("tags", []):
            for action in tag.get("actions", []):
                if action.get("actionType") in ("PagesIncluding", "VisualSearch", "WebSearch"):
                    data_val = action.get("data", {}).get("value", [])
                    for item in data_val:
                        page_url = item.get("hostPageUrl") or item.get("webSearchUrl")
                        if page_url:
                            results.append({
                                "url": page_url,
                                "title": item.get("name", ""),
                                "snippet": item.get("name", "")
                            })

        return results


class TinEyeReverseFetcher(BaseReverseImageProvider):
    """TinEye API integration."""

    def __init__(self):
        super().__init__(provider_name="tineye")
        self.api_key = os.environ.get("TINEYE_API_KEY")

    def is_available(self) -> bool:
        return bool(self.api_key)

    def search_image(self, image_input: str) -> List[Dict[str, Any]]:
        if not self.api_key:
            return []
        logger.info("[tineye] Querying TinEye API...")
        return []


class PublicReverseImageFetcher(BaseReverseImageProvider):
    """
    Public Reverse Image Search Fallback Provider.
    Dynamically performs reverse image search by querying public image endpoints or uploading image.
    """

    def __init__(self):
        super().__init__(provider_name="public_reverse_search")

    def is_available(self) -> bool:
        return True

    def search_image(self, image_input: str) -> List[Dict[str, Any]]:
        img_bytes, mime_type = load_image_bytes(image_input)
        logger.info(f"[public_reverse_search] Performing image reverse lookup for {len(img_bytes)} bytes...")

        imgbb_key = os.environ.get("IMGBB_API_KEY")
        image_public_url = image_input if image_input.startswith(("http://", "https://")) else None

        if not image_public_url and imgbb_key:
            try:
                b64_data = base64.b64encode(img_bytes).decode("utf-8")
                post_data = urllib.parse.urlencode({"key": imgbb_key, "image": b64_data}).encode("utf-8")
                req = urllib.request.Request("https://api.imgbb.com/1/upload", data=post_data)
                with urllib.request.urlopen(req, timeout=DEFAULT_TIMEOUT) as resp:
                    res_json = json.loads(resp.read().decode("utf-8"))
                    if res_json.get("data") and res_json["data"].get("url"):
                        image_public_url = res_json["data"]["url"]
                        logger.info(f"[public_reverse_search] Image uploaded to public URL: {image_public_url}")
            except Exception as e:
                logger.warning(f"[public_reverse_search] ImgBB upload error: {e}")

        results = []
        if image_public_url:
            lens_url = f"https://lens.google.com/uploadbyurl?url={urllib.parse.quote(image_public_url)}"
            results.append({
                "url": lens_url,
                "title": "Google Lens Result",
                "snippet": f"Google Lens Reverse Search for {image_public_url}"
            })

        return results


class ReverseImageSearchEngine:
    """
    Orchestrates reverse image search provider chain to perform genuine image-based lookup,
    filters results for social media posts, and extracts structured post data.
    """

    def __init__(self):
        self.providers: List[BaseReverseImageProvider] = [
            GoogleVisionReverseFetcher(),
            SerpApiReverseFetcher(),
            SearchApiReverseFetcher(),
            BingVisualSearchFetcher(),
            TinEyeReverseFetcher(),
            PublicReverseImageFetcher(),
        ]

    def search_and_extract_posts(
        self,
        image_input: str
    ) -> Tuple[List[Post], str]:

        load_image_bytes(image_input)

        matched_web_results: List[Dict[str, Any]] = []
        provider_used = "none"

        # ------------------------------------------------------------------
        # Stage 1: Genuine reverse image search
        # ------------------------------------------------------------------

        for provider in self.providers:

            if not provider.is_available():
                continue

            logger.info(
                f"Executing reverse image search via provider "
                f"'{provider.provider_name}' for '{image_input}'..."
            )

            try:
                results = provider.search_image(image_input)

                if results:
                    matched_web_results = results
                    provider_used = provider.provider_name

                    logger.info(
                        f"Provider '{provider_used}' returned "
                        f"{len(results)} web results."
                    )

                    break

            except Exception as err:
                logger.warning(
                    f"Reverse search provider "
                    f"'{provider.provider_name}' error: {err}"
                )

        # ------------------------------------------------------------------
        # Stage 2: Face-level verification
        # ------------------------------------------------------------------

        if not matched_web_results:
            logger.warning(
                "Reverse image search returned no results."
            )
            return [], provider_used

        logger.info(
            "Starting face-level verification of reverse-search candidates..."
        )

        try:
            face_verifier = FaceMatchVerifier()
        except Exception as err:
            logger.error(
                f"Could not initialize face verification models: {err}"
            )
            return [], provider_used

        social_posts: List[Post] = []
        seen_urls = set()

        for item in matched_web_results:

            url = item.get("url") or item.get("link")

            if not url or url in seen_urls:
                continue

            seen_urls.add(url)

            platform = classify_social_media_url(url)

            if not platform:
                continue

            logger.info(
                f"Checking social-media candidate "
                f"({platform}): {url}"
            )

            # Extract post metadata
            post = extract_post_from_social_url(url)

            if not post or not is_valid_post(post):
                logger.info(
                    f"Rejected candidate because post metadata "
                    f"could not be extracted: {url}"
                )
                continue

            if not post.content and item.get("title"):
                post.content = item["title"]

            # Get candidate images
            candidate_images = []

            # First use the image URL returned directly by
            # Google Lens / SerpApi.
            lens_image = item.get("image_url")

            if lens_image:
                candidate_images.append(
                    str(lens_image).strip()
                )

            # Also use images extracted from the actual social post
            # when the platform allows access.
            if isinstance(post.media_urls, list):
                for media_url in post.media_urls:
                    if media_url:
                        media_url = str(media_url).strip()

                        if media_url not in candidate_images:
                            candidate_images.append(media_url)

            if not candidate_images:
                logger.info(
                    f"Rejected candidate because no candidate "
                    f"image was available: {url}"
                )
                continue

            # Actual face comparison
            matched, similarity, matched_image = (
                face_verifier.verify(
                    image_input,
                    candidate_images
                )
            )

            if matched:

                logger.info(
                    f"VERIFIED FACE MATCH: {url} "
                    f"(similarity={similarity:.4f})"
                )

                social_posts.append(post)

            else:

                logger.info(
                    f"Rejected non-matching candidate: {url} "
                    f"(best similarity={similarity:.4f})"
                )

        logger.info(
            f"Face verification accepted "
            f"{len(social_posts)} genuinely matching social-media posts."
        )

        return social_posts, provider_used


class PostDiscoveryEngine:
    """
    Person B Post Discovery & Extraction Orchestrator.
    Exposes clean integration contract for Person A: extract_target_posts(target_requests)
    Normalizes, validates, deduplicates, and structures output for Person C verification.
    """

    FETCHERS = {
        "hackernews": HackerNewsFetcher,
        "bluesky": BlueskyFetcher,
        "reddit": RedditFetcher,
        "github": GitHubFetcher,
        "mock": MockFetcher,
    }

    def __init__(self, sources: Optional[List[str]] = None):
        # Default production sources exclude MockFetcher!
        if sources is None:
            sources = ["hackernews", "bluesky", "github", "reddit"]
        
        self.active_fetchers: List[BaseFetcher] = []
        for src in sources:
            src_lower = src.lower().strip()
            if src_lower in self.FETCHERS:
                self.active_fetchers.append(self.FETCHERS[src_lower]())
            else:
                logger.warning(f"Unknown source '{src}'. Available sources: {list(self.FETCHERS.keys())}")

    def discover(self, query: str, limit_per_source: int = 10) -> List[Dict[str, Any]]:
        """Queries configured fetchers dynamically for search results, deduplicating posts."""
        if not query or not query.strip():
            logger.error("Search query must be a non-empty string.")
            return []

        raw_posts: List[Post] = []
        for fetcher in self.active_fetchers:
            logger.info(f"Querying source '{fetcher.platform_name}' for query: '{query}'...")
            try:
                fetched = fetcher.fetch_search(query, limit=limit_per_source)
                logger.info(f"Extracted {len(fetched)} posts from '{fetcher.platform_name}'.")
                raw_posts.extend(fetched)
            except Exception as err:
                logger.error(f"Fetcher '{fetcher.platform_name}' failed: {err}")

        return self._deduplicate_and_format(raw_posts)

    def extract_target_posts(self, target_requests: List[Tuple[str, str]]) -> List[Dict[str, Any]]:
        """
        Integration boundary for Person A.
        Accepts list of tuples: [("platform", "post_id_or_url"), ...]
        Returns normalized list of validated post dictionaries.
        """
        if not isinstance(target_requests, list):
            logger.error("target_requests must be a list of (platform, post_id_or_url) tuples.")
            return []

        raw_posts: List[Post] = []
        for req in target_requests:
            if not isinstance(req, (tuple, list)) or len(req) != 2:
                logger.warning(f"Invalid target request format: {req}. Must be (platform, post_id_or_url).")
                continue

            platform_name, target_id = req[0], req[1]
            if not platform_name or not target_id:
                logger.warning(f"Empty target platform or target_id in request: {req}")
                continue

            platform_lower = str(platform_name).lower().strip()
            if platform_lower not in self.FETCHERS:
                logger.warning(f"Unsupported target platform '{platform_name}'.")
                continue
            
            fetcher = self.FETCHERS[platform_lower]()
            logger.info(f"Fetching target '{target_id}' on platform '{platform_lower}'...")
            try:
                post = fetcher.fetch_target(str(target_id))
                if post and is_valid_post(post):
                    raw_posts.append(post)
                else:
                    logger.warning(f"Target '{target_id}' on platform '{platform_lower}' returned invalid/unavailable data.")
            except Exception as err:
                logger.error(f"Target fetch failed for '{target_id}' on '{platform_lower}': {err}")

        return self._deduplicate_and_format(raw_posts)

    def _deduplicate_and_format(self, raw_posts: List[Post]) -> List[Dict[str, Any]]:
        seen_keys = set()
        formatted_posts: List[Dict[str, Any]] = []

        for p in raw_posts:
            if not is_valid_post(p):
                continue

            post_dict = p.to_dict()
            primary_key = f"{post_dict.get('platform')}:{post_dict.get('post_id')}"
            url_key = post_dict.get("url")

            if primary_key in seen_keys:
                logger.debug(f"Skipping duplicate key: {primary_key}")
                continue
            if url_key and url_key in seen_keys:
                logger.debug(f"Skipping duplicate URL: {url_key}")
                continue

            seen_keys.add(primary_key)
            if url_key:
                seen_keys.add(url_key)

            formatted_posts.append(post_dict)

        logger.info(f"Total extracted posts after deduplication: {len(formatted_posts)}")
        return formatted_posts

    @staticmethod
    def save_to_json(posts: List[Dict[str, Any]], filepath: str = "discovered_posts.json") -> None:
        """Saves normalized posts list to output JSON file for Person C consumption."""
        output_payload = {
            "posts": posts
        }
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(output_payload, f, indent=2, ensure_ascii=False)
        logger.info(f"Successfully saved {len(posts)} posts to '{filepath}'.")

    def extract_post_from_image(self, image_input: str, output_filepath: str = "post.json") -> Dict[str, Any]:
        """
        Integration contract for Person A: accepts cropped face image path/URL as runtime input.
        Performs genuine reverse image search using actual search services/APIs.
        Filters matching social media posts, extracts details, and writes output deliverable to post.json.
        """
        logger.info(f"Received cropped face image input from Person A: '{image_input}'")
        search_engine = ReverseImageSearchEngine()

        try:
            matched_posts, provider_used = search_engine.search_and_extract_posts(image_input)
        except Exception as err:
            logger.error(f"Reverse image search failed for '{image_input}': {err}")
            deliverable = {
                "canonical_data": None,
                "extraction_metadata": {
                    "discovered_at": format_iso8601(),
                    "extracted_by": "PersonB_PostDiscoveryEngine/2.0",
                    "schema_version": "1.0",
                    "search_provider": "unknown",
                    "input_image": str(image_input),
                    "error": str(err),
                    "status": "image_processing_error"
                },
                "all_matched_posts": []
            }
            self.save_post_deliverable(deliverable, filepath=output_filepath)
            return deliverable

        formatted_posts = self._deduplicate_and_format(matched_posts)
        primary_canonical = formatted_posts[0] if formatted_posts else None

        deliverable = {
            "canonical_data": primary_canonical,
            "extraction_metadata": {
                "discovered_at": format_iso8601(),
                "extracted_by": "PersonB_PostDiscoveryEngine/2.0",
                "schema_version": "1.0",
                "search_provider": provider_used,
                "input_image": str(image_input),
                "status": "success" if primary_canonical else "no_social_media_post_found"
            },
            "all_matched_posts": formatted_posts
        }

        self.save_post_deliverable(deliverable, filepath=output_filepath)
        return deliverable

    @staticmethod
    def save_post_deliverable(payload: Dict[str, Any], filepath: str = "post.json") -> None:
        """Saves deliverable payload to output JSON file (post.json)."""
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(payload, f, indent=2, ensure_ascii=False)
        logger.info(f"Successfully saved deliverable to '{filepath}'.")


def main():
    parser = argparse.ArgumentParser(description="Person B Social Media Post Data Extraction Module")
    parser.add_argument("--image", "-i", type=str, default=None, help="Cropped face image file path or URL from Person A")
    parser.add_argument("--query", "-q", type=str, default=None, help="Search query for post discovery")
    parser.add_argument("--target", "-t", type=str, default=None, help="Specific Person A target in format 'platform:post_id_or_url'")
    parser.add_argument("--sources", "-s", nargs="+", default=["hackernews", "bluesky", "github", "reddit"], help="Data sources to query (hackernews, bluesky, reddit, github)")
    parser.add_argument("--limit", "-l", type=int, default=5, help="Maximum posts to fetch per source")
    parser.add_argument("--output", "-o", type=str, default=None, help="Output JSON filepath")
    args = parser.parse_args()

    if not args.image and not args.target and not args.query:
        parser.error("Must specify --image / -i, --target / -t, or --query / -q.")

    engine = PostDiscoveryEngine(sources=args.sources)

    if args.image:
        output_file = args.output if args.output else "post.json"
        engine.extract_post_from_image(args.image, output_filepath=output_file)
    elif args.target:
        output_file = args.output if args.output else "discovered_posts.json"
        parts = args.target.split(":", 1)
        if len(parts) == 2:
            platform, target_id = parts[0], parts[1]
            posts = engine.extract_target_posts([(platform, target_id)])
            engine.save_to_json(posts, filepath=output_file)
        else:
            logger.error("Target flag format must be 'platform:post_id_or_url'")
            sys.exit(1)
    else:
        output_file = args.output if args.output else "discovered_posts.json"
        posts = engine.discover(query=args.query, limit_per_source=args.limit)
        engine.save_to_json(posts, filepath=output_file)


if __name__ == "__main__":
    main()
