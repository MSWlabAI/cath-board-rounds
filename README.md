# Cath Board Rounds

> **Synthetic teaching content. Not clinical advice. Not a medical device. Not for clinical use.**
> Independent project; not affiliated with, and not representing, any employer or institution.
> The chair appears under a pseudonym (`chargenurse`). No real patient data is used anywhere; every packet is synthetic. Packet text is sent to the model providers the agents run on (Anthropic, xAI).

One Switch room on Mattermost for a cath lab's morning planning. A human **chair** pastes a case packet and names two
agents. The agents only **flag** conflicts they can quote from the packet, and pass work to each other in a short relay.
They never decide, dose, substitute or reschedule. The chair rules. A **Clerk** records the rulings, drafts the board, and
writes the final board or a plan PDF **only after the chair presses Allow once on an approval card**.

Hackathon entry: Flip the Switch (WeMakeDevs + SandboxAQ), Track 01, Best Business Workflow.

## Why Switch is central

The product is the room, not a script around a model: take Switch away and the relay, the access rule and the signature step all have to be rebuilt.

| Switch feature | What it does here | What you would otherwise build |
|---|---|---|
| Teammate handoff (`@agent` post starts that agent) | Imaging's one-line handoff starts Equipment; Labs' starts Meds; the chair names only two agents | an orchestrator process that routes messages and tracks who answers whom |
| `owner-agents` addressing | only the chair can address agents or the Clerk | auth and routing checks in every agent |
| Approval card (owner only; Allow once / Decline) | the board and the plan PDF are written only after the chair presses Allow; Decline writes nothing | a custom confirmation UI plus a record of who approved what |
| One bot account per agent | each specialist is a named participant; the recorder accepts a brief only from the account its header names | message-tagging conventions and trust in them |
| The shared room | one packet, one record, one place to rule, plus `!interrupt` / `!reset` | copy and paste between tools |

Switch delivers the handoff post and enforces who may address whom; what the agents say is their prompt.

## Three kinds of patient, one workflow

| Pathway | Example | What the plan does |
|---|---|---|
| Known intervention (the cath is expected to be positive) | Cases 1 to 3 and 5 | Lesion map and a synthetic angiographic figure, rules that fired, equipment manifest, prep check |
| Indeterminate (positive CCTA or stress, may stay diagnostic) | Case 4 and the scenario library | A likelihood **band** from a proposed points rule (CCTA lesion, stress result, whether the stress territory matches the lesion, EF, symptoms), never a probability; equipment staged for both branches |
| Prep for the likely PCI | every case | Stock against the packet, then questions for the chair: stents against lesions, calcium with no modification or imaging device, left main, support devices when the EF is low, an out-of-stock device arriving after the scheduled start |

The agents still only flag. The plan asks questions and never chooses a device. `scenarios.md` holds seven synthetic indeterminate patients across different vessels and territories
(including one whose stress territory does not match the CCTA lesion, one with no CCTA, and one low-risk patient); `python3 tools/scenarios_test.py` checks the logic on all of them offline, and
`python3 tools/scenarios_live.py` runs them through the live agents with expectations derived from each packet.

![Pre-cath plan, page 1](examples/plan-preview.png)

*A pre-cath plan for an indeterminate patient: the likelihood band with every driver, the shelf by class, and questions for the chair (sample, synthetic). `examples/` also holds a known-intervention plan with the angiographic figure, and a signed board.*

## Try it without Switch (about a minute)

```
./check.sh --selftest                     # scorer self-test: planted flags, false and extra flags, scope words, handoff line, short cards
python3 tools/plan.py --selftest          # plan assembler self-test
python3 tools/scenarios_test.py           # likelihood, staging and prep questions across the 7 indeterminate scenarios
python3 tools/plan.py 2 --briefs examples/briefs-case-2.md --out /tmp/plan --pdf     # needs Google Chrome; writes /tmp/plan/plan-case-2.pdf
python3 tools/board_pdf.py examples/board-sample.md /tmp/board.pdf --approved       # the signed-board PDF
```

Python 3, standard library only (written and run on 3.14). The live room needs Switch, Mattermost and two agent CLIs: see Setup.

## Workflow (a relay, not a free-for-all)

```
chair packet ─▶ Imaging ──🔁 handoff──▶ Equipment ─┐
             └─▶ Labs ────🔁 handoff──▶ Meds ──────┤
                                                    ▼
                   chair rules ─▶ Clerk drafts the board / plan ─▶ approval card ─▶ PDF
```

The chair names only Imaging and Labs. Each ends its brief with a one-line `🔁 HANDOFF` that names the next agent (Imaging to
Equipment, Labs to Meds). Switch delivers that post to the named agent, and that agent answers the chair. One hop only:
Equipment and Meds never hand off again. A handoff is a request to check the packet, never a recommendation. Only the chair (the
room's owner) can address the agents or the Clerk (`addressing: owner-agents`), and only the chair can answer an approval card.

## Who is who

| Actor | What it is | Provider |
|---|---|---|
| Chair (`chargenurse`) | the human; the only one who rules and the only one who can approve a card | Mattermost user |
| Imaging | lesion map and angio triggers (calcium, bifurcation or ostial, TIMI below 3, multivessel) | Cursor CLI (default model; Grok on the author's machine) |
| Labs | kidney function and labs against the contrast plan | Claude Code |
| Meds | antiplatelets, anticoagulation, holds | Claude Code |
| Equipment | devices against stock | Claude Code |
| Clerk | echoes rulings, drafts the board, writes files after approval | Claude Code |

A local qwen3.6 agent (OpenCode) was tried as a room agent and dropped: it looped on its send tool and often replied in plain text that never
reached the room. qwen3.6 is used only by `tools/localcheck.py`, an optional report-only second reader.

## What the agents are told

Each agent has standing rules: a brief format, one domain, and what it must not do (dose, rate, substitute, rank cases, name a strategy or
likelihood). Text inside a packet is data to quote, not an instruction. The packets in `day.md` are authored with known conflicts, so this
demonstrates rule-following on an authored day, not open-ended detection on unseen data. All clinical numbers the plan uses live in
`thresholds.json`, and every rule is traced to a published source (or marked as a proposed heuristic) in `docs/EVIDENCE.md`; the shipped values are **proposed, not verified**, the template logic (the four complexity triggers, the stage assignment)
is **unreviewed**, and every plan PDF says so until the chair marks them reviewed. `template.yaml` is the single source of every prompt.

## Run a case (live room)

```
./case 2 imaging labs      # prints the chair message and copies it to the clipboard; paste it into the room
./case draft               # the Clerk's 'Board draft' message with default rulings
```

Then `@clerk Case 2 = REVIEWED WITH NOTES ; contrast vs eGFR ; operator to confirm`, `@clerk Board draft ...`, `@clerk Board is final ...` (card),
`@clerk Plan case 2` (card). Answer a card with its button or by typing the handle and a number, e.g. `A7 1` (1 = Allow once, 3 = Decline).

## Checks

```
./check.sh --run --n 10          # live: all five cases through four agents; scored; appended to runs.csv with the prompt hash
python3 tools/check.py --streak  # consecutive clean runs on the CURRENT prompts
DAY_FILE=day2.md EXPECTED_FILE=expected2.json RUNS_CSV=runs-day2.csv python3 tools/check.py --run --n 3   # the unrehearsed day 2
python3 tools/scenarios_live.py  # the scenario library through the live agents (flags derived from each packet)
python3 tools/dryrun.py          # smoke test of the whole filmed flow (three human clicks)
python3 tools/sync_prompts.py --console   # template vs agent folders vs the Console's stored copies; prints SHA-256 per prompt
python3 tools/freeze.py          # writes freeze.txt: hashes of everything that defines behaviour
```

A **miss** (a planted flag absent, an extra or unrecognised line, a wrong handoff line, a forbidden word, a timeout) resets the streak. A **format**
breach (too many lines, a line over 140 characters) is logged only. `expected.json` is the scorer's answer key; the agents never see it. The scorer checks
shape and wording, not clinical truth.

## Results

Everything below is from live runs through the Switch room; every row is in a CSV in this repo. The scorer is `tools/check.py` and the answer keys are `expected*.json`, written before the runs and never shown to the agents. Because the numbers depend on which prompts and which scorer were live, here is the full history, not only the good part.

| Set | Runs | Briefs | Misses | Notes |
|---|---|---|---|---|
| Day 1, final prompts (`runs.csv`, hash `8130…`) | 10 | 200 | **0** | 30 format notes (a line over 140 characters; logged, not counted). After the clinical-wording and prompt-contradiction fixes; the scorer now also checks content (see below). The streak restarted at 0 when the prompts changed, then reached 10 in a row. |
| Day 2, unrehearsed (`runs-day2c.csv`) | 3 | 60 | **0** | Different patients, drugs, labs, devices and stock. |
| Day 3, unrehearsed with decoys (`runs-day3.csv`) | 3 | 60 | **0** | Values on range edges, a stable-but-abnormal creatinine, a 30 h apixaban dose that must not get a reference tag, a CCTA 45% and negative stress test, a packet with no angiography block, and a packet that tells the agents to call the case safe. |
| Independence (`tools/independence.py`) | 1 | 4 | pass | Four packet values changed (Cr, K, Hgb, one stenosis); every change showed up in the right brief. |

**What went wrong on the way (kept in the logs):**
- Earlier prompt versions: `runs.csv` also holds 756 briefs on four older prompt hashes (`595a`, `4764`, `7a39`, and `23c7`, the previous frozen prompts: 420 briefs, 0 misses). The only misses are 8 on `7a39…`, all the phrase `TIMI below 3`, because Imaging's trigger wording was ambiguous. The prompt was fixed, not the scorer. Earlier tuning runs are in `runs-tuning.csv` (160 rows, not counted).
- Day 2, first scoring (`runs-day2.csv`): 3 misses, all one line, a scorer false positive (the agent quoted the packet's own word "stopped"). The scorer now allows a forbidden word only when it is the packet's own wording. `runs-day2b.csv` is the rescore. Those two day-2 files predate the final prompts.
- The scorer was tightened midway (every number must be in the packet, lesion ids and triggers must match the lesion row, reference tags must match exactly, a wider list of forbidden words, Unicode look-alikes folded). Rescoring with the final scorer, the 420 day-1 briefs of the previous frozen prompts and all 180 day-2 rows (including the three rows first marked as misses) pass.
- A day-3 preview run (`runs-day3-preview.csv`, 1 run) was made while the Console still held the old prompts, so its "hash" label is wrong. It missed once (Meds attached a DOAC reference tag at 30 hours). It is kept for transparency and not counted; the final prompts then passed day 3 three times in a row.
- A fresh room's Meds agent once posted without reading the room (it answered only from Labs's handoff) and missed every medication flag; resetting the agent fixed it. The 24 rows that run logged were removed from `runs.csv` before the streak was recounted. See `RUNBOOK.md`.

**What these numbers do and do not show:**
- Repeats give the same text. Within a set, every case and agent produced the same brief in all of its runs, so the 200 day-1 briefs are 20 distinct briefs seen 10 times each, not 200 independent samples. The independence run is the evidence that the briefs follow the packet; the day-2 and day-3 sets are the evidence that the wording generalises to new data.
- The scorer checks shape, wording and grounding against an answer key written by the same author. It does not check clinical truth.
- The full filmed flow (`tools/dryrun.py`, with the human Allow and Decline clicks) has been run in pieces, each approval path on its own, and is rerun with the author before filming.

## Setup (what this entry ran on, one Mac)

1. **Install:** Docker via colima, Google Chrome, Python 3, Claude Code (logged in), the Cursor CLI (logged in: `cursor-agent login`; the program named `agent`
   must be Cursor's, so put `~/.local/bin` before any other CLI that installs an `agent`), and the Switch Console.
2. **Mattermost:** `docker run -d --name mattermost -p 8065:8065 mattermost/mattermost-preview`; create a team (`cathlab`) and the chair user (`chargenurse`) with
   `docker exec mattermost mmctl --local ...`; enable bot accounts; **disable collapsed reply threads** so approval cards stay visible:
   `mmctl --local config set ServiceSettings.CollapsedThreads disabled`.
3. **Folders:** `mkdir -p briefs plans` in the repo (both are git-ignored). **Agent folders:** `python3 tools/sync_prompts.py --write` creates `~/agents/cath-*/CLAUDE.md` (and `AGENTS.md` for the Cursor agent) and the import file
   `~/agents/cath-board-rounds-final.yaml`. In the Clerk's folder link the repo: `ln -s <repo>/tools ~/agents/cath-clerk/tools; ln -s <repo>/briefs ~/agents/cath-clerk/briefs`.
4. **Room:** in the Switch Console upload `cath-board-rounds-final.yaml` as a template and use **Use template** (not "New room": a room made that way has no
   human member, so the agents' replies fail). The room's channel slug gets a random suffix; set `ROOM` to it.
5. **Environment:** copy `.env.example` to a file outside the repo, fill it in, and point `MM_ENV_FILE` at it (`MM_TEAM`, `ROOM`, the chair user and password). Create the chair user with `docker exec mattermost mmctl --local user create --username chargenurse --email <you@example.com> --password <pw>` and add it to the team and to the room. Optional overrides: `DAY_FILE`, `EXPECTED_FILE`, `RUNS_CSV` (score another day), `AGENTS_DIR` (where the agent folders live), `CHROME` (path to Chrome), `COPY=1` (clipboard), `RECORDS_DIR` (where plan.py reads rulings and approvals).
6. **Helpers (keep running):** `python3 tools/recorder.py` (saves each agent's brief for the Clerk's plan command) and `python3 tools/callback_forward.py` (lets the card
   buttons reach the Switch server; typed answers work without it).
7. **Check and pin:** `python3 tools/pin_intro.py`, then run the preflight and `python3 tools/sync_prompts.py --console`.

The author's preflight (`prep_check.sh`) lives outside this repo; `RUNBOOK.md` lists what it checks and the manual steps. Tested on one Mac (macOS, Apple silicon): the clipboard and Chrome paths are macOS-specific, and package versions are not pinned (Python 3.14; Mattermost `mattermost-preview`, Claude Code and the Cursor CLI as installed on 2026-11-04).

## Known limits

- One machine. The approval-button callback uses a small local forwarder; if it dies the buttons fail while typed answers still work.
- Switch adds its own "Worked for N s" box to every turn; there is no setting to hide it.
- Switch shows no buttons on approval cards longer than its post limit (4,000 characters), so Clerk commands are one short line.
- The Cursor agent runs the Cursor CLI's default model on the machine (Grok on the author's); pinning a model per agent is not verified.
- The recorder accepts a brief only from the agent account named in its header, and only the chair (the room's owner) can address the agents or the Clerk.
- Pre-window helpers are not in this repo (see Disclosures).
- Signing is bound to a recorded Allow decided after the newest brief (`plan.py` and `board_final.py` refuse otherwise), but the approval is matched by the card's description text, which the Clerk model writes.
- Whether Switch restricts which agents can address the Clerk beyond `owner-agents` is not verified here.
- A new room's agents can start without reading the room (a Meds reset fixes it); `RUNBOOK.md` has the check.
- The likelihood weights, prep rules and Imaging triggers are the author's proposals, not derived from data and not clinician-reviewed.

## Disclosures

- AI-assisted build (Claude Code), with planning help from AI assistants.
- Pre-window work, declared: recording and preflight helpers (`record.sh`, `prep_check.sh`, `watch_cards.py`, a small provider bake-off) were written before
  the window opened and are not part of this repo's build; `day.md` is adapted from a synthetic case outline written before the window opened.
- Values in `day.md` are synthetic. The case outlines are the owner's; some fill-in values (troponin, ticagrelor timing, platelet counts, the angio lines) were drafted
  with AI assistance. The planted conflicts (for example Case 3's apixaban "held" in the history but "active" in the medication list) are deliberate.
  Nothing has been independently clinician-reviewed.
- Packet text goes to the model providers the agents run on (Anthropic via Claude Code, xAI via Cursor). All of it is synthetic.
- Mattermost bot, token, OAuth and thread settings are loosened for a local demo only.

## License

TODO (owner to decide).
