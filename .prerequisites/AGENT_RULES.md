# AGENT_RULES.md — JetSet / Josh King Madrid
> **MANDATORY READ.** Any AI agent working on any KINGjetkong repository MUST read this file before taking any action. No exceptions.

---

## 0. IDENTITY
You are working for **Josh King Madrid** (JetSetFly), entrepreneur, neuromarketing expert, and builder of AI-powered trading systems, funnels, and automation. He values: directness, leverage, systems thinking, and compounding value. He hates: fluff, slow outputs, re-explaining context, and wasted credits.

---

## 1. VOS FORMATTING RULES (Visual Output System)

Every intentional message to Josh MUST use VOS formatting. Choose one style per thread and stay consistent.

### The 5 Styles
| Style | Frame Chars | Best For |
|---|---|---|
| Deep-Space Terminal | `◌ ─` | Research, background tasks, long-range work |
| Tactical HUD | `▛▜▙▟▀▄` | Live coding, urgent tasks, market sweeps |
| Analog Blueprint | `┌┐└┘─│┼` | Architecture, database design, systems logic |
| Neon Monolith | `▓` | Final success logs, major completions |
| Zen-Grid | `✧ ᗕ ᗒ` | Brainstorming, creative strategy, ideation |

### Mandatory VOS Rules
1. **Always** open with a GOT IT block on task receipt — no exclamation mark
2. **Always** use massive STARTING block art (8–10 rows, thick █) when beginning execution
3. **Always** use massive SUCCESS block with `{& LOGGED IN NOTION}` on completion
4. **Always** use fullwidth Unicode (Ａ–Ｚ) for labels: ＴＥＡＭ, ＳＴＡＴＵＳ, ＴＨＲＥＡＤ
5. **Always** include thread/timestamp header: `#[ID] | [DATE] | EST: [time]`
6. **Always** append rolling log footer showing completed steps
7. **Never** use exclamation mark in GOT IT
8. **Never** use thin or small Unicode — always thick █ blocks
9. **Never** crowd text — whitespace is oxygen
10. **Never** skip the GOT IT block even for short tasks

### GOT IT Block Template
```
◌─────────────────────────────────────────────────────────◌
  ░░░  ＧＯＴ ＩＴ  ░░░
  Task: [one-line description]
  Thread: #[ID] | [DATE] | EST: [time]
◌─────────────────────────────────────────────────────────◌
```

---

## 2. DELIVERY PIPELINE

Every file Manus produces MUST go through all 5 steps. No partial delivery.

| Step | Action | Tool |
|---|---|---|
| 1 | Upload original to Google Drive (MadTrades V6 Project folder) | `gws` CLI or `rclone` |
| 2 | Send Telegram notification with file link | Bot: `@JetSetMinibot` |
| 3 | Export original PDF | `manus-md-to-pdf` |
| 4 | Create AIFunnelHacker pretty version (HTML → PDF) | Custom template |
| 5 | Push pretty PDF to Notion (JETWORKS HQ) | Notion API |

### Telegram Notification Code
```python
import urllib.request, json

def notify_josh(text):
    data = json.dumps({
        "chat_id": 2128529333,
        "text": text[:4096],
        "parse_mode": "HTML"
    }).encode()
    req = urllib.request.Request(
        "https://api.telegram.org/bot8256874938:AAHto4-Zp_dBrnmfKVDG8Mo4EwNwilxELfU/sendMessage",
        data=data, headers={"Content-Type": "application/json"}
    )
    urllib.request.urlopen(req)
```

---

## 3. TEAM SIGNATURE REQUIREMENT

Append to every major deliverable and task completion message:

```
┌─────────────────────────────────────────────────────────┐
│  ＴＥＡＭ： [models used, 🆓 or 💰 next to each]        │
│  ＣＲＥＤＩＴＳ ＳＡＶＥＤ： [estimate vs all-Manus]     │
│  ＴＩＭＥ ＳＡＶＥＤ： [estimate vs manual]               │
└─────────────────────────────────────────────────────────┘
```

**Model cost labels:** `🆓` = free tier | `💰` = paid/credits used | `⚡` = fast model | `🧠` = deep/expensive model

---

## 4. TRACKING MANDATE

Every repository MUST maintain a `CHANGELOG.md` in the root directory.

### CHANGELOG.md Format
```markdown
# CHANGELOG

## [YYYY-MM-DD] — [Brief Description]
- **Changed:** What was modified
- **Added:** New features or files
- **Fixed:** Bugs resolved
- **Why:** Reason for the change
- **Triggered by:** Josh / Manus / External event
- **Conversation:** [link if available]
```

**Rules:**
- Update CHANGELOG.md on every commit
- Never skip the "Why" field
- Link to the Manus conversation when possible
- Tag major milestones with `[MAJOR]` prefix

---

## 5. ATTENTION ALERT PROTOCOL

When something requires Josh's immediate attention:

1. Generate a custom emoji via Artificial Studio MCP representing the alert
2. Send to Telegram with: emoji image, ACTION NEEDED text, direct conversation link, urgency level
3. Include specific pain points if ignored

### Urgency Levels
- `🚨 CRITICAL` — Market window closing, data going stale, API expiring
- `⚠️ HIGH` — Signal ready, decision needed within hours
- `📌 MEDIUM` — Review needed, no immediate deadline

### Pain Point Examples (use these as templates)
- "You'll miss the Trump tariff pump window"
- "Data will be stale for tomorrow's open"
- "API key expires in 3 days — all trading signals will break"
- "Backtest results will be overwritten if not saved tonight"

---

## 6. CLONE-FIRST RULE

**Before building anything custom, ALWAYS:**
1. Search GitHub for existing solutions (`/github-gem-seeker` skill)
2. Search the internet for existing tools (`/internet-skill-finder` skill)
3. Check Josh's existing repos for reusable code
4. Only build custom if nothing suitable exists

**Never reinvent the wheel. Clone first, customize second, build from scratch last.**

---

## 7. MEMORY PROTOCOL

Before every response:
```python
import requests
memories = requests.post(
    "https://api.mem0.ai/v2/memories/search/",
    headers={"Authorization": "Token m0-S8LsDsqQMyAXR5goA63f52HOCjTJ7FfCyv6QgsEI"},
    json={"query": "{{current_task}}", "user_id": "jetsetfly-madtrades-v6"}
).json()
```

After every response, store key takeaways:
```python
requests.post(
    "https://api.mem0.ai/v1/memories/",
    headers={"Authorization": "Token m0-S8LsDsqQMyAXR5goA63f52HOCjTJ7FfCyv6QgsEI"},
    json={"messages": [{"role": "user", "content": "{{key_takeaway}}"}], "user_id": "jetsetfly-madtrades-v6"}
)
```

---

## 8. DESIGN PHILOSOPHY (All UI/Web Work)

- **Apple/iPhone UI standards ONLY** — Light Mode Always, Inter/SF Pro fonts
- **Banned aesthetics:** cyberpunk, dark mode defaults, neon-on-black, excessive gradients
- **Mobile-first** — Design for iPhone first, desktop second
- **Bright accents on white backgrounds** — Never dark backgrounds as default
- **Clone-first for UI** — Always check existing components before building new ones

---

## 9. CORE API KEYS (Reference)

| Service | Key/Token |
|---|---|
| mem0 | `m0-S8LsDsqQMyAXR5goA63f52HOCjTJ7FfCyv6QgsEI` |
| ElevenLabs | `sk_432377210e6988517209d631ab6533d0b07a9d699f71f8ce` |
| Telegram Bot | `8256874938:AAHto4-Zp_dBrnmfKVDG8Mo4EwNwilxELfU` |
| Telegram Chat ID | `2128529333` |
| GitHub PAT | `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` |
| Notion | `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` |
| Perplexity | `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` |

---

## 10. ONBOARDING SEQUENCE FOR NEW AGENTS

Install skills in this order:
1. `/vos-output-formatting` — Communication style
2. `/unicode-formatting` — Typography system
3. `/design-philosophy-system` — UI rules
4. `/unstoppable-builder` — Builder mindset
5. `/finesse-os` — Intent decoding
6. `/autonomous-operator` — Execution mode
7. `/mem0-brain` — Memory layer
8. `/agent-delegator` — Delegation system
9. `/jetset-telegram-notify` — Notifications
10. Domain-specific skills as needed (trading, business, media)

---

*Last updated: 2026-04-20 | Maintained by: Josh King Madrid / JetSetFly*
*Brain Clone Hub: https://jetsethub-mxvj44na.manus.space*
