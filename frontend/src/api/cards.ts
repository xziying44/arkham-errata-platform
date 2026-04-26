import client from './client';
import type { CardDetail, CardTreeResponse, PreviewAllResponse } from '../types';

export async function fetchCards(params: { category?: string; cycle?: string; keyword?: string; mapping_status?: string; page?: number; page_size?: number }) {
  const resp = await client.get('/cards', { params });
  return resp.data;
}

export async function fetchFilters() {
  const resp = await client.get('/cards/filters');
  return resp.data;
}

export async function fetchCardTree(keyword?: string): Promise<CardTreeResponse> {
  const resp = await client.get('/cards/tree', { params: { keyword: keyword || undefined } });
  return resp.data;
}

export async function fetchCardDetail(arkhamdbId: string): Promise<CardDetail> {
  const resp = await client.get(`/cards/${arkhamdbId}`);
  return resp.data;
}

export async function previewAllFaces(arkhamdbId: string): Promise<PreviewAllResponse> {
  const resp = await client.post(`/cards/${arkhamdbId}/preview-all`);
  return resp.data;
}
