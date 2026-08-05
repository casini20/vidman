const API = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${API}${path}`, init);
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    throw new Error(body.detail ?? `Request failed: ${res.status}`);
  }
  return res.json();
}

export interface Account {
  id: string;
  username: string;
  display_name?: string;
  avatar_url?: string;
  followers: string;
  following: string;
  likes: string;
  last_synced?: string;
  created_at: string;
}

export interface Post {
  id: string;
  caption: string;
  video_filename: string;
  status: "pending" | "in_progress" | "completed" | "partial" | "failed";
  total_accounts: number;
  success_count: number;
  failed_count: number;
  created_at: string;
  accounts?: PostAccount[];
}

export interface PostAccount {
  id: string;
  post_id: string;
  account_id: string;
  username: string;
  status: "pending" | "in_progress" | "success" | "failed";
  error_message?: string;
  posted_at?: string;
}

export const api = {
  accounts: {
    list: () => request<Account[]>("/api/accounts/"),
    add: (cookies: string) =>
      request<Account & { message: string }>("/api/accounts/", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ cookies }),
      }),
    remove: (id: string) =>
      request<{ message: string }>(`/api/accounts/${id}`, { method: "DELETE" }),
    sync: (id: string) =>
      request<Account & { message: string }>(`/api/accounts/${id}/sync`, {
        method: "POST",
      }),
  },
  posts: {
    list: () => request<Post[]>("/api/posts/"),
    get: (id: string) => request<Post>(`/api/posts/${id}`),
    create: (formData: FormData) =>
      request<{ post_id: string; status: string; message: string }>(
        "/api/posts/",
        { method: "POST", body: formData }
      ),
  },
};
