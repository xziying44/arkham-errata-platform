import client from './client';
import type { ErrataAuditLog, ErrataDraft } from '../types';

export async function fetchErrataDraft(arkhamdbId: string): Promise<ErrataDraft | null> {
  try {
    const resp = await client.get(`/errata-drafts/${arkhamdbId}`);
    return resp.data;
  } catch (error: any) {
    if (error?.response?.status === 404) return null;
    throw error;
  }
}

export async function saveErrataDraft(
  arkhamdbId: string,
  data: { modified_faces: Record<string, Record<string, unknown>>; changed_faces: string[]; diff_summary?: string | null },
): Promise<ErrataDraft> {
  const resp = await client.put(`/errata-drafts/${arkhamdbId}`, data);
  return resp.data;
}

export async function fetchErrataDraftLogs(arkhamdbId: string): Promise<ErrataAuditLog[]> {
  const resp = await client.get(`/errata-drafts/${arkhamdbId}/logs`);
  return resp.data;
}
