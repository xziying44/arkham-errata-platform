import client from './client';
import { CardIndex, CardDetail } from '../types';

export async function fetchCards(params: { category?: string; cycle?: string; keyword?: string; page?: number; page_size?: number }) {
  const resp = await client.get('/cards', { params });
  return resp.data;
}

export async function fetchFilters() {
  const resp = await client.get('/cards/filters');
  return resp.data;
}

export async function fetchCardDetail(arkhamdbId: string): Promise<CardDetail> {
  const resp = await client.get(`/cards/${arkhamdbId}`);
  return resp.data;
}
