import json
import hashlib


def canonicalize_json(data):
    """
    Convert JSON into a deterministic string.
    Same data -> same string -> same hash.
    """
    return json.dumps(
        data,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False
    )


def hash_post(data):
    """
    Generate SHA-256 hash of canonical JSON.
    """
    canonical_json = canonicalize_json(data)

    hash_hex = hashlib.sha256(
        canonical_json.encode("utf-8")
    ).hexdigest()

    return hash_hex


if __name__ == "__main__":
    # Temporary test data
    test_post = {
        "platform": "Instagram",
        "post_url": "https://example.com/post/123",
        "caption": "Renewable energy project",
        "author": "test_user"
    }

    canonical = canonicalize_json(test_post)
    post_hash = hash_post(test_post)

    print("Canonical JSON:")
    print(canonical)

    print("\nSHA-256 Hash:")
    print(post_hash)

    print("\nHash length:", len(post_hash))