export type User = {
  id: number;
  username: string;
  email: string;
  first_name: string;
  last_name: string;
  is_staff: boolean;
  is_active: boolean;
  role: "admin" | "sales";
};

export type Pipeline = {
  id: number;
  name: string;
  is_default: boolean;
};

export type Stage = {
  id: number;
  pipeline: number;
  pipeline_name?: string;
  name: string;
  order: number;
  is_won: boolean;
  is_lost: boolean;
};

export type Deal = {
  id: number;
  title: string;
  company: number;
  company_name?: string;
  contact_person: string;
  value: string | null;
  currency: string;
  pipeline: number;
  pipeline_name?: string;
  stage: number;
  stage_name?: string;
  owner: number;
  owner_username?: string;
  status: "open" | "won" | "lost";
  expected_close_date: string | null;
  notes: string;
  commission: string | null;
  created_at: string;
  updated_at: string;
};

export type Client = {
  id: number;
  name: string;
  contact_person: string;
  email: string;
  phone: string;
  country: string;
  status: "active" | "inactive";
  notes: string;
  created_at: string;
};

export type Project = {
  id: number;
  title: string;
  client: number;
  client_name?: string;
  type: "branding" | "web" | "dev" | "other";
  status: "lead" | "proposal" | "in_progress" | "delivered" | "paid";
  budget: string | null;
  start_date: string | null;
  deadline: string | null;
  notes: string;
  created_at: string;
};

export type Task = {
  id: number;
  title: string;
  description: string;
  project: number | null;
  project_title?: string;
  client: number | null;
  client_name?: string;
  deal: number | null;
  deal_title?: string;
  due_date: string | null;
  status: "todo" | "doing" | "done";
  created_at: string;
};

export type Activity = {
  id: number;
  type: "call" | "meeting" | "email" | "note";
  content: string;
  client: number | null;
  client_name?: string;
  deal: number | null;
  deal_title?: string;
  project: number | null;
  project_title?: string;
  created_at: string;
};

export type Meeting = {
  id: number;
  title: string;
  description: string;
  start_datetime: string;
  end_datetime: string;
  location: string;
  deal: number | null;
  deal_title?: string;
  company: number | null;
  company_name?: string;
  owner: number;
  owner_name?: string;
  owner_username?: string;
  status: "scheduled" | "completed" | "cancelled";
  created_at: string;
  updated_at: string;
};

export type DashboardStats = {
  scope: "company" | "personal";
  total_open_deals: number;
  total_pipeline_value: number;
  deals_won_this_month: number;
  win_rate: number;
  value_by_stage: Array<{
    stage_id: number;
    stage_name: string;
    count: number;
    value: number;
  }>;
};

export type CommissionSummary = {
  commission_rate_percent: string;
  earned_commission: string;
  potential_commission: string;
  won_deal_value: string;
  open_deal_value: string;
  scope: "company" | "personal";
};

export type LeaderboardRow = {
  rank: number;
  rep_id?: number;
  rep_name: string;
  rep_initials: string;
  is_current_user: boolean;
  open_count?: number;
  won_count?: number;
  won_value?: string;
  open_value?: string;
  potential_commission?: string;
  earned_commission?: string;
};

export type LeaderboardResponse = {
  scope: "company" | "personal";
  period: "this_month" | "all_time";
  commission_rate_percent: string;
  results: LeaderboardRow[];
};

export type AICommandTier = "auto" | "confirm" | "blocked" | "unknown";

export type AICommandDraft = {
  intent: string | null;
  fields: Record<string, unknown>;
  confidence: number;
  missing: string[];
};

export type AICommandOption = { id: number; label: string };

export type AICommandPreview = {
  record?: string;
  field?: string;
  old?: string;
  new?: string;
  changes?: Record<string, { old: string; new: string }>;
};

/** Full contract returned by POST /api/ai/command/ and the confirm endpoint. */
export type AICommandResponse = {
  intent?: string | null;
  tier?: AICommandTier;
  acted?: boolean;
  blocked?: boolean;
  refusal?: string;
  summary?: string;
  reason?: string;
  requires_confirmation?: boolean;
  requires_disambiguation?: boolean;
  needs_review?: boolean;
  missing?: string[];
  options?: Record<string, AICommandOption[]>;
  preview?: AICommandPreview;
  draft?: AICommandDraft;
  understood?: { intent: string | null; fields: Record<string, unknown>; confidence: number; missing: string[] };
  undoable?: boolean;
  action_id?: number;
  changes?: Record<string, { old: string; new: string }>;
  confirmation_id?: string;
  confirmation_expires_at?: string;
  // Error envelope
  detail?: string;
  code?: string;
  error?: string;
};

export type AICommandUndoResponse = {
  undone: boolean;
  action_id: number;
  summary: string;
};

export type SearchResults = {
  clients: Array<{ id: number; name: string; contact_person?: string; email?: string; phone?: string; status: string }>;
  deals: Array<{ id: number; title: string; company_name: string | null; contact_person?: string; owner_username: string | null; status: string; value: string | null }>;
  tasks: Array<{ id: number; title: string; status: string; due_date: string | null; client_name: string | null; deal_title: string | null }>;
  meetings: Array<{ id: number; title: string; status: string; start_datetime: string; company_name: string | null; deal_title: string | null }>;
  activities: Array<{ id: number; type: string; content: string; created_at: string; client_name: string | null; deal_title: string | null }>;
};

export type GlobalSearchResponse = { query: string; results: SearchResults };
