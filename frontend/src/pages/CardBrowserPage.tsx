import { useCallback, useEffect, useMemo, useState } from 'react';
import { Button, Card, Empty, Input, Layout, message, Space, Spin, Tag, Tree, Typography } from 'antd';
import type { DataNode } from 'antd/es/tree';
import { fetchCardDetail, fetchCardTree, previewAllFaces } from '../api/cards';
import { fetchCardFileContent, previewCard, submitErrata } from '../api/errata';
import CardComparison from '../components/CardComparison';
import JsonEditor from '../components/JsonEditor';
import type { CardDetail, CardTreeNode, PreviewFace } from '../types';

const { Sider, Content } = Layout;
const { Text, Title } = Typography;

function collectLeafKeys(nodes: CardTreeNode[]): string[] {
  return nodes.flatMap((node) => node.children?.length ? collectLeafKeys(node.children) : [node.key]);
}

function toTreeData(nodes: CardTreeNode[]): DataNode[] {
  return nodes.map((node) => ({
    key: node.key,
    title: node.card ? `${node.card.arkhamdb_id} ${node.card.name_zh || node.card.name_en}` : node.title,
    children: node.children ? toTreeData(node.children) : undefined,
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

export default function CardBrowserPage() {
  const [tree, setTree] = useState<CardTreeNode[]>([]);
  const [expandedKeys, setExpandedKeys] = useState<React.Key[]>([]);
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

  const loadTree = useCallback(async (search?: string) => {
    setTreeLoading(true);
    try {
      const data = await fetchCardTree(search);
      setTree(data.tree);
      if (search) setExpandedKeys(collectLeafKeys(data.tree));
      if (!selectedId && data.tree.length > 0) {
        const firstLeaf = collectLeafKeys(data.tree)[0];
        if (firstLeaf) setSelectedId(String(firstLeaf));
      }
    } finally {
      setTreeLoading(false);
    }
  }, [selectedId]);

  useEffect(() => { loadTree(); }, [loadTree]);

  useEffect(() => {
    if (!selectedId) return;
    let cancelled = false;
    const loadDetail = async () => {
      setDetailLoading(true);
      try {
        const cardDetail = await fetchCardDetail(selectedId);
        if (cancelled) return;
        setDetail(cardDetail);
        const contents: Record<string, Record<string, unknown>> = {};
        const jsonByFace: Record<string, string> = {};
        for (const file of cardDetail.local_files) {
          const data = await fetchCardFileContent(selectedId, file.face);
          if (cancelled) return;
          contents[file.face] = data.content;
          jsonByFace[file.face] = JSON.stringify(data.content, null, 2);
        }
        setFileContents(contents);
        setModifiedJsonByFace(jsonByFace);
        setSelectedFace(cardDetail.local_files[0]?.face || 'a');
        const previews = await previewAllFaces(selectedId);
        if (!cancelled) setPreviewFaces(previews.items);
      } catch (e: any) {
        message.error(e?.response?.data?.detail || '加载卡牌失败');
      } finally {
        if (!cancelled) setDetailLoading(false);
      }
    };
    loadDetail();
    return () => { cancelled = true; };
  }, [selectedId]);

  const treeData = useMemo(() => toTreeData(tree), [tree]);
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
      { key: `preview-${primaryFace}-front`, title: '本地预发布正面', url: previewMap[primaryFace]?.preview_url || null, error: previewMap[primaryFace]?.error },
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
      { key: `preview-${face}`, title: `本地预发布 ${faceLabel(face)}`, url: previewMap[face]?.preview_url || null, error: previewMap[face]?.error, footer: face === 'b' ? <Text type="secondary">双面卡背面由本地 .card 渲染，不需要卡背预设</Text> : undefined },
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
        return [...next, { face: selectedFace, relative_path: '', preview_url: data.preview_url || data.preview_path, error: null }];
      });
      message.success('当前面渲染成功');
    } catch (e: any) {
      message.error(e?.response?.data?.detail || e?.message || 'JSON 格式错误或渲染失败');
    } finally {
      setRendering(false);
    }
  };

  const handleSubmit = async () => {
    if (!selectedId || !fileContents[selectedFace] || !currentJson) return;
    try {
      const modified = JSON.parse(currentJson);
      await submitErrata({
        arkhamdb_id: selectedId,
        original_content: fileContents[selectedFace],
        modified_content: modified,
      });
      message.success('勘误已提交，等待审核');
    } catch (e: any) {
      message.error(e?.response?.data?.detail || '提交失败');
    }
  };

  return (
    <Layout style={{ minHeight: 'calc(100vh - 112px)', background: 'transparent' }}>
      <Sider width={360} theme="light" style={{ padding: 12, borderRadius: 8, overflow: 'auto', maxHeight: 'calc(100vh - 120px)' }}>
        <Space direction="vertical" style={{ width: '100%' }}>
          <Input.Search
            placeholder="搜索内容、卡名、编号或文件名"
            allowClear
            value={keyword}
            onChange={(e) => setKeyword(e.target.value)}
            onSearch={(value) => loadTree(value)}
          />
          <Button block onClick={() => loadTree(keyword)} loading={treeLoading}>刷新列表</Button>
          <Spin spinning={treeLoading}>
            <Tree
              treeData={treeData}
              selectedKeys={selectedId ? [selectedId] : []}
              expandedKeys={expandedKeys}
              onExpand={setExpandedKeys}
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
                  <Button danger type="primary" onClick={handleSubmit}>提交勘误</Button>
                </Space>
              }
            >
              <JsonEditor
                value={currentJson}
                onChange={(value) => setModifiedJsonByFace((prev) => ({ ...prev, [selectedFace]: value }))}
                height="520px"
              />
            </Card>
          </Space>
        ) : null}
      </Content>
    </Layout>
  );
}
