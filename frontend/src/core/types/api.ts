export interface Job {
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
