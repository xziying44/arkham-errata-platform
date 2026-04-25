import client from './client';

/** 获取卡牌指定面的原始 JSON 文件内容 */
export async function fetchCardFileContent(arkhamdbId: string, face: string) {
  const resp = await client.get(`/cards/${arkhamdbId}/files/${face}`);
  return resp.data;
}

/** 预览卡牌渲染效果 */
export async function previewCard(arkhamdbId: string, content: Record<string, unknown>) {
  const resp = await client.post('/cards/preview', { arkhamdb_id: arkhamdbId, content });
  return resp.data;
}

/** 提交勘误 */
export async function submitErrata(data: {
  arkhamdb_id: string;
  original_content: Record<string, unknown>;
  modified_content: Record<string, unknown>;
}) {
  const resp = await client.post('/errata', data);
  return resp.data;
}

/** 获取当前用户的勘误列表 */
export async function fetchMyErrata(params: { page?: number; status?: string }) {
  const resp = await client.get('/errata', { params });
  return resp.data;
}
