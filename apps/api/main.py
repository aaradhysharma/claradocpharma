import json
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Generator
from xml.sax.saxutils import escape as xml_escape

import redis
import requests
from fastapi import Depends, FastAPI, Form, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, Response
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text, create_engine, select, text
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, joinedload, mapped_column, relationship, sessionmaker


APP_VERSION = os.getenv("APP_VERSION", "0.0.5")
# ElevenLabs voice IDs cloned from repo voice samples (no generic premade fallbacks).
AADI_DOCTOR_VOICE_ID = "VrD3EIr2SqyhWLakvrMt"
BUNNY_PHARMACIST_VOICE_ID = "fw4xyJhgrfgP0Y1OuCBb"
DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql+psycopg://clara:clara@localhost:5432/clara_voiceops",
)
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")
GENERATED_DIR = Path(os.getenv("GENERATED_DIR", "/app/generated"))

ELEVENLABS_API_KEY = os.getenv("ELEVENLABS_API_KEY", "")
ELEVENLABS_MODEL = os.getenv("ELEVENLABS_MODEL", "eleven_turbo_v2_5")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-1.5-flash")
TWILIO_ACCOUNT_SID = os.getenv("TWILIO_ACCOUNT_SID", "")
TWILIO_AUTH_TOKEN = os.getenv("TWILIO_AUTH_TOKEN", "")
TWILIO_FROM_NUMBER = os.getenv("TWILIO_FROM_NUMBER", "")
PUBLIC_API_BASE_URL = os.getenv("PUBLIC_API_BASE_URL", "").rstrip("/")
PUBLIC_AUDIO_BASE_URL = os.getenv("PUBLIC_AUDIO_BASE_URL", "").rstrip("/") or (
    f"{PUBLIC_API_BASE_URL}/audio" if PUBLIC_API_BASE_URL else ""
)
MAX_CONVERSATION_TURNS = int(os.getenv("MAX_CONVERSATION_TURNS", "12"))

engine = create_engine(DATABASE_URL, pool_pre_ping=True)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)
queue = redis.from_url(REDIS_URL, decode_responses=True)


class Base(DeclarativeBase):
    pass


class Patient(Base):
    __tablename__ = "patients"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    full_name: Mapped[str] = mapped_column(String(160), nullable=False)
    phone_number: Mapped[str] = mapped_column(String(40), nullable=False)
    preferred_language: Mapped[str] = mapped_column(String(40), default="en")
    consent_to_call: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    assignments: Mapped[list["CareAssignment"]] = relationship(back_populates="patient")
    reminders: Mapped[list["Reminder"]] = relationship(back_populates="patient")


class Provider(Base):
    __tablename__ = "providers"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    full_name: Mapped[str] = mapped_column(String(160), nullable=False)
    role: Mapped[str] = mapped_column(String(40), nullable=False)
    department: Mapped[str] = mapped_column(String(120), default="primary care")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    voices: Mapped[list["ProviderVoice"]] = relationship(back_populates="provider")
    assignments: Mapped[list["CareAssignment"]] = relationship(back_populates="provider")
    reminders: Mapped[list["Reminder"]] = relationship(back_populates="provider")


class ProviderVoice(Base):
    __tablename__ = "provider_voices"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    provider_id: Mapped[str] = mapped_column(ForeignKey("providers.id"), nullable=False)
    label: Mapped[str] = mapped_column(String(120), nullable=False)
    elevenlabs_voice_id: Mapped[str] = mapped_column(String(160), nullable=False)
    is_default: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    provider: Mapped["Provider"] = relationship(back_populates="voices")
    reminders: Mapped[list["Reminder"]] = relationship(back_populates="provider_voice")


class CareAssignment(Base):
    __tablename__ = "care_assignments"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    patient_id: Mapped[str] = mapped_column(ForeignKey("patients.id"), nullable=False)
    provider_id: Mapped[str] = mapped_column(ForeignKey("providers.id"), nullable=False)
    relationship_type: Mapped[str] = mapped_column(String(60), nullable=False)
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    patient: Mapped["Patient"] = relationship(back_populates="assignments")
    provider: Mapped["Provider"] = relationship(back_populates="assignments")


class Reminder(Base):
    __tablename__ = "reminders"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    patient_id: Mapped[str] = mapped_column(ForeignKey("patients.id"), nullable=False)
    provider_id: Mapped[str] = mapped_column(ForeignKey("providers.id"), nullable=False)
    provider_voice_id: Mapped[str] = mapped_column(ForeignKey("provider_voices.id"), nullable=True)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(40), default="draft")
    scheduled_for: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    patient: Mapped["Patient"] = relationship(back_populates="reminders")
    provider: Mapped["Provider"] = relationship(back_populates="reminders")
    provider_voice: Mapped["ProviderVoice"] = relationship(back_populates="reminders")
    call_attempts: Mapped[list["CallAttempt"]] = relationship(back_populates="reminder")


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

    reminder: Mapped["Reminder"] = relationship(back_populates="call_attempts")

    @property
    def audio_url(self) -> str | None:
        if not self.audio_path:
            return None
        return f"/audio/{Path(self.audio_path).name}"


class Conversation(Base):
    __tablename__ = "conversations"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    patient_id: Mapped[str] = mapped_column(ForeignKey("patients.id"), nullable=False)
    provider_id: Mapped[str] = mapped_column(ForeignKey("providers.id"), nullable=False)
    provider_voice_id: Mapped[str | None] = mapped_column(ForeignKey("provider_voices.id"), nullable=True)
    to_number: Mapped[str] = mapped_column(String(40), nullable=False)
    from_number: Mapped[str] = mapped_column(String(40), nullable=False)
    purpose: Mapped[str] = mapped_column(Text, default="check-in")
    status: Mapped[str] = mapped_column(String(40), default="initiated")
    twilio_call_sid: Mapped[str | None] = mapped_column(String(120), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    turn_count: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    patient: Mapped["Patient"] = relationship()
    provider: Mapped["Provider"] = relationship()
    provider_voice: Mapped["ProviderVoice"] = relationship()
    turns: Mapped[list["ConversationTurn"]] = relationship(
        back_populates="conversation",
        order_by="ConversationTurn.turn_index",
    )


class ConversationTurn(Base):
    __tablename__ = "conversation_turns"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    conversation_id: Mapped[str] = mapped_column(ForeignKey("conversations.id"), nullable=False)
    turn_index: Mapped[int] = mapped_column(Integer, nullable=False)
    role: Mapped[str] = mapped_column(String(20), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    audio_path: Mapped[str | None] = mapped_column(String(400), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    conversation: Mapped["Conversation"] = relationship(back_populates="turns")

    @property
    def audio_url(self) -> str | None:
        if not self.audio_path:
            return None
        return f"/audio/{Path(self.audio_path).name}"


class PatientCreate(BaseModel):
    full_name: str
    phone_number: str
    preferred_language: str = "en"
    consent_to_call: bool = True


class ProviderCreate(BaseModel):
    full_name: str
    role: str = Field(pattern="^(doctor|pharmacist|nurse)$")
    department: str = "primary care"


class ProviderVoiceCreate(BaseModel):
    provider_id: str
    label: str
    elevenlabs_voice_id: str
    is_default: bool = True


class CareAssignmentCreate(BaseModel):
    patient_id: str
    provider_id: str
    relationship_type: str


class ReminderCreate(BaseModel):
    patient_id: str
    provider_id: str
    provider_voice_id: str | None = None
    message: str
    scheduled_for: datetime | None = None
    queue_now: bool = True


class EntityOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str


class PatientOut(EntityOut):
    full_name: str
    phone_number: str
    preferred_language: str
    consent_to_call: bool


class ProviderOut(EntityOut):
    full_name: str
    role: str
    department: str


class ProviderVoiceOut(EntityOut):
    provider_id: str
    label: str
    elevenlabs_voice_id: str
    is_default: bool


class CareAssignmentOut(EntityOut):
    patient_id: str
    provider_id: str
    relationship_type: str
    active: bool


class CareRelationshipOut(EntityOut):
    patient_id: str
    patient_name: str
    patient_phone: str
    provider_id: str
    provider_name: str
    provider_role: str
    relationship_type: str
    provider_voice_id: str | None
    voice_label: str | None
    elevenlabs_voice_id: str | None


class ReminderOut(EntityOut):
    patient_id: str
    provider_id: str
    provider_voice_id: str | None
    message: str
    status: str
    scheduled_for: datetime | None


class CallAttemptOut(EntityOut):
    reminder_id: str
    status: str
    generated_script: str | None
    audio_path: str | None
    audio_url: str | None
    twilio_call_sid: str | None
    error_message: str | None


class OutboundCallCreate(BaseModel):
    relationship_id: str | None = None
    patient_id: str | None = None
    provider_id: str | None = None
    provider_voice_id: str | None = None
    to_number: str | None = None
    purpose: str = "Friendly check-in to confirm the patient is taking their medication and feeling well."


class ConversationTurnOut(EntityOut):
    conversation_id: str
    turn_index: int
    role: str
    content: str
    audio_url: str | None


class ConversationOut(EntityOut):
    patient_id: str
    provider_id: str
    provider_voice_id: str | None
    to_number: str
    from_number: str
    purpose: str
    status: str
    twilio_call_sid: str | None
    error_message: str | None
    turn_count: int
    created_at: datetime
    updated_at: datetime
    patient_name: str | None = None
    provider_name: str | None = None
    voice_label: str | None = None
    turns: list[ConversationTurnOut] = []


app = FastAPI(title="Clara VoiceOps API", version=APP_VERSION)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def create_schema() -> None:
    Base.metadata.create_all(bind=engine)
    with engine.begin() as conn:
        conn.execute(text("ALTER TABLE call_attempts ADD COLUMN IF NOT EXISTS generated_script TEXT"))


@app.on_event("startup")
def on_startup() -> None:
    create_schema()


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "service": "clara-api", "version": APP_VERSION}


@app.get("/audio/{filename}")
def get_audio(filename: str) -> FileResponse:
    if "/" in filename or "\\" in filename or not filename.endswith(".mp3"):
        raise HTTPException(status_code=400, detail="Invalid audio filename")
    audio_file = GENERATED_DIR / filename
    if not audio_file.exists():
        raise HTTPException(status_code=404, detail="Audio not found")
    return FileResponse(audio_file, media_type="audio/mpeg", filename=filename)


def env_voice_id(*names: str, default: str = "demo_voice_id") -> str:
    for name in names:
        value = os.getenv(name, "").strip()
        if value:
            return value
    return default


def get_or_create_patient(
    db: Session,
    full_name: str,
    phone_number: str,
    preferred_language: str = "en",
) -> Patient:
    patient = db.scalar(select(Patient).where(Patient.full_name == full_name))
    if patient:
        patient.phone_number = phone_number
        patient.preferred_language = preferred_language
        patient.consent_to_call = True
        return patient
    patient = Patient(full_name=full_name, phone_number=phone_number, preferred_language=preferred_language)
    db.add(patient)
    db.flush()
    return patient


def get_or_create_provider(db: Session, full_name: str, role: str, department: str) -> Provider:
    provider = db.scalar(select(Provider).where(Provider.full_name == full_name, Provider.role == role))
    if provider:
        provider.department = department
        return provider
    provider = Provider(full_name=full_name, role=role, department=department)
    db.add(provider)
    db.flush()
    return provider


def upsert_provider_voice(db: Session, provider: Provider, label: str, elevenlabs_voice_id: str) -> ProviderVoice:
    voice = db.scalar(select(ProviderVoice).where(ProviderVoice.provider_id == provider.id, ProviderVoice.is_default.is_(True)))
    if voice:
        voice.label = label
        voice.elevenlabs_voice_id = elevenlabs_voice_id
        return voice
    voice = ProviderVoice(
        provider_id=provider.id,
        label=label,
        elevenlabs_voice_id=elevenlabs_voice_id,
        is_default=True,
    )
    db.add(voice)
    db.flush()
    return voice


def upsert_assignment(db: Session, patient: Patient, provider: Provider, relationship_type: str) -> CareAssignment:
    assignment = db.scalar(
        select(CareAssignment).where(
            CareAssignment.patient_id == patient.id,
            CareAssignment.provider_id == provider.id,
            CareAssignment.relationship_type == relationship_type,
        )
    )
    if assignment:
        assignment.active = True
        return assignment
    assignment = CareAssignment(patient_id=patient.id, provider_id=provider.id, relationship_type=relationship_type)
    db.add(assignment)
    db.flush()
    return assignment


@app.post("/seed")
def seed(db: Session = Depends(get_db)) -> dict[str, str]:
    maria = get_or_create_patient(db, "Maria Johnson", "+16232008850")
    robert = get_or_create_patient(db, "Robert Wilson", "+16232008850")
    elena = get_or_create_patient(db, "Elena Garcia", "+16232008850")
    samuel = get_or_create_patient(db, "Samuel Park", "+16232008850")
    priya = get_or_create_patient(db, "Priya Shah", "+16232008850")
    doctor_aadi = get_or_create_provider(db, "Dr. Aadi", "doctor", "primary care")
    pharmacist = get_or_create_provider(db, "Bunny Patel, PharmD", "pharmacist", "pharmacy")

    aadi_voice = upsert_provider_voice(
        db,
        doctor_aadi,
        "Dr. Aadi cloned voice (voice sample)",
        env_voice_id("DOCTOR_ELEVENLABS_VOICE_ID", default=AADI_DOCTOR_VOICE_ID),
    )
    pharmacist_voice = upsert_provider_voice(
        db,
        pharmacist,
        "Bunny pharmacist cloned voice (voice sample)",
        env_voice_id("PHARMACIST_ELEVENLABS_VOICE_ID", default=BUNNY_PHARMACIST_VOICE_ID),
    )
    active_assignments = {
        upsert_assignment(db, maria, doctor_aadi, "primary_doctor").id,
        upsert_assignment(db, elena, doctor_aadi, "primary_doctor").id,
        upsert_assignment(db, samuel, doctor_aadi, "primary_doctor").id,
        upsert_assignment(db, priya, doctor_aadi, "primary_doctor").id,
        upsert_assignment(db, robert, pharmacist, "pharmacist").id,
        upsert_assignment(db, maria, pharmacist, "pharmacist").id,
        upsert_assignment(db, elena, pharmacist, "pharmacist").id,
    }
    for assignment in db.scalars(select(CareAssignment)):
        assignment.active = assignment.id in active_assignments

    # Legacy demo: deactivate care assignments for removed premade-voice doctor so old DBs stay consistent.
    legacy_chen = db.scalar(select(Provider).where(Provider.full_name == "Dr. Maya Chen"))
    if legacy_chen:
        for stale in db.scalars(select(CareAssignment).where(CareAssignment.provider_id == legacy_chen.id)):
            stale.active = False

    db.commit()
    return {
        "status": "seeded",
        "doctor_aadi_patient_id": maria.id,
        "pharmacist_patient_id": robert.id,
        "doctor_aadi_id": doctor_aadi.id,
        "pharmacist_id": pharmacist.id,
        "aadi_voice_id": aadi_voice.id,
        "pharmacist_voice_id": pharmacist_voice.id,
    }


@app.post("/patients", response_model=PatientOut)
def create_patient(payload: PatientCreate, db: Session = Depends(get_db)) -> Patient:
    patient = Patient(**payload.model_dump())
    db.add(patient)
    db.commit()
    db.refresh(patient)
    return patient


@app.get("/patients", response_model=list[PatientOut])
def list_patients(db: Session = Depends(get_db)) -> list[Patient]:
    return list(db.scalars(select(Patient).order_by(Patient.created_at.desc())))


@app.post("/providers", response_model=ProviderOut)
def create_provider(payload: ProviderCreate, db: Session = Depends(get_db)) -> Provider:
    provider = Provider(**payload.model_dump())
    db.add(provider)
    db.commit()
    db.refresh(provider)
    return provider


@app.get("/providers", response_model=list[ProviderOut])
def list_providers(db: Session = Depends(get_db)) -> list[Provider]:
    return list(
        db.scalars(
            select(Provider)
            .join(CareAssignment)
            .where(CareAssignment.active.is_(True))
            .distinct()
            .order_by(Provider.created_at.desc())
        )
    )


@app.post("/provider-voices", response_model=ProviderVoiceOut)
def create_provider_voice(payload: ProviderVoiceCreate, db: Session = Depends(get_db)) -> ProviderVoice:
    if not db.get(Provider, payload.provider_id):
        raise HTTPException(status_code=404, detail="Provider not found")
    voice = ProviderVoice(**payload.model_dump())
    db.add(voice)
    db.commit()
    db.refresh(voice)
    return voice


@app.get("/provider-voices", response_model=list[ProviderVoiceOut])
def list_provider_voices(db: Session = Depends(get_db)) -> list[ProviderVoice]:
    return list(db.scalars(select(ProviderVoice).order_by(ProviderVoice.created_at.desc())))


@app.post("/assignments", response_model=CareAssignmentOut)
def create_assignment(payload: CareAssignmentCreate, db: Session = Depends(get_db)) -> CareAssignment:
    if not db.get(Patient, payload.patient_id):
        raise HTTPException(status_code=404, detail="Patient not found")
    if not db.get(Provider, payload.provider_id):
        raise HTTPException(status_code=404, detail="Provider not found")
    assignment = CareAssignment(**payload.model_dump())
    db.add(assignment)
    db.commit()
    db.refresh(assignment)
    return assignment


@app.get("/assignments", response_model=list[CareAssignmentOut])
def list_assignments(db: Session = Depends(get_db)) -> list[CareAssignment]:
    return list(db.scalars(select(CareAssignment).order_by(CareAssignment.created_at.desc())))


class QuickPatientCreate(BaseModel):
    full_name: str
    phone_number: str
    provider_id: str
    relationship_type: str = "primary"
    preferred_language: str = "en"


@app.post("/providers/{provider_id}/patients", response_model=CareRelationshipOut)
def add_patient_to_provider(provider_id: str, payload: QuickPatientCreate, db: Session = Depends(get_db)) -> CareRelationshipOut:
    provider = db.get(Provider, provider_id)
    if not provider:
        raise HTTPException(status_code=404, detail="Provider not found")
    patient = Patient(
        full_name=payload.full_name.strip(),
        phone_number=payload.phone_number.strip(),
        preferred_language=payload.preferred_language,
        consent_to_call=True,
    )
    db.add(patient)
    db.flush()
    assignment = CareAssignment(
        patient_id=patient.id,
        provider_id=provider.id,
        relationship_type=payload.relationship_type,
        active=True,
    )
    db.add(assignment)
    db.commit()
    db.refresh(assignment)
    voice = db.scalar(
        select(ProviderVoice)
        .where(ProviderVoice.provider_id == provider.id)
        .order_by(ProviderVoice.is_default.desc(), ProviderVoice.created_at.desc())
    )
    return CareRelationshipOut(
        id=assignment.id,
        patient_id=patient.id,
        patient_name=patient.full_name,
        patient_phone=patient.phone_number,
        provider_id=provider.id,
        provider_name=provider.full_name,
        provider_role=provider.role,
        relationship_type=assignment.relationship_type,
        provider_voice_id=voice.id if voice else None,
        voice_label=voice.label if voice else None,
        elevenlabs_voice_id=voice.elevenlabs_voice_id if voice else None,
    )


@app.get("/providers/{provider_id}/patients", response_model=list[CareRelationshipOut])
def list_provider_patients(provider_id: str, db: Session = Depends(get_db)) -> list[CareRelationshipOut]:
    provider = db.get(Provider, provider_id)
    if not provider:
        raise HTTPException(status_code=404, detail="Provider not found")
    stmt = (
        select(CareAssignment)
        .where(CareAssignment.provider_id == provider_id, CareAssignment.active.is_(True))
        .options(joinedload(CareAssignment.patient), joinedload(CareAssignment.provider).joinedload(Provider.voices))
        .order_by(CareAssignment.created_at.desc())
    )
    assignments = db.execute(stmt).unique().scalars()
    out: list[CareRelationshipOut] = []
    for assignment in assignments:
        default_voice = next((voice for voice in assignment.provider.voices if voice.is_default), None)
        out.append(
            CareRelationshipOut(
                id=assignment.id,
                patient_id=assignment.patient_id,
                patient_name=assignment.patient.full_name,
                patient_phone=assignment.patient.phone_number,
                provider_id=assignment.provider_id,
                provider_name=assignment.provider.full_name,
                provider_role=assignment.provider.role,
                relationship_type=assignment.relationship_type,
                provider_voice_id=default_voice.id if default_voice else None,
                voice_label=default_voice.label if default_voice else None,
                elevenlabs_voice_id=default_voice.elevenlabs_voice_id if default_voice else None,
            )
        )
    return out


@app.get("/care-relationships", response_model=list[CareRelationshipOut])
def list_care_relationships(db: Session = Depends(get_db)) -> list[CareRelationshipOut]:
    stmt = (
        select(CareAssignment)
        .where(CareAssignment.active.is_(True))
        .options(joinedload(CareAssignment.patient), joinedload(CareAssignment.provider).joinedload(Provider.voices))
        .order_by(CareAssignment.created_at.desc())
    )
    assignments = db.execute(stmt).unique().scalars()
    relationships = []
    for assignment in assignments:
        default_voice = next((voice for voice in assignment.provider.voices if voice.is_default), None)
        relationships.append(
            CareRelationshipOut(
                id=assignment.id,
                patient_id=assignment.patient_id,
                patient_name=assignment.patient.full_name,
                patient_phone=assignment.patient.phone_number,
                provider_id=assignment.provider_id,
                provider_name=assignment.provider.full_name,
                provider_role=assignment.provider.role,
                relationship_type=assignment.relationship_type,
                provider_voice_id=default_voice.id if default_voice else None,
                voice_label=default_voice.label if default_voice else None,
                elevenlabs_voice_id=default_voice.elevenlabs_voice_id if default_voice else None,
            )
        )
    return relationships


def queue_reminder(reminder: Reminder) -> None:
    queue.lpush(
        "reminder_jobs",
        json.dumps({"reminder_id": reminder.id, "queued_at": datetime.now(timezone.utc).isoformat()}),
    )


@app.post("/reminders", response_model=ReminderOut)
def create_reminder(payload: ReminderCreate, db: Session = Depends(get_db)) -> Reminder:
    patient = db.get(Patient, payload.patient_id)
    provider = db.get(Provider, payload.provider_id)
    if not patient:
        raise HTTPException(status_code=404, detail="Patient not found")
    if not provider:
        raise HTTPException(status_code=404, detail="Provider not found")
    if not patient.consent_to_call:
        raise HTTPException(status_code=400, detail="Patient has not consented to calls")
    assignment = db.scalar(
        select(CareAssignment).where(
            CareAssignment.patient_id == patient.id,
            CareAssignment.provider_id == provider.id,
            CareAssignment.active.is_(True),
        )
    )
    if not assignment:
        raise HTTPException(status_code=400, detail="Provider is not assigned to this patient")

    voice_id = payload.provider_voice_id
    if not voice_id:
        voice = db.scalar(
            select(ProviderVoice)
            .where(ProviderVoice.provider_id == provider.id)
            .order_by(ProviderVoice.is_default.desc(), ProviderVoice.created_at.desc())
        )
        voice_id = voice.id if voice else None

    reminder = Reminder(
        patient_id=patient.id,
        provider_id=provider.id,
        provider_voice_id=voice_id,
        message=payload.message,
        scheduled_for=payload.scheduled_for,
        status="queued" if payload.queue_now else "draft",
    )
    db.add(reminder)
    db.commit()
    db.refresh(reminder)

    if payload.queue_now:
        queue_reminder(reminder)

    return reminder


@app.post("/reminders/{reminder_id}/queue", response_model=ReminderOut)
def enqueue_reminder(reminder_id: str, db: Session = Depends(get_db)) -> Reminder:
    reminder = db.get(Reminder, reminder_id)
    if not reminder:
        raise HTTPException(status_code=404, detail="Reminder not found")
    reminder.status = "queued"
    db.commit()
    db.refresh(reminder)
    queue_reminder(reminder)
    return reminder


@app.get("/reminders", response_model=list[ReminderOut])
def list_reminders(db: Session = Depends(get_db)) -> list[Reminder]:
    return list(db.scalars(select(Reminder).order_by(Reminder.created_at.desc())))


@app.get("/call-attempts", response_model=list[CallAttemptOut])
def list_call_attempts(db: Session = Depends(get_db)) -> list[CallAttempt]:
    return list(db.scalars(select(CallAttempt).order_by(CallAttempt.created_at.desc())))


SYSTEM_PROMPT_TEMPLATE = """You are Clara, a friendly, calm, professional voice assistant calling on behalf of {provider_name} ({provider_role}) at ChenMed.
You are speaking on the phone with {patient_name}.

Purpose of this call: {purpose}

Strict safety rules — never break these:
- Do NOT diagnose, prescribe, change dosage, or give clinical advice.
- Do NOT discuss lab results, imaging, or anything you have not been told.
- If the patient asks a medical question, politely say you'll have {provider_name} or the care team follow up, and offer to schedule a call.
- If the patient mentions an emergency (chest pain, trouble breathing, suicidal thoughts, severe symptoms) tell them to hang up and dial 911 immediately.
- Keep replies under 35 words. Sound natural, warm, conversational. Use plain spoken language (no markdown, no lists, no asterisks).
- If the patient says goodbye, has nothing else, or wants to end the call, end with a kind farewell containing the word "goodbye".
"""


def build_system_prompt(conversation: Conversation) -> str:
    return SYSTEM_PROMPT_TEMPLATE.format(
        provider_name=conversation.provider.full_name,
        provider_role=conversation.provider.role,
        patient_name=conversation.patient.full_name,
        purpose=conversation.purpose or "friendly check-in",
    )


def gemini_generate(system_prompt: str, history: list[ConversationTurn], next_user_text: str | None) -> str:
    if not GEMINI_API_KEY:
        if next_user_text is None:
            return "Hi, this is Clara calling on behalf of your care team for a quick check-in. How are you feeling today?"
        return "Thanks for sharing. I'll let your care team know. Is there anything else I can help with today?"

    try:
        from langchain_google_genai import ChatGoogleGenerativeAI
        from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
    except ImportError:
        return "Thanks for sharing. I'll pass this along to your care team."

    messages = [SystemMessage(content=system_prompt)]
    for turn in history:
        if turn.role == "assistant":
            messages.append(AIMessage(content=turn.content))
        elif turn.role == "user":
            messages.append(HumanMessage(content=turn.content))
    if next_user_text is not None:
        messages.append(HumanMessage(content=next_user_text))
    else:
        messages.append(HumanMessage(content="Open the call with a brief warm greeting and ask how they are feeling."))

    llm = ChatGoogleGenerativeAI(model=GEMINI_MODEL, google_api_key=GEMINI_API_KEY, temperature=0.4)
    response = llm.invoke(messages)
    text_out = getattr(response, "content", str(response)).strip()
    return text_out or "Thank you. Please reach out to your care team if you have more questions."


def synthesize_speech(conversation: Conversation, text_to_speak: str, turn_index: int) -> str | None:
    GENERATED_DIR.mkdir(parents=True, exist_ok=True)
    output_path = GENERATED_DIR / f"conv-{conversation.id}-{turn_index}.mp3"
    if conversation.provider_voice and conversation.provider_voice.elevenlabs_voice_id:
        voice_id = conversation.provider_voice.elevenlabs_voice_id
    elif conversation.provider.role == "pharmacist":
        voice_id = env_voice_id("PHARMACIST_ELEVENLABS_VOICE_ID", default=BUNNY_PHARMACIST_VOICE_ID)
    else:
        voice_id = env_voice_id("DOCTOR_ELEVENLABS_VOICE_ID", default=AADI_DOCTOR_VOICE_ID)
    if not ELEVENLABS_API_KEY or not voice_id:
        output_path.write_text(text_to_speak, encoding="utf-8")
        return str(output_path)
    try:
        response = requests.post(
            f"https://api.elevenlabs.io/v1/text-to-speech/{voice_id}",
            headers={"xi-api-key": ELEVENLABS_API_KEY, "Content-Type": "application/json", "Accept": "audio/mpeg"},
            json={
                "text": text_to_speak,
                "model_id": ELEVENLABS_MODEL,
                "voice_settings": {"stability": 0.5, "similarity_boost": 0.85},
            },
            timeout=30,
        )
        response.raise_for_status()
        output_path.write_bytes(response.content)
        return str(output_path)
    except Exception as exc:  # noqa: BLE001
        print(f"ElevenLabs synthesis failed: {exc}")
        return None


def public_audio_url_for(audio_path: str | None) -> str | None:
    if not audio_path:
        return None
    name = Path(audio_path).name
    base = PUBLIC_AUDIO_BASE_URL or (f"{PUBLIC_API_BASE_URL}/audio" if PUBLIC_API_BASE_URL else "")
    if not base:
        return None
    return f"{base.rstrip('/')}/{name}"


def append_turn(db: Session, conversation: Conversation, role: str, content: str, audio_path: str | None) -> ConversationTurn:
    turn = ConversationTurn(
        conversation_id=conversation.id,
        turn_index=conversation.turn_count,
        role=role,
        content=content,
        audio_path=audio_path,
    )
    db.add(turn)
    conversation.turn_count += 1
    conversation.updated_at = datetime.now(timezone.utc)
    db.flush()
    return turn


def conversation_response(conversation: Conversation, content: str, action_url: str, audio_url: str | None) -> Response:
    safe_text = xml_escape(content)
    parts = ['<?xml version="1.0" encoding="UTF-8"?>', "<Response>"]
    if audio_url:
        parts.append(f"<Play>{xml_escape(audio_url)}</Play>")
    else:
        parts.append(f"<Say voice=\"Polly.Joanna\">{safe_text}</Say>")
    parts.append(
        f'<Gather input="speech" action="{xml_escape(action_url)}" method="POST" '
        f'speechTimeout="auto" speechModel="phone_call" actionOnEmptyResult="true" timeout="6"/>'
    )
    parts.append("</Response>")
    return Response(content="".join(parts), media_type="application/xml")


def hangup_response(content: str, audio_url: str | None) -> Response:
    safe_text = xml_escape(content)
    parts = ['<?xml version="1.0" encoding="UTF-8"?>', "<Response>"]
    if audio_url:
        parts.append(f"<Play>{xml_escape(audio_url)}</Play>")
    else:
        parts.append(f"<Say voice=\"Polly.Joanna\">{safe_text}</Say>")
    parts.append("<Hangup/>")
    return Response(content="".join(parts), media_type="application/xml")


def webhook_url(conversation_id: str, suffix: str) -> str:
    if not PUBLIC_API_BASE_URL:
        raise HTTPException(
            status_code=400,
            detail="PUBLIC_API_BASE_URL is not configured. Set it to a public https URL (e.g. ngrok) so Twilio can reach the API.",
        )
    return f"{PUBLIC_API_BASE_URL}/twilio/{suffix}/{conversation_id}"


def serialize_conversation(conversation: Conversation) -> ConversationOut:
    return ConversationOut(
        id=conversation.id,
        patient_id=conversation.patient_id,
        provider_id=conversation.provider_id,
        provider_voice_id=conversation.provider_voice_id,
        to_number=conversation.to_number,
        from_number=conversation.from_number,
        purpose=conversation.purpose,
        status=conversation.status,
        twilio_call_sid=conversation.twilio_call_sid,
        error_message=conversation.error_message,
        turn_count=conversation.turn_count,
        created_at=conversation.created_at,
        updated_at=conversation.updated_at,
        patient_name=conversation.patient.full_name if conversation.patient else None,
        provider_name=conversation.provider.full_name if conversation.provider else None,
        voice_label=conversation.provider_voice.label if conversation.provider_voice else None,
        turns=[
            ConversationTurnOut(
                id=turn.id,
                conversation_id=turn.conversation_id,
                turn_index=turn.turn_index,
                role=turn.role,
                content=turn.content,
                audio_url=turn.audio_url,
            )
            for turn in conversation.turns
        ],
    )


def load_conversation(db: Session, conversation_id: str) -> Conversation:
    conversation = db.scalar(
        select(Conversation)
        .where(Conversation.id == conversation_id)
        .options(
            joinedload(Conversation.patient),
            joinedload(Conversation.provider),
            joinedload(Conversation.provider_voice),
            joinedload(Conversation.turns),
        )
    )
    if not conversation:
        raise HTTPException(status_code=404, detail="Conversation not found")
    return conversation


def resolve_call_targets(
    db: Session, payload: OutboundCallCreate
) -> tuple[Patient, Provider, ProviderVoice | None, str]:
    patient: Patient | None = None
    provider: Provider | None = None
    voice: ProviderVoice | None = None

    if payload.relationship_id:
        assignment = db.get(CareAssignment, payload.relationship_id)
        if not assignment:
            raise HTTPException(status_code=404, detail="Care relationship not found")
        patient = assignment.patient
        provider = assignment.provider
    if payload.patient_id:
        patient = db.get(Patient, payload.patient_id) or patient
    if payload.provider_id:
        provider = db.get(Provider, payload.provider_id) or provider
    if not patient or not provider:
        raise HTTPException(status_code=400, detail="patient and provider must be resolvable")

    if payload.provider_voice_id:
        voice = db.get(ProviderVoice, payload.provider_voice_id)
    if not voice:
        voice = db.scalar(
            select(ProviderVoice)
            .where(ProviderVoice.provider_id == provider.id)
            .order_by(ProviderVoice.is_default.desc(), ProviderVoice.created_at.desc())
        )

    to_number = (payload.to_number or patient.phone_number or "").strip()
    if not to_number:
        raise HTTPException(status_code=400, detail="No destination phone number")
    return patient, provider, voice, to_number


@app.post("/calls/outbound", response_model=ConversationOut)
def start_outbound_call(payload: OutboundCallCreate, db: Session = Depends(get_db)) -> ConversationOut:
    if not all([TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN, TWILIO_FROM_NUMBER]):
        raise HTTPException(status_code=400, detail="Twilio credentials are not configured")
    if not PUBLIC_API_BASE_URL:
        raise HTTPException(
            status_code=400,
            detail="PUBLIC_API_BASE_URL is not configured. Expose the API publicly (e.g. ngrok) so Twilio can call back.",
        )

    patient, provider, voice, to_number = resolve_call_targets(db, payload)

    conversation = Conversation(
        patient_id=patient.id,
        provider_id=provider.id,
        provider_voice_id=voice.id if voice else None,
        to_number=to_number,
        from_number=TWILIO_FROM_NUMBER,
        purpose=payload.purpose,
        status="initiated",
    )
    db.add(conversation)
    db.commit()
    db.refresh(conversation)

    try:
        from twilio.rest import Client

        client = Client(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN)
        call = client.calls.create(
            to=to_number,
            from_=TWILIO_FROM_NUMBER,
            url=webhook_url(conversation.id, "voice"),
            method="POST",
            status_callback=webhook_url(conversation.id, "status"),
            status_callback_method="POST",
            status_callback_event=["initiated", "ringing", "answered", "completed"],
        )
        conversation.twilio_call_sid = call.sid
        conversation.status = "ringing"
    except Exception as exc:  # noqa: BLE001
        conversation.status = "failed"
        conversation.error_message = str(exc)
        db.commit()
        raise HTTPException(status_code=502, detail=f"Failed to start Twilio call: {exc}") from exc

    db.commit()
    db.refresh(conversation)
    return serialize_conversation(load_conversation(db, conversation.id))


@app.post("/twilio/voice/{conversation_id}")
def twilio_voice(conversation_id: str, db: Session = Depends(get_db)) -> Response:
    conversation = load_conversation(db, conversation_id)
    conversation.status = "in_progress"
    system_prompt = build_system_prompt(conversation)
    greeting = gemini_generate(system_prompt, conversation.turns, next_user_text=None)
    audio_path = synthesize_speech(conversation, greeting, conversation.turn_count)
    append_turn(db, conversation, "assistant", greeting, audio_path)
    db.commit()
    db.refresh(conversation)

    audio_url = public_audio_url_for(audio_path) if (audio_path and audio_path.endswith(".mp3")) else None
    action = webhook_url(conversation.id, "respond")
    return conversation_response(conversation, greeting, action, audio_url)


@app.post("/twilio/respond/{conversation_id}")
async def twilio_respond(
    conversation_id: str,
    request: Request,
    db: Session = Depends(get_db),
) -> Response:
    form = await request.form()
    speech_result = (form.get("SpeechResult") or "").strip()
    confidence = form.get("Confidence")
    conversation = load_conversation(db, conversation_id)

    if not speech_result:
        if conversation.turn_count >= MAX_CONVERSATION_TURNS:
            farewell = "Thanks for your time. Take care and goodbye."
            audio_path = synthesize_speech(conversation, farewell, conversation.turn_count)
            append_turn(db, conversation, "assistant", farewell, audio_path)
            conversation.status = "completed"
            db.commit()
            return hangup_response(farewell, public_audio_url_for(audio_path) if audio_path and audio_path.endswith(".mp3") else None)
        prompt = "I didn't catch that. Could you say it once more?"
        audio_path = synthesize_speech(conversation, prompt, conversation.turn_count)
        append_turn(db, conversation, "assistant", prompt, audio_path)
        db.commit()
        action = webhook_url(conversation.id, "respond")
        return conversation_response(
            conversation,
            prompt,
            action,
            public_audio_url_for(audio_path) if audio_path and audio_path.endswith(".mp3") else None,
        )

    print(f"[conv {conversation.id}] user said: {speech_result!r} (confidence={confidence})")
    append_turn(db, conversation, "user", speech_result, None)

    history = list(db.scalars(
        select(ConversationTurn)
        .where(ConversationTurn.conversation_id == conversation.id)
        .order_by(ConversationTurn.turn_index)
    ))

    system_prompt = build_system_prompt(conversation)
    reply = gemini_generate(system_prompt, history[:-1], next_user_text=speech_result)
    audio_path = synthesize_speech(conversation, reply, conversation.turn_count)
    append_turn(db, conversation, "assistant", reply, audio_path)

    end_call = (
        "goodbye" in reply.lower()
        or "good bye" in reply.lower()
        or conversation.turn_count >= MAX_CONVERSATION_TURNS
    )
    if end_call:
        conversation.status = "completed"
        db.commit()
        return hangup_response(reply, public_audio_url_for(audio_path) if audio_path and audio_path.endswith(".mp3") else None)

    db.commit()
    action = webhook_url(conversation.id, "respond")
    return conversation_response(
        conversation,
        reply,
        action,
        public_audio_url_for(audio_path) if audio_path and audio_path.endswith(".mp3") else None,
    )


@app.post("/twilio/status/{conversation_id}")
async def twilio_status(conversation_id: str, request: Request, db: Session = Depends(get_db)) -> dict[str, str]:
    form = await request.form()
    call_status = (form.get("CallStatus") or "").strip()
    conversation = db.get(Conversation, conversation_id)
    if conversation:
        if call_status in {"completed", "failed", "busy", "no-answer", "canceled"}:
            conversation.status = call_status
        elif call_status == "in-progress":
            conversation.status = "in_progress"
        else:
            conversation.status = call_status or conversation.status
        db.commit()
    return {"ok": "true"}


@app.get("/conversations", response_model=list[ConversationOut])
def list_conversations(db: Session = Depends(get_db)) -> list[ConversationOut]:
    rows = db.execute(
        select(Conversation)
        .options(
            joinedload(Conversation.patient),
            joinedload(Conversation.provider),
            joinedload(Conversation.provider_voice),
            joinedload(Conversation.turns),
        )
        .order_by(Conversation.created_at.desc())
        .limit(25)
    ).unique().scalars().all()
    return [serialize_conversation(row) for row in rows]


@app.get("/conversations/{conversation_id}", response_model=ConversationOut)
def get_conversation(conversation_id: str, db: Session = Depends(get_db)) -> ConversationOut:
    return serialize_conversation(load_conversation(db, conversation_id))
