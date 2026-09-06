"""
test_post_discovery.py - Isolated Unit Tests for Person B Post Data Extraction Module
"""

import json
import os
import unittest
from unittest.mock import MagicMock, patch
import urllib.error

from post_discovery import (
    Post,
    Engagement,
    PostDiscoveryEngine,
    HackerNewsFetcher,
    BlueskyFetcher,
    RedditFetcher,
    GitHubFetcher,
    MockFetcher,
    parse_timestamp_to_iso8601,
    is_valid_post,
    classify_social_media_url,
    extract_post_from_social_url,
    load_image_bytes,
    ReverseImageSearchEngine
)


class TestPersonBDataExtraction(unittest.TestCase):

    # --------------------------------------------------------------------------
    # 1. Core Schema & Canonical Determinism (Person C Integration Contract)
    # --------------------------------------------------------------------------

    def test_engagement_schema(self):
        eng = Engagement(likes=10, comments=2)
        eng_dict = eng.to_dict()
        self.assertEqual(eng_dict["likes"], 10)
        self.assertEqual(eng_dict["comments"], 2)
        self.assertIsNone(eng_dict["shares"])
        self.assertIsNone(eng_dict["views"])

    def test_canonical_determinism_for_person_c(self):
        """
        Verify that canonical post payload is strictly deterministic regardless of
        when or how many times Person B extracts the data (hash stability for Person C).
        """
        post1 = Post(
            post_id="45129085",
            platform="HackerNews",  # Mixed casing
            author="_nvs",
            author_id="_nvs",
            content="Stripe Launches L1 Blockchain: Tempo",
            timestamp="2025-09-04T16:32:24Z",
            url="https://tempo.xyz",
            media_urls=["https://b.com/img.png", "https://a.com/img.png"],  # Unsorted
            engagement=Engagement(likes=808, comments=1072),
            discovered_at="2026-09-04T10:00:00Z"
        )
        post2 = Post(
            post_id="45129085",
            platform="hackernews",
            author="_nvs",
            author_id="_nvs",
            content="Stripe Launches L1 Blockchain: Tempo",
            timestamp="2025-09-04T16:32:24Z",
            url="https://tempo.xyz",
            media_urls=["https://a.com/img.png", "https://b.com/img.png"],
            engagement=Engagement(likes=808, comments=1072),
            discovered_at="2026-09-04T12:34:56Z"  # Different runtime timestamp
        )

        canon1 = post1.to_canonical_dict()
        canon2 = post2.to_canonical_dict()

        # Canonical dicts and media ordering must be identical
        self.assertEqual(canon1, canon2)
        self.assertEqual(canon1["platform"], "hackernews")
        self.assertEqual(canon1["media_urls"], ["https://a.com/img.png", "https://b.com/img.png"])

        # Serialized JSON must be byte-for-byte identical
        json1 = json.dumps(canon1, sort_keys=True)
        json2 = json.dumps(canon2, sort_keys=True)
        self.assertEqual(json1, json2)

    def test_person_c_payload_contract(self):
        post = Post(
            post_id="101",
            platform="mock_platform",
            author="alice",
            author_id="usr_01",
            content="Person B to Person C test payload",
            timestamp="2026-09-04T10:00:00Z",
            url="https://example.com/101",
            media_urls=[],
            engagement=Engagement(likes=10, comments=2)
        )
        payload = post.to_person_c_payload()
        self.assertIn("canonical_data", payload)
        self.assertIn("extraction_metadata", payload)
        self.assertEqual(payload["canonical_data"]["post_id"], "101")
        self.assertEqual(payload["extraction_metadata"]["extracted_by"], "PersonB_PostDiscoveryEngine/2.0")

    def test_timestamp_parsing(self):
        epoch_ts = 1757000000
        parsed = parse_timestamp_to_iso8601(epoch_ts)
        self.assertIsNotNone(parsed)
        self.assertTrue(parsed.endswith("Z"))

        iso_str = "2026-09-04T10:30:00+00:00"
        parsed_iso = parse_timestamp_to_iso8601(iso_str)
        self.assertEqual(parsed_iso, "2026-09-04T10:30:00Z")

        self.assertIsNone(parse_timestamp_to_iso8601("invalid_date_string"))

    # --------------------------------------------------------------------------
    # 2. Person A Integration Boundary (`extract_target_posts`)
    # --------------------------------------------------------------------------

    def test_person_a_targeted_extraction_contract(self):
        """Verify Person A boundary: extract_target_posts accepts list of (platform, target_id)."""
        engine = PostDiscoveryEngine(sources=["mock"])
        target_results = engine.extract_target_posts([("mock", "mock_target_999")])
        self.assertEqual(len(target_results), 1)
        self.assertEqual(target_results[0]["post_id"], "mock_target_999")
        self.assertEqual(target_results[0]["platform"], "mock_platform")

    def test_person_a_invalid_target_requests(self):
        """Verify invalid target tuple formats or empty inputs are rejected without crashing."""
        engine = PostDiscoveryEngine(sources=["mock"])
        # Malformed tuples
        self.assertEqual(engine.extract_target_posts("invalid_not_a_list"), [])
        self.assertEqual(engine.extract_target_posts([("mock",)]), [])
        self.assertEqual(engine.extract_target_posts([("", "123")]), [])
        self.assertEqual(engine.extract_target_posts([("unsupported_platform", "123")]), [])

    # --------------------------------------------------------------------------
    # 3. Dynamic Extraction vs Static Data Detection
    # --------------------------------------------------------------------------

    def test_different_post_inputs_produce_different_outputs(self):
        """Verify that Post A and Post B produce distinct extracted data."""
        fetcher = HackerNewsFetcher()
        
        hit_a = {
            "objectID": "10001",
            "title": "Post A Title",
            "author": "alice_dev",
            "created_at_i": 1757001000,
            "url": "https://example.com/post_a",
            "points": 150,
            "num_comments": 25
        }
        hit_b = {
            "objectID": "20002",
            "title": "Post B Title",
            "author": "bob_crypto",
            "created_at_i": 1757002000,
            "url": "https://example.com/post_b",
            "points": 340,
            "num_comments": 82
        }

        post_a = fetcher._parse_hit(hit_a)
        post_b = fetcher._parse_hit(hit_b)

        self.assertIsNotNone(post_a)
        self.assertIsNotNone(post_b)

        dict_a = post_a.to_dict()
        dict_b = post_b.to_dict()

        self.assertNotEqual(dict_a["post_id"], dict_b["post_id"])
        self.assertNotEqual(dict_a["author"], dict_b["author"])
        self.assertNotEqual(dict_a["content"], dict_b["content"])
        self.assertNotEqual(dict_a["url"], dict_b["url"])
        self.assertEqual(dict_a["post_id"], "10001")
        self.assertEqual(dict_b["post_id"], "20002")

    def test_static_data_detection_guard(self):
        """
        Static Data Guard Test: Fails if the fetcher accidentally returns hardcoded values
        instead of deriving output dynamically from input.
        """
        fetcher = HackerNewsFetcher()
        custom_id = "9988776655"
        custom_title = "Unique Non-Hardcoded Title 9988"

        hit = {
            "objectID": custom_id,
            "title": custom_title,
            "author": "dynamic_user",
            "created_at_i": 1757000000,
            "url": f"https://example.com/{custom_id}",
            "points": 99,
            "num_comments": 12
        }
        parsed = fetcher._parse_hit(hit)
        self.assertIsNotNone(parsed)
        self.assertEqual(parsed.post_id, custom_id)
        self.assertEqual(parsed.content, custom_title)

    def test_missing_optional_fields(self):
        """Verify that posts missing optional fields default to None / [] safely."""
        fetcher = HackerNewsFetcher()
        minimal_hit = {
            "objectID": "55555",
            "title": "Minimal Post Content"
        }
        post = fetcher._parse_hit(minimal_hit)
        self.assertIsNotNone(post)
        p_dict = post.to_dict()

        self.assertEqual(p_dict["post_id"], "55555")
        self.assertEqual(p_dict["content"], "Minimal Post Content")
        self.assertIsNone(p_dict["author"])
        self.assertEqual(p_dict["media_urls"], [])
        self.assertIsNone(p_dict["engagement"]["likes"])

    def test_post_validation(self):
        """Verify strict is_valid_post checks."""
        valid_post = Post(
            post_id="1", platform="hackernews", author="user", author_id="1",
            content="text", timestamp="2026-09-04T10:00:00Z", url="https://example.com",
            media_urls=[], engagement=Engagement()
        )
        self.assertTrue(is_valid_post(valid_post))

        # Invalid posts
        self.assertFalse(is_valid_post(None))
        self.assertFalse(is_valid_post("not_a_post"))

        invalid_id = Post(
            post_id="", platform="hackernews", author="user", author_id="1",
            content="text", timestamp=None, url="", media_urls=[], engagement=Engagement()
        )
        self.assertFalse(is_valid_post(invalid_id))

    # --------------------------------------------------------------------------
    # 4. HTTP Boundary Mocks (Network & Error Isolation)
    # --------------------------------------------------------------------------

    @patch("post_discovery.BaseFetcher.http_get_json")
    def test_fetch_target_mocked_success(self, mock_http):
        mock_http.return_value = {
            "id": 123456,
            "by": "test_by",
            "title": "Mocked HN Post",
            "time": 1757000000,
            "url": "https://news.ycombinator.com/item?id=123456",
            "score": 10
        }
        fetcher = HackerNewsFetcher()
        post = fetcher.fetch_target("123456")

        self.assertIsNotNone(post)
        self.assertEqual(post.post_id, "123456")
        self.assertEqual(post.author, "test_by")
        self.assertEqual(post.content, "Mocked HN Post")

    @patch("urllib.request.urlopen")
    def test_permanent_http_error_handling_no_retry(self, mock_urlopen):
        """Verify 404 / 403 permanent errors return None without retrying."""
        err = urllib.error.HTTPError(
            url="https://api.github.com", code=404, msg="Not Found", hdrs={}, fp=None
        )
        mock_urlopen.side_effect = err

        fetcher = GitHubFetcher()
        data = fetcher.http_get_json("https://api.github.com/test", retries=2)
        self.assertIsNone(data)
        # Should only be called once because 404 is a permanent error
        self.assertEqual(mock_urlopen.call_count, 1)

    @patch("urllib.request.urlopen")
    def test_transient_http_429_rate_limit_retry(self, mock_urlopen):
        """Verify HTTP 429 rate limits log warning and retry."""
        err = urllib.error.HTTPError(
            url="https://api.github.com", code=429, msg="Rate Limited", hdrs={}, fp=None
        )
        mock_urlopen.side_effect = err

        fetcher = GitHubFetcher()
        data = fetcher.http_get_json("https://api.github.com/test", retries=1)
        self.assertIsNone(data)
        # Called 2 times (initial + 1 retry)
        self.assertEqual(mock_urlopen.call_count, 2)

    # --------------------------------------------------------------------------
    # 5. Deduplication & Output Persistence
    # --------------------------------------------------------------------------

    def test_deduplication(self):
        engine = PostDiscoveryEngine(sources=["mock"])
        posts = engine.discover(query="blockchain", limit_per_source=2)
        self.assertEqual(len(posts), 2)

    def test_json_persistence(self):
        test_file = "test_discovered_posts.json"
        engine = PostDiscoveryEngine(sources=["mock"])
        posts = engine.discover(query="blockchain", limit_per_source=2)
        engine.save_to_json(posts, filepath=test_file)

        self.assertTrue(os.path.exists(test_file))
        with open(test_file, "r", encoding="utf-8") as f:
            data = json.load(f)
        
        self.assertIn("posts", data)
        self.assertEqual(len(data["posts"]), 2)
        
        if os.path.exists(test_file):
            os.remove(test_file)

    # --------------------------------------------------------------------------
    # 6. Genuine Reverse Image Search & Image Input (Person A -> Person C)
    # --------------------------------------------------------------------------

    def test_classify_social_media_url(self):
        """Verify URL domain classification for social media platforms."""
        self.assertEqual(classify_social_media_url("https://twitter.com/user/status/12345"), "twitter")
        self.assertEqual(classify_social_media_url("https://x.com/user/status/12345"), "twitter")
        self.assertEqual(classify_social_media_url("https://www.reddit.com/r/technology/comments/abc/title/"), "reddit")
        self.assertEqual(classify_social_media_url("https://bsky.app/profile/handle.bsky.social/post/rkey123"), "bluesky")
        self.assertEqual(classify_social_media_url("https://news.ycombinator.com/item?id=45129085"), "hackernews")
        self.assertEqual(classify_social_media_url("https://github.com/owner/repo/issues/101"), "github")
        self.assertEqual(classify_social_media_url("https://www.instagram.com/p/abc12345/"), "instagram")
        self.assertEqual(classify_social_media_url("https://www.facebook.com/user/posts/12345"), "facebook")
        self.assertEqual(classify_social_media_url("https://www.linkedin.com/posts/activity-12345"), "linkedin")
        self.assertIsNone(classify_social_media_url("https://example.com/random_page.html"))

    def test_load_image_bytes_missing_file(self):
        """Verify FileNotFoundError is raised for non-existent image path."""
        with self.assertRaises(FileNotFoundError):
            load_image_bytes("non_existent_cropped_face.jpg")

    def test_extract_post_from_image_missing_file_handling(self):
        """Verify extract_post_from_image generates valid post.json deliverable on invalid/missing file without crashing."""
        test_out = "test_missing_post.json"
        engine = PostDiscoveryEngine()
        result = engine.extract_post_from_image("non_existent_image.jpg", output_filepath=test_out)

        self.assertIn("canonical_data", result)
        self.assertIsNone(result["canonical_data"])
        self.assertEqual(result["extraction_metadata"]["status"], "image_processing_error")
        self.assertTrue(os.path.exists(test_out))

        if os.path.exists(test_out):
            os.remove(test_out)

    @patch.object(ReverseImageSearchEngine, "search_and_extract_posts")
    def test_extract_post_from_image_success_flow(self, mock_search):
        """Verify genuine reverse image search returns matching post and saves post.json deliverable."""
        sample_post = Post(
            post_id="tweet_999",
            platform="twitter",
            author="john_doe",
            author_id="usr_999",
            content="Original social media post containing target face.",
            timestamp="2026-09-01T12:00:00Z",
            url="https://x.com/john_doe/status/999",
            media_urls=["https://pbs.twimg.com/media/face.jpg"],
            engagement=Engagement(likes=50, comments=10)
        )
        mock_search.return_value = ([sample_post], "serpapi_google_lens")

        dummy_img = "test_dummy_cropped.jpg"
        with open(dummy_img, "wb") as f:
            f.write(b"\xFF\xD8\xFF\xE0\x00\x10JFIF\x00\x01\x01\x01\x00`\x00`\x00\x00\xFF\xD9")

        test_out = "test_post.json"
        engine = PostDiscoveryEngine()
        deliverable = engine.extract_post_from_image(dummy_img, output_filepath=test_out)

        self.assertTrue(os.path.exists(test_out))
        self.assertEqual(deliverable["extraction_metadata"]["search_provider"], "serpapi_google_lens")
        self.assertIsNotNone(deliverable["canonical_data"])
        self.assertEqual(deliverable["canonical_data"]["post_id"], "tweet_999")
        self.assertEqual(deliverable["canonical_data"]["platform"], "twitter")

        if os.path.exists(test_out):
            os.remove(test_out)
        if os.path.exists(dummy_img):
            os.remove(dummy_img)


if __name__ == "__main__":
    unittest.main()
