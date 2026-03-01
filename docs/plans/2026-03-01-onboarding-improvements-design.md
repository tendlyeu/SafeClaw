# Onboarding Improvements Design

## Goal

Improve the SaaS onboarding flow to: (1) collect the user's Mistral API key for per-user LLM features, (2) show proper plugin connection instructions using `~/.safeclaw/config.json` instead of ephemeral `export`, and (3) add a `safeclaw connect` CLI command for one-step plugin setup.

## Architecture

The onboarding wizard expands from 2 steps to 3. A new `mistral_api_key` column on the `users` table stores per-user keys. The service resolves each user's Mistral key per-request via the existing auth middleware, falling back to the global `SAFECLAW_MISTRAL_API_KEY` env var. A new CLI command writes the SafeClaw API key to the config file.

## Onboarding Flow (3 Steps)

### Step 1: Autonomy Level (unchanged)

Three radio-button cards: Cautious, Moderate (default), Autonomous.

### Step 2: Mistral API Key (new)

- Text input for the user's Mistral API key
- Optional — "Skip for now" link below the submit button
- Explanation text: "SafeClaw uses Mistral for security review, smart classification, and plain-English decision explanations. You can add this later from Preferences."
- On submit: stores key in `users.mistral_api_key`

### Step 3: SafeClaw API Key + Connection Instructions (updated)

Shows the generated SafeClaw API key in a prominent copy-able box, then:

```
1. Install the SafeClaw plugin:
   openclaw plugins install openclaw-safeclaw-plugin

2. Connect your plugin (choose one):

   Option A — CLI (recommended):
   safeclaw connect sc_your_key_here

   Option B — Manual:
   Add to ~/.safeclaw/config.json:
   { "remote": { "apiKey": "sc_your_key_here", "serviceUrl": "https://api.safeclaw.eu/api/v1" } }
```

## Mistral Key Storage

- New column: `users.mistral_api_key: str = ""` (plaintext in SQLite, same security posture as the local DB)
- Service-side: `SQLiteAPIKeyManager` gets `get_user_mistral_key(user_id: str) -> str | None`
- Auth middleware already resolves `user_id` from the SafeClaw API key
- Engine looks up per-user Mistral key, falls back to global env var

## `safeclaw connect` CLI Command

```
safeclaw connect <api-key> [--service-url URL]
```

1. Reads existing `~/.safeclaw/config.json` (or creates from defaults)
2. Sets `remote.apiKey` to the provided key
3. Sets `remote.serviceUrl` to `https://api.safeclaw.eu/api/v1` (default, overridable)
4. Writes the file back
5. Prints confirmation message

## Dashboard Nudge

If user has no Mistral key set, the dashboard Overview shows a dismissable banner:

> "LLM features disabled — add your Mistral API key in Preferences to enable security review and smart classification."

The Preferences page gets a new "Mistral API Key" masked input field.

## Per-Request LLM Client

- Current: one global `llm_client` created at startup from env var
- New: engine looks up user's Mistral key per-request, caches LLM clients by key
- Falls back to global `SAFECLAW_MISTRAL_API_KEY` if user hasn't set one

## Files Modified

| File | Change |
|------|--------|
| `safeclaw-landing/db.py` | Add `mistral_api_key` column to User |
| `safeclaw-landing/dashboard/onboard.py` | Add Step 2 (Mistral key), update Step 3 (config instructions) |
| `safeclaw-landing/main.py` | New onboard step route, prefs Mistral field, dashboard nudge |
| `safeclaw-service/safeclaw/cli/connect_cmd.py` | New `safeclaw connect` command |
| `safeclaw-service/safeclaw/cli/main.py` | Register connect command |
| `safeclaw-service/safeclaw/auth/api_key.py` | Add `get_user_mistral_key()` to SQLiteAPIKeyManager |
| `safeclaw-service/safeclaw/engine/full_engine.py` | Per-user LLM client lookup |
| `safeclaw-service/tests/` | Tests for connect CLI, Mistral key storage, per-user LLM |
