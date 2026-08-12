/**
 * Describes the screen the user is on, so the assistant can answer questions
 * about it.
 *
 * The widget previously sent a ticket id and only on ticket pages, which left
 * the assistant blind everywhere else — asked "what's on this page?" from the
 * SLA monitor it had nothing to work with. This maps a route to a human label
 * plus whatever identifiers the backend needs to look the data up.
 *
 * Deliberately no page *contents* are sent, only identifiers and filters. The
 * server re-reads the data itself under the user's own permissions, so the
 * client cannot widen what the assistant is allowed to see by lying about what
 * is on screen.
 */

export interface PageContext {
  route: string;
  label: string;
  details?: Record<string, string | number | boolean>;
}

/** Ticket detail routes carry the id the server needs to load the ticket. */
export function ticketIdFromPath(pathname: string): string | undefined {
  return pathname.match(/^\/tickets\/([0-9a-fA-F-]{36})$/)?.[1];
}

const STATIC_LABELS: Array<[RegExp, string]> = [
  [/^\/dashboard/, 'Dashboard — overview of ticket volume and SLA health'],
  [/^\/tickets\/new/, 'Create Ticket — raising a new ticket'],
  [/^\/tickets\/[0-9a-fA-F-]{36}$/, 'Ticket Detail'],
  [/^\/tickets/, 'Tickets — the ticket list'],
  [/^\/sla/, 'SLA Monitor — breached, at-risk and on-time tickets'],
  [/^\/escalations/, 'Escalations — escalated tickets, rules and event log'],
  [/^\/org/, 'Org Hierarchy — units, levels and roles'],
  [/^\/users/, 'Users — the staff directory'],
  [/^\/reports/, 'Reports — charts, KPIs and downloadable reports'],
  [/^\/audit/, 'Audit Log — immutable record of every change'],
  [/^\/security/, 'Security — two-factor authentication for your account'],
];

export function describePage(pathname: string, search = ''): PageContext {
  const label = STATIC_LABELS.find(([re]) => re.test(pathname))?.[1] ?? 'Unknown page';

  const details: Record<string, string> = {};
  // Active filters live in the query string on the list pages; they are what
  // makes "how many of these are breached?" answerable.
  new URLSearchParams(search).forEach((value, key) => {
    if (value) details[key] = value;
  });

  return {
    route: pathname,
    label,
    ...(Object.keys(details).length ? { details } : {}),
  };
}
