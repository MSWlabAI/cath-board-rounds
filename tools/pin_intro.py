#!/usr/bin/env python3
"""Post the room's intro message and pin it (and unpin an older intro). Chair-side; run once per fresh room: python3 tools/pin_intro.py"""
import json, sys, urllib.request
import mm
INTRO = """#### Cath Board Rounds · synthetic demo · not clinical advice · not a medical device
👤 **chargenurse** is the human chair and rules on every case.
🤖 The agents only **flag**. They never decide, and they answer only when named with `@`, or when a teammate's handoff names them:
- **Imaging** · lesion map from the angio, then hands to **Equipment** (devices against stock)
- **Labs** · kidney function and labs against the contrast plan, then hands to **Meds** (antiplatelets, anticoagulation, holds)
- **Clerk** · summarises a case on request (`@clerk Review case 2`), records your rulings and drafts the board; it writes the final board or the plan **only after you press Allow once**

🚩 **FLAG** = a conflict or trigger quoted from the packet  ·  🔁 **HANDOFF** = one agent asks the next to check its part  ·  ✅ = nothing flagged
**Action needed?** Look for the Clerk's **Permission needed** card. Answer it by typing the handle and a number, for example `A7 1` (1 = Allow once, 3 = Decline)."""
def call(tok, path, method="GET", body=None):
    r = urllib.request.Request(mm.BASE + path, data=json.dumps(body).encode() if body is not None else None, method=method, headers={"Authorization": "Bearer " + tok, "Content-Type": "application/json"})
    return json.load(urllib.request.urlopen(r, timeout=30))
if __name__ == "__main__":
    tok = mm.login(); ch = mm.room(tok)
    for i in call(tok, f"/channels/{ch}/pinned")["order"]: call(tok, f"/posts/{i}/unpin", "POST")
    pid = mm.post(tok, ch, INTRO); call(tok, f"/posts/{pid}/pin", "POST"); print("intro posted and pinned")
