import { useCallback, useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import { API_URL, AuthError, api, deskPassword, type AgentEvent, type AgentKey, type Approval, type Board, type Cash, type Health, type Message, type Ticket } from "./api";
import { PERSONAS, TEAM, busyAgents, crewReport, latestRun, money, plain, toolVerb } from "./agents";
import Bulldog from "./Bulldog";

const STATUS_LABEL: Record<Ticket["status"], string> = {
  open: "Open",
  in_progress: "Crew working",
  awaiting_approval: "Needs your signature",
  needs_human: "Needs you",
  resolved: "Resolved",
};
const TYPE_LABEL: Record<string, string> = { customer_order: "Customer order", rent_notice: "Rent notice", price_override: "Price override" };
const prettyDate = (iso: string) =>
  iso ? new Date(iso + "T12:00:00").toLocaleDateString("en-US", { weekday: "short", month: "short", day: "numeric", year: "numeric" }) : "…";

type Act = (fn: () => Promise<unknown>, ok?: string) => Promise<void>;

export default function App() {
  const [tickets, setTickets] = useState<Ticket[]>([]);
  const [events, setEvents] = useState<AgentEvent[]>([]);
  const [approvals, setApprovals] = useState<Approval[]>([]);
  const [cash, setCash] = useState<Cash | null>(null);
  const [board, setBoard] = useState<Board | null>(null);
  const [health, setHealth] = useState<Health | null>(null);
  // ?ticket=101 opens that ticket directly (handy for links and screenshots); selection updates the URL.
  const [selected, setSelectedState] = useState<number | null>(() => Number(new URLSearchParams(location.search).get("ticket")) || null);
  const setSelected = useCallback((id: number) => {
    setSelectedState(id);
    try { history.replaceState(null, "", `?ticket=${id}`); } catch { /* file:// or sandboxed */ }
  }, []);
  const [offline, setOffline] = useState<string | null>(null);
  const [toast, setToast] = useState<{ text: string; bad?: boolean } | null>(null);
  // Hosted desks ask for a password; "wrong" means we tried one and the server said no.
  const [login, setLogin] = useState<null | "ask" | "wrong">(null);
  const lastId = useRef(0);

  const refresh = useCallback(async () => {
    try {
      const [t, a, c, b] = await Promise.all([api.tickets(), api.approvals(), api.cash(), api.board()]);
      setTickets(t);
      setApprovals(a);
      setCash(c);
      setBoard(b);
      const fresh = await api.events(lastId.current);
      if (fresh.length) {
        lastId.current = Math.max(lastId.current, fresh[fresh.length - 1].id);
        setEvents((prev) => {
          const seen = new Set(prev.map((e) => e.id));
          return [...prev, ...fresh.filter((e) => !seen.has(e.id))];
        });
      }
      setOffline(null);
      setLogin(null);
    } catch (e) {
      if (e instanceof AuthError) {
        setOffline(null);
        setLogin(deskPassword.get() ? "wrong" : "ask");
      } else {
        setOffline((e as Error).message);
      }
    }
  }, []);

  useEffect(() => {
    refresh();
    const loadHealth = () => api.health().then(setHealth).catch(() => setHealth(null));
    loadHealth();
    const t = setInterval(refresh, 1500);
    const h = setInterval(loadHealth, 20000);
    return () => { clearInterval(t); clearInterval(h); };
  }, [refresh]);

  useEffect(() => {
    if (tickets.length && (selected == null || !tickets.some((t) => t.id === selected))) setSelectedState(tickets[0].id);
  }, [tickets, selected]);

  useEffect(() => {
    if (!toast) return;
    const t = setTimeout(() => setToast(null), 5500);
    return () => clearTimeout(t);
  }, [toast]);

  const act: Act = useCallback(async (fn, ok) => {
    try {
      const r = (await fn()) as { effect?: string } | undefined;
      setToast({ text: r?.effect ?? ok ?? "Done." });
      await refresh();
    } catch (e) {
      if (e instanceof AuthError) setLogin(deskPassword.get() ? "wrong" : "ask");
      else setToast({ text: (e as Error).message, bad: true });
    }
  }, [refresh]);

  const signIn = (pw: string) => {
    deskPassword.set(pw);
    refresh();
  };
  const signOut = () => {
    deskPassword.clear();
    setLogin("ask");
  };

  const current = board?.worker.current ?? null;
  const busy = current != null || (board?.worker.queued.length ?? 0) > 0;
  const runningRun = useMemo(() => (current != null ? latestRun(events, current) : []), [events, current]);
  const busyNow = useMemo(() => busyAgents(runningRun, current != null), [runningRun, current]);
  const ticket = tickets.find((t) => t.id === selected) ?? null;
  const pending = approvals.filter((a) => a.status === "pending");

  const reset = () => {
    if (!confirm("Start fresh? This restores the original shop data: all tickets open, $3,400 in checking, no approvals or drafts.")) return;
    act(async () => {
      await api.reset();
      lastId.current = 0;
      setEvents([]);
    }, "Fresh start: the shop is back to its original data.");
  };

  return (
    <div className="desk">
      <div className="netscape">
        <div className="titlebar">
          <Bulldog size={18} face="#fff" ink="#00356b" />
          <span>Campus Customs Online — Back Office</span>
          <span className="winbtns" aria-hidden><i>_</i><i>□</i><i>×</i></span>
        </div>
        <div className="toolbar">
          <div className="location"><b>Location:</b> <code>{API_URL || location.origin}/api</code></div>
          <span className={`led ${offline ? "bad" : health?.mcp_ok ? "good" : "bad"}`}>{offline ? "Backend offline" : health?.mcp_ok ? "MCP online" : "MCP offline"}</span>
          <span className="led good">{health?.model ?? "gpt-6-luna"}</span>
          <span className="calendar" title="The shop's 'today' (desk.date_today)">📅 Shop date: <b>{prettyDate(board?.date_today ?? "")}</b></span>
          <button className="w95" onClick={reset} disabled={busy} title={busy ? "Wait for the crew to finish" : "Restore the original data"}>↺ Fresh start</button>
          {health?.auth_required && <button className="w95" onClick={signOut}>🔒 Sign out</button>}
        </div>
      </div>

      {offline && <div className="banner bad" role="alert">⚠️ {offline}</div>}

      <main className="grid">
        <section className="col left" aria-label="Ticket inbox">
          <Win title={`Inbox — ${tickets.length} tickets`} icon="📥">
            <ul className="inbox">
              {tickets.map((t) => (
                <li key={t.id}>
                  <button className={`row ${t.id === selected ? "on" : ""} st-${t.status}`} onClick={() => setSelected(t.id)}
                    aria-current={t.id === selected ? "true" : undefined}>
                    <span className="num">#{t.id}</span>
                    <span className="what">
                      <b>{t.subject}</b>
                      <small>{t.requester} · {TYPE_LABEL[t.type] ?? t.type}</small>
                    </span>
                    <span className={`pill p-${t.status}`}>{t.queued ? "Queued" : STATUS_LABEL[t.status]}</span>
                    {t.state === "resolved" && <span className="stamp small" aria-hidden>RESOLVED</span>}
                  </button>
                </li>
              ))}
              {!tickets.length && !offline && <li className="muted pad">Loading tickets…</li>}
            </ul>
          </Win>
          <Outbox messages={board?.messages ?? []} act={act} />
        </section>

        <section className="col mid" aria-label="Case file">
          {ticket ? (
            <CaseFile ticket={ticket} events={events} busy={busy} current={current} approvals={approvals} act={act} />
          ) : (
            <Win title="Case file" icon="🗂️"><p className="pad muted">Pick a ticket from the inbox.</p></Win>
          )}
        </section>

        <section className="col right" aria-label="Team and money">
          <BuddyList busyNow={busyNow} runEvents={runningRun} current={current} />
          <CashRegister cash={cash} payments={board?.payments ?? []} />
          <Signatures pending={pending} cash={cash} act={act} />
        </section>
      </main>

      <footer className="foot">
        <span className="badge88">Best viewed at a desk with coffee</span>
        <span className="badge88">Agents draft · <b>You</b> sign</span>
        <span className="badge88" title="Handsome Dan disabled this one for good.">🚫 Harvard Mode: disabled</span>
      </footer>

      {login && <SignIn wrong={login === "wrong"} onSubmit={signIn} />}

      {toast && <div className={`toast ${toast.bad ? "bad" : ""}`} role="status">{toast.bad ? "⚠️ " : "✅ "}{toast.text}</div>}
    </div>
  );
}

function SignIn({ wrong, onSubmit }: { wrong: boolean; onSubmit: (pw: string) => void }) {
  const [pw, setPw] = useState("");
  useEffect(() => { if (wrong) setPw(""); }, [wrong]);
  return (
    <div className="modal" role="dialog" aria-modal="true" aria-labelledby="signin-title">
      <form className="win signin" onSubmit={(e) => { e.preventDefault(); if (pw) onSubmit(pw); }}>
        <div className="win-title"><span className="win-icon" aria-hidden>🔒</span><h2 id="signin-title">Campus Customs Online — Staff sign-in</h2></div>
        <div className="win-body">
          <div className="signin-row">
            <Bulldog size={56} title="Handsome Dan" />
            <div>
              <p><b>This is the back office.</b> Enter the desk password to watch the crew, run tickets and sign for payments.</p>
              <label htmlFor="desk-pw" className="small">Desk password</label>
              <input id="desk-pw" className="sunken" type="password" autoFocus autoComplete="current-password"
                value={pw} onChange={(e) => setPw(e.target.value)} />
              {wrong && <p className="bad small" role="alert">⚠️ That password didn't work. Try again.</p>}
            </div>
          </div>
          <div className="signin-actions"><button className="w95 primary" type="submit" disabled={!pw}>Sign in ➤</button></div>
        </div>
      </form>
    </div>
  );
}

function Win({ title, icon, children, className = "", extra }: { title: string; icon: ReactNode; children: ReactNode; className?: string; extra?: ReactNode }) {
  return (
    <div className={`win ${className}`}>
      <div className="win-title"><span className="win-icon" aria-hidden>{icon}</span><h2>{title}</h2>{extra}</div>
      <div className="win-body">{children}</div>
    </div>
  );
}

function Avatar({ agent, size = 26 }: { agent: AgentKey; size?: number }) {
  const p = PERSONAS[agent];
  return (
    <span className="avatar" style={{ ["--c" as string]: p.color, width: size, height: size }} aria-hidden>
      {p.icon === "dan" ? <Bulldog size={size - 6} ink={p.color} /> : <span style={{ fontSize: size * 0.55 }}>{p.icon}</span>}
    </span>
  );
}

const Who = ({ agent }: { agent: AgentKey }) => (
  <b className="who" style={{ color: PERSONAS[agent]?.color }}>{PERSONAS[agent]?.screen ?? agent}</b>
);

/* ------------------------------------------------------------------ case file */

function CaseFile({ ticket, events, busy, current, approvals, act }: {
  ticket: Ticket; events: AgentEvent[]; busy: boolean; current: number | null; approvals: Approval[]; act: Act;
}) {
  const [note, setNote] = useState("");
  const run = useMemo(() => latestRun(events, ticket.id), [events, ticket.id]);
  // Everything that happened on this ticket: every crew run (first pass and follow-ups) plus your approvals.
  const history = useMemo(() => events.filter((e) => e.ticket_id === ticket.id), [events, ticket.id]);
  const allRuns = useMemo(() => history.filter((e) => e.run_id), [history]);
  const running = current === ticket.id;
  const decision = run.find((e) => e.kind === "decision");
  const waiting = approvals.filter((a) => a.ticket_id === ticket.id && a.status === "pending").length;
  const canRun = ticket.status !== "resolved" && !running && !ticket.queued;

  const facts: [string, string][] = [
    ["Requester", ticket.requester],
    ["Type", TYPE_LABEL[ticket.type] ?? ticket.type],
  ];
  if (ticket.sku) facts.push(["Item", `${ticket.sku}${ticket.size ? ` · size ${ticket.size}` : ""}${ticket.qty != null ? ` · qty ${ticket.qty}` : ""}`]);
  if (ticket.invoice_id) facts.push(["Linked invoice", `#${ticket.invoice_id}`]);
  if (ticket.lease_id) facts.push(["Linked lease", `#${ticket.lease_id}`]);

  return (
    <>
      <Win title={`Case file — Ticket #${ticket.id}`} icon="🗂️" className="casefile">
        <div className="case-head">
          <div>
            <h1 className="wordart">{ticket.subject}</h1>
            <p className="note-line">“{(ticket.notes ?? "").split("\n")[0]}”</p>
          </div>
          {ticket.state === "resolved" ? <span className="stamp big">RESOLVED</span>
            : ticket.status === "awaiting_approval" ? <span className="sticky">Needs your<br />signature ✍️</span>
            : ticket.status === "needs_human" ? <span className="sticky">Needs you 👋</span> : null}
        </div>
        <dl className="facts">
          {facts.map(([k, v]) => <div key={k}><dt>{k}</dt><dd>{v}</dd></div>)}
          <div><dt>Status</dt><dd><span className={`pill p-${ticket.status}`}>{ticket.queued ? "Queued" : STATUS_LABEL[ticket.status]}</span></dd></div>
        </dl>

        <div className="run-box">
          <label className="sr-only" htmlFor="note">Optional note for the Boss</label>
          <input id="note" className="sunken" value={note} onChange={(e) => setNote(e.target.value)}
            placeholder="Optional note for the Boss, e.g. “cap any discount at 25%”" disabled={!canRun} />
          <button className="w95 primary" disabled={!canRun}
            onClick={() => { act(() => api.runTicket(ticket.id, note), `Ticket #${ticket.id} is with the crew.`); setNote(""); }}>
            {running ? "Crew is working…" : ticket.queued ? "Queued…" : ticket.status === "resolved" ? "Resolved ✔" : run.length ? "Run the crew again ➤" : "Send to the crew ➤"}
          </button>
        </div>
        {busy && !running && canRun && <p className="muted small pad-x">Another ticket is being worked; this one will start right after.</p>}
        {waiting > 0 && <p className="callout">✍️ {waiting} request{waiting > 1 ? "s" : ""} on this ticket {waiting > 1 ? "are" : "is"} waiting for your signature (Sign Here, right column).</p>}
      </Win>

      {decision && !running && <CrewReport runs={allRuns} decision={decision} />}

      <Transcript events={history} running={running} ticketId={ticket.id} />
    </>
  );
}

const summarize = (text: string) => {
  const t = plain(text).replace(/\s+/g, " ").trim();
  if (t.length <= 260) return t;
  const cut = t.slice(0, 260);
  return cut.slice(0, cut.lastIndexOf(" ")) + "…";
};

function CrewReport({ runs, decision }: { runs: AgentEvent[]; decision: AgentEvent }) {
  // Summarizes every run on the ticket; the Boss's call shown is the latest one.
  const lines = crewReport(runs);
  const c = decision.content;
  const decisions = runs.filter((e) => e.kind === "decision");
  const handoffs = runs.filter((e) => e.kind === "delegate").length;
  const tokens = decisions.reduce((s, e) => s + Number(e.content.ticket_tokens ?? 0), 0);
  return (
    <Win title="Crew report" icon="📋" className="report"
      extra={<span className="report-meta">{decisions.length} run{decisions.length === 1 ? "" : "s"} · {handoffs} handoffs · {tokens.toLocaleString()} tokens</span>}>
      <div className="bosscall">
        <Avatar agent="boss" size={44} />
        <div>
          <div className="eyebrow">The Boss's call · <span className={`pill p-${c.outcome}`}>{STATUS_LABEL[c.outcome as Ticket["status"]] ?? c.outcome}</span></div>
          <p className="call">{plain(String(c.decision ?? ""))}</p>
        </div>
      </div>
      <ul className="crew">
        {lines.filter((l) => l.agent !== "boss").map((l) => (
          <li key={l.agent} style={{ ["--c" as string]: PERSONAS[l.agent].color }}>
            <Avatar agent={l.agent} />
            <div>
              <div className="crew-name"><Who agent={l.agent} /> <span className="muted small">{PERSONAS[l.agent].role}</span>
                {l.made.map((m) => <span key={m} className="made">{m}</span>)}</div>
              <p className="said">{summarize(l.said) || <span className="muted">No written reply.</span>}</p>
              <p className="muted small">
                {l.askedBy.length > 0 && <>Asked by {l.askedBy.map((a) => PERSONAS[a].role).join(", ")}. </>}
                {l.askedOthers.length > 0 && <>Asked {l.askedOthers.map((a) => PERSONAS[a].role).join(", ")} for help. </>}
                Tools: {l.tools.map(([t, n]) => `${t}${n > 1 ? ` ×${n}` : ""}`).join(", ") || "none"}
              </p>
            </div>
          </li>
        ))}
      </ul>
    </Win>
  );
}

function Transcript({ events, running, ticketId }: { events: AgentEvent[]; running: boolean; ticketId: number }) {
  const [showTools, setShowTools] = useState(true);
  const box = useRef<HTMLDivElement>(null);
  const busy = useMemo(() => busyAgents(events, running), [events, running]);
  const shown = events
    .filter((e) => e.kind !== "tool_result" || e.content.ok === false)
    .filter((e) => showTools || e.kind !== "tool_call");
  const typing = [...busy].filter((a) => a !== "boss" || busy.size === 1);

  useEffect(() => {
    const el = box.current; // follow the newest line, but never scroll the page itself
    if (el && el.scrollHeight - el.scrollTop - el.clientHeight < 220) el.scrollTo({ top: el.scrollHeight });
  }, [shown.length, typing.length]);

  return (
    <Win title={`Instant Messages — Ticket #${ticketId}`} icon="💬" className="aim"
      extra={<label className="toggle"><input type="checkbox" checked={showTools} onChange={(e) => setShowTools(e.target.checked)} /> show tool use</label>}>
      <div className="im" ref={box} aria-live="polite">
        {!shown.length && <p className="muted pad">No conversation yet. Send the ticket to the crew and watch them work it out here.</p>}
        {shown.map((e) => <ImLine key={e.id} e={e} />)}
        {typing.map((a) => (
          <p key={a} className="typing"><Who agent={a} /> is typing<span className="dots"><i>.</i><i>.</i><i>.</i></span></p>
        ))}
      </div>
    </Win>
  );
}

function ImLine({ e }: { e: AgentEvent }) {
  const c = e.content;
  const time = new Date(e.created_at.endsWith("Z") ? e.created_at : e.created_at + "Z")
    .toLocaleTimeString([], { hour: "numeric", minute: "2-digit", second: "2-digit" });
  const to = PERSONAS[c.to as AgentKey]?.screen ?? c.to;
  switch (e.kind) {
    case "run_started":
      return <p className="sys">*** {PERSONAS.boss.screen} picked up the ticket · {time} ***</p>;
    case "tool_call":
      return <p className="act"><Who agent={e.agent} /> {toolVerb(c.tool)} <code>{c.tool}</code></p>;
    case "tool_result":
      return <p className="act bad">⚠️ <Who agent={e.agent} />'s <code>{c.tool}</code> was refused: {String(c.result).replace(/^Error executing tool \w+: /, "").slice(0, 220)}</p>;
    case "delegate":
      return (
        <div className="msg" style={{ ["--c" as string]: PERSONAS[e.agent].color }}>
          <span className="stamp-time">{time}</span><Who agent={e.agent} /> <span className="to">→ {to}</span>: {String(c.task)}
        </div>
      );
    case "reply":
      return (
        <div className="msg reply" style={{ ["--c" as string]: PERSONAS[e.agent].color }}>
          <span className="stamp-time">{time}</span><Who agent={e.agent} /> <span className="to">→ {to}</span>: {plain(String(c.text))}
        </div>
      );
    case "decision":
      return (
        <div className="msg final">
          <Who agent="boss" /> <b>made the call</b> ({STATUS_LABEL[c.outcome as Ticket["status"]] ?? c.outcome}): {plain(String(c.decision))}
        </div>
      );
    case "human":
      return (
        <p className="sys human">✍️ You {String(c.action).replace("message_", "")} {c.approval_id ? `#${c.approval_id}` : c.message_id ? `draft #${c.message_id}` : ""} — {c.effect ?? c.summary}</p>
      );
    case "error":
      return <p className="act bad">⚠️ <Who agent={e.agent} /> hit a snag: {String(c.message).slice(0, 220)}</p>;
    default:
      return null;
  }
}

/* ------------------------------------------------------------------ right column */

function BuddyList({ busyNow, runEvents, current }: { busyNow: Set<AgentKey>; runEvents: AgentEvent[]; current: number | null }) {
  const last: Partial<Record<AgentKey, AgentEvent>> = {};
  for (const e of runEvents) if (e.kind === "tool_call" || e.kind === "delegate" || e.kind === "reply") last[e.agent] = e;
  const doing = (a: AgentKey) => {
    const e = last[a];
    if (!e) return "getting started…";
    if (e.kind === "tool_call") return `${toolVerb(e.content.tool)}…`;
    if (e.kind === "delegate") return `asked ${PERSONAS[e.content.to as AgentKey]?.role}…`;
    return `replied to ${PERSONAS[e.content.to as AgentKey]?.role}`;
  };
  const groups: [string, AgentKey[]][] = [
    ["On the clock", TEAM.filter((a) => busyNow.has(a))],
    ["Standing by", TEAM.filter((a) => !busyNow.has(a))],
  ];
  return (
    <Win title="Buddy List — The Crew" icon={<Bulldog size={16} face="#fff" ink="#00356b" />} className="buddies"
      extra={current != null ? <span className="live"><span className="dot" />on #{current}</span> : undefined}>
      {groups.map(([label, list]) => (
        <div key={label}>
          <div className="group">▾ {label} ({list.length}/{TEAM.length})</div>
          {list.map((a) => (
            <div key={a} className={`buddy ${busyNow.has(a) ? "busy" : ""}`} style={{ ["--c" as string]: PERSONAS[a].color }}>
              <Avatar agent={a} />
              <div>
                <div><Who agent={a} /> <span className="muted small">{PERSONAS[a].role}</span></div>
                <div className="away">{busyNow.has(a) ? doing(a) : <i>{PERSONAS[a].away}</i>}</div>
              </div>
            </div>
          ))}
        </div>
      ))}
    </Win>
  );
}

function useRolling(target: number | null) {
  const [shown, setShown] = useState(target);
  const from = useRef(target);
  useEffect(() => {
    if (target == null) return;
    const start = from.current ?? target;
    from.current = target;
    if (start === target || window.matchMedia("(prefers-reduced-motion: reduce)").matches) { setShown(target); return; }
    const t0 = performance.now();
    let raf = 0;
    const step = (now: number) => {
      const k = Math.min(1, (now - t0) / 1400);
      setShown(start + (target - start) * (1 - Math.pow(1 - k, 3)));
      if (k < 1) raf = requestAnimationFrame(step);
    };
    raf = requestAnimationFrame(step);
    return () => cancelAnimationFrame(raf);
  }, [target]);
  return shown;
}

function CashRegister({ cash, payments }: { cash: Cash | null; payments: Board["payments"] }) {
  const shown = useRolling(cash?.balance ?? null);
  const [drop, setDrop] = useState<{ amount: number; key: number } | null>(null);
  const prev = useRef<number | null>(null);
  useEffect(() => {
    if (cash == null) return;
    if (prev.current != null && cash.balance < prev.current) setDrop({ amount: prev.current - cash.balance, key: Date.now() });
    prev.current = cash.balance;
  }, [cash]);
  const low = cash != null && cash.cash_after_all_pending < 500;
  return (
    <Win title="Cash Register — Checking" icon="💵" className="register">
      <div className="lcd" role="status" aria-label={`Checking balance ${money(cash?.balance)}`}>
        <span className="lcd-label">CHECKING · AS OF {cash?.as_of ?? ""}</span>
        <span className="lcd-value">{money(shown)}</span>
        {drop && <span key={drop.key} className="drop" aria-hidden>−{money(drop.amount)}</span>}
      </div>
      {cash && (
        <p className={`after ${low ? "low" : ""}`}>
          {cash.pending_cash_out > 0
            ? <>If you sign everything waiting: <b>{money(cash.cash_after_all_pending)}</b> left ({money(cash.pending_cash_out)} going out).</>
            : <>Nothing waiting to go out. No revenue is modeled, so cash only goes down.</>}
        </p>
      )}
      <div className="tape" aria-label="Payments made">
        <div className="tape-head">— RECEIPT TAPE —</div>
        {!payments.length && <div className="tape-row muted">No payments yet.</div>}
        {payments.map((p) => (
          <div key={p.id} className="tape-row">
            <span>{p.paid_at} · {p.kind === "purchase_order" ? "PO" : p.kind} #{p.ref_id}</span>
            <span>−{money(p.amount)}</span>
            <span className="paid">PAID</span>
          </div>
        ))}
      </div>
    </Win>
  );
}

function Signatures({ pending, cash, act }: { pending: Approval[]; cash: Cash | null; act: Act }) {
  const [signing, setSigning] = useState<number | null>(null);
  const balance = cash?.balance ?? 0;
  const icon = { payment: "💸", purchase_order: "📦", discount: "🏷️" } as const;
  const sign = async (a: Approval, decision: "approved" | "rejected") => {
    setSigning(a.id);
    await act(() => api.decide(a.id, decision), decision === "rejected" ? `Rejected request #${a.id}.` : undefined);
    setSigning(null);
  };
  return (
    <Win title={`Sign Here — ${pending.length} waiting`} icon="✍️" className={`sign ${pending.length ? "has" : ""}`}>
      {!pending.length && (
        <p className="muted pad">Nothing to sign. The agents can only <i>prepare</i> payments, purchase orders and discounts. Nothing moves until you approve it here.</p>
      )}
      {pending.map((a) => {
        const after = balance - (a.kind === "discount" ? 0 : a.amount ?? 0);
        return (
          <div key={a.id} className={`check ${signing === a.id ? "signing" : ""}`}>
            <div className="check-top">
              <span className="kind">{icon[a.kind]} {a.kind.replace("_", " ")}</span>
              <span className="muted small">#{a.id} · ticket {a.ticket_id} · by {PERSONAS[a.requested_by as AgentKey]?.role ?? a.requested_by}</span>
            </div>
            <p className="memo">{a.summary}</p>
            <div className="check-line">
              <span className="amount">{money(a.amount)}</span>
              {a.kind === "discount"
                ? <span className="muted small">Locks in the quote; no cash moves.</span>
                : after < 0
                  ? <span className="bad small">Not enough cash; this will be refused.</span>
                  : <span className={`small ${after < 500 ? "low" : "muted"}`}>Checking after: {money(after)}</span>}
            </div>
            <div className="sig">
              <span className="x" aria-hidden>✗</span><span className="sigline" aria-hidden />
              <button className="w95 primary" disabled={signing != null} onClick={() => sign(a, "approved")}>Approve</button>
              <button className="w95" disabled={signing != null} onClick={() => sign(a, "rejected")}>Reject</button>
            </div>
          </div>
        );
      })}
    </Win>
  );
}

function Outbox({ messages, act }: { messages: Message[]; act: Act }) {
  const visible = messages.filter((m) => m.status !== "discarded");
  if (!visible.length) return null;
  const drafts = visible.filter((m) => m.status === "draft").length;
  return (
    <Win title={`Outbox — ${drafts} draft${drafts === 1 ? "" : "s"}`} icon="✉️" className="outbox">
      <p className="muted small pad-x">Drafts are never emailed. They wait here for you.</p>
      {visible.map((m) => (
        <details key={m.id} className="draft" open={m.status === "draft"}>
          <summary><b>{m.subject}</b> <span className="muted small">→ {m.recipient} · #{m.ticket_id}</span>
            {m.status === "approved" && <span className="pill p-resolved">approved</span>}</summary>
          <p className="draft-body">{m.body}</p>
          {m.status === "draft" && (
            <div className="row-btns">
              <button className="w95" onClick={() => act(() => api.message(m.id, "approve"), `Draft #${m.id} approved (not emailed).`)}>Approve draft</button>
              <button className="w95" onClick={() => act(() => api.message(m.id, "discard"), `Draft #${m.id} discarded.`)}>Discard</button>
            </div>
          )}
        </details>
      ))}
    </Win>
  );
}
