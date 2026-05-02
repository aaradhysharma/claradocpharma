import json
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Generator

import redis
from fastapi import Depends, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import Boolean, DateTime, ForeignKey, String, Text, create_engine, select, text
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, joinedload, mapped_column, relationship, sessionmaker


APP_VERSION = os.getenv("APP_VERSION", "0.0.1")
PREMADE_DOCTOR_VOICE_ID = "21m00Tcm4TlvDq8ikWAM"
DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql+psycopg://clara:clara@localhost:5432/clara_voiceops",
)
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")
GENERATED_DIR = Path(os.getenv("GENERATED_DIR", "/app/generated"))

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
    maria = get_or_create_patient(db, "Maria Johnson", "+15555550123")
    robert = get_or_create_patient(db, "Robert Wilson", "+15555550124")
    doctor = get_or_create_provider(db, "Dr. Maya Chen", "doctor", "primary care")
    pharmacist = get_or_create_provider(db, "Bunny Patel, PharmD", "pharmacist", "pharmacy")

    doctor_voice = upsert_provider_voice(
        db,
        doctor,
        "Doctor reminder voice",
        env_voice_id("DOCTOR_ELEVENLABS_VOICE_ID", default=PREMADE_DOCTOR_VOICE_ID),
    )
    pharmacist_voice = upsert_provider_voice(
        db,
        pharmacist,
        "Pharmacist medication voice",
        env_voice_id("PHARMACIST_ELEVENLABS_VOICE_ID", "ELEVENLABS_VOICE_ID"),
    )
    upsert_assignment(db, maria, doctor, "primary_doctor")
    upsert_assignment(db, robert, pharmacist, "pharmacist")
    db.commit()
    return {
        "status": "seeded",
        "doctor_patient_id": maria.id,
        "pharmacist_patient_id": robert.id,
        "doctor_id": doctor.id,
        "pharmacist_id": pharmacist.id,
        "doctor_voice_id": doctor_voice.id,
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
    return list(db.scalars(select(Provider).order_by(Provider.created_at.desc())))


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
