import client from './client';
import type { CardBackPreset, MappingDetail, PublishDirectoryPreset, PublishSession, ReplacementPreviewItem, TTSCardImage } from '../types';

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
export async function step1GenerateSheets(packageId: number | string) {
  const resp = await client.post('/admin/publish/step1-generate-sheets', { package_id: Number(packageId) });
  return resp.data;
}

/** 第二步：上传精灵图到图床 */
export async function step2Upload(sheets: unknown[], uploadConfig: Record<string, unknown>) {
  const resp = await client.post('/admin/publish/step2-upload', { sheets, upload_config: uploadConfig });
  return resp.data;
}

/** 第三步：导出 TTS 存档 JSON */
export async function step3ExportTTS(packageId: number | string, sheetUrls: Record<string, string>, sheetGrids: Record<string, unknown>) {
  const resp = await client.post('/admin/publish/step3-export-tts', {
    package_id: Number(packageId),
    sheet_urls: sheetUrls,
    sheet_grids: sheetGrids,
  }, { responseType: 'blob' });
  return resp.data as Blob;
}

/** 第五步：上传 TTS 导出 JSON 并提取 URL 映射 */
export async function step5UploadTTSJson(file: File) {
  const form = new FormData();
  form.append('file', file);
  const resp = await client.post('/admin/publish/step5-upload-tts-json', form);
  return resp.data;
}

/** 第六步：根据 URL 映射导出 SCED-downloads PR 补丁包 */
export async function step6ExportReplacements(urlMapping: Record<string, unknown>) {
  const resp = await client.post('/admin/publish/step6-export-replacements', { url_mapping: urlMapping }, { responseType: 'blob' });
  return resp.data as Blob;
}


export async function fetchMappingDetail(arkhamdbId: string): Promise<MappingDetail> {
  const resp = await client.get(`/admin/mapping/${arkhamdbId}`);
  return resp.data;
}

export async function searchTTSCandidates(params: { source?: string; keyword?: string; limit?: number }): Promise<{ items: TTSCardImage[] }> {
  const resp = await client.get('/admin/mapping/search/tts', { params });
  return resp.data;
}

export async function bindTTSMapping(body: { arkhamdb_id: string; local_face: string; source: string; tts_id: number; tts_side: string }) {
  const resp = await client.post('/admin/mapping/bind', body);
  return resp.data;
}

export async function unbindTTSMapping(body: { arkhamdb_id: string; local_face: string; source: string }) {
  const resp = await client.post('/admin/mapping/unbind', body);
  return resp.data;
}

export async function swapTTSMapping(body: { arkhamdb_id: string; source: string }) {
  const resp = await client.post('/admin/mapping/swap', body);
  return resp.data;
}

export async function confirmTTSMapping(arkhamdbId: string): Promise<MappingDetail> {
  const resp = await client.post('/admin/mapping/confirm', { arkhamdb_id: arkhamdbId });
  return resp.data;
}

export async function fetchBackPresets(): Promise<{ items: CardBackPreset[] }> {
  const resp = await client.get('/admin/mapping/back-presets');
  return resp.data;
}

export async function setBackOverride(arkhamdbId: string, face: string, presetKey: string): Promise<MappingDetail> {
  const resp = await client.post(`/admin/mapping/${arkhamdbId}/faces/${face}/back-override`, { preset_key: presetKey });
  return resp.data;
}

export async function clearBackOverride(arkhamdbId: string, face: string): Promise<MappingDetail> {
  const resp = await client.delete(`/admin/mapping/${arkhamdbId}/faces/${face}/back-override`);
  return resp.data;
}


export async function createPublishSession(packageId: number): Promise<PublishSession> {
  const resp = await client.post('/admin/publish/sessions', { package_id: packageId });
  return resp.data;
}

export async function fetchPublishSession(sessionId: number): Promise<PublishSession> {
  const resp = await client.get(`/admin/publish/sessions/${sessionId}`);
  return resp.data;
}

export async function generateSessionSheets(sessionId: number): Promise<PublishSession> {
  const resp = await client.post(`/admin/publish/sessions/${sessionId}/generate-sheets`);
  return resp.data;
}

export async function fetchReplacementPreview(sessionId: number): Promise<{ items: ReplacementPreviewItem[] }> {
  const resp = await client.get(`/admin/publish/sessions/${sessionId}/replacement-preview`);
  return resp.data;
}

export async function fetchDirectoryPresets(): Promise<{ items: PublishDirectoryPreset[] }> {
  const resp = await client.get('/admin/publish/directory-presets');
  return resp.data;
}
