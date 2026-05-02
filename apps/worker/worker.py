import json
import os
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

import redis
import requests
from sqlalchemy import DateTime, ForeignKey, String, Text, create_engine, select, text
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column, relationship, sessionmaker
from twilio.rest import Client


DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql+psycopg://clara:clara@localhost:5432/clara_voiceops",
)
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")
AI_SCRIPT_ENABLED = os.getenv("AI_SCRIPT_ENABLED", "true").lower() in {"1", "true", "yes"}
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-1.5-flash")
ELEVENLABS_API_KEY = os.getenv("ELEVENLABS_API_KEY", "")
DEFAULT_ELEVENLABS_VOICE_ID = os.getenv("ELEVENLABS_VOICE_ID", "")
PUBLIC_AUDIO_BASE_URL = os.getenv("PUBLIC_AUDIO_BASE_URL", "")
TWILIO_ACCOUNT_SID = os.getenv("TWILIO_ACCOUNT_SID", "")
TWILIO_AUTH_TOKEN = os.getenv("TWILIO_AUTH_TOKEN", "")
TWILIO_FROM_NUMBER = os.getenv("TWILIO_FROM_NUMBER", "")
GENERATED_DIR = Path(os.getenv("GENERATED_DIR", "/app/generated"))

engine = create_engine(DATABASE_URL, pool_pre_ping=True)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)
queue = redis.from_url(REDIS_URL, decode_responses=True)


class Base(DeclarativeBase):
    pass


class Patient(Base):
    __tablename__ = "patients"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    full_name: Mapped[str] = mapped_column(String(160), nullable=False)
    phone_number: Mapped[str] = mapped_column(String(40), nullable=False)


class Provider(Base):
    __tablename__ = "providers"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    full_name: Mapped[str] = mapped_column(String(160), nullable=False)
    role: Mapped[str] = mapped_column(String(40), nullable=False)


class ProviderVoice(Base):
    __tablename__ = "provider_voices"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    provider_id: Mapped[str] = mapped_column(ForeignKey("providers.id"), nullable=False)
    elevenlabs_voice_id: Mapped[str] = mapped_column(String(160), nullable=False)


class Reminder(Base):
    __tablename__ = "reminders"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    patient_id: Mapped[str] = mapped_column(ForeignKey("patients.id"), nullable=False)
    provider_id: Mapped[str] = mapped_column(ForeignKey("providers.id"), nullable=False)
    provider_voice_id: Mapped[str | None] = mapped_column(ForeignKey("provider_voices.id"), nullable=True)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(40), default="queued")

    patient: Mapped["Patient"] = relationship()
    provider: Mapped["Provider"] = relationship()
    provider_voice: Mapped["ProviderVoice"] = relationship()


class CallAttempt(Base):
    __tablename__ = "call_attempts"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    reminder_id: Mapped[str] = mapped_column(ForeignKey("reminders.id"), nullable=False)
    status: Mapped[str] = mapped_column(String(40), default="queued")
    generated_script: Mapped[str | None] = mapped_column(Text, nullable=True)
    audio_path: Mapped[str | None] = mapped_column(String(400), nullable=True)
    twilio_call_sid: Mapped[str | None] = mapped_column(String(120), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))


def ensure_schema() -> None:
    with engine.begin() as conn:
        conn.execute(text("ALTER TABLE call_attempts ADD COLUMN IF NOT EXISTS generated_script TEXT"))


def generate_ai_script(reminder: Reminder) -> str:
    if not AI_SCRIPT_ENABLED or not GEMINI_API_KEY:
        return reminder.message

    try:
        from langchain_google_genai import ChatGoogleGenerativeAI
    except ImportError:
        print("LangChain Gemini package unavailable; using original reminder message.")
        return reminder.message

    llm = ChatGoogleGenerativeAI(
        model=GEMINI_MODEL,
        google_api_key=GEMINI_API_KEY,
        temperature=0.3,
    )
    prompt = f"""
You write short healthcare reminder call scripts for a demo app.

Rules:
- Use only the provided information.
- Do not diagnose, prescribe, or add medical advice.
- Keep it under 45 words.
- Sound warm, calm, and professional.
- Mention the provider role and name.
- End by telling the patient to contact their care team with questions.

Patient: {reminder.patient.full_name}
Provider: {reminder.provider.full_name}, {reminder.provider.role}
Original reminder: {reminder.message}
"""
    response = llm.invoke(prompt)
    generated = getattr(response, "content", str(response)).strip()
    return generated or reminder.message


def generate_audio(reminder: Reminder, script_text: str) -> str:
    GENERATED_DIR.mkdir(parents=True, exist_ok=True)
    output_path = GENERATED_DIR / f"{reminder.id}.mp3"
    voice_id = (
        reminder.provider_voice.elevenlabs_voice_id
        if reminder.provider_voice and reminder.provider_voice.elevenlabs_voice_id
        else DEFAULT_ELEVENLABS_VOICE_ID
    )

    if not ELEVENLABS_API_KEY or not voice_id:
        output_path.write_text(
            f"Demo placeholder audio for reminder {reminder.id}: {script_text}\n",
            encoding="utf-8",
        )
        print("ElevenLabs credentials missing; wrote placeholder artifact.")
        return str(output_path)

    response = requests.post(
        f"https://api.elevenlabs.io/v1/text-to-speech/{voice_id}",
        headers={"xi-api-key": ELEVENLABS_API_KEY, "Content-Type": "application/json"},
        json={
            "text": script_text,
            "model_id": "eleven_multilingual_v2",
            "voice_settings": {"stability": 0.55, "similarity_boost": 0.8},
        },
        timeout=60,
    )
    response.raise_for_status()
    output_path.write_bytes(response.content)
    return str(output_path)


def maybe_place_twilio_call(reminder: Reminder, audio_path: str) -> str | None:
    if not all([TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN, TWILIO_FROM_NUMBER, PUBLIC_AUDIO_BASE_URL]):
        print("Twilio configuration incomplete; leaving call attempt as audio_generated.")
        return None

    audio_url = f"{PUBLIC_AUDIO_BASE_URL.rstrip('/')}/{Path(audio_path).name}"
    twiml = f'<Response><Play>{audio_url}</Play></Response>'
    client = Client(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN)
    call = client.calls.create(to=reminder.patient.phone_number, from_=TWILIO_FROM_NUMBER, twiml=twiml)
    return call.sid


def process_job(payload: dict[str, str]) -> None:
    reminder_id = payload["reminder_id"]
    with SessionLocal() as db:
        reminder = db.scalar(select(Reminder).where(Reminder.id == reminder_id))
        if not reminder:
            print(f"Reminder {reminder_id} not found")
            return

        attempt = CallAttempt(reminder_id=reminder.id, status="processing")
        db.add(attempt)
        reminder.status = "processing"
        db.commit()

        try:
            generated_script = generate_ai_script(reminder)
            attempt.generated_script = generated_script
            audio_path = generate_audio(reminder, generated_script)
            call_sid = maybe_place_twilio_call(reminder, audio_path)
            attempt.status = "call_started" if call_sid else "audio_generated"
            attempt.audio_path = audio_path
            attempt.twilio_call_sid = call_sid
            reminder.status = attempt.status
            print(f"Processed reminder {reminder.id} with status {attempt.status}")
        except Exception as exc:
            attempt.status = "failed"
            attempt.error_message = str(exc)
            reminder.status = "failed"
            print(f"Failed reminder {reminder.id}: {exc}")
        finally:
            db.commit()


def main() -> None:
    ensure_schema()
    print("Clara VoiceOps worker started")
    while True:
        job = queue.brpop("reminder_jobs", timeout=5)
        if not job:
            time.sleep(1)
            continue
        _, raw_payload = job
        process_job(json.loads(raw_payload))


if __name__ == "__main__":
    main()
