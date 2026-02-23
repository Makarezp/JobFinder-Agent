export interface Job {
  id: string;
  title: string;
  company: string;
  location: string;
  salary: string | null;
  description: string;
  apply_link: string;
}

export interface ChatResponse {
  user_message: string;
  ai_message: string;
  jobs: Job[];
}

export interface Preference {
  key: string;
  value: string | number | boolean | string[];
  category: "hard" | "soft";
  sentiment: "positive" | "negative";
}

export interface DecisionLogEntry {
  job_title: string;
  company: string;
  action: "pass" | "pursue";
  description: string | null;
  reason: string | null;
  timestamp: string;
}

export interface ProfileResponse {
  profile: {
    id: number;
    name: string | null;
    role: string | null;
    cv_summary: string | null;
    cv_uploaded: boolean;
  };
  preferences: Record<string, Preference>;
  decisions: DecisionLogEntry[];
}

export interface FeedbackRequest {
  job_title: string;
  company: string;
  action: "pass" | "pursue";
  description: string | null;
  reason: string | null;
  job_id: string;
}
