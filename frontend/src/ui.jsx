export const SOURCE = {
  profile: ["From your profile", "c-blue"], knowledge_base: ["Saved answer", "c-green"], ai_generated: ["AI-written", "c-amber"],
  user: ["You answered", "c-green"], prefilled: ["Prefilled by site", "c-grey"], resume_file: ["Your resume", "c-blue"], calculated: ["Calculated from your history", "c-blue"], approved: ["Approved answer", "c-green"],
};
const FLAGS = { calculated: ["Calculated", "c-blue"], sensitive: ["Sensitive", "c-rose"], needs_review: ["Read before approving", "c-amber"], verify_failed: ["Didn’t stick", "c-red"], edited: ["Edited by you", "c-green"], unfilled: ["Not filled", "c-red"] };
const STATUS = { Submitted: "c-green", Failed: "c-red", "Requires Manual Intervention": "c-red", "Waiting for User Input": "c-amber", "Ready for Review": "c-amber", "In Progress": "c-blue", Pending: "c-grey", Cancelled: "c-grey", Paused: "c-amber" };

export const Chip = ({ cls = "c-grey", children }) => <span className={`chip ${cls}`}>{children}</span>;
export const StatusChip = ({ status }) => <Chip cls={STATUS[status] || "c-grey"}>{status}</Chip>;
export const SourceChip = ({ source }) => (source && SOURCE[source] ? <Chip cls={SOURCE[source][1]}>{SOURCE[source][0]}</Chip> : null);
export const FlagChips = ({ flags = [] }) => flags.filter((f) => FLAGS[f]).map((f) => <Chip key={f} cls={FLAGS[f][1]}>{FLAGS[f][0]}</Chip>);
export const when = (d) => (d ? new Date(d).toLocaleString([], { dateStyle: "medium", timeStyle: "short" }) : "");
export const host = (u) => { try { return new URL(u).hostname.replace(/^www\./, ""); } catch { return u; } };
export const Field = ({ label, children }) => <label className="fld"><span>{label}</span>{children}</label>;

export const norm = (s) => String(s || "").toLowerCase().replace(/[^a-z0-9 ]/g, " ").replace(/\s+/g, " ").trim();
const FACT = { user_confirmed: ["Confirmed", "c-green"], approved: ["Approved", "c-green"], calculated: ["Calculated", "c-blue"], user_entered: ["Typed, not confirmed", "c-amber"],
  resume_link: ["From resume link", "c-amber"], resume: ["From resume", "c-amber"], unverified: ["Unverified", "c-amber"], missing: ["Missing", "c-grey"] };
export function FactChip({ meta, empty }) {
  if (empty) return <Chip cls="c-grey">Missing</Chip>;
  if (!meta) return <Chip cls="c-amber">Unverified</Chip>;
  const [l, c] = FACT[meta.source] || ["Unverified", "c-amber"];
  return <Chip cls={c}>{l} {Math.round((meta.confidence || 0) * 100)}%</Chip>;
}
