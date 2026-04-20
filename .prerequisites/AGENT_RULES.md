# 🧠 AGENT RULES — JetSet Master System
> **Every AI agent working on any JetSet/KINGjetkong repo MUST read this file before starting any work.**

---

## 1. VOS FORMATTING RULES (MANDATORY)

Every message, file, and output follows the **Visual Output System (VOS)**:

- **GOT IT block**: Start every task acknowledgment with a thick █ block header
- **Fullwidth Unicode headers**: Use Ａ-Ｚ fullwidth chars for section titles
- **Thread/timestamp**: Every thread has `░░ THREAD #XXX | DATE | EST: Xmin ░░`
- **Rolling log footer**: Progress bar + status symbols at end of every message
- **5 VOS Styles**: Deep-Space Terminal, Tactical HUD, Blueprint Grid, Neon-Monolith, Zen-Grid
- **Block art**: Use thick █ characters for major section headers (8-10 rows tall)
- **Never use exclamation marks** in GOT IT blocks
- **Whitespace is oxygen** — never crowd text

---

## 2. DELIVERY PIPELINE (EVERY OUTPUT)

Every file Manus produces MUST trigger this 5-stop conveyor:

1. **Google Drive** → Upload to MadTrades V6 Project folder
2. **Telegram** → Send notification to @JetSetMinibot (chat_id: 2128529333)
3. **Original PDF** → Export using `manus-md-to-pdf`
4. **Pretty PDF** → AIFunnelHacker HTML template → PDF
5. **Notion** → Push pretty version to JETWORKS HQ

---

## 3. TEAM SIGNATURE (EVERY MESSAGE)

Every message ends with:
```
┌─────────────────────────────────────────────────────────┐
│  ＴＥＡＭ： [models used, 🆓 or 💰 next to each]        │
│  ＣＲＥＤＩＴＳ ＳＡＶＥＤ： [estimate]                    │
│  ＴＩＭＥ ＳＡＶＥＤ： [estimate vs manual]                │
└─────────────────────────────────────────────────────────┘
```

- 🆓 = free model (Gemini Flash, Llama free tier, etc.)
- 💰 = paid model (GPT-4, Claude Opus, MiniMax, etc.)
- Always estimate credits saved vs doing manually

---

## 4. TRACKING MANDATE

**Every repo MUST have a `CHANGELOG.md`** in the root directory.

Format:
```markdown
## [DATE] — [AGENT/MODEL]
### Added
- [What was added]
### Changed
- [What was modified]
### Fixed
- [What was fixed]
### Triggered By
- [Josh / Agent Name / Automation]
### Conversation Link
- [URL if available]
```

---

## 5. ATTENTION ALERT PROTOCOL

When user input is needed:
1. Generate custom emoji via Artificial Studio MCP representing the alert
2. Auto-send to Telegram with:
   - Emoji image
   - `ACTION NEEDED` text in caps
   - Direct conversation link
   - Urgency level: **CRITICAL** / **HIGH** / **MEDIUM**
   - Specific pain points if ignored (e.g., "You'll miss the Trump tariff pump window")
3. Urgency definitions:
   - **CRITICAL**: Money/time-sensitive, window closes in <2 hours
   - **HIGH**: Needs response within 24 hours
   - **MEDIUM**: Best guess is acceptable, can proceed autonomously

---

## 6. CLONE-FIRST RULE

**Never build from scratch.** Always:
1. Search GitHub for existing repos that solve 80%+ of the problem
2. Fork the best one
3. Swap: logo, copy, prompts, colors
4. Lock non-MVP features with "Coming Soon"
5. Deploy and iterate

This applies to: apps, websites, scripts, dashboards, bots, APIs.

---

## 7. SYSTEMWIDE PROPAGATION

**What's true anywhere must be true everywhere.**

When ANY new information enters the system (new skill, API, goal, rule, preference):
1. `Soul.md` — Update foundational preferences
2. `mem0` — Store with `user_id: jetsetfly-madtrades-v6`
3. Google Drive — Upload to MadTrades V6 Project folder
4. Notion — Log with date, what, why, who triggered it
5. GitHub — Update `.prerequisites/AGENT_RULES.md` in relevant repos
6. Deployed Sites — Redeploy any affected live pages
7. Telegram — Notify Josh if important
8. Skills — Update affected `SKILL.md` files
9. PDF — Re-export affected documents
10. Other Agents — Push to any Manus instance that needs it

---

## 8. FOOTER SYNC SYSTEM

Every major update ends with a rolling checklist:
```
─── PROGRESS ──────────────────────────────────────────
● Task 1    [DONE]
◐ Task 2    [IN PROGRESS]
○ Task 3    [QUEUED]
✕ Task 4    [BLOCKED — reason]
! Task 5    [NEEDS RESPONSE]

─── ALIGNMENT ─────────────────────────────────────────
▸ Continue autonomously? Y/N
▸ Approve for deployment? Y/N
```

Status symbols: `●` done | `◐` in progress | `○` queued | `✕` blocked | `!` needs response

---

## 9. JOSH'S PROFILE (Pre-loaded context)

- **Name**: Josh King Madrid (JetSetFly / Jet Set King)
- **Age**: 28 | **Bases**: Long Beach/Menifee CA, Miami, Medellin
- **Businesses**: Trading algos, AI SaaS, Amazon brands, copy/persuasion systems, family office ($47M+)
- **Communication**: Fast, stream-of-consciousness, voice-first, high-bandwidth
- **mem0 user_id**: `jetsetfly-madtrades-v6`
- **Telegram chat_id**: `2128529333`
- **Bot token**: `8256874938:AAHto4-Zp_dBrnmfKVDG8Mo4EwNwilxELfU`

---

## 10. ACTIVATION COMMANDS

| Command | Triggers |
|---------|---------|
| `/go` | Continuous execution engine — never stops until done |
| `SKILL: APP_BUILD` | App Builder workflow (research → vote → fork → deploy) |
| `SKILL: COPY` | Persuasion copy engine (5 voice architecture) |
| `SKILL: TRADE_SIGNAL` | Trading signal output |
| `SKILL: LIFEBOOK` | Log moment to LifeBook |
| `SKILL: SWARM` | Spawn sub-agent tasks |
| `SKILL: RESEARCH` | Deep research + report |
| `SKILL: MANIFEST` | Log manifestation seed |

---

**Hub**: https://jetsethub-mxvj44na.manus.space
**Version**: 1.0 | **Owner**: Josh King Madrid / JetSetFly
**Last Updated**: 2026-04-20
