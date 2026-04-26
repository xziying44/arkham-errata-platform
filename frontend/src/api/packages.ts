import client from './client';
import type { ErrataPackage } from '../types';

export async function fetchPackages(): Promise<{ items: ErrataPackage[] }> {
  const resp = await client.get('/admin/packages');
  return resp.data;
}

export async function fetchPackageDetail(packageId: number) {
  const resp = await client.get(`/admin/packages/${packageId}`);
  return resp.data;
}

export async function unlockPackage(packageId: number, note?: string): Promise<ErrataPackage> {
  const resp = await client.post(`/admin/packages/${packageId}/unlock`, { note });
  return resp.data;
}

export async function completePackage(packageId: number): Promise<ErrataPackage> {
  const resp = await client.post(`/admin/packages/${packageId}/complete`);
  return resp.data;
}

export async function createReviewPackage(arkhamdbIds: string[], note?: string) {
  const resp = await client.post('/admin/review/package', { arkhamdb_ids: arkhamdbIds, note });
  return resp.data;
}
