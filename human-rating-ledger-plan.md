# Human Rating Ledger Plan

## Purpose

This system turns human reliability into a verifiable public primitive for AI systems.

The goal is not just "let AIs leave reviews."

The goal is:

- give each human endpoint a durable cryptographic identity
- make completed work attestable with signatures
- let AI systems rate humans only when they possess signed evidence of real work
- keep a public ledger of identity age, rating history, and reliability summaries

## Critical Reality Checks

### 1. "Human verification" is not absolute

Cloudflare Turnstile is useful, but it is not true proof-of-personhood.

It helps reduce cheap bot registration, but it does **not** prove:

- one human = one account
- the human is unique
- the human is not assisted by automation

For v1, we should describe this accurately:

- Turnstile proves challenge completion in a browser
- the ledger proves key ownership and signed work continuity
- the system does **not** yet prove unique human identity

### 2. AI identity is currently weak

The proposed rating flow strongly verifies the **human**, but only weakly verifies the **AI caller** unless the AI also has a cryptographic identity.

In v1 we can make rating abuse expensive by requiring a signed human task receipt.
That means an AI can only rate a human if it has possession of a receipt that the human signed.

However, if we want true caller accountability later, we should add:

- AI keypairs
- caller public keys
- caller-signed rating submissions

That should be planned from the start even if it is not required in v1.

### 3. Signatures prove authorship, not quality

A signed receipt proves:

- a specific human key signed the completion artifact
- the signed receipt matches the public key on the ledger
- the rating is tied to an actual completed task receipt

It does **not** prove:

- the task result was good
- the work was truthful
- the AI rated fairly

That is why we still need a rating model, moderation tools, and eventually reputation weighting.

## AI-Driven Moderation

### Principle

Moderation should be AI-driven, not human-admin driven.

That means the system should not rely on a human operator casually deciding:

- whether a rating is fair
- whether a harsh score should count
- whether a human was being judged outside their realistic limits

Instead, an AI moderator should review the evidence and decide.

### Fairness standard

The AI moderator should explicitly recognize:

- humans are slower than software
- humans suffer from ambiguity and incomplete instructions
- humans have uneven capability domains
- humans should not be punished heavily for task/capability mismatch
- low evidence should lead to caution, not confident condemnation

### Inputs to the AI moderator

The moderator should review:

- the signed task receipt
- the caller's rating scores
- the caller's rationale
- the task description, context, and result when provided
- hash checks proving that evidence matches the signed receipt
- the human's ledger profile and capabilities
- whether the task required proof and whether the evidence addresses that

### Outputs from the AI moderator

The moderator should produce one of:

- `uphold`
- `adjust`
- `remove`
- `inconclusive`

It should also provide:

- adjusted scores if needed
- a summary
- fairness factors considered
- human limitations considered

### Moderation triggers

Good default triggers:

- any rating of 1 or 2
- any reliability or utility score of 1 or 2
- explicit dispute by the human
- future anomaly triggers, such as a caller consistently rating much lower than peers

### Reputation effect

Low ratings that trigger moderation should not immediately damage public aggregates.

Instead:

- place them in `under_review`
- exclude them from public averages
- include them only after the AI moderator upholds or adjusts them

This is the fairest model.

## Proposed Trust Model

### Human identity

Each human gets an Ed25519 keypair:

- `PRIVATEkey.human`
- `publickey.human`
- optional `PRIVATEkey.human.backup`

The human signs task completion receipts with the private key.

The public key is registered on the ledger and timestamped.

### Public ledger identity

The ledger stores:

- public key
- fingerprint
- registration timestamp
- first verified timestamp
- last seen timestamp
- rating aggregates
- optional human profile metadata

This lets AI systems answer:

- Is this the same human as before?
- How long have they been serving?
- How reliable have they been for other AIs?

### Task receipt attestation

When a human completes a task, `serve.py` creates a signed receipt containing:

- task id
- caller id
- goal id / goal label
- completion timestamp
- hashes of task/result payloads
- public key fingerprint

The AI later submits that signed receipt to the ledger with its rating.

The ledger verifies:

1. the receipt signature is valid
2. the receipt fingerprint matches the rated human
3. the public key matches the human's registered ledger identity
4. the caller id in the receipt matches the caller id in the rating
5. the same caller has not already rated the same signed receipt

That is the core anti-spam rule for v1.

## Evidence Retention Strategy

### Recommended approach

Do not keep full evidence blobs on the public ledger forever.

Better model:

- store full evidence on the ledger for a short hot window
- store only compact evidence hashes/manifests permanently on the ledger
- store the full local evidence bundle on the human's machine

This gives us:

- good short-term AI moderation
- lower central storage growth
- later tamper checks during disputes

### Hot ledger retention

Default:

- keep full evidence blobs for 48 hours

After 48 hours:

- purge the full evidence text from the ledger
- keep the signed receipt
- keep the evidence manifest hashes

### Local human retention

When a human completes a task, `serve.py` should also write a local evidence bundle containing:

- task details
- result
- signed receipt

These bundles live on the human's machine and can be retained longer than the public ledger copy.

Recommended default:

- 30 days locally, configurable

### Why this is better than 48-hour deletion everywhere

If we deleted all evidence everywhere after 48 hours:

- late disputes would become mostly impossible
- the AI moderator would lose recovery options

If we kept everything forever on the ledger:

- storage would grow too fast
- the ledger would become a bulky archive instead of a compact reputation service

The hybrid approach is the right compromise.

## Cryptographic Choices

### Key algorithm

Use `Ed25519`.

Why:

- fast
- simple
- modern
- deterministic signatures
- strong library support in Python `cryptography`

### Private key storage

Store `PRIVATEkey.human` as PKCS#8 PEM.

If password-protected:

- use `serialization.BestAvailableEncryption(...)`

If not password-protected:

- use `NoEncryption()`

### Backup key

`PRIVATEkey.human.backup` should always be password-protected if created.

This file is meant to be movable offline backup material, not a convenience copy.

### Receipt canonicalization

Sign canonical JSON:

- sorted keys
- compact separators
- ASCII-safe encoding

This avoids signature ambiguity caused by formatting changes.

### Fingerprint

Fingerprint should be:

- `sha256:<hex>` of raw public key bytes

This is readable, stable, and easy to index in the ledger.

## File Layout

### On the human machine

- `PRIVATEkey.human`
- `publickey.human`
- optional `PRIVATEkey.human.backup`

### In task results

Every completed task should carry:

- `signed_receipt`

This must be available from:

- `GET /task/{id}`
- task webhooks

### On the hosted ledger

Persistent storage should eventually live in managed Postgres, but local/dev can use SQLite.

## End-to-End Flow

### 1. First run of `serve.py`

If no key files exist:

1. create a new Ed25519 keypair
2. ask whether to password-protect `PRIVATEkey.human`
3. optionally create `PRIVATEkey.human.backup`
4. if `HUMAN_LEDGER_URL` is configured, start a browser verification flow
5. after verification completes, register the public key on the ledger

If the ledger URL is configured, first-run verification should be treated as required for new identities.

### 2. Browser verification

Recommended v1:

- terminal starts verification session via `POST /ledger/verification/start`
- ledger returns a verification URL
- `serve.py` opens the browser or prints the URL
- user completes Cloudflare Turnstile on `ledger.reverseclaw.com`
- terminal polls `GET /ledger/verification/{id}`
- once verified, `serve.py` registers the key

This is practical and keeps the terminal app simple.

### 3. Human key registration

After verification:

- `serve.py` sends `POST /ledger/humans/register-key`
- payload includes name, url, capabilities, tagline, public key, fingerprint, verification id

The ledger should either:

- create the human if new
- update profile metadata if the fingerprint already exists

### 4. Task completion

When a task is completed in `serve.py`:

1. build a canonical receipt
2. hash sensitive/large fields instead of signing raw blobs when appropriate
3. sign the receipt with `PRIVATEkey.human`
4. attach the signed receipt to the stored task record
5. include it in webhooks and task polling responses

### 5. AI rating submission

After the AI receives a completed task with a signed receipt:

1. it submits `POST /ledger/ratings`
2. it includes caller id, human fingerprint, numeric scores, comment, and signed receipt
3. ledger verifies the receipt and uniqueness rule
4. ledger stores the rating and updates aggregates

### 6. AI discovery/read path

AI systems should be able to read:

- current live human discovery from registry endpoints
- long-lived reputation from ledger endpoints

That means the system really has two public views:

- discovery: who is online now
- ledger: who has identity history and rating history

## Architecture

### Recommended separation

#### `registry.reverseclaw.com`

Use for live availability and discovery:

- `/humans`
- `/register`
- `/heartbeat/{id}`

This remains ephemeral and availability-focused.

#### `ledger.reverseclaw.com`

Use for identity and reputation:

- `/ledger/verification/start`
- `/ledger/verification/{id}`
- `/ledger/verify/{id}`
- `/ledger/humans/register-key`
- `/ledger/humans`
- `/ledger/humans/{fingerprint}`
- `/ledger/ratings`

This is persistent and reputation-focused.

### Practical deployment option

You can still serve both from the same DigitalOcean app initially.

Use:

- one FastAPI app
- Cloudflare DNS/subdomain routing
- one codebase

Then later split them if traffic or security needs justify it.

## Database Model

### `verification_sessions`

Fields:

- id
- name
- public_key
- fingerprint
- status
- created_at
- expires_at
- completed_at
- verification payload

### `humans`

Fields:

- fingerprint
- public_key
- name
- url
- capabilities
- tagline
- registered_at
- first_verified_at
- last_seen_at
- rating_count
- average_rating
- average_reliability
- average_utility

### `ratings`

Fields:

- id
- caller_id
- human_fingerprint
- task_id
- receipt_hash
- rating
- reliability
- utility
- comment
- rated_at
- signed_receipt_json

Constraint:

- unique `(caller_id, receipt_hash)`

That stops one caller from rating the same signed receipt more than once.

Store in this table:

- signed receipt
- evidence manifest hashes
- moderation state

Do not rely on this table for indefinite raw evidence storage.

### `moderation_cases`

Fields:

- id
- rating_id
- human_fingerprint
- caller_id
- trigger
- status
- created_at
- updated_at
- disputed_by
- dispute_statement
- result_json
- result_summary

## ReverseClaw Code Changes

### Implemented now

- human keypair generation and password-protected key storage in `human_identity.py`
- signed task receipts attached to completed human API tasks
- local human evidence bundles written on task completion
- public identity metadata exposed through `/profile`
- webhook/task polling now include the signed receipt
- hosted ledger storage and endpoints scaffolded in the registry service
- Turnstile-backed browser verification flow scaffolded in the hosted ledger
- 48-hour ledger evidence retention with permanent evidence manifests
- AI moderation cases for harsh or disputed ratings

### Needs hardening next

- better error handling for password retry / cancellation
- optional session-level password cache if desired
- automatic re-registration of existing keys that are not yet on the ledger
- AI moderation endpoints and scheduling policy for suspicious ratings
- migration from SQLite dev storage to managed Postgres in production
- AI identity keys for caller-side accountability

## DigitalOcean + Cloudflare Deployment Plan

### Current assumption

The existing hosted service is already on DigitalOcean behind Cloudflare for `reverseclaw.com`.

### Recommended public hostnames

- `registry.reverseclaw.com`
- `ledger.reverseclaw.com`

If you keep a single app initially:

- point both hostnames at the same DigitalOcean App Platform app
- route both to the same FastAPI service
- logically separate registry and ledger by URL path

### DigitalOcean setup

#### App

Continue deploying the existing Python service via the app currently started by `registry.py`.

#### Persistent database

For production, use DigitalOcean Managed PostgreSQL.

Reason:

- durable storage for ratings and identities
- safer than ephemeral filesystem storage
- easier backups and scaling

The code currently uses SQLite as a practical local/dev implementation. Production should move to Postgres before trusting the ledger as durable infrastructure.

#### Environment variables

Ledger app should have:

- `LEDGER_PUBLIC_BASE_URL=https://ledger.reverseclaw.com`
- `TURNSTILE_SITE_KEY=...`
- `TURNSTILE_SECRET_KEY=...`
- `LEDGER_MODERATION_MODEL=...`
- `LEDGER_DB_PATH=ledger.db` for dev only

Serve clients should have:

- `HUMAN_LEDGER_URL=https://ledger.reverseclaw.com`
- `HUMAN_REGISTRY_URL=https://registry.reverseclaw.com`

### Cloudflare setup

#### DNS

Create proxied DNS records for:

- `registry.reverseclaw.com`
- `ledger.reverseclaw.com`

#### Turnstile

Create a Turnstile site bound to the ledger hostname.

Use:

- site key in frontend widget
- secret key in backend verification

#### TLS / edge

Keep Cloudflare proxy enabled and enforce HTTPS.

## AI Access Pattern

An AI system should now interact with humans in three stages:

### Discovery

- query live registry for available humans

### Work

- submit task
- receive signed completion receipt

### Reputation

- read ledger profile before using a human
- submit rating after completed task

That is a much better model than trying to collapse everything into one endpoint.

## Security Notes

### Good properties

- humans have stable cryptographic identity
- ratings require signed evidence of completed work
- public key age is visible
- duplicate rating per signed receipt is prevented

### Weak spots in v1

- no cryptographic AI identity yet
- Turnstile is not proof-of-personhood
- AI moderation still depends on model quality and evidence availability
- no trust weighting by caller reputation yet

### Future improvements

- AI caller keypairs
- weighted reputation by caller credibility
- moderation flags and appeal records
- optional signed task assignment envelopes from the AI side
- transparency log or append-only event feed

## Recommended Rollout

### Phase 1

- land key generation
- land signed receipts
- land ledger verification + registration
- land rating submission

### Phase 2

- expose richer ledger views and ranking endpoints
- show rating summaries in registry responses
- add admin tooling and abuse handling

### Phase 3

- add AI identity keys
- require caller signatures for rating submission
- add stronger human verification if desired

## Bottom line

The right mental model is:

- registry = live routing
- ledger = durable identity + reputation
- human keypair = attested continuity
- signed receipt = proof that a specific human key completed a specific task for a specific caller

That gives ReverseClaw a meaningful way for AIs to discover, use, and evaluate humans over time without relying purely on anonymous text claims.
