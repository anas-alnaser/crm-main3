export type User = {
  id: number;
  username: string;
  email: string;
  first_name: string;
  last_name: string;
  is_staff: boolean;
  is_superuser: boolean;
  is_active: boolean;
  role: "admin" | "sales";
};

// --- Danger zone: permanent delete + full reset ---
export type LeadDeleteImpact = {
  lead_id: number;
  name: string;
  status: LeadStatus;
  status_display: string;
  is_converted: boolean;
  contact_attempt_count: number;
  deletion_allowed: boolean;
  blocked_reason: string | null;
  confirmation_phrase: string;
};

export type CompanyDeleteImpact = {
  client_id: number;
  name: string;
  is_archived: boolean;
  impact: {
    deals: number;
    projects: number;
    tasks: number;
    activities: number;
    meetings: number;
    documents: number;
    converted_leads: number;
  };
  cascade_delete_count: number;
  dependencies_exist: boolean;
  confirmation_phrase: string;
};

export type UserDeleteImpact = {
  user_id: number;
  username: string;
  role: "admin" | "sales";
  is_active: boolean;
  is_self: boolean;
  impact: Record<string, number | boolean>;
  protect_blockers: string[];
  deletion_allowed: boolean;
  blocked_reason: string | null;
  confirmation_phrase: string;
};

export type ResetPreview = {
  preserved_user: { id: number; username: string; email: string };
  counts: Record<string, number>;
  other_users_to_delete: number;
  total_rows: number;
  preserved_config: { legal_entities: string[]; brands: string[] };
  preview_token: string;
  preview_expires_at: string;
  confirmation_phrase: string;
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
  closed_at: string | null;
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
  created_by: number | null;
  created_by_username?: string;
  is_archived: boolean;
  archived_at: string | null;
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
  created_by: number | null;
  created_by_username?: string;
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
  created_by: number | null;
  created_by_username?: string;
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
  created_by: number | null;
  created_by_username?: string;
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

// --- Workforce / shift ---
export type ShiftTotals = {
  date: string;
  credited_seconds: number;
  credited_display: string;
  target_seconds: number;
  target_display: string;
  remaining_seconds: number;
  remaining_display: string;
  overtime_seconds: number;
  overtime_display: string;
  session_count: number;
};

export type ShiftStatus = {
  shift_tracking_required: boolean;
  on_shift: boolean;
  server_time: string;
  local_time: string;
  today: string;
  reason: string;
  can_start: boolean;
  totals: ShiftTotals;
  policy?: {
    timezone: string;
    earliest_start_time: string;
    latest_end_time: string;
    daily_target_minutes: number;
    working_days: number[];
    working_day_labels: string[];
    overtime_allowed: boolean;
  };
  window?: { is_working_day: boolean; start_time: string; end_time: string };
  session?: {
    id: number;
    started_at: string;
    last_activity_at: string;
    work_date: string;
    current_session_seconds: number;
    current_session_display: string;
  };
  last_auto_closure?: { reason: string; reason_display: string; ended_at: string };
};

export type ShiftEndPreview = {
  employee_name: string;
  message: string;
  current_session_seconds: number;
  current_session_display: string;
  credited_seconds_today: number;
  credited_display_today: string;
  target_display: string;
  remaining_display: string;
  overtime_display: string;
  session_count: number;
};

export type WorkPolicy = {
  id: number;
  user: number;
  username: string;
  employee_name: string;
  shift_tracking_required: boolean;
  is_active: boolean;
  timezone: string;
  working_days: number[];
  working_day_labels: string[];
  earliest_start_time: string;
  latest_end_time: string;
  daily_target_minutes: number;
  monthly_target_minutes: number | null;
  basic_salary: string | null;
  salary_currency: string;
  overtime_allowed: boolean;
};

// --- Leads ---
export type LeadStatus = "new" | "contacted" | "no_answer" | "follow_up" | "interested" | "not_interested" | "converted";

export type Lead = {
  id: number;
  batch: number | null;
  name: string;
  original_phone: string;
  normalized_phone: string;
  source: string;
  notes: string;
  assigned_to: number | null;
  assigned_to_name: string | null;
  status: LeadStatus;
  status_display: string;
  is_terminal: boolean;
  follow_up_at: string | null;
  first_viewed_at: string | null;
  converted_client: number | null;
  converted_deal: number | null;
  converted_at: string | null;
  reopened_reason: string;
  contact_attempt_count: number;
  created_at: string;
};

export type LeadContactAttempt = {
  id: number;
  lead: number;
  employee: number | null;
  employee_username?: string;
  created_at: string;
  method: string;
  outcome: string;
  notes: string;
  follow_up_at: string | null;
  resulting_status: string;
};

export type LeadImportBatch = {
  id: number;
  source: string;
  original_filename: string;
  uploaded_by_username?: string;
  assigned_to: number | null;
  assigned_to_username?: string;
  uploaded_at: string;
  status: string;
  total_rows: number;
  imported_count: number;
  invalid_count: number;
  duplicate_count: number;
  skipped_count: number;
  assigned_count: number;
};

// --- Audit ---
export type AuditEvent = {
  id: number;
  created_at: string;
  user: number | null;
  user_username: string | null;
  work_session: number | null;
  action: string;
  category: string;
  category_display: string;
  source: string;
  entity_type: string;
  entity_id: string;
  summary: string;
  metadata: Record<string, unknown>;
  old_values: Record<string, unknown>;
  new_values: Record<string, unknown>;
  ip_address: string | null;
  user_agent: string;
};

// --- Branding ---
export type BrandProfile = {
  id: number;
  key: string;
  legal_entity: number;
  legal_name: string;
  display_name: string;
  logo_url: string | null;
  accent_color: string;
  secondary_color: string;
  website: string;
  public_email: string;
  service_category: string;
  document_prefix: string;
  default_signatory: number | null;
  is_active: boolean;
};

export type LegalEntity = {
  id: number;
  key: string;
  legal_name: string;
  registration_number: string;
  tax_number: string;
  address: string;
  phone: string;
  email: string;
  website: string;
  bank_details: string;
  owner_name: string;
  owner_title: string;
  legal_terms: string;
  is_active: boolean;
};

export type GeneratedDocument = {
  id: number;
  document_type: string;
  document_type_display: string;
  document_number: string;
  brand: number;
  brand_name: string;
  legal_name: string;
  client: number | null;
  amount: string | null;
  currency: string;
  status: string;
  created_at: string;
  snapshot: Record<string, unknown> | null;
};

// --- Workforce dashboard ---
export type WorkforceDashboard = {
  employee: { id: number; username: string; name: string };
  period: { start: string; end: string };
  work: Record<string, unknown>;
  leads: Record<string, unknown>;
  crm: Record<string, unknown>;
  salary: Record<string, unknown>;
  daily: Array<Record<string, unknown>>;
};
