import { useCallback, useEffect, useMemo, useState } from 'react';
import { Button, Card, Col, Empty, Image, Input, Layout, message, Row, Select, Space, Spin, Table, Tag, Tree, Typography } from 'antd';
import type { ColumnsType } from 'antd/es/table';
import type { DataNode } from 'antd/es/tree';
import { fetchCardTree, previewAllFaces } from '../api/cards';
import { bindTTSMapping, clearBackOverride, confirmTTSMapping, fetchBackPresets, fetchMappingDetail, searchTTSCandidates, setBackOverride, unbindTTSMapping } from '../api/admin';
import type { CardBackPreset, CardTreeNode, MappingDetail, PreviewFace, TTSCardImage, TTSImageMapping } from '../types';

const { Sider, Content } = Layout;
const { Text, Title } = Typography;
type Side = 'front' | 'back';

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

function sideLabel(side: string) {
  return side === 'back' ? 'TTS 对象背面' : 'TTS 对象正面';
}

function englishMappingFor(detail: MappingDetail | null, face: string): TTSImageMapping | undefined {
  return detail?.image_mappings.find((item) => item.local_face === face && item.source === '英文');
}

export default function MappingPage() {
  const [tree, setTree] = useState<CardTreeNode[]>([]);
  const [expandedKeys, setExpandedKeys] = useState<React.Key[]>([]);
  const [keyword, setKeyword] = useState('');
  const [treeLoading, setTreeLoading] = useState(false);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [detail, setDetail] = useState<MappingDetail | null>(null);
  const [previews, setPreviews] = useState<PreviewFace[]>([]);
  const [detailLoading, setDetailLoading] = useState(false);
  const [localFace, setLocalFace] = useState('a');
  const [candidateKeyword, setCandidateKeyword] = useState('');
  const [backPresets, setBackPresets] = useState<CardBackPreset[]>([]);
  const [candidates, setCandidates] = useState<TTSCardImage[]>([]);
  const [candidateLoading, setCandidateLoading] = useState(false);

  const loadTree = useCallback(async (search?: string) => {
    setTreeLoading(true);
    try {
      const data = await fetchCardTree({ keyword: search });
      setTree(data.tree);
      if (search) setExpandedKeys(collectLeafKeys(data.tree));
      if (!selectedId) {
        const firstLeaf = collectLeafKeys(data.tree)[0];
        if (firstLeaf) setSelectedId(String(firstLeaf));
      }
    } finally {
      setTreeLoading(false);
    }
  }, [selectedId]);

  const loadDetail = useCallback(async (arkhamdbId: string) => {
    setDetailLoading(true);
    try {
      const [mapping, previewData] = await Promise.all([
        fetchMappingDetail(arkhamdbId),
        previewAllFaces(arkhamdbId),
      ]);
      setDetail(mapping);
      setPreviews(previewData.items);
      setLocalFace(mapping.local_files[0]?.face || 'a');
    } catch (e: any) {
      message.error(e?.response?.data?.detail || '加载映射失败');
    } finally {
      setDetailLoading(false);
    }
  }, []);

  const loadCandidates = useCallback(async () => {
    setCandidateLoading(true);
    try {
      const data = await searchTTSCandidates({ source: '英文', keyword: candidateKeyword || selectedId || undefined, limit: 80 });
      setCandidates(data.items);
    } catch (e: any) {
      message.error(e?.response?.data?.detail || '搜索英文 TTS 失败');
    } finally {
      setCandidateLoading(false);
    }
  }, [candidateKeyword, selectedId]);

  useEffect(() => { loadTree(); }, [loadTree]);
  useEffect(() => {
    fetchBackPresets()
      .then((data) => setBackPresets(data.items))
      .catch(() => setBackPresets([]));
  }, []);
  useEffect(() => { if (selectedId) loadDetail(selectedId); }, [loadDetail, selectedId]);
  useEffect(() => { if (selectedId) loadCandidates(); }, [loadCandidates, selectedId]);

  const treeData = useMemo(() => toTreeData(tree), [tree]);
  const previewMap = Object.fromEntries(previews.map((item) => [item.face, item]));
  const selectedCard = selectedId ? findCard(tree, selectedId) : null;
  const faces = detail?.local_files.map((file) => file.face) ?? [];
  const isSingleSided = detail?.is_single_sided ?? faces.length === 1;
  const primaryFace = faces[0] || 'a';
  const backOverride = detail?.back_overrides?.[primaryFace] || null;

  const refreshMapping = async () => {
    if (selectedId) await loadDetail(selectedId);
  };

  const handleBind = async (ttsId: number, side: Side) => {
    if (!selectedId) return;
    await bindTTSMapping({ arkhamdb_id: selectedId, local_face: localFace, source: '英文', tts_id: ttsId, tts_side: side });
    message.success(`已将本地${faceLabel(localFace)}对齐到 ${sideLabel(side)}`);
    await refreshMapping();
  };

  const handleUnbind = async () => {
    if (!selectedId) return;
    await unbindTTSMapping({ arkhamdb_id: selectedId, local_face: localFace, source: '英文' });
    message.success(`已解除本地${faceLabel(localFace)}的英文对齐`);
    await refreshMapping();
  };

  const handleConfirm = async () => {
    if (!selectedId) return;
    const data = await confirmTTSMapping(selectedId);
    setDetail(data);
    message.success('已确认本地 .card 与英文卡图对齐关系');
  };

  const handleBackPresetChange = async (presetKey?: string) => {
    if (!selectedId || !primaryFace) return;
    try {
      const data = presetKey
        ? await setBackOverride(selectedId, primaryFace, presetKey)
        : await clearBackOverride(selectedId, primaryFace);
      setDetail(data);
      message.success(presetKey ? '已设置本地预发布卡背' : '已清除本地预发布卡背');
    } catch (e: any) {
      message.error(e?.response?.data?.detail || '保存卡背预设失败');
    }
  };

  const columns: ColumnsType<TTSCardImage> = [
    { title: 'GMNotes.id', dataIndex: 'arkhamdb_id', width: 110 },
    { title: 'CardID', dataIndex: 'card_id', width: 95 },
    { title: '对象文件', dataIndex: 'relative_json_path', ellipsis: true },
    {
      title: '英文正面', width: 150,
      render: (_, item) => <Image width={90} src={`/api/cards/tts-images/${item.id}/front`} />,
    },
    {
      title: '对象背面/共享背', width: 150,
      render: (_, item) => <Image width={90} src={`/api/cards/tts-images/${item.id}/back`} />,
    },
    {
      title: `对齐到本地${faceLabel(localFace)}`, width: 190,
      render: (_, item) => (
        <Space direction="vertical">
          <Button size="small" type="primary" onClick={() => handleBind(item.id, 'front')}>本地面对齐对象正面</Button>
          <Button size="small" onClick={() => handleBind(item.id, 'back')}>本地面对齐对象背面</Button>
        </Space>
      ),
    },
  ];

  return (
    <Layout style={{ minHeight: 'calc(100vh - 112px)', background: 'transparent' }}>
      <Sider width={360} theme="light" style={{ padding: 12, borderRadius: 8, overflow: 'auto', maxHeight: 'calc(100vh - 120px)' }}>
        <Space direction="vertical" style={{ width: '100%' }}>
          <Input.Search placeholder="搜索内容、卡名、编号或文件名" allowClear value={keyword} onChange={(e) => setKeyword(e.target.value)} onSearch={(value) => loadTree(value)} />
          <Button block onClick={() => loadTree(keyword)} loading={treeLoading}>刷新卡牌树</Button>
          <Spin spinning={treeLoading}>
            <Tree treeData={treeData} selectedKeys={selectedId ? [selectedId] : []} expandedKeys={expandedKeys} onExpand={setExpandedKeys} onSelect={(keys) => {
              const key = String(keys[0] || '');
              if (key && findCard(tree, key)) setSelectedId(key);
            }} height={650} />
          </Spin>
        </Space>
      </Sider>
      <Content style={{ paddingLeft: 16 }}>
        {!selectedId ? <Empty description="请选择左侧卡牌" /> : detailLoading ? <Spin style={{ display: 'block', margin: '100px auto' }} /> : (
          <Space direction="vertical" size={16} style={{ width: '100%' }}>
            <Card>
              <Space direction="vertical" style={{ width: '100%' }}>
                <Space wrap>
                  <Title level={4} style={{ margin: 0 }}>{selectedCard?.name_zh || selectedId}</Title>
                  <Text type="secondary">{selectedId}</Text>
                  <Tag color={detail?.confirmed ? 'green' : 'orange'}>{detail?.confirmed ? '英文对齐已确认' : '英文对齐未确认'}</Tag>
                  <Text type="secondary">索引：{detail?.index_path}</Text>
                </Space>
                <Text type="secondary">这里先确认“本地渲染面”和“英文 GMNotes.id 对象的某一面”是否一致；英文和中文都是只读参考，只有本地预发布结果会被保存为发布依据。</Text>
              </Space>
            </Card>
            <Row gutter={[12, 12]}>
              {faces.map((face) => {
                const mapping = englishMappingFor(detail, face);
                return (
                  <Col span={12} key={face}>
                    <Card size="small" title={`本地 ${faceLabel(face)} ↔ 英文卡图`} extra={<Tag>{mapping?.status || '未找到'}</Tag>}>
                      <Row gutter={12} align="middle">
                        <Col span={12} style={{ textAlign: 'center' }}>
                          <Text strong>本地渲染 {faceLabel(face)}</Text>
                          <div style={{ minHeight: 260, marginTop: 8 }}>
                            {previewMap[face]?.preview_url ? <Image width={180} src={previewMap[face].preview_url!} /> : <Empty description={previewMap[face]?.error || '暂无本地渲染'} />}
                          </div>
                        </Col>
                        <Col span={12} style={{ textAlign: 'center' }}>
                          <Text strong>{mapping?.tts_side ? sideLabel(mapping.tts_side) : '英文卡图'}</Text>
                          <div style={{ minHeight: 260, marginTop: 8 }}>
                            {mapping?.image_url ? <Image width={180} src={mapping.image_url} /> : <Empty description="未绑定英文卡图" />}
                          </div>
                          {mapping?.relative_json_path && <Text type="secondary" ellipsis style={{ display: 'block' }}>{mapping.relative_json_path}</Text>}
                        </Col>
                      </Row>
                    </Card>
                  </Col>
                );
              })}
            </Row>
            <Card title="单面卡本地预发布卡背">
              {isSingleSided ? (
                <Space direction="vertical" style={{ width: '100%' }}>
                  <Text type="secondary">该设置只作用于右侧本地预发布结果；英文和中文参考图不会被修改。</Text>
                  <Select
                    allowClear
                    placeholder="选择发布用卡背"
                    value={backOverride?.preset_key}
                    onChange={(value) => handleBackPresetChange(value)}
                    style={{ width: 280 }}
                    options={backPresets.map((preset) => ({ label: preset.label, value: preset.key }))}
                  />
                  {backOverride ? <Tag color="blue">发布将使用：{backOverride.label}</Tag> : <Tag>未设置发布卡背</Tag>}
                </Space>
              ) : (
                <Text type="secondary">该卡为双面卡，背面由本地 .card 文件渲染，不需要卡背预设。</Text>
              )}
            </Card>
            <Card title="选择英文 TTS 对象并对齐到本地面" extra={<Button type="primary" onClick={handleConfirm}>确认本卡英文对齐</Button>}>
              <Space wrap style={{ marginBottom: 12 }}>
                {faces.map((face) => <Button key={face} type={face === localFace ? 'primary' : 'default'} onClick={() => setLocalFace(face)}>当前本地面：{faceLabel(face)}</Button>)}
                <Button danger onClick={handleUnbind}>解除当前本地面的英文对齐</Button>
              </Space>
              <Input.Search placeholder="搜索英文 GMNotes.id、名称、路径或 CardID" allowClear value={candidateKeyword} onChange={(e) => setCandidateKeyword(e.target.value)} onSearch={loadCandidates} enterButton="搜索英文候选" style={{ marginBottom: 12 }} />
              <Table rowKey="id" size="small" columns={columns} dataSource={candidates} loading={candidateLoading} pagination={{ pageSize: 10 }} />
            </Card>
          </Space>
        )}
      </Content>
    </Layout>
  );
}
