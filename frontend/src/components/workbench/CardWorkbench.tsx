import { useCallback, useEffect, useMemo, useState } from 'react';
import type { Key, ReactNode } from 'react';
import { FolderOpenOutlined, FolderOutlined } from '@ant-design/icons';
import { Button, Card, Empty, Input, Layout, message, Modal, Segmented, Space, Spin, Tag, Tree, Typography } from 'antd';
import type { DataNode } from 'antd/es/tree';
import { fetchCardDetail, fetchCardTree, previewOneFace } from '../../api/cards';
import { fetchCardFileContent, previewCard } from '../../api/errata';
import CardComparison from '../CardComparison';
import JsonEditor from '../JsonEditor';
import CardTextFieldsEditor from './CardTextFieldsEditor';
import ErrataDiffPanel from './ErrataDiffPanel';
import SymbolReferenceHelp from './SymbolReferenceHelp';
import type { CardDetail, CardTreeCard, CardTreeNode, ErrataAuditLog, ErrataDraft, PreviewFace, WorkbenchMode } from '../../types';
import { cancelErrataDraft, fetchErrataDraft, fetchErrataDraftLogs, saveErrataDraft } from '../../api/errataDrafts';
import { createReviewPackage } from '../../api/packages';
import { buildErrataDiff, buildJsonStringDecorations, offsetRangeToMonacoRange } from './errataDiff';

const { Sider, Content } = Layout;
const { Text, Title } = Typography;

type TreeStats = {
  total: number;
  pending: number;
  approved: number;
};

const cardListPanelStyle = {
  padding: 14,
  borderRadius: 14,
  overflow: 'auto',
  maxHeight: 'calc(100vh - 120px)',
  border: '1px solid #e7edf5',
  boxShadow: '0 10px 28px rgba(15, 23, 42, 0.08)',
} satisfies React.CSSProperties;

function collectLeafKeys(nodes: CardTreeNode[]): string[] {
  return nodes.flatMap((node) => node.children?.length ? collectLeafKeys(node.children) : [node.key]);
}

function collectExpandableKeys(nodes: CardTreeNode[]): string[] {
  return nodes.flatMap((node) => node.children?.length ? [node.key, ...collectExpandableKeys(node.children)] : []);
}

function summarizeTree(nodes: CardTreeNode[]): TreeStats {
  return nodes.reduce<TreeStats>((stats, node) => {
    if (node.card) {
      return {
        total: stats.total + 1,
        pending: stats.pending + (node.card.pending_errata_count > 0 ? 1 : 0),
        approved: stats.approved + (node.card.pending_errata_count === 0 && node.card.approved_errata_count > 0 ? 1 : 0),
      };
    }
    const childStats = summarizeTree(node.children || []);
    return {
      total: stats.total + childStats.total,
      pending: stats.pending + childStats.pending,
      approved: stats.approved + childStats.approved,
    };
  }, { total: 0, pending: 0, approved: 0 });
}

function errataTag(card: CardTreeCard) {
  if (card.pending_errata_count > 0) {
    return <Tag color="processing" style={{ marginInlineEnd: 0 }}>勘误 {card.pending_errata_count}</Tag>;
  }
  if (card.approved_errata_count > 0) {
    return <Tag color="warning" style={{ marginInlineEnd: 0 }}>待发布 {card.approved_errata_count}</Tag>;
  }
  return <Tag color="success" style={{ marginInlineEnd: 0 }}>正常</Tag>;
}

function faceSummary(card: CardTreeCard) {
  const faces = card.local_files.map((file) => file.face).sort();
  if (!faces.length) return null;
  return <Tag color="default" style={{ marginInlineEnd: 0 }}>{faces.join('/')}</Tag>;
}

function renderGroupTitle(
  node: CardTreeNode,
  expanded: boolean,
  onToggle: (key: string) => void,
): ReactNode {
  const stats = summarizeTree(node.children || []);
  return (
    <div
      onClick={(event) => {
        event.stopPropagation();
        onToggle(node.key);
      }}
      style={{
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'space-between',
        gap: 8,
        width: '100%',
        padding: '6px 8px',
        borderRadius: 10,
        cursor: 'pointer',
        background: expanded ? '#eef6ff' : 'transparent',
      }}
    >
      <Space size={8} style={{ minWidth: 0 }}>
        {expanded ? <FolderOpenOutlined style={{ color: '#1677ff' }} /> : <FolderOutlined style={{ color: '#64748b' }} />}
        <Text strong ellipsis style={{ maxWidth: 148 }}>{node.title}</Text>
      </Space>
      <Space size={4} wrap>
        <Tag color="default">{stats.total}</Tag>
        {stats.pending > 0 && <Tag color="processing">勘误 {stats.pending}</Tag>}
        {stats.approved > 0 && <Tag color="warning">待发布 {stats.approved}</Tag>}
      </Space>
    </div>
  );
}

type CardTitleFaceMode = 'front' | 'back';

function titleForCardFace(card: CardTreeCard, mode: CardTitleFaceMode) {
  const faceTitles = card.face_titles || {};
  if (mode === 'back') {
    return faceTitles.b || faceTitles['a-c'] || faceTitles.a || card.name_zh || card.name_en || '未命名卡牌';
  }
  return faceTitles.a || faceTitles['a-c'] || faceTitles.b || card.name_zh || card.name_en || '未命名卡牌';
}

function subtitleForCardFace(card: CardTreeCard, mode: CardTitleFaceMode) {
  const faceSubtitles = card.face_subtitles || {};
  if (mode === 'back') {
    return faceSubtitles.b || faceSubtitles['a-c'] || faceSubtitles.a || '';
  }
  return faceSubtitles.a || faceSubtitles['a-c'] || faceSubtitles.b || '';
}

function renderCardTitle(card: CardTreeCard, titleFaceMode: CardTitleFaceMode) {
  const subtitle = subtitleForCardFace(card, titleFaceMode);
  return (
    <div style={{ display: 'flex', alignItems: 'flex-start', gap: 6, width: '100%', minWidth: 0 }}>
      <Tag color="geekblue" style={{ marginInlineEnd: 0, flex: '0 0 auto' }}>{card.arkhamdb_id}</Tag>
      <div style={{ flex: '1 1 auto', minWidth: 0, lineHeight: 1.2 }}>
        <Text strong ellipsis style={{ display: 'block' }}>{titleForCardFace(card, titleFaceMode)}</Text>
        {subtitle && <Text type="secondary" ellipsis style={{ display: 'block', fontSize: 12, marginTop: 2 }}>{subtitle}</Text>}
      </div>
      <Space size={4} style={{ flex: '0 0 auto', paddingTop: 1 }}>
        {errataTag(card)}
        {faceSummary(card)}
        {card.latest_batch_id && <Tag color="gold" style={{ marginInlineEnd: 0 }}>包 {card.latest_batch_id}</Tag>}
      </Space>
    </div>
  );
}

function toTreeData(
  nodes: CardTreeNode[],
  expandedKeys: Key[],
  onToggle: (key: string) => void,
  titleFaceMode: CardTitleFaceMode,
): DataNode[] {
  const expanded = new Set(expandedKeys.map(String));
  return nodes.map((node) => ({
    key: node.key,
    title: node.card ? renderCardTitle(node.card, titleFaceMode) : renderGroupTitle(node, expanded.has(node.key), onToggle),
    children: node.children ? toTreeData(node.children, expandedKeys, onToggle, titleFaceMode) : undefined,
    isLeaf: Boolean(node.card),
  }));
}

function findCard(nodes: CardTreeNode[], key: string): CardTreeNode['card'] | null {
  for (const node of nodes) {
    if (node.key === key && node.card) return node.card;
    const found = node.children ? findCard(node.children, key) : null;
    if (found) return found;
  }
  return null;
}

function faceLabel(face: string) {
  if (face === 'a') return '正面';
  if (face === 'b') return '背面';
  return `面 ${face}`;
}

function ttsSideLabel(side?: string) {
  if (side === 'back') return 'TTS 背面';
  if (side === 'front') return 'TTS 正面';
  return '未绑定';
}

function withCacheBust(url?: string | null, cacheBust?: number) {
  if (!url || !cacheBust) return url || null;
  return `${url}${url.includes('?') ? '&' : '?'}t=${cacheBust}`;
}

function parseObjectJson(value?: string): Record<string, unknown> | null {
  if (!value) return {};
  try {
    const parsed = JSON.parse(value);
    return parsed && typeof parsed === 'object' && !Array.isArray(parsed) ? parsed : null;
  } catch {
    return null;
  }
}

const horizontalCardTypes = new Set([
  '调查员',
  '调查员卡',
  '调查员背面',
  '调查员卡背',
  '场景卡',
  '场景卡背',
  '场景卡-大画',
  '密谋卡',
  '密谋卡背',
  '密谋卡-大画',
]);

interface CardWorkbenchProps {
  mode: WorkbenchMode;
  packageId?: number;
}

function scopeForMode(mode: WorkbenchMode) {
  if (mode === 'my-errata') return 'mine';
  if (mode === 'review') return 'review';
  if (mode === 'package-review') return 'package';
  return 'all';
}

function titleForMode(mode: WorkbenchMode) {
  if (mode === 'my-errata') return '我的勘误';
  if (mode === 'review') return '勘误审核';
  if (mode === 'package-review') return '勘误包审阅';
  return '卡牌数据库';
}

export default function CardWorkbench({ mode, packageId }: CardWorkbenchProps) {
  const [tree, setTree] = useState<CardTreeNode[]>([]);
  const [expandedKeys, setExpandedKeys] = useState<Key[]>([]);
  const [keyword, setKeyword] = useState('');
  const [treeLoading, setTreeLoading] = useState(false);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [detail, setDetail] = useState<CardDetail | null>(null);
  const [fileContents, setFileContents] = useState<Record<string, Record<string, unknown>>>({});
  const [modifiedJsonByFace, setModifiedJsonByFace] = useState<Record<string, string>>({});
  const [previewFaces, setPreviewFaces] = useState<PreviewFace[]>([]);
  const [selectedFace, setSelectedFace] = useState('a');
  const [detailLoading, setDetailLoading] = useState(false);
  const [rendering, setRendering] = useState(false);
  const [draft, setDraft] = useState<ErrataDraft | null>(null);
  const [auditLogs, setAuditLogs] = useState<ErrataAuditLog[]>([]);
  const [packaging, setPackaging] = useState(false);
  const [canceling, setCanceling] = useState(false);
  const [titleFaceMode, setTitleFaceMode] = useState<CardTitleFaceMode>('front');
  const [symbolHelpOpen, setSymbolHelpOpen] = useState(false);

  const loadTree = useCallback(async (search?: string) => {
    setTreeLoading(true);
    try {
      const data = await fetchCardTree({ keyword: search, scope: scopeForMode(mode), package_id: packageId });
      setTree(data.tree);
      if (search) setExpandedKeys(collectExpandableKeys(data.tree));
      setSelectedId((currentSelectedId) => {
        if (currentSelectedId || data.tree.length === 0) return currentSelectedId;
        const firstLeaf = collectLeafKeys(data.tree)[0];
        return firstLeaf ? String(firstLeaf) : currentSelectedId;
      });
    } finally {
      setTreeLoading(false);
    }
  }, [mode, packageId]);

  useEffect(() => { loadTree(); }, [loadTree]);

  useEffect(() => {
    if (!selectedId) return;
    let cancelled = false;
    const loadDetail = async () => {
      setDetailLoading(true);
      setDetail(null);
      setFileContents({});
      setModifiedJsonByFace({});
      setPreviewFaces([]);
      setDraft(null);
      setAuditLogs([]);
      try {
        const cardDetail = await fetchCardDetail(selectedId);
        if (cancelled) return;
        setDetail(cardDetail);
        setSelectedFace(cardDetail.local_files[0]?.face || 'a');

        const contents: Record<string, Record<string, unknown>> = {};
        const jsonByFace: Record<string, string> = {};
        const fileResults = await Promise.allSettled(
          cardDetail.local_files.map(async (file) => {
            const data = await fetchCardFileContent(selectedId, file.face);
            return { face: file.face, content: data.content };
          }),
        );
        if (cancelled) return;
        for (const result of fileResults) {
          if (result.status === 'fulfilled') {
            contents[result.value.face] = result.value.content;
            jsonByFace[result.value.face] = JSON.stringify(result.value.content, null, 2);
          }
        }
        let currentJsonByFace = jsonByFace;
        let activeDraft: ErrataDraft | null = null;
        try {
          const currentDraft = await fetchErrataDraft(selectedId);
          if (!cancelled && currentDraft) {
            setDraft(currentDraft);
            activeDraft = currentDraft;
            currentJsonByFace = Object.fromEntries(
              Object.entries(currentDraft.modified_faces).map(([face, content]) => [face, JSON.stringify(content, null, 2)]),
            );
          }
        } catch (e: any) {
          if (!cancelled) message.warning(e?.response?.data?.detail || '勘误副本读取失败');
        }
        setFileContents(contents);
        setModifiedJsonByFace(currentJsonByFace);
        setDetailLoading(false);
        try {
          const logs = await fetchErrataDraftLogs(selectedId);
          if (!cancelled) setAuditLogs(logs);
        } catch {
          if (!cancelled) setAuditLogs([]);
        }
        if (fileResults.some((result) => result.status === 'rejected')) {
          message.warning('部分 .card 文件读取失败，可稍后重试');
        }

        setPreviewFaces(cardDetail.local_files.map((file) => ({
          face: file.face,
          relative_path: file.relative_path,
          preview_url: activeDraft?.rendered_previews?.[file.face] || null,
          error: activeDraft ? '正在生成勘误副本预览…' : '正在生成本地预览…',
          cache_bust: activeDraft?.rendered_previews?.[file.face] ? Date.parse(activeDraft.updated_at) : undefined,
        })));
        await Promise.allSettled(
          cardDetail.local_files.map(async (file) => {
            try {
              const preview = activeDraft
                ? {
                    face: file.face,
                    relative_path: file.relative_path,
                    preview_url: activeDraft.rendered_previews?.[file.face] || (await previewCard(`${selectedId}_${file.face}`, activeDraft.modified_faces[file.face] || {})).preview_url || null,
                    error: null,
                    cache_bust: Date.now(),
                  }
                : await previewOneFace(selectedId, file.face);
              if (!cancelled) {
                setPreviewFaces((items) => {
                  const others = items.filter((item) => item.face !== preview.face);
                  return [...others, preview].sort((left, right) => left.face.localeCompare(right.face));
                });
              }
            } catch (e: any) {
              if (!cancelled) {
                setPreviewFaces((items) => items.map((item) => item.face === file.face ? {
                  ...item,
                  error: e?.response?.data?.detail || '本地预览生成失败，可稍后重试',
                } : item));
              }
            }
          }),
        );
      } catch (e: any) {
        if (!cancelled) {
          message.error(e?.response?.data?.detail || '加载卡牌基础信息失败');
          setDetailLoading(false);
        }
      }
    };
    loadDetail();
    return () => { cancelled = true; };
  }, [selectedId]);

  const toggleExpandedKey = useCallback((key: string) => {
    setExpandedKeys((keys) => keys.map(String).includes(key) ? keys.filter((item) => String(item) !== key) : [...keys, key]);
  }, []);

  const treeData = useMemo(
    () => toTreeData(tree, expandedKeys, toggleExpandedKey, titleFaceMode),
    [tree, expandedKeys, toggleExpandedKey, titleFaceMode],
  );
  const treeStats = useMemo(() => summarizeTree(tree), [tree]);
  const currentJson = modifiedJsonByFace[selectedFace] || '';
  const currentDiff = useMemo(() => {
    const original = draft?.original_faces?.[selectedFace] || fileContents[selectedFace] || {};
    const modified = parseObjectJson(currentJson);
    return buildErrataDiff(original, modified || {});
  }, [currentJson, draft, fileContents, selectedFace]);
  const jsonDecorations = useMemo(() => (
    buildJsonStringDecorations(currentJson, currentDiff.changedFields).map((item) => {
      const range = offsetRangeToMonacoRange(currentJson, item.startOffset, item.endOffset);
      const originalText = currentDiff.changedFields.find((field) => field.key === item.key)?.originalText || '无';
      return {
        startLineNumber: range.lineNumber,
        startColumn: range.column,
        endLineNumber: range.endLineNumber,
        endColumn: range.endColumn,
        className: item.kind === 'added' ? 'errata-json-diff-added' : 'errata-json-diff-changed',
        hoverMessage: `原始值：${originalText}`,
      };
    })
  ), [currentDiff.changedFields, currentJson]);
  const previewMap = Object.fromEntries(previewFaces.map((item) => [item.face, item]));
  const faces = detail?.local_files.map((file) => file.face) ?? [];
  const isSingleSided = detail?.is_single_sided ?? faces.length === 1;
  const primaryFace = faces[0] || 'a';
  const backOverride = detail?.back_overrides?.[primaryFace] || null;

  const cardContentForFace = (face: string) => {
    const json = modifiedJsonByFace[face];
    if (json) {
      try {
        return JSON.parse(json) as Record<string, unknown>;
      } catch {
        return fileContents[face] || {};
      }
    }
    return fileContents[face] || {};
  };

  const isHorizontalFace = (face: string) => {
    const content = cardContentForFace(face);
    const cardType = typeof content.type === 'string' ? content.type : '';
    return horizontalCardTypes.has(cardType);
  };

  const renderBackPresetStatus = () => (
    <Space direction="vertical" size={4} style={{ width: '100%' }}>
      <Text type="secondary">卡背设置仅在映射管理中维护；这里展示预发布结果</Text>
      {backOverride ? <Tag color="blue">发布将使用：{backOverride.label}</Tag> : <Tag>未设置发布卡背</Tag>}
    </Space>
  );

  const imageSlots = isSingleSided && primaryFace ? (() => {
    const englishMapping = detail?.image_mappings.find((item) => item.local_face === primaryFace && item.source === '英文');
    const chineseMapping = detail?.image_mappings.find((item) => item.local_face === primaryFace && item.source === '中文');
    const horizontal = isHorizontalFace(primaryFace);
    return [
      { key: `en-${primaryFace}-front`, title: `英文正面参考（${ttsSideLabel(englishMapping?.tts_side)}）`, url: englishMapping?.image_url || null, error: englishMapping?.status, horizontal, rotateCounterClockwise: horizontal },
      { key: `zh-${primaryFace}-front`, title: `中文正面现状（${ttsSideLabel(chineseMapping?.tts_side)}）`, url: chineseMapping?.image_url || null, error: chineseMapping?.status, horizontal, rotateCounterClockwise: horizontal },
      { key: `preview-${primaryFace}-front`, title: '本地预发布正面', url: withCacheBust(previewMap[primaryFace]?.preview_url, previewMap[primaryFace]?.cache_bust), error: previewMap[primaryFace]?.error, horizontal },
      { key: `en-${primaryFace}-back`, title: '英文卡背参考（只读）', url: englishMapping?.tts_id ? `/api/cards/tts-images/${englishMapping.tts_id}/back` : null, error: englishMapping?.status, horizontal, rotateCounterClockwise: horizontal },
      { key: `zh-${primaryFace}-back`, title: '中文卡背现状（只读）', url: chineseMapping?.tts_id ? `/api/cards/tts-images/${chineseMapping.tts_id}/back` : null, error: chineseMapping?.status, horizontal, rotateCounterClockwise: horizontal },
      { key: `preview-${primaryFace}-back`, title: '本地预发布卡背', url: backOverride?.back_url || null, error: '请选择发布用卡背', footer: renderBackPresetStatus() },
    ];
  })() : faces.flatMap((face) => {
    const englishMapping = detail?.image_mappings.find((item) => item.local_face === face && item.source === '英文');
    const chineseMapping = detail?.image_mappings.find((item) => item.local_face === face && item.source === '中文');
    const horizontal = isHorizontalFace(face);
    return [
      { key: `en-${face}`, title: `英文对齐图（本地${faceLabel(face)} → ${ttsSideLabel(englishMapping?.tts_side)}）`, url: englishMapping?.image_url || null, error: englishMapping?.status, horizontal, rotateCounterClockwise: horizontal },
      { key: `zh-${face}`, title: `中文替换目标（跟随 ${ttsSideLabel(chineseMapping?.tts_side)}）`, url: chineseMapping?.image_url || null, error: chineseMapping?.status, horizontal, rotateCounterClockwise: horizontal },
      { key: `preview-${face}`, title: `本地预发布 ${faceLabel(face)}`, url: withCacheBust(previewMap[face]?.preview_url, previewMap[face]?.cache_bust), error: previewMap[face]?.error, horizontal, footer: face === 'b' ? <Text type="secondary">双面卡背面由本地 .card 渲染，不需要卡背预设</Text> : undefined },
    ];
  });

  const handleUpdateFaceJson = useCallback((face: string, value: string) => {
    setModifiedJsonByFace((prev) => ({ ...prev, [face]: value }));
  }, []);

  const handleRenderSelected = async () => {
    if (!selectedId || !currentJson) return;
    setRendering(true);
    try {
      const content = JSON.parse(currentJson);
      const data = await previewCard(`${selectedId}_${selectedFace}`, content);
      setPreviewFaces((items) => {
        const next = items.filter((item) => item.face !== selectedFace);
        return [...next, { face: selectedFace, relative_path: '', preview_url: data.preview_url || data.preview_path, error: null, cache_bust: Date.now() }];
      });
      message.success('当前面渲染成功，右侧本地预发布图已刷新');
    } catch (e: any) {
      message.error(e?.response?.data?.detail || e?.message || 'JSON 格式错误或渲染失败');
    } finally {
      setRendering(false);
    }
  };

  const handleSubmit = async () => {
    if (!selectedId || !Object.keys(modifiedJsonByFace).length) return;
    try {
      const modifiedFaces = Object.fromEntries(
        Object.entries(modifiedJsonByFace).map(([face, value]) => [face, JSON.parse(value)]),
      );
      const changedFaces = Object.keys(modifiedFaces).filter((face) => JSON.stringify(modifiedFaces[face]) !== JSON.stringify(fileContents[face] || {}));
      const saved = await saveErrataDraft(selectedId, {
        modified_faces: modifiedFaces,
        changed_faces: changedFaces.length ? changedFaces : Object.keys(modifiedFaces),
        diff_summary: mode === 'review' ? '审核修改' : '保存勘误',
      });
      setDraft(saved);
      setPreviewFaces((items) => {
        const existing = Object.fromEntries(items.map((item) => [item.face, item]));
        return Object.entries(saved.rendered_previews).map(([face, previewUrl]) => ({
          face,
          relative_path: existing[face]?.relative_path || '',
          preview_url: previewUrl,
          error: previewUrl ? null : '勘误副本预览缺失',
          cache_bust: Date.now(),
        })).sort((left, right) => left.face.localeCompare(right.face));
      });
      try {
        setAuditLogs(await fetchErrataDraftLogs(selectedId));
      } catch {
        setAuditLogs([]);
      }
      message.success(mode === 'review' ? '审核修改已保存' : '勘误已保存');
      await loadTree(keyword);
    } catch (e: any) {
      message.error(e?.response?.data?.detail || e?.message || '保存失败');
    }
  };

  const handleCreatePackage = async () => {
    const ids = collectLeafKeys(tree);
    if (!ids.length) {
      message.warning('当前没有可打包的勘误卡牌');
      return;
    }
    setPackaging(true);
    try {
      const data = await createReviewPackage(ids);
      message.success(`已生成勘误包：${data.package.package_no}`);
      await loadTree(keyword);
    } catch (e: any) {
      message.error(e?.response?.data?.detail || '生成勘误包失败');
    } finally {
      setPackaging(false);
    }
  };

  const handleCancelErrata = async () => {
    if (!selectedId) return;
    Modal.confirm({
      title: '取消这张卡的勘误状态？',
      content: '这会将当前勘误副本归档，卡牌回到正常状态；历史操作日志会保留。',
      okText: '取消勘误',
      okButtonProps: { danger: true },
      cancelText: '返回',
      onOk: async () => {
        setCanceling(true);
        try {
          await cancelErrataDraft(selectedId, '审核员取消勘误状态');
          message.success('已取消勘误状态');
          setDraft(null);
          setAuditLogs([]);
          setSelectedId(null);
          await loadTree(keyword);
        } catch (e: any) {
          message.error(e?.response?.data?.detail || '取消勘误失败');
        } finally {
          setCanceling(false);
        }
      },
    });
  };

  return (
    <Layout style={{ minHeight: 'calc(100vh - 112px)', background: 'transparent' }}>
      <Sider width={430} theme="light" style={cardListPanelStyle}>
        <Space direction="vertical" size={12} style={{ width: '100%' }}>
          <Card size="small" styles={{ body: { padding: 12 } }} style={{ borderRadius: 12, background: 'linear-gradient(135deg, #f8fbff 0%, #eef6ff 100%)' }}>
            <Space direction="vertical" size={8} style={{ width: '100%' }}>
              <Space style={{ width: '100%', justifyContent: 'space-between' }}>
                <Text strong>{titleForMode(mode)}</Text>
                <Tag color="blue">{treeStats.total} 张</Tag>
              </Space>
              <Space size={4} wrap>
                <Tag color="processing">勘误 {treeStats.pending}</Tag>
                <Tag color="warning">待发布 {treeStats.approved}</Tag>
              </Space>
            </Space>
          </Card>
          <Input.Search
            placeholder="搜索卡名、编号、文件名、内容或遭遇组"
            allowClear
            value={keyword}
            onChange={(e) => setKeyword(e.target.value)}
            onSearch={(value) => loadTree(value)}
            enterButton="搜索"
          />
          <Space.Compact block>
            <Button onClick={() => setExpandedKeys(collectExpandableKeys(tree))}>全部展开</Button>
            <Button onClick={() => setExpandedKeys([])}>全部收起</Button>
            <Button onClick={() => loadTree(keyword)} loading={treeLoading}>刷新</Button>
          </Space.Compact>
          <Segmented
            block
            value={titleFaceMode}
            onChange={(value) => setTitleFaceMode(value as CardTitleFaceMode)}
            options={[
              { label: '显示正面标题', value: 'front' },
              { label: '显示背面标题', value: 'back' },
            ]}
          />
          {mode === 'review' && (
            <Button type="primary" block loading={packaging} onClick={handleCreatePackage}>
              将当前列表生成勘误包
            </Button>
          )}
          <Spin spinning={treeLoading}>
            <Tree
              blockNode
              treeData={treeData}
              selectedKeys={selectedId ? [selectedId] : []}
              expandedKeys={expandedKeys}
              onExpand={(keys) => setExpandedKeys(keys)}
              onSelect={(keys) => {
                const key = String(keys[0] || '');
                if (key && findCard(tree, key)) setSelectedId(key);
              }}
              height={650}
            />
          </Spin>
        </Space>
      </Sider>
      <Content style={{ paddingLeft: 16 }}>
        {!selectedId ? (
          <Empty description="请选择左侧卡牌" />
        ) : detailLoading ? (
          <Spin style={{ display: 'block', margin: '100px auto' }} />
        ) : detail ? (
          <Space direction="vertical" size={16} style={{ width: '100%' }}>
            <Card>
              <Space direction="vertical" style={{ width: '100%' }}>
                <Space wrap>
                  <Title level={4} style={{ margin: 0 }}>{detail.index.name_zh || selectedId}</Title>
                  <Text type="secondary">{selectedId}</Text>
                </Space>
                <Space wrap>
                  <Tag color={draft?.status === '待发布' ? 'warning' : draft ? 'processing' : 'success'}>{draft?.status || '正常'}</Tag>
                  {draft?.participant_usernames.map((name) => <Tag key={name}>{name}</Tag>)}
                </Space>
                <CardComparison images={imageSlots} />
              </Space>
            </Card>
            <Card
              title={`编辑 ${faceLabel(selectedFace)}`}
              extra={
                <Space>
                  {faces.map((face) => (
                    <Button key={face} type={face === selectedFace ? 'primary' : 'default'} onClick={() => setSelectedFace(face)}>
                      {faceLabel(face)}
                    </Button>
                  ))}
                  <Button onClick={() => setSymbolHelpOpen(true)}>符号参考</Button>
                  <Button type="primary" onClick={handleRenderSelected} loading={rendering}>校验渲染</Button>
                  {mode === 'review' && draft?.status === '勘误' && (
                    <Button danger onClick={handleCancelErrata} loading={canceling}>取消勘误状态</Button>
                  )}
                  <Button danger type="primary" onClick={handleSubmit} disabled={draft?.status === '待发布'}>{mode === 'review' ? '保存审核修改' : '保存勘误'}</Button>
                </Space>
              }
            >
              <ErrataDiffPanel fields={currentDiff.changedFields} />
              <CardTextFieldsEditor
                selectedFace={selectedFace}
                jsonByFace={modifiedJsonByFace}
                onFaceJsonChange={handleUpdateFaceJson}
                changedFieldKeys={currentDiff.changedFieldKeys}
              />
              <JsonEditor
                value={currentJson}
                onChange={(value) => handleUpdateFaceJson(selectedFace, value)}
                height="360px"
                decorations={jsonDecorations}
              />
            </Card>
            {auditLogs.length > 0 && (
              <Card title="操作日志" size="small">
                <Space direction="vertical" size={6}>
                  {auditLogs.map((log) => (
                    <Text key={log.id}>
                      {log.created_at} · {log.username} · {log.action}{log.diff_summary ? `：${log.diff_summary}` : ''}
                    </Text>
                  ))}
                </Space>
              </Card>
            )}
          </Space>
        ) : null}
      </Content>
      <SymbolReferenceHelp open={symbolHelpOpen} onClose={() => setSymbolHelpOpen(false)} />
    </Layout>
  );
}
