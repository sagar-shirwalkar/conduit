#!/usr/bin/env python3
"""Generate an admin API key for bootstrapping Conduit."""

from conduit.common.crypto import generate_api_key


def main() -> None:
    raw_key, key_hash, key_prefix = generate_api_key()

    print("\n" + "=" * 60)
    print("  CONDUIT — Admin API Key Generator")
    print("=" * 60)
    print()
    print(f"  API Key:    {raw_key}")
    print(f"  Prefix:     {key_prefix}")
    print(f"  SHA-256:    {key_hash}")
    print()
    print("  ⚠️  Save this key now — it cannot be retrieved later!")
    print()
    print("  Set it in your environment:")
    print(f'    export CONDUIT_MASTER_API_KEY="{raw_key}"')
    print()
    print("  Or in conduit.yaml:")
    print(f"    auth:")
    print(f'      master_api_key: "{raw_key}"')
    print()
    print("=" * 60 + "\n")


if __name__ == "__main__":
    main()