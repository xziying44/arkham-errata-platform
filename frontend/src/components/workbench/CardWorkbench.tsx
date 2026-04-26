import { useCallback, useEffect, useMemo, useState } from 'react';
import type { Key, ReactNode } from 'react';
import { FolderOpenOutlined, FolderOutlined } from '@ant-design/icons';
import { Button, Card, Empty, Input, Layout, message, Space, Spin, Tag, Tree, Typography } from 'antd';
import type { DataNode } from 'antd/es/tree';
import { fetchCardDetail, fetchCardTree, previewAllFaces } from '../../api/cards';
import { fetchCardFileContent, previewCard } from '../../api/errata';
import CardComparison from '../CardComparison';
import JsonEditor from '../JsonEditor';
import type { CardDetail, CardTreeCard, CardTreeNode, ErrataAuditLog, ErrataDraft, PreviewFace, WorkbenchMode } from '../../types';
import { fetchErrataDraft, fetchErrataDraftLogs, saveErrataDraft } from '../../api/errataDrafts';
import { createReviewPackage } from '../../api/packages';

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

function renderCardTitle(card: CardTreeCard) {
  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: 6, width: '100%', minWidth: 0 }}>
      <Tag color="geekblue" style={{ marginInlineEnd: 0, flex: '0 0 auto' }}>{card.arkhamdb_id}</Tag>
      <Text strong ellipsis style={{ flex: '1 1 auto', minWidth: 0 }}>{card.name_zh || card.name_en || '未命名卡牌'}</Text>
      <Space size={4} style={{ flex: '0 0 auto' }}>
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
): DataNode[] {
  const expanded = new Set(expandedKeys.map(String));
  return nodes.map((node) => ({
    key: node.key,
    title: node.card ? renderCardTitle(node.card) : renderGroupTitle(node, expanded.has(node.key), onToggle),
    children: node.children ? toTreeData(node.children, expandedKeys, onToggle) : undefined,
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

  const loadTree = useCallback(async (search?: string) => {
    setTreeLoading(true);
    try {
      const data = await fetchCardTree({ keyword: search, scope: scopeForMode(mode), package_id: packageId });
      setTree(data.tree);
      if (search) setExpandedKeys(collectExpandableKeys(data.tree));
      if (!selectedId && data.tree.length > 0) {
        const firstLeaf = collectLeafKeys(data.tree)[0];
        if (firstLeaf) setSelectedId(String(firstLeaf));
      }
    } finally {
      setTreeLoading(false);
    }
  }, [selectedId, mode, packageId]);

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
        setDetailLoading(false);

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
        try {
          const currentDraft = await fetchErrataDraft(selectedId);
          if (!cancelled && currentDraft) {
            setDraft(currentDraft);
            currentJsonByFace = Object.fromEntries(
              Object.entries(currentDraft.modified_faces).map(([face, content]) => [face, JSON.stringify(content, null, 2)]),
            );
          }
        } catch (e: any) {
          if (!cancelled) message.warning(e?.response?.data?.detail || '勘误副本读取失败');
        }
        setFileContents(contents);
        setModifiedJsonByFace(currentJsonByFace);
        try {
          const logs = await fetchErrataDraftLogs(selectedId);
          if (!cancelled) setAuditLogs(logs);
        } catch {
          if (!cancelled) setAuditLogs([]);
        }
        if (fileResults.some((result) => result.status === 'rejected')) {
          message.warning('部分 .card 文件读取失败，可稍后重试');
        }

        try {
          const previews = await previewAllFaces(selectedId);
          if (!cancelled) setPreviewFaces(previews.items);
        } catch (e: any) {
          if (!cancelled) {
            message.warning(e?.response?.data?.detail || '本地预览仍在生成或暂时失败，不影响编辑');
          }
        }
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

  const treeData = useMemo(() => toTreeData(tree, expandedKeys, toggleExpandedKey), [tree, expandedKeys, toggleExpandedKey]);
  const treeStats = useMemo(() => summarizeTree(tree), [tree]);
  const currentJson = modifiedJsonByFace[selectedFace] || '';
  const previewMap = Object.fromEntries(previewFaces.map((item) => [item.face, item]));
  const faces = detail?.local_files.map((file) => file.face) ?? [];
  const isSingleSided = detail?.is_single_sided ?? faces.length === 1;
  const primaryFace = faces[0] || 'a';
  const backOverride = detail?.back_overrides?.[primaryFace] || null;

  const renderBackPresetStatus = () => (
    <Space direction="vertical" size={4} style={{ width: '100%' }}>
      <Text type="secondary">卡背设置仅在映射管理中维护；这里展示预发布结果</Text>
      {backOverride ? <Tag color="blue">发布将使用：{backOverride.label}</Tag> : <Tag>未设置发布卡背</Tag>}
    </Space>
  );

  const imageSlots = isSingleSided && primaryFace ? (() => {
    const englishMapping = detail?.image_mappings.find((item) => item.local_face === primaryFace && item.source === '英文');
    const chineseMapping = detail?.image_mappings.find((item) => item.local_face === primaryFace && item.source === '中文');
    return [
      { key: `en-${primaryFace}-front`, title: `英文正面参考（${ttsSideLabel(englishMapping?.tts_side)}）`, url: englishMapping?.image_url || null, error: englishMapping?.status },
      { key: `zh-${primaryFace}-front`, title: `中文正面现状（${ttsSideLabel(chineseMapping?.tts_side)}）`, url: chineseMapping?.image_url || null, error: chineseMapping?.status },
      { key: `preview-${primaryFace}-front`, title: '本地预发布正面', url: withCacheBust(previewMap[primaryFace]?.preview_url, previewMap[primaryFace]?.cache_bust), error: previewMap[primaryFace]?.error },
      { key: `en-${primaryFace}-back`, title: '英文卡背参考（只读）', url: englishMapping?.tts_id ? `/api/cards/tts-images/${englishMapping.tts_id}/back` : null, error: englishMapping?.status },
      { key: `zh-${primaryFace}-back`, title: '中文卡背现状（只读）', url: chineseMapping?.tts_id ? `/api/cards/tts-images/${chineseMapping.tts_id}/back` : null, error: chineseMapping?.status },
      { key: `preview-${primaryFace}-back`, title: '本地预发布卡背', url: backOverride?.back_url || null, error: '请选择发布用卡背', footer: renderBackPresetStatus() },
    ];
  })() : faces.flatMap((face) => {
    const englishMapping = detail?.image_mappings.find((item) => item.local_face === face && item.source === '英文');
    const chineseMapping = detail?.image_mappings.find((item) => item.local_face === face && item.source === '中文');
    return [
      { key: `en-${face}`, title: `英文对齐图（本地${faceLabel(face)} → ${ttsSideLabel(englishMapping?.tts_side)}）`, url: englishMapping?.image_url || null, error: englishMapping?.status },
      { key: `zh-${face}`, title: `中文替换目标（跟随 ${ttsSideLabel(chineseMapping?.tts_side)}）`, url: chineseMapping?.image_url || null, error: chineseMapping?.status },
      { key: `preview-${face}`, title: `本地预发布 ${faceLabel(face)}`, url: withCacheBust(previewMap[face]?.preview_url, previewMap[face]?.cache_bust), error: previewMap[face]?.error, footer: face === 'b' ? <Text type="secondary">双面卡背面由本地 .card 渲染，不需要卡背预设</Text> : undefined },
    ];
  });

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
            placeholder="搜索内容、卡名、编号或文件名"
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
                  <Button type="primary" onClick={handleRenderSelected} loading={rendering}>校验渲染</Button>
                  <Button danger type="primary" onClick={handleSubmit} disabled={draft?.status === '待发布'}>{mode === 'review' ? '保存审核修改' : '保存勘误'}</Button>
                </Space>
              }
            >
              <JsonEditor
                value={currentJson}
                onChange={(value) => setModifiedJsonByFace((prev) => ({ ...prev, [selectedFace]: value }))}
                height="520px"
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
    </Layout>
  );
}
