import client from './client';
import type { User, UserRole } from '../types';

export async function login(username: string, password: string) {
  const resp = await client.post('/auth/login', { username, password });
  return resp.data;
}

export async function fetchCurrentUser(): Promise<User> {
  const resp = await client.get('/auth/me');
  return resp.data;
}

export async function fetchUsers(): Promise<User[]> {
  const resp = await client.get('/auth/users');
  return resp.data;
}

export async function createUser(data: { username: string; password: string; role: UserRole }): Promise<User> {
  const resp = await client.post('/auth/users', data);
  return resp.data;
}

export async function updateUser(userId: number, data: { role?: UserRole; is_active?: boolean }): Promise<User> {
  const resp = await client.patch(`/auth/users/${userId}`, data);
  return resp.data;
}

export async function resetPassword(userId: number, password: string): Promise<{ ok: boolean }> {
  const resp = await client.post(`/auth/users/${userId}/reset-password`, { password });
  return resp.data;
}
