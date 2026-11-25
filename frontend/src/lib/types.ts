export interface Freshness {
  computed_at: string;
  latest_posted_at: string | null;
  posted_at_age_hours: number | null;
  latest_source_ingested_at: string | null;
  source_ingested_at_age_hours: number | null;
  latest_snapshot_at: string | null;
  snapshot_at_age_hours: number | null;
}

export interface Publication {
  version: number;
  run_id: string;
  published_at: string;
  vacancy_count: number;
  row_counts: Record<string, number>;
  freshness: Freshness;
}

export interface Health {
  status: "ok" | "no_data";
  gold_version: number | null;
  published_at: string | null;
  vacancies: number;
  freshness: Freshness | null;
  demo?: boolean;
}

export interface SkillDemand {
  skill_uri: string;
  skill_label: string;
  skill_type: string | null;
  vacancies: number;
  share_of_text_pct: number;
}

export interface VacancyListItem {
  job_id: string;
  source: string;
  source_name: string | null;
  title: string;
  company_name: string | null;
  employment_type: string | null;
  salary_from: number | null;
  salary_to: number | null;
  salary_currency: string | null;
  salary_period: string | null;
  has_salary: number;
  posted_at: string | null;
  deadline_at: string | null;
  has_text: number;
  text_lang: string | null;
  skill_status: "matched" | "no_match" | "no_text" | null;
  skill_count: number;
  occupation_uri: string | null;
  occupation_label: string | null;
  url: string | null;
  also_listed_on: { job_id: string; source: string; url: string | null }[];
}

export interface Overview {
  published: boolean;
  publication: Publication;
  kpis: {
    vacancies: number; employers: number; sources: number; with_salary: number; with_text: number;
    with_skills: number; no_text: number; no_match: number; with_occupation: number; with_mirrors: number;
    distinct_skills: number; skill_matches: number; raw_records: number; duplicates_removed: number;
  };
  last_run: { run_id: string; run_type: string; trigger: string; status: string; started_at: string; duration_s: number } | null;
  quality: { passed: number; total: number };
  salary: { coverage_pct: number; with_any_salary: number; vacancies: number; median_salary_from: number | null; currency: string | null } | null;
  top_skills: SkillDemand[];
  sources: { source: string; source_name: string; vacancies: number; share_pct: number; with_salary: number; with_text: number }[];
  occupations: { occupation_uri: string; occupation_label: string; vacancies: number }[];
  companies: { company_name: string; vacancies: number; with_salary: number }[];
  first_seen_trend: { day: string; vacancies: number }[];
  posted_trend: { day: string; vacancies: number }[];
  languages: { lang: string; n: number }[];
  recent: (Pick<VacancyListItem, "job_id" | "title" | "company_name" | "source_name" | "posted_at" | "salary_from" |
    "salary_to" | "salary_currency" | "salary_period" | "skill_count" | "occupation_label">)[];
}

export interface VacancyPage {
  total: number;
  published_total: number;
  page: number;
  page_size: number;
  items: VacancyListItem[];
}

export interface Facet { value: string; label?: string; n: number }
export interface Facets { sources: Facet[]; employment_types: Facet[]; occupations: Facet[]; skills: Facet[]; companies: Facet[];
  salary_periods: Facet[]; currencies: Facet[]; posted_range: { min_date: string | null; max_date: string | null; without_date: number; today_baku: string } }

export interface Evidence {
  skill_uri: string;
  skill_label: string;
  skill_type: string | null;
  field: "title" | "description" | "requirements";
  start_pos: number;
  end_pos: number;
  matched_text: string;
  label: string;
  label_type: string;
  lang: string;
  snippet: string | null;
}

export interface VacancyDetail extends VacancyListItem {
  company_key: string | null;
  city: string;
  job_function_raw: string | null;
  career_level_raw: string | null;
  posted_date: string | null;
  first_seen_at: string | null;
  description_text: string | null;
  requirements_text: string | null;
  occupation_match: string | null;
  skills: Evidence[];
}

export interface SkillRow {
  skill_uri: string;
  skill_label: string;
  skill_type: string | null;
  vacancies: number;
  mentions: number;
  langs: string | null;
  label_types: string | null;
  share_pct: number;
}

export interface SkillsResponse {
  analysable_vacancies: number;
  total_skills: number;
  total_matches: number;
  returned: number;
  coverage: { total: number; matched: number; no_match: number; no_text: number };
  by_label_type: { label_type: string; n: number }[];
  by_language: { lang: string; n: number }[];
  by_skill_type: { skill_type: string; skills: number }[];
  items: SkillRow[];
  method: string;
}

export interface SkillDetail {
  skill_uri: string;
  preferred_label: string;
  skill_type: string | null;
  reuse_level: string | null;
  alt_labels: string[];
  description: string | null;
  demand: { vacancies: number; share_of_text_pct: number } | null;
  evidence: { job_id: string; title: string; company_name: string | null; source_name: string | null; field: string;
    matched_text: string; label: string; label_type: string; lang: string; snippet: string | null }[];
  matched_forms: { matched_text: string; label_type: string; lang: string; n: number }[];
  co_occurring: { skill_uri: string; skill_label: string; vacancies: number }[];
  esco_occupations: { essential: number | null; optional: number | null };
  market_occupations: { occupation_uri: string; occupation_label: string; vacancies: number }[];
}

export interface EscoOccupation { occupation_uri: string; preferred_label: string; isco_group: string | null; market_vacancies: number }
export interface EscoSkill { skill_uri: string; preferred_label: string; skill_type: string | null; baku_vacancies: number }

export interface MarketReq {
  skill_uri: string; label: string; skill_type: string | null; vacancies: number; share_pct: number;
  user_has: boolean; esco_relation: string | null;
}
export interface EscoReq {
  skill_uri: string; label: string; skill_type: string | null; relation_type: string; user_has: boolean;
  baku: { vacancies: number; share_pct: number };
}
export interface CareerMatch {
  occupation: { occupation_uri: string; preferred_label: string; isco_group: string | null; description: string | null };
  occupation_vacancies: number;
  market_requirements: MarketReq[];
  esco_essential: EscoReq[];
  esco_optional: EscoReq[];
  coverage: {
    market: { matched: number; total: number; weighted_pct: number | null };
    esco_essential: { matched: number; total: number; pct: number | null };
    esco_optional: { matched: number; total: number; pct: number | null };
  };
  other_user_skills: { skill_uri: string; label: string }[];
  method: string;
  limitations: string[];
}

export interface RoadmapItem {
  skill_uri: string; label: string; skill_type: string | null; esco_relation: string | null;
  occupation_vacancies: number; baku_vacancies: number; score: number;
  components: { occupation_market: number; esco_relation: number; baku_market: number };
  priority: "high" | "medium" | "low"; reasons: string[]; description: string | null;
}
export interface Roadmap {
  occupation: CareerMatch["occupation"];
  occupation_vacancies: number;
  items: RoadmapItem[];
  omitted_optional_without_evidence: number;
  formula: Record<string, string>;
}

export interface SalaryGroup {
  currency: string; period: string; vacancies: number; with_from: number; with_to: number; with_range: number;
  median_from: number | null; median_to: number | null; median_midpoint: number | null;
  p25_from: number | null; p75_from: number | null; min_from: number | null; max_to: number | null;
}
export interface SalaryBreakdown { key: string; label: string | null; vacancies: number; median_from: number | null;
  median_to: number | null; min_from: number | null; max_to: number | null }
export interface SalaryResponse {
  total_vacancies: number; with_salary: number; coverage_pct: number;
  groups: SalaryGroup[]; selected: SalaryGroup | null;
  histogram?: { from: number; to: number; vacancies: number; overflow: boolean }[];
  bin_width?: number;
  by_occupation?: SalaryBreakdown[]; by_source?: SalaryBreakdown[]; by_employment_type?: SalaryBreakdown[];
  vacancies?: { job_id: string; title: string; source_name: string | null; occupation_uri?: string | null; occupation_label: string | null;
    salary_from: number | null; salary_to: number | null }[];
  coverage_by_source: { source: string; vacancies: number; with_salary: number; coverage_pct: number }[];
  rules: string[];
}

export interface TaskRun { task_name: string; status: string; attempts: number; duration_s: number | null;
  rows_out: number | null; error: string | null }
export interface PipelineRun {
  run_id: string; run_type: string; trigger: string; status: string; started_at: string; finished_at: string | null;
  duration_s: number | null; params: Record<string, unknown>; error: string | null; tasks: TaskRun[]; retries: number;
}
export interface SchedulerState {
  enabled: number; mode: string; interval_hours: number; live: number; started_at: string | null;
  last_run_at: string | null; last_run_id: string | null; last_status: string | null; next_run_at: string | null;
  heartbeat_at: string | null;
}
export interface PipelineResponse {
  runs: PipelineRun[];
  status_counts: Record<string, number>;
  publications: { version: number; run_id: string; published_at: string; vacancy_count: number; row_counts: Record<string, number> }[];
  current_publication: Publication | null;
  alerts: { id: number; run_id: string | null; level: string; message: string; created_at: string }[];
  layer_counts: Record<string, number>;
  scheduler: { state: SchedulerState | null; web: { enabled: boolean; interval_hours?: number; next_run_at?: string | null } };
  lock: { run_id: string; acquired_at: string } | null;
}
export interface RunDetail {
  run: PipelineRun & { params: Record<string, unknown> };
  tasks: (TaskRun & { started_at: string | null; finished_at: string | null; details: Record<string, unknown> })[];
  metrics: { metric: string; value: number | null }[];
  quality: { check_name: string; severity: string; passed: number; checked_count: number; failed_count: number }[];
  alerts: { level: string; message: string; created_at: string }[];
}

export interface QualityCheck {
  check_name: string; severity: "blocking" | "warning"; passed: number; checked_count: number; failed_count: number;
  created_at: string; detail: string | null; sample: unknown[]; rule: string | null;
}
export interface QualityResponse {
  run: { run_id: string; status: string; started_at: string } | null;
  checks: QualityCheck[];
  history: { check_name: string; runs: number; passed: number; failed: number }[];
  runs: { run_id: string; started_at: string; status: string; passed: number; total: number }[];
  normalization_issues: { field: string; issue: string; n: number }[];
  gate: string;
}

export interface SourcesResponse {
  softon: {
    api_key_configured: boolean; base_url: string; city: string; page_limit: number;
    budget: { monthly_budget: number; used_this_month: number; remaining: number;
      last_quota: { quota_limit: number; quota_used: number; requested_at: string } | null };
    incremental: { watermark: string | null; updated_at: string | null; resume_pending: boolean;
      resume_params: Record<string, string> | null };
    files: { file_id: number; source: string; file_kind: string; path: string; sha256: string; size_bytes: number;
      snapshot_at: string | null; registered_at: string; record_count: number | null }[];
    requests: { requested_at: string; status_code: number | null; records: number | null; quota_limit: number | null;
      quota_used: number | null; duration_ms: number | null; attempt: number; params: Record<string, string>; error: string | null }[];
    sources: { source: string; source_name: string; vacancies: number; duplicates_removed: number; share_pct: number;
      with_salary: number; with_text: number; with_skills: number; last_posted_at: string | null }[];
    bronze_records: number; distinct_ids: number; published_vacancies: number; cross_source_duplicates: number;
    mirrors: { job_id: string; title: string; source_name: string; company_name: string | null;
      also_listed_on: { job_id: string; source: string; url: string | null }[] }[];
  };
  esco: {
    occupations: number; skills: number; relations: number;
    skill_types: { skill_type: string; n: number }[]; relation_types: { relation_type: string; n: number }[];
    dictionary_labels: number; dictionary_by_type: { label_type: string; lang: string; n: number }[];
  };
  layers: Record<string, number>;
}

export interface Operation {
  op_id: string; kind: string; status: "queued" | "running" | "success" | "blocked" | "failed";
  params: Record<string, unknown> | null; requested_at: string; started_at: string | null; finished_at: string | null;
  run_id: string | null; result: Record<string, unknown> | null; error: string | null;
}
export interface DemoStep {
  step: number; title: string; expected: string; ok: boolean; run_status: string | null; run_id: string | null;
  tasks: Record<string, string> | null;
  state: { gold_sha256: string; gold_version: number | null; published_vacancies: number | null; bronze_rows: number; error_alerts?: number };
  [k: string]: unknown;
}
export interface AdminStatus {
  local: boolean; busy: boolean; current_operation: string | null; db_lock: { run_id: string; acquired_at: string } | null;
  api_key_configured: boolean; budget_remaining: number; default_live_pages: number; demos: Record<string, string>;
  scheduler: { enabled: boolean; interval_hours: number; next_run_at?: string | null };
}
