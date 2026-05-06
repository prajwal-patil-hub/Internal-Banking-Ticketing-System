export type Priority = 'critical' | 'high' | 'medium' | 'low';

export type TicketStatus =
  | 'new' | 'acknowledged' | 'assigned' | 'in_progress' | 'on_hold'
  | 'escalated' | 'resolved' | 'closed' | 'reopened';

export interface TicketSummary {
  id: string;
  ticket_no: string;
  title: string;
  branch_id: string;
  priority: Priority;
  status: TicketStatus;
  sla_due_at: string | null;
  assigned_user_id: string | null;
  created_at: string;
}

export interface TicketDetail extends TicketSummary {
  description: string;
  category_id: string;
  raised_by: string;
  first_response_at: string | null;
  resolved_at: string | null;
  closed_at: string | null;
  reopened_count: number;
  assigned_team_id: string | null;
  updated_at: string;
}

export interface Branch {
  id: string;
  code: string;
  name: string;
  region: string;
  address: string;
  ifsc: string;
  contact_email: string;
  contact_phone: string;
  is_active: boolean;
  created_at: string;
}

export interface Category {
  id: string;
  name: string;
  description: string;
  default_priority: Priority;
  is_active: boolean;
}
