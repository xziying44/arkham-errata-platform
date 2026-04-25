import client from './client';

export async function login(username: string, password: string) {
  const resp = await client.post('/auth/login', { username, password });
  return resp.data;
}
