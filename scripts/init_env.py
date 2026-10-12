"""Create a fresh local .env from the example; never overwrite existing secrets."""
import secrets
from pathlib import Path

root = Path(__file__).resolve().parents[1]
destination = root / ".env"
content = (root / ".env.example").read_text(encoding="utf-8")
content = content.replace("replace_with_new_random_urlsafe_password", secrets.token_urlsafe(32))
with destination.open("x", encoding="utf-8", newline="\n") as out:
    out.write(content)
print("Created local .env with a new random password; contents not printed.")
