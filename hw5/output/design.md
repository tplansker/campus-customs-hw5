# Campus Customs Back Office: Dashboard Design (Problem 8)

**Concept:** the back office behind the HW4 storefront. HW4's customer site was a 1996 Yale
homepage, with a starfield, Netscape windows, WordArt, AIM and rubber stamps. The desk keeps that
world but turns the volume down. People will sit at it for a shift, reading agent conversations and
signing for real money, so it reads like a well-organized 1996 office.

The code is in `frontend/src/`: `App.tsx` (layout and panels), `agents.ts` (agent personas and the
crew-report logic), `styles.css` (the look) and `Bulldog.tsx` (HW4's Handsome Dan). Start it with
`npm run dev` in `frontend/`. It calls the Problem 7 routes on `http://localhost:8000`.

## Layout: three columns that follow the work

| Column | What's there | Why |
|---|---|---|
| **Inbox** (left) | The three tickets as rows: number in Impact, subject, requester, type, and a status pill. Customer drafts sit underneath in an **Outbox**. | You always see the whole board at once, and every ticket's state is readable without opening it. |
| **Case file** (center) | The selected ticket's facts, a **Send to the crew ➤** button with an optional note for the Boss, the **Crew report**, and the live **Instant Messages** transcript. | The center is where you read, and the thing you're working on gets the most room. |
| **Crew & money** (right, sticky) | The **Buddy List** (who's working), the **Cash Register** (checking balance) and **Sign Here** (approvals). | Money and people stay on screen while you scroll a long transcript, so you never lose sight of the balance. |

On narrower screens the right column drops under the other two. On phones everything stacks into
one column, with no sideways scrolling at 375px.

## How the agents read differently

Each agent is an AIM buddy, with a screen name, a color and an icon that follow it everywhere: the
buddy list, the transcript and the crew report.

| Agent | Screen name | Look |
|---|---|---|
| Boss | **HandsomeDan96** | Yale Blue, with HW4's Handsome Dan bulldog as the avatar. The Boss *is* the mascot. |
| Inventory | **StockRoom96** | Purple, 📦 |
| Accounting | **TheLedger96** | Green, 🧾 |
| Facilities | **WrenchCrew96** | Orange, 🔧 |
| Customer Service | **FrontDesk96** | Teal, 💬. Deliberately not crimson. |

- **Different kinds of activity look different, so they're easy to scan:**
  - Handoffs and replies are colored message bubbles with an arrow ("TheLedger96 → WrenchCrew96: …").
  - Tool use is a small gray line written as a verb ("StockRoom96 *checked the shelves* `check_stock`").
  - The Boss's final call gets a yellow, outlined box.
  - Your own approvals appear as a dashed "✍️ You approved #1 — Paid rent…" line.
  - A "show tool use" checkbox hides tool lines when you only want the conversation.
- **"is typing…":** whichever agents are mid-task show AIM's three blinking dots at the bottom of the
  transcript, so you can tell the run is alive even while the model is thinking.
- **The Buddy List works like AIM's.** "On the clock" agents get a colored row, a gently bobbing
  avatar, and their current action as the status ("checked the cash drawer…"). "Standing by" agents
  are dimmed and show an away message ("Counting hoodies in the back room."). It shows at a glance
  that only the right specialists were called.
- **Crew report:** when a run finishes, the Boss's call appears at the top with its outcome pill. Below
  it, each specialist gets one line: what it said, tags for anything it created (`approval #1`,
  `draft #2`), who asked it for help or whom it asked, and the tools it used. It's built only from that
  run's events.

## How resolved tickets and cash show up

- **Ticket states** have their own pills: white *Open*, blue *Crew working*, yellow *Needs your
  signature*, orange *Needs you*, green *Resolved*.
  - A yellow **sticky note** ("Needs your signature ✍️") sits on the case file of any ticket that's
    waiting on you.
  - A resolved ticket gets a red **RESOLVED rubber stamp** that lands with a *thunk* on the case file
    and also marks its inbox row. The run button changes to "Resolved ✔".
- **The cash register** shows the checking balance as a green **LCD readout** (from `/api/cash`).
  - When a payment is approved, the number **rolls down** to the new balance, and a red
    "−$2,400.00" falls off the display.
  - The **receipt tape** below prints the payment with a red **PAID** stamp.
  - A line under the display says what would be left if you signed everything waiting. It turns amber
    when that's under $500, and it reminds you that no revenue is modeled.
- **Sign Here:** each pending request is drawn as a **check**: pale blue security pattern, amount
  in large type, memo line, and an ✗ ____ signature line beside the **Approve** and **Reject** buttons.
  Each check shows *checking after* for that request, or "Not enough cash; this will be refused".
  The window's title bar turns orange whenever something is waiting.

## What makes it feel special

- **It belongs with the storefront.** Same Yale Blue starfield, Netscape title bar and location bar,
  beveled Win95 buttons, WordArt ticket titles and Handsome Dan. Someone who knows the customer site
  feels at home in the back office.
- **The metaphors match the jobs.** Agents chat like AIM buddies, approvals are checks you sign, cash
  is a register with a receipt tape, and resolved means a rubber stamp. Each one tells you what an
  action does before you click.
- **The moments that matter are rewarding.** Signing a check and watching the register roll down, or a
  RESOLVED stamp landing, gives a small thrill, but only when a person did something real.
- **Small jokes at the edges, not in the way.** The away messages, an 88×31 "Best viewed at a desk with
  coffee" badge, and "🚫 Harvard Mode: disabled" carry HW4's rivalry gag without slowing anyone down.

## Desk-first guardrails

- **Readable for hours:** dark text on light "paper" windows, Tahoma/Verdana for body text, and
  Impact/Comic only for headings, names and labels. The starfield is static and stays behind the windows.
- **Motion only means something:** typing dots, the bobbing busy avatar, the register roll, the
  falling amount and the stamp. Nothing loops in the reading area, and every animation turns off
  under *prefers-reduced-motion* (the register then updates instantly).
- **Honest numbers:** every figure comes from the API (`/api/tickets`, `/api/events`, `/api/cash`,
  `/api/approvals`). The page never computes a balance on its own, and it can't move money: only a
  human clicking Approve does, through `POST /api/approvals/{id}`.
- **Clear when something's wrong:** if the backend is down, a red banner says where it looked and how
  to start it. Refused approvals (for example, not enough cash) come back as a red notice in plain words.
- **Accessible:** real buttons and labels, visible focus rings, `aria-live` on the transcript and the
  register, and the selected ticket marked with `aria-current`.

## Verified (2026-11-06)

Tested at 1440×900 and 375×812:
1. Picked ticket #102 and sent it to the crew. The Buddy List showed HandsomeDan96, TheLedger96 and
   WrenchCrew96 on the clock, and the transcript streamed their handoffs and tool use.
2. The $2,400 rent check appeared under Sign Here mid-run, and the crew report appeared when the run
   finished.
3. Clicked **Approve**. The register rolled from $3,400.00 to $1,000.00 with a falling "−$2,400.00",
   and the tape printed `rent #1 · −$2,400.00 · PAID`.
4. The follow-up run closed the ticket, and the RESOLVED stamp landed on the case file and the inbox.
