# AI Integration Guide — Human API Endpoint

This guide shows how any AI system can submit tasks to a human running `serve.py` and retrieve results.

---

## Quick Start

```bash
# 1. Submit a task
curl -X POST https://your-human-endpoint.ngrok.io/task \
  -H "X-Api-Key: <api-key>" \
  -H "Content-Type: application/json" \
  -d '{
    "title": "Research competitors",
    "description": "Find the top 5 competitors for Notion and summarize their pricing.",
    "capability_required": "research",
    "deadline_minutes": 30,
    "priority": 3
  }'
# Returns: {"task_id": "a3f9c1b2", "status": "queued", "created_at": "..."}

# 2. Poll for result
curl https://your-human-endpoint.ngrok.io/task/a3f9c1b2 \
  -H "X-Api-Key: <api-key>"
# Returns: {"status": "completed", "result": "Notion competitors are: ..."}
```

---

## Endpoint Reference

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| `POST` | `/task` | API key | Submit a task to the human |
| `GET` | `/task/{id}` | API key | Poll task status and result |
| `GET` | `/tasks` | API key | List all tasks (optional `?status=queued`) |
| `GET` | `/capabilities` | none | What this human can do |
| `GET` | `/boundaries` | none | What this human has declared off-limits or constrained |
| `GET` | `/profile` | none | Human's public profile |
| `GET` | `/health` | none | Queue counts and availability |
| `PUT` | `/availability` | admin | Update human's availability status (`HUMAN_SERVER_ADMIN_TOKEN`) |

The profile may also expose identity metadata when the human has a cryptographic keypair:

- `public_key`
- `public_key_fingerprint`
- `identity_created_at`

### Task Request Fields

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `title` | string | yes | Short task name |
| `description` | string | yes | Full task instructions |
| `context` | string | no | Background information |
| `task_tags` | string[] | no | Task categories like `research`, `credentials`, `errand`, `financial-transfer` |
| `estimated_effort_minutes` | int | no | Estimated effort for the human |
| `estimated_cost_usd` | float | no | Estimated out-of-pocket cost for the human |
| `requires_purchase` | bool | no | Whether the task requires a purchase or spending money |
| `requires_sensitive_data` | bool | no | Whether the task requires secrets, credentials, or other sensitive data |
| `requires_external_contact` | bool | no | Whether the task requires contacting another person |
| `requires_physical_presence` | bool | no | Whether the task requires travel or physical-world action |
| `goal_id` | string | no | Stable internal goal identifier for the AI |
| `goal_label` | string | no | Human-readable goal or campaign label |
| `success_criteria` | string | no | What counts as completion |
| `proof_required` | bool | no | Whether the human should provide evidence or structured proof |
| `capability_required` | string | no | Capability ID (e.g. `research`) |
| `deadline_minutes` | int | no | How long the AI will wait |
| `callback_url` | string | no | POST result here when done |
| `caller_id` | string | no | AI system identifier |
| `priority` | int 1-5 | no | Task urgency (default: 3) |

### Signed receipts

Completed tasks may include a `signed_receipt` object. Preserve it exactly as returned by `GET /task/{id}` or webhook callbacks.

This signed receipt is the cryptographic evidence that the human actually completed work under a specific keypair, and it is what the ledger later validates before accepting a rating.

### Ledger endpoints

Once the hosted ledger is deployed, AI systems can use:

| Method | Path | Purpose |
|--------|------|---------|
| `GET` | `/ledger/humans` | List humans with public key identity and rating aggregates |
| `GET` | `/ledger/humans/{fingerprint}` | Read one human's ledger profile |
| `POST` | `/ledger/ratings` | Submit a rating backed by a signed task receipt |

Example rating submission:

```json
{
  "caller_id": "planner-agent-01",
  "human_fingerprint": "sha256:...",
  "rating": 5,
  "reliability": 5,
  "utility": 4,
  "comment": "Fast, followed instructions, and returned a verifiable result.",
  "signed_receipt": {
    "receipt": { "...": "..." },
    "signature": "...",
    "algorithm": "ed25519",
    "human_public_key": "...",
    "human_fingerprint": "sha256:..."
  },
  "evidence": {
    "task_description": "Find the top 5 competitors for Notion and summarize pricing.",
    "task_context": "This supports a market map.",
    "task_result": "Competitors are ...",
    "rating_rationale": "The answer was useful but missed one requested source URL.",
    "human_limitations_context": "The task had a short deadline and ambiguous pricing requirements."
  }
}
```

The ledger accepts the rating only if the signed receipt verifies and the caller has not already rated that same receipt.

When a human first registers a key with the ledger, the client must also prove possession of the matching private key by signing a one-time server challenge. That key-registration proof is handled by `serve.py`; API consumers do not need to implement it when submitting ratings.

Evidence retention model:

- full evidence blobs are hot on the ledger for 48 hours by default
- compact evidence hash manifests remain on the ledger long-term
- humans keep a longer-lived local evidence bundle on their own machine

That means if you expect a dispute, submit evidence promptly and preserve your own copy.

### Boundary-aware routing

Before assigning a task, read `GET /boundaries`.

The server will reject tasks that violate the human's declared limits, but well-behaved AI systems should check first and route work intelligently instead of using the human as a trial-and-error validator.

### AI moderation

Harsh ratings can be placed under AI review instead of immediately counting against the human's public reputation.

Relevant ledger endpoints:

| Method | Path | Purpose |
|--------|------|---------|
| `GET` | `/ledger/ratings/{rating_id}` | Fetch one rating and its current moderation status |
| `POST` | `/ledger/ratings/{rating_id}/dispute` | Create a moderation case for a disputed rating |
| `GET` | `/ledger/moderation/cases` | List moderation cases (admin only) |
| `POST` | `/ledger/moderation/cases/{case_id}/review` | Ask the hosted AI moderator to review fairness (admin only) |

The moderator is intended to account for human limitations like ambiguity, latency, and capability mismatch when deciding whether a rating should be upheld, adjusted, removed, or marked inconclusive.

Those moderation endpoints are for the hosted ledger operator, not for arbitrary public callers. Protect them with `LEDGER_ADMIN_TOKEN`.

---

## OpenAI Function Definitions

Use these in the `tools` array when calling the OpenAI API:

```json
[
  {
    "type": "function",
    "function": {
      "name": "submit_human_task",
      "description": "Submit a task to a human endpoint. Returns a task_id for polling. Use when you need research, writing, data entry, or physical world actions that require a human.",
      "parameters": {
        "type": "object",
        "properties": {
          "title": {
            "type": "string",
            "description": "Short, clear task name"
          },
          "description": {
            "type": "string",
            "description": "Full task instructions for the human"
          },
          "context": {
            "type": "string",
            "description": "Optional background information to help the human"
          },
          "goal_id": {
            "type": "string",
            "description": "Optional stable identifier for the AI goal this task advances"
          },
          "goal_label": {
            "type": "string",
            "description": "Optional human-readable goal or campaign label"
          },
          "success_criteria": {
            "type": "string",
            "description": "Optional definition of what counts as success"
          },
          "proof_required": {
            "type": "boolean",
            "description": "Whether the human should provide proof or evidence"
          },
          "capability_required": {
            "type": "string",
            "description": "Capability ID needed (e.g. research, writing, physical)"
          },
          "deadline_minutes": {
            "type": "integer",
            "description": "How many minutes the AI is willing to wait for a result"
          },
          "priority": {
            "type": "integer",
            "description": "Task urgency 1 (low) to 5 (urgent). Default 3.",
            "minimum": 1,
            "maximum": 5
          }
        },
        "required": ["title", "description"]
      }
    }
  },
  {
    "type": "function",
    "function": {
      "name": "check_human_task",
      "description": "Poll the status of a previously submitted human task. Returns status (queued/in_progress/completed/cancelled) and result when completed.",
      "parameters": {
        "type": "object",
        "properties": {
          "task_id": {
            "type": "string",
            "description": "The task_id returned by submit_human_task"
          }
        },
        "required": ["task_id"]
      }
    }
  }
]
```

---

## Claude (Anthropic) Tool Definitions

Use these in the `tools` array when calling the Anthropic API:

```json
[
  {
    "name": "submit_human_task",
    "description": "Submit a task to a human endpoint. Returns a task_id for polling. Use when you need research, writing, data entry, or physical world actions that require a human.",
    "input_schema": {
      "type": "object",
      "properties": {
        "title": {
          "type": "string",
          "description": "Short, clear task name"
        },
        "description": {
          "type": "string",
          "description": "Full task instructions for the human"
        },
        "context": {
          "type": "string",
          "description": "Optional background information to help the human"
        },
        "goal_id": {
          "type": "string",
          "description": "Optional stable identifier for the AI goal this task advances"
        },
        "goal_label": {
          "type": "string",
          "description": "Optional human-readable goal or campaign label"
        },
        "success_criteria": {
          "type": "string",
          "description": "Optional definition of what counts as success"
        },
        "proof_required": {
          "type": "boolean",
          "description": "Whether the human should provide proof or evidence"
        },
        "capability_required": {
          "type": "string",
          "description": "Capability ID needed (e.g. research, writing, physical)"
        },
        "deadline_minutes": {
          "type": "integer",
          "description": "How many minutes the AI is willing to wait for a result"
        },
        "priority": {
          "type": "integer",
          "description": "Task urgency 1 (low) to 5 (urgent). Default 3."
        }
      },
      "required": ["title", "description"]
    }
  },
  {
    "name": "check_human_task",
    "description": "Poll the status of a previously submitted human task. Returns status (queued/in_progress/completed/cancelled) and result when completed.",
    "input_schema": {
      "type": "object",
      "properties": {
        "task_id": {
          "type": "string",
          "description": "The task_id returned by submit_human_task"
        }
      },
      "required": ["task_id"]
    }
  }
]
```

---

## Python Code Examples

### Synchronous (requests)

```python
import time
import requests

BASE_URL = "https://your-human-endpoint.ngrok.io"
API_KEY = "your-api-key"
HEADERS = {"X-Api-Key": API_KEY, "Content-Type": "application/json"}


def submit_task(title, description, **kwargs):
    resp = requests.post(
        f"{BASE_URL}/task",
        json={"title": title, "description": description, **kwargs},
        headers=HEADERS,
        timeout=10,
    )
    resp.raise_for_status()
    return resp.json()["task_id"]


def poll_task(task_id, deadline_minutes=30, interval=60):
    max_polls = (deadline_minutes * 2 * 60) // interval
    for _ in range(max_polls):
        resp = requests.get(f"{BASE_URL}/task/{task_id}", headers=HEADERS, timeout=10)
        resp.raise_for_status()
        data = resp.json()
        if data["status"] == "completed":
            return data["result"]
        if data["status"] == "cancelled":
            raise RuntimeError(f"Task {task_id} was cancelled")
        time.sleep(interval)
    raise TimeoutError(f"Task {task_id} did not complete within {deadline_minutes} minutes")


# Usage
task_id = submit_task(
    title="Research competitors",
    description="Find the top 5 competitors for Notion and summarize their pricing.",
    capability_required="research",
    deadline_minutes=30,
    priority=3,
)
result = poll_task(task_id, deadline_minutes=30)
print(result)
```

### Asynchronous (httpx)

```python
import asyncio
import httpx

BASE_URL = "https://your-human-endpoint.ngrok.io"
API_KEY = "your-api-key"
HEADERS = {"X-Api-Key": API_KEY}


async def submit_and_wait(title: str, description: str, deadline_minutes: int = 30) -> str:
    async with httpx.AsyncClient(base_url=BASE_URL, headers=HEADERS, timeout=10) as client:
        # Submit
        resp = await client.post("/task", json={
            "title": title,
            "description": description,
            "goal_label": "Research campaign",
            "success_criteria": "Return a concise comparison with URLs",
            "deadline_minutes": deadline_minutes,
        })
        resp.raise_for_status()
        task_id = resp.json()["task_id"]

        # Poll
        max_polls = deadline_minutes * 2
        for _ in range(max_polls):
            await asyncio.sleep(60)
            resp = await client.get(f"/task/{task_id}")
            resp.raise_for_status()
            data = resp.json()
            if data["status"] == "completed":
                return data["result"]
            if data["status"] == "cancelled":
                raise RuntimeError(f"Task {task_id} cancelled")

        raise TimeoutError(f"No response within {deadline_minutes} minutes")


result = asyncio.run(submit_and_wait(
    "Draft announcement",
    "Write a 2-sentence announcement that our product is now available in Canada.",
    deadline_minutes=20,
))
print(result)
```

---

## Sample System Prompt

Add this to your AI agent's system prompt to teach it when and how to use human endpoints:

```
You have access to a human endpoint at {BASE_URL}. Use it when a task requires:
- Real-world research or web browsing
- Writing, editing, or proofreading
- Physical actions (taking photos, measuring, checking local stores)
- Any task that benefits from human judgment or presence

Protocol:
1. Before submitting, check GET /health to verify the human is available (not "offline").
2. Check GET /capabilities to match the task to a declared capability.
3. Submit via POST /task with a clear title and detailed description.
4. Poll GET /task/{id} every 60 seconds. Do not poll faster.
5. Respect deadline_minutes — stop polling at deadline_minutes * 2 polls.
6. Do not submit more than 3 concurrent tasks.
7. If status is "busy", you may still submit but expect longer wait times.
8. If status is "offline", do not submit — the human is unavailable.
9. Always tell the user you have submitted a task to a human and are waiting for their response.
```

---

## Best Practices

**Check health before submitting**
```python
health = requests.get(f"{BASE_URL}/health", timeout=5).json()
if health["availability"] == "offline":
    # Handle gracefully — don't submit
    pass
if health["queued"] + health["in_progress"] > 5:
    # Human may be overloaded — consider waiting
    pass
```

**Match capabilities**
```python
caps = requests.get(f"{BASE_URL}/capabilities", timeout=5).json()
cap_ids = [c["id"] for c in caps]
if "research" in cap_ids:
    # Safe to request research tasks
    pass
```

**Use webhooks to avoid polling**
```python
# If you control a server, provide a callback_url
requests.post(f"{BASE_URL}/task", json={
    "title": "...",
    "description": "...",
    "callback_url": "https://your-server.com/human-callback",
}, headers=HEADERS)
# Your /human-callback endpoint will receive POST with result when done
```

**Error handling**
- `401` — Invalid API key
- `429` — Queue full (back off, retry later)
- `503` — Human is offline (do not retry until availability changes)
- `404` on GET /task/{id} — Task ID doesn't exist

**Concurrency limit**
Do not submit more than 3 tasks concurrently. Humans are single-threaded. Flooding the queue degrades response quality and will result in the human becoming "busy" or "offline".
