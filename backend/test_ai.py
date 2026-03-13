"""
Minimal Azure OpenAI connectivity test.
Run from the backend/ directory:
    .venv/Scripts/python.exe test_ai.py
"""
import asyncio
import os
import sys


def load_env(path: str = ".env") -> None:
    """Manually parse .env without any library."""
    try:
        with open(path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                if "=" in line:
                    key, _, val = line.partition("=")
                    os.environ.setdefault(key.strip(), val.strip())
    except FileNotFoundError:
        print(f"WARNING: {path} not found — using existing env vars")


async def main() -> None:
    load_env(".env")

    key = os.environ.get("AZURE_OPENAI_KEY", "")
    endpoint = os.environ.get("AZURE_OPENAI_ENDPOINT", "")
    deployment = os.environ.get("AZURE_OPENAI_DEPLOYMENT_NAME", "gpt-4o")
    api_version = os.environ.get("AZURE_OPENAI_API_VERSION", "2024-02-01")
    ai_enabled = os.environ.get("AI_ENABLED", "false").lower()

    print(f"AI_ENABLED                  = {ai_enabled!r}")
    print(f"AZURE_OPENAI_KEY len        = {len(key)}")
    print(f"AZURE_OPENAI_KEY prefix     = {key[:8]!r}" if key else "AZURE_OPENAI_KEY            = (empty)")
    print(f"AZURE_OPENAI_ENDPOINT       = {endpoint!r}")
    print(f"AZURE_OPENAI_DEPLOYMENT_NAME= {deployment!r}")
    print(f"AZURE_OPENAI_API_VERSION    = {api_version!r}")

    errors = []
    if not key or key == "your-azure-openai-key-here":
        errors.append("AZURE_OPENAI_KEY is not set or is still the placeholder value.")
    if not endpoint or endpoint == "https://your-resource-name.openai.azure.com/":
        errors.append("AZURE_OPENAI_ENDPOINT is not set or is still the placeholder value.")
    if not deployment:
        errors.append("AZURE_OPENAI_DEPLOYMENT_NAME is empty.")
    if errors:
        print()
        for e in errors:
            print(f"ERROR: {e}")
        print("\nOpen backend/.env and fill in your real Azure credentials.")
        sys.exit(1)

    if ai_enabled not in ("true", "1", "yes"):
        print(f"\nWARNING: AI_ENABLED={ai_enabled!r}. Set AI_ENABLED=true in .env to activate AI.")

    print("\nAttempting Azure OpenAI API call...")
    try:
        from openai import AsyncAzureOpenAI
    except ImportError:
        print("ERROR: 'openai' package not installed. Run: uv add openai")
        sys.exit(1)

    client = AsyncAzureOpenAI(
        api_key=key,
        azure_endpoint=endpoint,
        api_version=api_version,
    )
    try:
        resp = await client.chat.completions.create(
            model=deployment,
            max_tokens=20,
            messages=[{"role": "user", "content": "Say hello in exactly 3 words."}],
        )
        text = resp.choices[0].message.content
        print(f"\nSUCCESS: {text!r}")
    except Exception as exc:
        err_type = type(exc).__name__
        print(f"\nERROR ({err_type}): {exc}")
        if "AuthenticationError" in err_type or "401" in str(exc):
            print("  Your API key was rejected. Check for typos or leading/trailing spaces.")
        elif "NotFound" in err_type or "404" in str(exc):
            print(f"  Deployment '{deployment}' not found. Check AZURE_OPENAI_DEPLOYMENT_NAME.")
        elif "Connection" in err_type:
            print(f"  Could not connect to {endpoint!r}. Check AZURE_OPENAI_ENDPOINT.")
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
