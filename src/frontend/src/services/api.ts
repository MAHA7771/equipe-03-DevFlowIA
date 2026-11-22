export const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";
export const USE_MOCK = (process.env.NEXT_PUBLIC_USE_MOCK ?? "true") === "true";

export async function api<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${API_URL}${path}`, {
    ...init,
    headers: { "Content-Type": "application/json", ...(init?.headers ?? {}) },
  });
  if (!res.ok) {
    throw new Error(`Erreur API ${res.status} sur ${path}`);
  }
  return (await res.json()) as T;
}

export const delay = (ms = 250) => new Promise((r) => setTimeout(r, ms));