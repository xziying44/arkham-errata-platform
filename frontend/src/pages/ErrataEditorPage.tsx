import { useState, useEffect } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { Card, Button, Select, Space, message, Spin } from 'antd';
import { fetchCardDetail } from '../api/cards';
import { fetchCardFileContent, previewCard, submitErrata } from '../api/errata';
import CardComparison from '../components/CardComparison';
import JsonEditor from '../components/JsonEditor';
import type { CardDetail } from '../types';

/** 勘误编辑器页面：三栏卡图对比 + JSON 编辑器 */
export default function ErrataEditorPage() {
  const { arkhamdbId } = useParams<{ arkhamdbId: string }>();
  const [detail, setDetail] = useState<CardDetail | null>(null);
  const [selectedFace, setSelectedFace] = useState<string>('a');
  const [fileContent, setFileContent] = useState<Record<string, unknown> | null>(null);
  const [modifiedJson, setModifiedJson] = useState('');
  const [previewUrl, setPreviewUrl] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [rendering, setRendering] = useState(false);
  const navigate = useNavigate();

  useEffect(() => {
    if (!arkhamdbId) return;
    setLoading(true);
    fetchCardDetail(arkhamdbId)
      .then((d) => {
        setDetail(d);
        const faces = d.local_files.map((f) => f.face);
        if (faces.length > 0) setSelectedFace(faces[0]);
      })
      .finally(() => setLoading(false));
  }, [arkhamdbId]);

  useEffect(() => {
    if (!arkhamdbId || !selectedFace) return;
    fetchCardFileContent(arkhamdbId, selectedFace).then((data) => {
      setFileContent(data.content);
      setModifiedJson(JSON.stringify(data.content, null, 2));
      setPreviewUrl(null);
    });
  }, [arkhamdbId, selectedFace]);

  const handlePreview = async () => {
    if (!arkhamdbId || !modifiedJson) return;
    setRendering(true);
    try {
      const content = JSON.parse(modifiedJson);
      const data = await previewCard(arkhamdbId, content);
      setPreviewUrl(data.preview_path);
      message.success('预览生成成功');
    } catch (e: any) {
      message.error(e?.message || 'JSON 格式错误或渲染失败');
    } finally {
      setRendering(false);
    }
  };

  const handleSubmit = async () => {
    if (!arkhamdbId || !fileContent || !modifiedJson) return;
    try {
      const modified = JSON.parse(modifiedJson);
      await submitErrata({
        arkhamdb_id: arkhamdbId,
        original_content: fileContent,
        modified_content: modified,
      });
      message.success('勘误已提交，等待审核');
      navigate('/my-errata');
    } catch (e: any) {
      message.error(e?.response?.data?.detail || '提交失败');
    }
  };

  if (loading)
    return <Spin style={{ display: 'block', margin: '100px auto' }} />;

  return (
    <div>
      <Card
        title={`${detail?.index.name_zh || arkhamdbId} — 勘误编辑`}
        style={{ marginBottom: 16 }}
      >
        <Space style={{ marginBottom: 16 }}>
          <Select
            value={selectedFace}
            onChange={setSelectedFace}
            style={{ width: 100 }}
            options={detail?.local_files.map((f) => ({
              value: f.face,
              label: `面 ${f.face}`,
            }))}
          />
        </Space>
        <CardComparison
          englishImageUrl={
            detail?.tts_en?.cached_front_path
              ? `/static/cache/${detail.tts_en.cached_front_path.split('/').pop()}`
              : null
          }
          chineseImageUrl={
            detail?.tts_zh?.cached_front_path
              ? `/static/cache/${detail.tts_zh.cached_front_path.split('/').pop()}`
              : null
          }
          previewImageUrl={previewUrl}
        />
      </Card>
      <Card
        title="卡牌 JSON 编辑器"
        extra={
          <Space>
            <Button type="primary" onClick={handlePreview} loading={rendering}>
              预览渲染
            </Button>
            <Button type="primary" danger onClick={handleSubmit}>
              提交勘误
            </Button>
          </Space>
        }
      >
        <JsonEditor value={modifiedJson} onChange={setModifiedJson} height="500px" />
      </Card>
    </div>
  );
}
