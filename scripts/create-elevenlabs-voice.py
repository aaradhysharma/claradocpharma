import json
import mimetypes
import os
from pathlib import Path
from urllib import error, request
from uuid import uuid4


def load_dotenv(path: Path) -> None:
    if not path.exists():
        return
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


def multipart_body(fields: dict[str, str], files: dict[str, Path]) -> tuple[bytes, str]:
    boundary = f"----claraVoiceOps{uuid4().hex}"
    parts: list[bytes] = []

    for name, value in fields.items():
        parts.append(f"--{boundary}\r\n".encode())
        parts.append(f'Content-Disposition: form-data; name="{name}"\r\n\r\n'.encode())
        parts.append(value.encode())
        parts.append(b"\r\n")

    for name, path in files.items():
        content_type = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
        parts.append(f"--{boundary}\r\n".encode())
        parts.append(
            f'Content-Disposition: form-data; name="{name}"; filename="{path.name}"\r\n'.encode()
        )
        parts.append(f"Content-Type: {content_type}\r\n\r\n".encode())
        parts.append(path.read_bytes())
        parts.append(b"\r\n")

    parts.append(f"--{boundary}--\r\n".encode())
    return b"".join(parts), boundary


def save_voice_id(env_path: Path, key: str, voice_id: str) -> None:
    """Update a single KEY= line in .env (e.g. PHARMACIST_ELEVENLABS_VOICE_ID)."""
    prefix = f"{key}="
    lines = env_path.read_text(encoding="utf-8").splitlines() if env_path.exists() else []
    for index, line in enumerate(lines):
        if line.startswith(prefix):
            lines[index] = f"{key}={voice_id}"
            break
    else:
        lines.append(f"{key}={voice_id}")
    env_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    env_path = Path(".env")
    load_dotenv(env_path)

    api_key = os.environ.get("ELEVENLABS_API_KEY", "").strip()
    if not api_key:
        raise SystemExit("ELEVENLABS_API_KEY is missing from .env")

    sample = Path("voicesample pharma/bunny pharma voice note.ogg")
    if not sample.exists():
        raise SystemExit(f"Voice sample not found: {sample}")

    body, boundary = multipart_body(
        fields={
            "name": "Clara Pharmacy Demo Voice",
            "description": "Pharmacy reminder demo voice for Clara VoiceOps interview project.",
        },
        files={"files": sample},
    )

    req = request.Request(
        "https://api.elevenlabs.io/v1/voices/add",
        data=body,
        headers={
            "xi-api-key": api_key,
            "Content-Type": f"multipart/form-data; boundary={boundary}",
        },
        method="POST",
    )

    try:
        with request.urlopen(req, timeout=120) as response:
            data = json.loads(response.read().decode())
    except error.HTTPError as exc:
        detail = exc.read().decode(errors="replace")
        raise SystemExit(f"ElevenLabs voice creation failed: HTTP {exc.code}: {detail}") from exc

    voice_id = data.get("voice_id")
    if not voice_id:
        raise SystemExit(f"ElevenLabs response did not include voice_id: {data}")

    # This script uses the pharmacy sample; store under pharmacist key (Bunny clone).
    save_voice_id(env_path, "PHARMACIST_ELEVENLABS_VOICE_ID", voice_id)
    print(json.dumps({"status": "saved_to_env", "key": "PHARMACIST_ELEVENLABS_VOICE_ID", "voice_id": voice_id}))


if __name__ == "__main__":
    main()
