# Voice agent — options, recommendation, and what it must not become

Status: **proposal**. Nothing here is built yet.

## The short version

Most of a voice agent already exists. `ai_chat` + `chat_grounding_service` +
`kb_retrieval_service` answer a question under the asker's own permissions and
return an answer with citations. Voice is a different **shell** on that, not a
different agent: microphone → text → the endpoint we already have → text →
speaker.

That framing matters, because it decides what is actually being chosen here.
The interesting question is not "which voice framework" — it is "which two
models, and do they run on our hardware". Everything else is already written.

```
browser mic ──► VAD ──► STT ──► POST /ai/chat/stream ──► TTS ──► speaker
  (getUserMedia)  silero  faster-whisper   (existing, RBAC-scoped)   piper
                                            │
                                            └── same JWT, same grounding,
                                                same audit row
```

## The constraint that eliminates most of the market

This bank runs its models locally. Ollama serves `glm4` and
`nomic-embed-text` on the bank's own hardware, and
`docs/06-rag-knowledge-base.md` records "embeddings never leave the local
model" as a deliberate default.

A voice agent carries **customer complaint audio** — names, account numbers,
grievances, spoken aloud. Sending that to a hosted speech API would quietly
undo the posture the rest of the system was built to hold, and it would do it
for the most sensitive data class in the product.

So: **the browser's built-in `SpeechRecognition` (Web Speech API) is
disqualified**, despite being the cheapest and easiest option by a wide margin.
In Chrome it streams audio to Google's servers; in Safari, to Apple's. It reads
as a local browser feature and is not one. This is worth stating explicitly
because it is the option everyone reaches for first.

Everything recommended below runs on the bank's own machines, costs nothing to
licence, and keeps audio inside the building.

## Speech to text

| Option | Licence | Size | Runs on | Notes |
|---|---|---|---|---|
| **faster-whisper** (`small`, int8) | MIT | ~470 MB | CPU | 4x faster and lighter than reference Whisper at the same accuracy. **Recommended.** |
| Moonshine v2 | MIT | 27 MB | CPU / edge | Purpose-built streaming encoder. The option if we later want live partial transcripts. |
| NVIDIA Parakeet TDT | CC-BY-4.0 | ~2 GB | GPU | Fastest batch throughput; wants a GPU we have not budgeted. |
| NVIDIA Canary-Qwen 2.5B | CC-BY-4.0 | ~5 GB | GPU | Leads English accuracy; heavy. |

**Recommendation: faster-whisper `small` with int8 quantisation, on CPU.**

The reason is the interaction pattern, not the benchmark. Whisper is a
**batch** model — it transcribes a finished utterance, not a live stream. That
sounds like a limitation until you consider where this runs: a branch office
or an agent's desk, in a room with other people and other conversations. An
always-listening microphone in that room is a bad idea on its own merits.
Push-to-talk is the correct interaction here, and push-to-talk *is* batch. The
constraint and the requirement agree.

A 10-second utterance transcribes in roughly 1–2 seconds on a modern CPU core,
which is well inside the pause a person expects after releasing a button.

Use **silero-vad** (MIT, ~2 MB) to trim silence off each end before
transcribing. It is not for barge-in; it is so a 3-second question does not
arrive as a 9-second clip with six seconds of room tone.

If live partial transcripts are wanted later, that is the moment to look at
Moonshine — it is the one model here designed for it. Do not adopt it up front
for a feature nobody has asked for.

## Text to speech

| Option | Licence | Size | Runs on | Notes |
|---|---|---|---|---|
| **Piper** | GPL-3.0 (binary) | ~60 MB/voice | CPU | Real-time on a Raspberry Pi 4. 30+ languages including Indian English and Hindi. **Recommended.** |
| Kokoro-82M | Apache-2.0 | 82M params | CPU or 2–3 GB VRAM | Noticeably more natural; 54 voices, 8 languages. The upgrade if Piper sounds too flat. |
| XTTS v2 | Coqui CPML | large | GPU | Voice cloning. We have no use for it, and cloning a staff member's voice inside a bank is a liability, not a feature. |

**Recommendation: Piper**, for two reasons specific to this bank.

First, **language coverage**: Piper ships Indian-English and Hindi voices.
SUCCESS Bank's branches are in India; a US-English voice reading Indian
place-names and customer names aloud is worse than no voice at all.

Second, **it fits the machine we already have**. Piper is CPU-only and
real-time on hardware far weaker than the API server. Nothing needs to be
bought.

On the GPL-3.0 licence: Piper runs as a **separate process** we invoke over a
socket or a subprocess, not as a library linked into our code. Copyleft
attaches to the linked work, so this does not reach our source. Keep it that
way — if anyone proposes importing Piper as a Python library, that is the
moment to switch to Kokoro (Apache-2.0) instead. Worth a note in the runbook.

## What this must not become

The standing rule on this project is that roles are strict and cannot be
exploited. A voice channel is a new way in, and new ways in are how role
boundaries get lost. Three rules, all structural rather than by convention:

**1. Voice adds no endpoint.** It calls `POST /ai/chat/stream` with the user's
existing JWT — the same endpoint, the same grounding service, the same
`accessible_collections` predicate. If voice ever needs its own route, that
route needs its own authorization, and a second copy of an authorization rule
is how the first one drifts. There is no "voice service account".

**2. Transcripts are PII and are treated as such.** A spoken question contains
everything a typed one does and usually more, because people speak more
loosely than they type. Transcripts go into `ai_interaction_log` under the same
retention, the same audit trail, and the same access rules as chat text.
**Raw audio is never persisted** — it is transcribed in memory and discarded.
Storing it would create a new class of record with no retention policy, no
redaction path, and no one accountable for it.

**3. Speech is input, not authority.** The assistant already cannot change a
ticket — it tells you which button to press. That does not relax because the
request was spoken. A voice command that closes a ticket is a voice command
that closes a ticket when someone says the right words near an unlocked
workstation, and it removes the deliberate click that makes the actor
identifiable in the audit row.

## Rough shape of the work

Roughly a week, mostly plumbing, because the reasoning half already exists.

1. `POST /api/v1/ai/voice/transcribe` — multipart audio in, text out. Reuses
   `BodySizeLimitMiddleware` with a voice-specific cap. Same auth dependency
   as every other AI route. Returns text; **stores no audio**.
2. `POST /api/v1/ai/voice/speak` — text in, audio out, streamed. Rate-limited
   per user, because it is the cheapest denial-of-service in the product.
3. A `VoiceButton` in `AIChatWidget`: hold to talk, release to send. It feeds
   the existing text path — the widget should not learn that voice exists
   beyond the button.
4. Two containers in `docker-compose`, CPU-only, on the internal network with
   **no egress**. Not being able to reach the internet is the enforcement of
   the promise in the first section; a comment saying "runs locally" is not.
5. Health checks in `/ai/health`, next to the existing Ollama probe, so a
   missing model is a diagnosable state rather than a hang.

### Costs

No licence cost, no per-minute cost, no vendor. The real cost is CPU: budget
about 1 core and 1.5 GB RAM for STT, and about 0.5 core and 300 MB for TTS,
per concurrent speaker. Both models load once and stay resident; loading per
request is what makes a local speech stack feel slow.

### What would make this a bad idea

Worth writing down so the decision can be revisited honestly:

- **If accuracy on Indian-accented English proves poor**, the feature is worse
  than useless — a misheard account number is a wrong answer delivered
  confidently. Measure this on real staff recordings before building the UI,
  not after. This is the single risk most likely to kill the feature, and it
  is cheap to test first.
- **If nobody wants it.** Agents type quickly and work in shared rooms.
  Speaking a customer's complaint aloud in an open-plan office may be
  unwelcome for reasons that have nothing to do with the technology.

## Sources

- [Best open-source speech-to-text models in 2026 — Gladia](https://www.gladia.io/blog/best-open-source-speech-to-text-models)
- [Best open source STT model in 2026, with benchmarks — Northflank](https://northflank.com/blog/best-open-source-speech-to-text-stt-model-in-2026-benchmarks)
- [Best Open Source Speech-to-Text Models in 2026 — AssemblyAI](https://www.assemblyai.com/blog/top-open-source-stt-options-for-voice-applications)
- [Best Self-Hosted TTS Models in 2026: Kokoro, Chatterbox, Piper — Seven Labs](https://www.sevenlabs.site/blogs/best-self-hosted-tts-models-2026)
- [Kokoro vs Piper vs XTTS v2 — Contra Collective](https://contracollective.com/blog/kokoro-vs-piper-vs-xtts-local-text-to-speech-m5-max-2026)
- [Best Open Source Self-Hosted TTS Models — Pinggy](https://pinggy.io/blog/best_open_source_self_hosted_text_to_speech_models/)
