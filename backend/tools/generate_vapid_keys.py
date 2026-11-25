"""Para kluczy VAPID do .env: `python -m tools.generate_vapid_keys`.

Format jak z `npx web-push generate-vapid-keys` (base64url, klucz prywatny 32 B, publiczny
65 B). Prywatny klucz tylko w `.env` backendu, publiczny odbiera front z API.
"""

import base64

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec


def b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def generate() -> tuple[str, str]:
    """(klucz publiczny, klucz prywatny) w base64url."""
    key = ec.generate_private_key(ec.SECP256R1())
    private = key.private_numbers().private_value.to_bytes(32, "big")
    public = key.public_key().public_bytes(
        serialization.Encoding.X962, serialization.PublicFormat.UncompressedPoint
    )
    return b64url(public), b64url(private)


if __name__ == "__main__":
    public, private = generate()
    print(f"VAPID_PUBLIC_KEY={public}")
    print(f"VAPID_PRIVATE_KEY={private}")
    print("VAPID_SUBJECT=mailto:twoj-adres@example.com")
