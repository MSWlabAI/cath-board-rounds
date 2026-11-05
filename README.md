# Cath Board Rounds

> **Synthetic teaching content. Not clinical advice. Not a medical device. Not for clinical use.**
> Independent project; not affiliated with, and not representing, any employer or institution.
> The chair appears under a pseudonym (`chargenurse`).

One Switch room on Mattermost for a cath lab's morning planning. A human **chair** pastes a case packet and names two
agents. The agents only **flag** conflicts they can quote from the packet, and pass work to each other in a short relay.
They never decide, dose, substitute or reschedule. The chair rules. A **Clerk** records the rulings, drafts the board, and
writes the final board or a plan PDF **only after the chair presses Allow once on an approval card**.

Hackathon entry: Flip the Switch (WeMakeDevs + SandboxAQ), Track 01, Best Business Workflow.

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

## Why Switch is central

| Switch feature | What it does here | Without it |
|---|---|---|
| `@`-addressing, `owner-agents` | only the chair's named agents answer; a teammate's handoff post starts the next agent | every agent talks on every message |
| Approval card (owner only) | the board and the plan are written only after Allow once; Decline writes nothing | the Clerk could write unreviewed |
| One bot account per agent | each specialist is a named participant, and the recorder accepts a brief only from its own agent's account | one blob of text |
| The shared room | one packet, one record, one place to rule | copy and paste between tools |
| `!interrupt`, `!reset` | stop a stuck turn, clear a stale card | stuck sessions |

Switch delivers the handoff post and enforces who may address whom; what the agents say is their prompt.

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

See `runs.csv` (frozen-prompt runs) and `runs-tuning.csv` (earlier runs, made while prompts were still being tuned; kept for transparency, not counted).
**Day 1, frozen prompts** (hash in `freeze.txt`): 21 live runs, 420 briefs (5 cases through 4 agents, scored against `expected.json`), **0 misses; the last 20 runs in a row clean**, the last 10 of them under the final scorer. 21 format notes (lines over 140 characters; logged, not counted).
**Day 2, an unrehearsed synthetic day** (`day2.md`, answer key `expected2.json` written before any run, never shown to the agents; different patients, drugs, labs, devices and stock; 3 runs, 60 briefs): the first scoring found **3 misses, all the same line**: Case 4 Meds quoted the packet's own words ("heparin infusion stopped overnight") to show a planted contradiction, and the scorer forbids the word "stop". That was a scorer false positive, not an agent error, so the scorer now allows a forbidden word only when it is the packet's own wording (a real instruction such as "stop the heparin" still fails; there is a self-test). After the fix, with the agents unchanged: **3 runs, 60 of 60 briefs clean**. Both logs are kept (`runs-day2.csv`, `runs-day2b.csv`). Day 2 was scored once more after the scorer change, so it is evidence of generalisation, not a second blind test.
**Earlier history:** the version before the frozen prompts missed the phrase `TIMI below 3` in 8 briefs because Imaging's trigger wording was ambiguous; the prompt was fixed, not the scorer. Earlier tuning runs: 6 runs, 120 briefs, 0 misses (`runs-tuning.csv`).
**Not claimed:** the scorer checks shape and wording against an answer key written by the same author, not clinical truth; the full dry run with the human clicks (`python3 tools/dryrun.py`) has been run in pieces (each approval path passed on its own) but not as one recorded pass.

## Setup (what this entry ran on, one Mac)

1. **Install:** Docker via colima, Google Chrome, Python 3, Claude Code (logged in), the Cursor CLI (logged in: `cursor-agent login`; the program named `agent`
   must be Cursor's, so put `~/.local/bin` before any other CLI that installs an `agent`), and the Switch Console.
2. **Mattermost:** `docker run -d --name mattermost -p 8065:8065 mattermost/mattermost-preview`; create a team (`cathlab`) and the chair user (`chargenurse`) with
   `docker exec mattermost mmctl --local ...`; enable bot accounts; **disable collapsed reply threads** so approval cards stay visible:
   `mmctl --local config set ServiceSettings.CollapsedThreads disabled`.
3. **Agent folders:** `python3 tools/sync_prompts.py --write` creates `~/agents/cath-*/CLAUDE.md` (and `AGENTS.md` for the Cursor agent) and the import file
   `~/agents/cath-board-rounds-final.yaml`. In the Clerk's folder link the repo: `ln -s <repo>/tools ~/agents/cath-clerk/tools; ln -s <repo>/briefs ~/agents/cath-clerk/briefs`.
4. **Room:** in the Switch Console upload `cath-board-rounds-final.yaml` as a template and use **Use template** (not "New room": a room made that way has no
   human member, so the agents' replies fail). The room's channel slug gets a random suffix; set `ROOM` to it.
5. **Environment:** copy `.env.example` to a file outside the repo, fill it in, and point `MM_ENV_FILE` at it (`MM_TEAM`, `ROOM`, the chair user and password).
6. **Helpers (keep running):** `python3 tools/recorder.py` (saves each agent's brief for the Clerk's plan command) and `python3 tools/callback_forward.py` (lets the card
   buttons reach the Switch server; typed answers work without it).
7. **Check and pin:** `python3 tools/pin_intro.py`, then run the preflight and `python3 tools/sync_prompts.py --console`.

The author's preflight (`prep_check.sh`) lives outside this repo and checks the helpers, the symlinks, the Console's PATH and prompt drift.

## Known limits

- One machine. The approval-button callback uses a small local forwarder; if it dies the buttons fail while typed answers still work.
- Switch adds its own "Worked for N s" box to every turn; there is no setting to hide it.
- Switch shows no buttons on approval cards longer than its post limit (4,000 characters), so Clerk commands are one short line.
- The Cursor agent runs the Cursor CLI's default model on the machine (Grok on the author's); pinning a model per agent is not verified.
- The recorder accepts a brief only from the agent account named in its header, and only the chair (the room's owner) can address the agents or the Clerk.
- Pre-window helpers are not in this repo (see Disclosures).

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
