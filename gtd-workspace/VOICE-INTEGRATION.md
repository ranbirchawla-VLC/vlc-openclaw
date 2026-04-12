# Voice Integration — GTD Agent

The GTD agent is text-native. Voice input works by converting audio to text before any GTD logic runs. The pipeline is identical regardless of whether the text came from typing, dictation, or a transcription service.

---

## 1. Telegram Voice Notes

### How it works

Telegram delivers voice messages as audio files (`.ogg` in OPUS format). The GTD agent must transcribe the audio to text **before** calling `gtd_router.py`. The transcribed text is then treated identically to typed input.

```
User records voice note → Telegram delivers audio file → Transcribe to text → gtd_router.py → normal flow
```

No special handling exists inside any Python tool for audio. The tools only see text.

### Transcription options

| Option | Latency | Cost | Notes |
|--------|---------|------|-------|
| OpenAI Whisper API | ~1–3 s | Per-minute billing | High accuracy for speech-to-text; handles accents well |
| Whisper local (CPU) | ~5–15 s | Free after hardware | Requires a machine with sufficient RAM; no API cost |
| Whisper local (GPU) | ~1–3 s | Free after hardware | Fast if a GPU is available |
| Telegram built-in (none) | — | — | Telegram does not transcribe voice notes automatically; audio file only |

**Recommendation:** OpenAI Whisper API for production. It is already in the Vardalux tech stack and handles the likely input language (English) well. Run local Whisper for offline dev.

### Where to insert transcription

The OpenClaw adapter for the GTD Telegram bot should:

1. Check if the incoming update has `message.voice` (not `message.text`).
2. If voice, download the file from Telegram using `getFile` + `downloadFile`.
3. Send the audio to Whisper.
4. Use the returned transcript as `raw_input` for `gtd_router.py`.
5. Proceed identically to a typed message.

No changes are required in `gtd_router.py` or any Python tool.

### Where `llm_title_rewriter` gets exercised

Voice transcription is imperfect. Common artifacts:

- Filler words: "uh", "um", "you know", "like"
- Run-on sentences: "remind me to call the customs broker about the shipment that's coming in next week from Hong Kong"
- Repetition: "I need to I need to send the invoice to Amit"
- Dictation artifacts from accents or background noise

`gtd_normalize.py` strips known filler words (`_FILLER_PATTERN`) before classification. When the resulting title is still messy or excessively long, `gtd_router.py` returns `needs_llm: true`. The OpenClaw adapter then invokes `llm_title_rewriter` to clean the title before proceeding. No LLM skill is called from inside the Python tools — skill invocation always happens at the OpenClaw layer.

For clean voice input (clear speech, minimal artifacts), the normaliser handles it without any LLM call.

### Optional: using Wispr Flow or system dictation instead

If the capture device runs Wispr Flow, macOS Dictation, or similar tool, the voice-to-text conversion happens at the OS level. Text arrives in the Telegram input field as normal typed characters. In this case:

- No audio file is delivered to the bot.
- No Whisper transcription step is needed.
- The agent receives clean text from the start.
- `llm_title_rewriter` may still be useful for occasional dictation artifacts.

This is the simpler path and is fully supported today without any additional integration work.

---

## 2. Wispr Flow / System Dictation

### How it works

Wispr Flow and macOS Dictation intercept microphone input and type the transcribed text directly into the focused application. When the focused application is the Telegram mobile or desktop client, the transcribed text appears as a typed message.

From the GTD agent's perspective:

```
User speaks → Wispr Flow types text in Telegram → user sends message → gtd_router.py receives typed text
```

There is no audio file. There is no transcription step at the bot layer. The agent sees `message.text` as normal.

### Behaviour differences from typed input

- Wispr Flow produces cleaner output than Telegram's own voice notes (trained for dictation use).
- Occasional artifacts: run-on sentences, missing punctuation, dictation commands that were not filtered ("period", "new line").
- `gtd_normalize.py`'s filler-word filter handles common artifacts.
- For longer or messier transcriptions, `llm_title_rewriter` cleans the title before storage.

### Token cost

On the clean dictation path (clear speech → Wispr Flow → clean text → normaliser succeeds), no LLM call occurs. The agent is zero-LLM-cost even for voice-first captures.

---

## 3. Alexa (Future)

### Current status

Alexa is a secondary surface. It is not yet wired. Do not add Alexa until the Telegram identity path and Google Drive storage are fully validated in production with real users.

### Identity constraint

Alexa must map into the existing Telegram-anchored user record. It must **not** create a new workspace.

The Alexa Skill handler must:

1. Identify the caller via Alexa's `userId` (from the request context).
2. Look up the corresponding `user_id` in a mapping table:
   ```
   alexa_user_id → telegram_chat_id → user_id → workspace
   ```
3. Use the resolved `user_id` to call `gtd_router.py` exactly as Telegram does.
4. The `source` field on the written record will be `"alexa"` (from the `Source` enum).

If no mapping exists for the Alexa user, the Skill must prompt the user to link their account (likely via a Telegram confirmation message) before allowing any writes.

### What must not happen

- Alexa must not bypass Telegram-anchored ownership.
- Alexa must not create a new `user_id` or a parallel storage path.
- No Alexa functionality before a valid user mapping exists.

### Linking flow (sketch)

Not yet built. The general approach: Alexa prompts the user to send `/start` to the Telegram bot to get a short-lived link code, then says "Alexa, link code XXXX" to complete the mapping. All subsequent Alexa requests use the resolved `user_id` and the existing workspace.

### After linking

```
Alexa utterance → Alexa Skill handler → resolve user_id → gtd_router.py → same workspace
```

The `telegram_chat_id` field on Alexa-sourced records will still be the user's Telegram chat ID (the identity anchor). The `source` field will be `"alexa"`. Everything else is identical.
