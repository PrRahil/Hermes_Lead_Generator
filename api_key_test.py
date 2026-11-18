"""Paste your OpenRouter API key below and run: python api_key_test.py

Uses OpenRouter's OpenAI-compatible API (https://openrouter.ai/api/v1).
"""

import urllib.error
import urllib.request

# Paste your OpenRouter key here (usually starts with sk-or-):
API_KEY = "sk-or-..."

BASE_URL = "https://openrouter.ai/api/v1"


def main() -> None:
    key = API_KEY.strip()
    if not key or key in ("sk-...", "sk-or-..."):
        print("Paste your OpenRouter API key into API_KEY first.")
        return

    req = urllib.request.Request(
        f"{BASE_URL}/models",
        headers={
            "Authorization": f"Bearer {key}",
            "Content-Type": "application/json",
        },
    )

    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            if resp.status == 200:
                print("VALID — OpenRouter key works (OpenAI-compatible API).")
            else:
                print(f"UNEXPECTED — HTTP {resp.status}")
    except urllib.error.HTTPError as e:
        if e.code == 401:
            print("INVALID — key rejected (401 Unauthorized).")
        elif e.code == 429:
            print("KEY LOOKS OK — but rate-limited (429). Try again later.")
        else:
            body = e.read().decode("utf-8", errors="replace")[:300]
            print(f"FAILED — HTTP {e.code}: {body}")
    except Exception as e:
        print(f"ERROR — {e}")


if __name__ == "__main__":
    main()
