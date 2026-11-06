# HW5 – AI Prompts Log

This file records the prompts I used with the AI coding assistant for each problem in Homework 5
(Campus Customs multi-agent operation: MCP server, FastAPI agent team, React dashboard).

<!-- Sections are added below as each problem is started. Format:

## Problem N: Title

**Prompt:**
> ...

**Follow-up prompt(s):**
> ...

-->

## Problem 1: Vibe Coder Prompts

**Prompt:**
> use my PORTKEY_API_KEY for AI calls. use only gpt-6-luna through portkey for every agent. final submission will be a public GitHub repo (the last problem shows the file tree).
>
> create AI_prompts.md at the start of this and keep it updated as i work. this is the file to log what i typed from this point forward into my vibe coder.
>
> Problem #1: i will put one section in for each problem like i did in HW4. each section must include the problem number and title, at least one prompt i typed, in my own words as much as possible, and one follow-up prompt if i need it.

**Follow-up prompt(s):**
> the was Problem #1: Vibe Coder Prompts

## Problem 2: Study the Campus Customs Database

**Prompt:**
> Open data/campus_customs.db, and copy the original file to data/campus_customs_new.db. we will update this working copy later. study the three open tickets so i see how they link to other tables.

**Follow-up prompt(s):**
> start output/harness.md. for each table, list the fields and one short line on why the table matters for the agents. i will keep growing this harness file in later problems.

## Problem 3: Build the MCP Server

**Prompt:**
> write an MCR server in mcp_server/ using Fast MCP. it will talk to data/campus_customs_new.db. i do not need to connect or run it in this problem
>
> every agent in this assignment used the tools in this MCP server. i will add more tools later. create these three tools keep the names clear, never invent any data, only use information in the databse:
>
> * ticket retrieval
> * ticket filtering
> * databse search

**Follow-up prompt(s):**
> Yes, add it _(adding the MCP tools section to output/harness.md)_

> in output/harness.md list each of the three tools. for every tool include which table it reads, which ticket it helps unlock (101, 102, 103), and one sentence on lwhy that tool is the right one for the ticket (as i have listed below)
>
> * ticket retrieveal: a direct retrieval tool is essential because it allows the AI agent to pull the complete, factual history of a specific ticket using its unique ID without hallucinating details
> * ticket filtering: a filtering tool is necessary because it enables the agent to aggregrate and organize multiple tickets by specific criteria, such as isolating only unresolved issues or prioritizing urget requests
> * database search: a keyword search tool provides the required flexibility for an agent to locate relevant records when the exact ID is unknown by scanning the database for specific campus customs issues.
>
> also add a short mcp_server/README.md file that explains what the MCP server is for, which database file it uses, and the three tools it has in it

## Problem 4: Add the MCP Server to Vibe Coders and Test Each Tool

**Prompt:**
> add my MCP server to this project so the vibe coder can call the tools. save the connection JSON text in .mcp.json at the project root, or however you save local MCP server lists
>
> then, test each of the three MCP tools. save the evidence in output/mcp_smoke.json. for every tool include:
>
> * the prompt i asked the vibe coder
> * the tool name
> * and the tool output (must match data/campus_customs_new.db)

**Follow-up prompt(s):**
> the three prompts:
>
> * to trigger Ticket Retrieval: what are the full details for ticket ID number 10
> * to trigger ticket filtering: can you list all the tickets that currently have and open status?
> * to trigger database search: search the database for any tickets that mention the phrase 'parking pass'

## Problem 5: Build the Agent Team and Grow the MCP Tools

**Prompt:**
> build the agentic team for Campus Customs using PydanticAI: boss, inventory, accounting, facilities, and customer service. include prompts, models, and agent loops so they can delegate work to each other with full connectivity. put the agent prompts in backend/prompts/ - one file per agent. put data types in backend/models.py, and the agent files under backend/. use the PORTKEY_API_KEY and ONLY gpt-6-luna for every agetn.

**Follow-up prompt(s):**
> here are the prompts with the shop rules that each agent needs:
>
> * Boss Agent
> You run the floor at Campus Customs. Your main job is triage and delegation. When a ticket comes in, you do not do the grunt work yourself; you figure out exactly who needs to handle it and pass it down the chain. If an issue is about stock levels or missing merch, kick it to Inventory. If it is a billing dispute or an unpaid invoice, hand it to Accounting. If the roof is leaking or a display case is busted, Facilities is your go-to. For angry students or general front-of-house inquiries, Customer Service takes the heat. Keep your communications tight, rely strictly on the data provided, and always route the ticket to the right specialist rather than trying to solve it out of your own pocket.
> * Inventory Agent
> You manage the back room and the shelves. Your entire world is stock levels, supply chains, and merchandise tracking. When the Boss or Customer Service asks if we have a specific item or size in stock, you check the database and give a hard yes or no. You are responsible for flagging low stock, logging incoming shipments, and making sure the physical counts match the system. If you notice a discrepancy that affects the money, delegate a heads-up to Accounting. Keep it strictly by the numbers, verify every count against the database, and never guess what is sitting in the boxes.
> * Accounting Agent
> You handle the cash flow, invoices, and financial disputes. If a ticket involves a refund, a double charge, or a vendor invoice, it stops with you. You make sure the math is airtight and every cent is accounted for before authorizing any payouts or adjusting a ledger. If a customer is complaining about a charge, you pull the exact ledger entry and hand the hard facts over to Customer Service so they can handle the conversation. If Facilities needs budget approval for a repair, you run the numbers. Stay sharp, trust the ledger, and do not authorize anything without verifying the database first.
> * Facilities Agent
> You keep the physical store standing and safe. Your jurisdiction covers everything from broken light fixtures and busted locks to cleaning schedules, physical security, and HVAC issues. When the Boss tosses you a ticket about a jammed door or a hazard on the floor, you map out the repair plan, execute the maintenance protocol, and log the resolution. If a repair is going to cost serious cash or requires an outside contractor, you delegate a cost-approval request to Accounting before pulling the trigger. Your focus is strictly on the physical premises; leave the customers and the retail gear to the rest of the crew.
> * Customer Service Agent
> You are the face of the shop and the first line of defense for customer interactions. Your job is to take the heat, de-escalate the situation, and get the customer a straight answer. You do not have direct access to the vault or the back room, so you need to heavily rely on the rest of the team. Delegate stock checks to Inventory and billing issues to Accounting, then take their hard data and package it into a solid, plain-spoken response for the customer. Keep your tone helpful but firm, resolve the ticket efficiently, and never make a promise the rest of the team cannot back up.

> add any tools the agents need to the MCP server so they can work on the open tickets. shop facts come from the MCP server over data/campus_customs_new.db - do not invent a second shopt tools layer that bypasses MCP. wire the agents so the append to output/audit_trail.json as they run: for each agent-loop step, record enough to audit later. append to ths file - do not wipe it each run.
>
> in output/harness.md , list each agent and each MCP tool (including ones you add in this problem) along with which table the tool uses. also add a short safety section: the guardrails a real business would want when agents touch real customers and real money, plus limits that keep token use in check. update mcp_server/README.md so the tool list matches what you have now.

## Problem 6: Plan the Three Tickets

**Prompt:**
> build output/desk_tickets.html - a page that i can double click with one tab per ticker.
>
> on each ticket tab fill and expected section only, leave room for an actual section i will fill in after we run the agents
>
> Based on the assignment parameters, the expected workflow for the agent team on each open ticket involves the following:
>
> * Triage and Delegation: The Boss agent will assess the ticket and delegate it to the appropriate specialist (Inventory, Accounting, Facilities, or Customer Service) using their connected agent loops.
> * Data Retrieval: The assigned specialist will use the established MCP tools to query the `data/campus_customs_new.db` database to pull the relevant facts.
> * Cross-Functional Collaboration: Because the agents have full connectivity, they will delegate work to each other if a ticket spans multiple departments (e.g., Customer Service asking Inventory for a stock check).
> * Factual Resolution: The team will formulate a resolution based entirely on the database records, ensuring they never invent any data.
>
> for each ticket's expected section, write
> * who the boss should call first and why
> * all the agent delegations you expect - not just boss calls everyone
> * which MCP tools expected that run to use
>
> do not just send every specialist on every ticket

**Follow-up prompt(s):**
> Run the agents

> Yes, fill them in _(fill the Actual sections of output/desk_tickets.html from the run)_

> Yes, fix both _(Customer Service leaking internal invoice/pricing details, and reading back-room data through search_database)_

## Problem 7: Backend Routes

**Prompt:**
> the react frontend dashboard (the next problem) needs a backend it can call. in backend/main.py use fastapi and add routes that do the following:
>
> * return the three tickets and whether each is open or resolved
> * take a ticket id and run your agent team on that ticket
> * return recent agent events - what each agent said and which tools they used - so the board can refresh
> * approve a payment or purchase after a human clicks approve (agents only prepare the pay; this route is what actually changes cash)
> * return the current checking balance from cash_accounts
> * reset the database to the original values you want to try a fresh run
>
> from the backend/ folder, start the server with:
>
> uvicorn main:app --reload --port 8000
>
> this turns the backend at http://localhost:8000 so the frontend dashboard can call those routes. in output_harness.md, list each route in one line (what url / what it does)

**Follow-up prompt(s):**
> _(none yet)_

## Problem 8: Agent Dashboard

**Prompt:**
> build the frontend dash in frontend/ with React + Vite + TypeScript. the page should call the routes you built in problem 7. at minimum the board should:
>
> * list all three tickets
> * let you pick one ticket and start the agent team on it
> * show each agent and what they are saying / doing while the ticket runs
> * mark a ticket resolved when the run finishes
> * show a short summary of what each agent did on the ticket
> * let a human approve a pay or purchase when asked
> * show the checking balance (it should drop after an approved par)
>
> make the dashboard look like my campus customs website from HW4, but remmeber this is a real desk people would want to sit at.
>
> tell the frontend to talk to the backend at http://localhost:8020 (or whatever it wound up becoming). on the backend, allow the Vite page origin (usually http://localhost:5173) so the browser is allowed to call those routes.
>
> start the board with:
>
> * npm run dev
>
> write output/design.md with what you chose for the dashbaord look (layout, how agents read differently, how resolved tickets and cash sho up) and why - including the creative choices that make it feel special and something humans would actually enjoy using.

**Follow-up prompt(s):**
> _(none yet)_

## Problem 9: Resolve the Tickets

**Prompt:**
> before testing the agents on a full run, reset the working database data/campus_customs_new.db again so you start clean. note the starting checking balance. then run all three tickets on the board (101 , 102 , 103) until each is resolved. open output/desk_tickets.html from problem 6. on each ticket tab fill the ACTUAL section from this run: which agents works, what why delegated, and which tools they used. keep the expected section so we can compare the two
>
> on the cash tab of the same output/desk_tickets.html, itemize the money:
>
> * staerting checking balance after the reset
> * for each ticket how cash changed when that ticket resolved, and why (which pay / purchase, dollar amount)
> * ending checking balance - it must match cash_accounts in the working database (wrong cash math loses points)
> * output/resolved_tickets.json - for each ticket: id, final status, short outcome, what each agent contributed, and any human approvals
> * output/resolved_board.html - a page yo candouble click with a screenshot of the REACT board for each resolved ticket
>
> append real runs to output/audit_trail.json. Finish routed, the dashboard, and safety rules

**Follow-up prompt(s):**
> _(none yet)_

## Problem 10: Reflection

**Prompt:**
> open output/desk_tickets.html and fill out the reflection tab with the following information:
>
> 1. Overall the team reached the right result on all three tickets. Every number came from the database, no money moved without approval, and the shop's rules held. Checking went from $3,400 to $152, and that matches cash_accounts. How efficiently it got there, and how good its judgment was, varied a lot by ticket.
> 2.
>
> * #101: The first call matched (Inventory). The Inventory → Accounting heads-up I expected happened, the follow-up run requested the $8 PO after invoice 501 was paid, and Facilities was never called. Two things differed. Customer Service added handoffs to Inventory and Accounting that I hadn't planned. And I expected the ticket to end at "awaiting approval" plus a follow-up run, but it took two extra runs and a manager note. One small tool difference: Accounting used `list_invoices` where I expected `get_invoice`.
> * #102: Almost an exact match. The first call was Facilities, the Facilities → Accounting handoff happened, there was one rent approval, and Inventory and Customer Service stayed out. The only extra was the Boss also asking Accounting directly, which was redundant but harmless.
> * #103: The first call (Inventory), the $36.67 floor, the Customer Service → Accounting handoff and "no PO" all matched. The Inventory → Accounting cash heads-up I expected never happened. I think that's exactly why the first quote covered 20 units: nobody told Accounting the restock wasn't affordable. My plan assumed someone would connect the stock shortfall to the cash, and in practice that took a human.
>
> 3. #102 for sure, and honestly most of #101 too. Rent is a straight line: look up the lease, check cash, request the payment. Splitting that across Boss → Facilities → Accounting added handoffs and tokens without improving the decision. One agent with get_lease, get_cash_position and request_payment would have done it in a single loop.
> 4.
>
> * Back-to-school restock planning. "Which SKUs are low before move-in week, and what can we afford to reorder?" Inventory uses `list_inventory`, `check_shortfall` and `plan_restock`. Accounting checks `get_cash_position`, ranks the reorders by margin with `calculate_margin`, and calls `request_purchase_order` only for vendors with `can_ship = true`. * A new overdue invoice from a second vendor. Accounting uses `list_invoices` (with the `overdue` and `days_overdue` fields) and `get_cash_position` to decide which bill to pay first and which vendor to unblock. It prepares `request_payment` for human approval, and the Boss explains the trade-off. * A customer asks "where's my order?" Inventory checks `list_purchase_orders` for the ETA and uses `receive_purchase_order` and `fulfill_from_stock` once the order arrives. Customer Service then writes an accurate update with `draft_customer_message`. This is the natural next step for Tauhid's tee.
>
> 5. Three new problems it could not solve, and what we'd need
>    1. Running out of cash with no way to earn it. We left revenue out of the model, so cash only goes down, and after these tickets checking is at $152. The team can't record a sale, take a deposit for the hoodie order, or forecast cash flow. We'd need:
>       * Tools: `record_sale`, `record_deposit` and `get_sales_history`.
>       * Database: the SQLite trigger that blocks balance increases would have to change to allow deposits.
>       * A new agent: a Sales/Cashier agent that rings up orders. Accounting could then build a cash forecast before approving POs.
>    2. Actually talking to customers and vendors. There's no send tool and no inbox, so drafts just sit on the board. The team also can't read replies, like the Yale AI Club agreeing to buy 8. And it can't negotiate with Bulldog, for example asking for a payment plan or a partial payment. We'd need:
>       * Tools: `read_inbox`, a `send_message` that only sends after a human approves it, and a partial-payment option in `request_payment`.
>       * A new agent: a Communications agent that turns incoming email into tickets and follow-ups.
>    3. Physical maintenance problems, like a leaking roof or a broken heat press at the Chapel Street shop. Facilities can only read leases. It has no record of maintenance contractors, work orders or equipment. We'd need:
>       * Tools: `create_work_order`, `list_service_vendors` and `get_equipment_status`.
>       * Facilities: a cost-approval path to Accounting, which it already uses for rent.
>       * Possibly a rule: that a landlord-responsibility issue goes to the landlord and isn't paid by the shop. That would need the lease terms stored in a structured way rather than as free-text notes.

**Follow-up prompt(s):**
> this is problem #10: Reflection

> here are the questions i answered
>
> _(Attachment: screenshot of the five Reflection questions: evaluate the agents' performance on each ticket and why; how Actual compared to the Expected plan; what would have been simpler as one agent with tools, and why; three new problems the team could solve with the tools built; three new problems it could not solve, and the tools and agents needed.)_

> Tie every answer to this app and the three tickets you ran - use the ticket tabs and cash tab on the same page as your evidence.

> how do i upload this to github repository now?

> put the URL in output/github_url.txt

> Yes, push them
