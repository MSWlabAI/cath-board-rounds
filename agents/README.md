# The five agents

One file per agent: the exact prompt each one runs on in the Switch room. **The source of truth is [`../template.yaml`](../template.yaml)**; these files are generated from it by `python3 tools/sync_prompts.py --write` and checked for drift by `python3 tools/sync_prompts.py`. Do not edit them by hand.

| Agent | Prompt | Domain | Hands off to |
|---|---|---|---|
| Imaging | [imaging.md](imaging.md) | lesion map and angio triggers (calcium, bifurcation or ostial, TIMI below 3, lesions in more than one coronary territory) | Equipment |
| Labs | [labs.md](labs.md) | kidney function against the contrast plan, Hgb, platelets, INR, potassium, troponin | Meds |
| Meds | [meds.md](meds.md) | antiplatelets, anticoagulation, metformin / ACEi / ARB / SGLT2 status | none |
| Equipment | [equipment.md](equipment.md) | devices against stock | none |
| Clerk | [clerk.md](clerk.md) | echoes the chair's rulings, drafts the board, writes the plan or board PDF only after the chair presses Allow once | none |

Every agent's only action is one Switch send-targeted-message call. Each flags only what it can quote from the packet and never decides, doses, substitutes or reschedules; the chair rules.
