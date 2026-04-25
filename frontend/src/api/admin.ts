import client from './client';

/** 获取待审核的勘误列表 */
export async function fetchPendingReviews() {
  const resp = await client.get('/admin/review/pending');
  return resp.data;
}

/** 批量通过勘误 */
export async function batchApprove(ids: number[], batchId?: string) {
  const resp = await client.post('/admin/review/approve', { ids, batch_id: batchId });
  return resp.data;
}

/** 批量驳回勘误 */
export async function batchReject(ids: number[], note: string) {
  const resp = await client.post('/admin/review/reject', { ids, note });
  return resp.data;
}

/** 第一步：生成精灵图 */
export async function step1GenerateSheets(batchId: string) {
  const resp = await client.post('/admin/publish/step1-generate-sheets', { batch_id: batchId });
  return resp.data;
}

/** 第二步：上传精灵图到图床 */
export async function step2Upload(sheets: unknown[], uploadConfig: Record<string, unknown>) {
  const resp = await client.post('/admin/publish/step2-upload', { sheets, upload_config: uploadConfig });
  return resp.data;
}

/** 第五步：上传 TTS 导出 JSON 并提取 URL 映射 */
export async function step5UploadTTSJson(file: File) {
  const form = new FormData();
  form.append('file', file);
  const resp = await client.post('/admin/publish/step5-upload-tts-json', form);
  return resp.data;
}

/** 第六步：根据 URL 映射替换中文卡图中的图片 URL */
export async function step6ReplaceUrls(urlMapping: Record<string, unknown>) {
  const resp = await client.post('/admin/publish/step6-replace-urls', { url_mapping: urlMapping });
  return resp.data;
}
