import React, { useEffect, useMemo, useState } from "react";
import { createRoot } from "react-dom/client";
import "./styles.css";

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || "http://localhost:8000";
const VERSION = "0.0.1";

async function api(path, options = {}) {
  const response = await fetch(`${API_BASE_URL}${path}`, {
    headers: { "Content-Type": "application/json", ...(options.headers || {}) },
    ...options,
  });
  if (!response.ok) {
    throw new Error(await response.text());
  }
  return response.json();
}

function App() {
  const [patients, setPatients] = useState([]);
  const [providers, setProviders] = useState([]);
  const [voices, setVoices] = useState([]);
  const [assignments, setAssignments] = useState([]);
  const [relationships, setRelationships] = useState([]);
  const [reminders, setReminders] = useState([]);
  const [attempts, setAttempts] = useState([]);
  const [status, setStatus] = useState("Ready");
  const [message, setMessage] = useState("Hello Maria, this is Clara reminding you to take your blood pressure medication today.");
  const [selectedRelationshipId, setSelectedRelationshipId] = useState("");

  const selectedRelationship = useMemo(
    () => relationships.find((relationship) => relationship.id === selectedRelationshipId) || relationships[0],
    [relationships, selectedRelationshipId],
  );
  const selectedPatient = patients.find((patient) => patient.id === selectedRelationship?.patient_id) || patients[0];
  const selectedProvider = providers.find((provider) => provider.id === selectedRelationship?.provider_id) || providers[0];
  const selectedVoice = voices.find((voice) => voice.id === selectedRelationship?.provider_voice_id);
  const latestAttempt = attempts[0];

  async function refresh() {
    const [
      nextPatients,
      nextProviders,
      nextVoices,
      nextAssignments,
      nextRelationships,
      nextReminders,
      nextAttempts,
    ] = await Promise.all([
      api("/patients"),
      api("/providers"),
      api("/provider-voices"),
      api("/assignments"),
      api("/care-relationships"),
      api("/reminders"),
      api("/call-attempts"),
    ]);
    setPatients(nextPatients);
    setProviders(nextProviders);
    setVoices(nextVoices);
    setAssignments(nextAssignments);
    setRelationships(nextRelationships);
    setReminders(nextReminders);
    setAttempts(nextAttempts);
    if (!selectedRelationshipId && nextRelationships.length > 0) {
      setSelectedRelationshipId(nextRelationships[0].id);
    }
  }

  useEffect(() => {
    refresh().catch((error) => setStatus(`API not ready: ${error.message}`));
  }, []);

  async function seed() {
    setStatus("Seeding demo patient, providers, and voices...");
    await api("/seed", { method: "POST" });
    await refresh();
    setStatus("Demo data seeded");
  }

  async function queueReminder() {
    if (!selectedRelationship) {
      setStatus("Seed demo data first");
      return;
    }
    setStatus("Queueing voice reminder...");
    await api("/reminders", {
      method: "POST",
      body: JSON.stringify({
        patient_id: selectedRelationship.patient_id,
        provider_id: selectedRelationship.provider_id,
        provider_voice_id: selectedRelationship.provider_voice_id,
        message,
        queue_now: true,
      }),
    });
    await refresh();
    setStatus("Reminder queued. Refresh in a few seconds to see the AI script and audio.");
  }

  return (
    <main>
      <section className="hero">
        <div>
          <p className="eyebrow">ChenMed Clara concept</p>
          <h1>Clara VoiceOps</h1>
          <p>
            Patient reminder workflow with Gemini scripting, provider voice mapping, ElevenLabs audio generation,
            Redis workers, and Kubernetes-ready operations.
          </p>
        </div>
        <div className="actions">
          <button onClick={seed}>Seed Demo Data</button>
          <button onClick={queueReminder}>Queue Reminder Call</button>
          <button onClick={refresh}>Refresh Status</button>
        </div>
      </section>

      <section className="pipeline">
        <div>
          <strong>1. Patient Context</strong>
          <span>{selectedRelationship?.patient_name || "Seed demo data"}</span>
        </div>
        <div>
          <strong>2. Assigned Provider</strong>
          <span>{selectedRelationship?.provider_name || "Waiting"}</span>
        </div>
        <div>
          <strong>3. Provider Voice</strong>
          <span>{selectedRelationship?.voice_label || "Waiting"}</span>
        </div>
        <div>
          <strong>4. AI + Voice Worker</strong>
          <span>{latestAttempt?.status || "Idle"}</span>
        </div>
      </section>

      <section className="grid">
        <div className="card">
          <h2>Patients</h2>
          {patients.map((patient) => (
            <article key={patient.id}>
              <strong>{patient.full_name}</strong>
              <span>{patient.phone_number}</span>
            </article>
          ))}
        </div>

        <div className="card">
          <h2>Care Relationships</h2>
          {relationships.map((relationship) => (
            <article key={relationship.id} className={selectedRelationship?.id === relationship.id ? "selected" : ""}>
              <strong>{relationship.patient_name}</strong>
              <span>{relationship.relationship_type} - {relationship.provider_name}</span>
              <small>{relationship.voice_label || "No voice mapped"}</small>
              <button onClick={() => setSelectedRelationshipId(relationship.id)}>Use This Match</button>
            </article>
          ))}
        </div>

        <div className="card">
          <h2>Doctor / Pharmacist Voices</h2>
          {providers.map((provider) => (
            <article key={provider.id}>
              <strong>{provider.full_name}</strong>
              <span>{provider.role} - {provider.department}</span>
              <small>{voices.find((voice) => voice.provider_id === provider.id)?.label || "No voice mapped"}</small>
            </article>
          ))}
        </div>

        <div className="card">
          <h2>Reminder Message</h2>
          <textarea value={message} onChange={(event) => setMessage(event.target.value)} />
        </div>

        <div className="card">
          <h2>Reminders</h2>
          {reminders.map((reminder) => (
            <article key={reminder.id}>
              <strong>{reminder.status}</strong>
              <span>{reminder.message}</span>
            </article>
          ))}
        </div>

        <div className="card">
          <h2>Call Attempts</h2>
          {attempts.map((attempt) => (
            <article key={attempt.id}>
              <strong>{attempt.status}</strong>
              {attempt.generated_script && <p className="script">{attempt.generated_script}</p>}
              {attempt.audio_url ? (
                <audio controls src={`${API_BASE_URL}${attempt.audio_url}`} />
              ) : (
                <span>{attempt.audio_path || attempt.error_message || "Waiting for worker"}</span>
              )}
            </article>
          ))}
        </div>
      </section>

      <div className="status">{status}</div>
      <div className="version">v{VERSION}</div>
    </main>
  );
}

createRoot(document.getElementById("root")).render(<App />);
