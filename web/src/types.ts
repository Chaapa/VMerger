export type Project = {
  id: string;
  title: string;
  brief: string;
  created_at: string;
};
export type Asset = {
  id: string;
  original_name: string;
  kind: string;
  duration_us: number;
  status: string;
};
export type Story = {
  id: string;
  title: string;
  description: string;
  current_version_id: string | null;
  status: string;
};
export type Version = {
  id: string;
  story_id: string;
  revision: number;
  change_summary: string;
};
export type Render = {
  id: string;
  version_id: string;
  story_id: string;
  storage_object_id: string;
  status: string;
  duration_us: number;
};
export type Message = {
  id: string;
  story_id: string | null;
  role: string;
  text: string;
};
export type Job = {
  id: string;
  kind: string;
  status: string;
  progress: number;
  attempt: number;
  error: { type: string } | null;
};
export type Observation = {
  id: string;
  metric: string;
  role: string;
  source: string;
  value: number;
  numerator: number | null;
  denominator: number | null;
  created_at: string;
};
export type Call = {
  purpose: string;
  model: string;
  status: string;
  input_tokens: number | null;
  output_tokens: number | null;
  duration_ms: number | null;
  estimated_cost_microusd: number | null;
  created_at: string;
};
export type Snapshot = Project & {
  assets: Asset[];
  stories: Story[];
  edit_versions: Version[];
  renders: Render[];
  messages: Message[];
  jobs: Job[];
  eval_results: Observation[];
  ai_calls: Call[];
};
