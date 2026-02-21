import { ChatResponse } from "../types/api";

export async function fetchHistoryRequest(): Promise<ChatResponse[]> {
  const response = await fetch("/api/history");
  if (!response.ok) {
    throw new Error(`HTTP error! status: ${response.status}`);
  }
  return response.json();
}

export async function sendMessageRequest(
  message: string
): Promise<ChatResponse> {
  const response = await fetch("/api/chat", {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify({ message }),
  });
  if (!response.ok) {
    throw new Error(`HTTP error! status: ${response.status}`);
  }
  return response.json();
}

export async function uploadCVRequest(file: File): Promise<ChatResponse> {
  const formData = new FormData();
  formData.append("file", file);

  // Note: We deliberately do NOT set "Content-Type" here.
  // fetch will automatically set it to multipart/form-data with the correct boundary
  const response = await fetch("/api/upload-cv", {
    method: "POST",
    body: formData,
  });

  if (!response.ok) {
    throw new Error(`HTTP error! status: ${response.status}`);
  }
  return response.json();
}
