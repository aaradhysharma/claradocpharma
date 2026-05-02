import React, { useEffect, useMemo, useState } from "react";
import { createRoot } from "react-dom/client";
import "./styles.css";

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || "/api";
const VERSION = "0.0.2";
const DEFAULT_LIVE_CALL_NUMBER = "+16232008850";

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
  const [conversations, setConversations] = useState([]);
  const [activeConversationId, setActiveConversationId] = useState("");
  const [livePhoneNumber, setLivePhoneNumber] = useState(DEFAULT_LIVE_CALL_NUMBER);
  const [callPurpose, setCallPurpose] = useState(
    "Friendly check-in to confirm the patient is taking their medication and feeling well.",
  );
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
      nextConversations,
    ] = await Promise.all([
      api("/patients"),
      api("/providers"),
      api("/provider-voices"),
      api("/assignments"),
      api("/care-relationships"),
      api("/reminders"),
      api("/call-attempts"),
      api("/conversations"),
    ]);
    setPatients(nextPatients);
    setProviders(nextProviders);
    setVoices(nextVoices);
    setAssignments(nextAssignments);
    setRelationships(nextRelationships);
    setReminders(nextReminders);
    setAttempts(nextAttempts);
    setConversations(nextConversations);
    if (!selectedRelationshipId && nextRelationships.length > 0) {
      setSelectedRelationshipId(nextRelationships[0].id);
    }
  }

  useEffect(() => {
    refresh().catch((error) => setStatus(`API not ready: ${error.message}`));
  }, []);

  useEffect(() => {
    if (!activeConversationId) return;
    const interval = setInterval(() => {
      api("/conversations")
        .then((rows) => {
          setConversations(rows);
          const active = rows.find((row) => row.id === activeConversationId);
          if (active && ["completed", "failed", "busy", "no-answer", "canceled"].includes(active.status)) {
            setStatus(`Live call ${active.status} (${active.turn_count} turns).`);
            setActiveConversationId("");
          }
        })
        .catch(() => {});
    }, 3000);
    return () => clearInterval(interval);
  }, [activeConversationId]);

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

  async function startLiveCall() {
    if (!selectedRelationship) {
      setStatus("Seed demo data first, then choose a care match.");
      return;
    }
    if (!livePhoneNumber.trim()) {
      setStatus("Enter a phone number to call.");
      return;
    }
    setStatus(`Placing live AI call to ${livePhoneNumber}...`);
    try {
      const conversation = await api("/calls/outbound", {
        method: "POST",
        body: JSON.stringify({
          relationship_id: selectedRelationship.id,
          patient_id: selectedRelationship.patient_id,
          provider_id: selectedRelationship.provider_id,
          provider_voice_id: selectedRelationship.provider_voice_id,
          to_number: livePhoneNumber,
          purpose: callPurpose,
        }),
      });
      setActiveConversationId(conversation.id);
      setStatus(
        `Live call started (sid ${conversation.twilio_call_sid || "n/a"}). Pick up the phone and talk to ${selectedRelationship.provider_name}'s AI voice.`,
      );
      await refresh();
    } catch (error) {
      setStatus(`Live call failed: ${error.message}`);
    }
  }

  const activeConversation = conversations.find((conv) => conv.id === activeConversationId) || conversations[0];

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
          <button className="primary" onClick={startLiveCall}>Start Live AI Call</button>
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

        <div className="card live-call">
          <h2>Talk to AI (Live Call)</h2>
          <p className="hint">
            Places an outbound call from your Twilio number using the selected provider voice.
            The patient picks up and has a real two-way conversation with Gemini + ElevenLabs.
          </p>
          <label>
            Phone number to call
            <input
              type="tel"
              value={livePhoneNumber}
              onChange={(event) => setLivePhoneNumber(event.target.value)}
              placeholder="+16232008850"
            />
          </label>
          <label>
            Purpose / context
            <textarea value={callPurpose} onChange={(event) => setCallPurpose(event.target.value)} />
          </label>
          <div className="live-meta">
            <span><strong>Provider:</strong> {selectedRelationship?.provider_name || "—"}</span>
            <span><strong>Voice:</strong> {selectedRelationship?.voice_label || "—"}</span>
            <span><strong>11Labs ID:</strong> {selectedRelationship?.elevenlabs_voice_id || "—"}</span>
          </div>
          <button className="primary" onClick={startLiveCall}>Call {livePhoneNumber || "patient"}</button>
        </div>

        <div className="card">
          <h2>Live Conversation</h2>
          {activeConversation ? (
            <>
              <article>
                <strong>{activeConversation.status.toUpperCase()}</strong>
                <span>
                  {activeConversation.provider_name} → {activeConversation.to_number}
                </span>
                <small>
                  {activeConversation.turn_count} turns · sid {activeConversation.twilio_call_sid || "pending"}
                </small>
              </article>
              <div className="transcript">
                {(activeConversation.turns || []).map((turn) => (
                  <div key={turn.id} className={`turn turn-${turn.role}`}>
                    <strong>{turn.role === "assistant" ? "AI" : "Patient"}:</strong> {turn.content}
                  </div>
                ))}
              </div>
              {activeConversation.error_message && (
                <p className="error">{activeConversation.error_message}</p>
              )}
            </>
          ) : (
            <p className="hint">No live calls yet. Start one above.</p>
          )}
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
