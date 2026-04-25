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

/** TTS 卡牌图片映射 */
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
  tts_en: TTSCardImage | null;
  tts_zh: TTSCardImage | null;
}
