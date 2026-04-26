/** 用户 */
export interface User {
  id: number;
  username: string;
  role: '管理员' | '用户';
  is_active: boolean;
}

/** 卡牌索引（主目录） */
export interface CardIndex {
  arkhamdb_id: string;
  name_zh: string;
  name_en: string;
  category: '剧本卡' | '玩家卡' | '重返卡';
  cycle: string;
  expansion: string;
  is_double_sided: boolean;
  mapping_status: '已确认' | '待确认' | '映射异常';
}

/** 本地 JSON 卡牌文件 */
export interface LocalCardFile {
  id: number;
  arkhamdb_id: string;
  face: 'a' | 'b' | 'a-c';
  relative_path: string;
  content_hash: string;
  last_modified: string;
  content: Record<string, unknown>;
}


export interface CardBackPreset {
  key: string;
  label: string;
  back_url: string;
  description: string;
}

export interface CardBackOverride {
  preset_key: string;
  label: string;
  back_url: string;
  source: string;
  reason: string;
  updated_by: string;
  updated_at: string;
}

/** TTS 卡牌图片映射 */
export interface TTSImageMapping {
  local_face: string;
  source: '英文' | '中文';
  tts_id: number | null;
  tts_side: 'front' | 'back';
  image_url: string | null;
  status: '已绑定' | '自动候选' | '未找到';
  relative_json_path: string | null;
  card_id: number | null;
}

export interface TTSCardImage {
  id: number;
  arkhamdb_id: string;
  source: '英文' | '中文';
  relative_json_path: string;
  card_id: number;
  deck_key: string;
  face_url: string;
  back_url: string;
  grid_width: number;
  grid_height: number;
  grid_position: number;
  unique_back: boolean;
  cached_front_path: string | null;
  cached_back_path: string | null;
  shared_back_id: number | null;
}

/** 勘误记录 */
export interface Errata {
  id: number;
  arkhamdb_id: string;
  user_id: number;
  original_content: Record<string, unknown>;
  modified_content: Record<string, unknown>;
  status: '待审核' | '已通过' | '已驳回';
  reviewer_id: number | null;
  review_note: string | null;
  batch_id: string | null;
  created_at: string;
  updated_at: string;
}

/** 卡牌详情（聚合视图） */
export interface CardDetail {
  index: CardIndex;
  local_files: LocalCardFile[];
  tts_en: TTSCardImage[];
  tts_zh: TTSCardImage[];
  image_mappings: TTSImageMapping[];
  is_single_sided: boolean;
  back_overrides: Record<string, CardBackOverride | null>;
}

export type CardErrataState = '正常' | '勘误中' | '待发布';

export interface CardTreeCard extends CardIndex {
  local_files: LocalCardFile[];
  pending_errata_count: number;
  approved_errata_count: number;
  latest_batch_id: string | null;
  errata_state: CardErrataState;
}

export interface CardTreeNode {
  key: string;
  title: string;
  children?: CardTreeNode[];
  card?: CardTreeCard;
}

export interface CardTreeResponse {
  tree: CardTreeNode[];
  total: number;
}

export interface PreviewFace {
  face: string;
  relative_path: string;
  preview_url: string | null;
  error: string | null;
  cache_bust?: number;
}

export interface PreviewAllResponse {
  items: PreviewFace[];
}


export interface MappingDetail {
  arkhamdb_id: string;
  card: CardIndex | null;
  local_files: LocalCardFile[];
  image_mappings: TTSImageMapping[];
  is_single_sided: boolean;
  back_overrides: Record<string, CardBackOverride | null>;
  confirmed: boolean;
  confirmed_by: string | null;
  confirmed_at: string | null;
  index_path: string;
}
