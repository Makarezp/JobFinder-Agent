import { FeedbackRequest, ProfileResponse } from "../types/api";

export async function fetchProfileRequest(): Promise<ProfileResponse> {
  const response = await fetch("/api/profile");
  if (!response.ok) {
    throw new Error(`HTTP error! status: ${response.status}`);
  }
  return response.json();
}

export async function submitFeedbackRequest(
  body: FeedbackRequest
): Promise<void> {
  const response = await fetch("/api/feedback", {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify(body),
  });
  if (!response.ok) {
    throw new Error(`HTTP error! status: ${response.status}`);
  }
}
