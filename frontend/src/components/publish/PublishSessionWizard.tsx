import { Button, Card, Space, Steps, Typography, message } from 'antd';
import { useEffect, useState } from 'react';
import { fetchReplacementPreview, generateSessionSheets } from '../../api/admin';
import type { PublishSession, ReplacementPreviewItem } from '../../types';
import SheetPreviewPanel from './SheetPreviewPanel';
import UrlMappingTable from './UrlMappingTable';

interface PublishSessionWizardProps {
  session: PublishSession | null;
  onSessionChange: (session: PublishSession) => void;
}

const stepIndex: Record<string, number> = {
  select_package: 0,
  confirm_sheets: 1,
  prepare_urls: 2,
  export_patch: 3,
  complete: 4,
};

export default function PublishSessionWizard({ session, onSessionChange }: PublishSessionWizardProps) {
  const [loading, setLoading] = useState(false);
  const [previewItems, setPreviewItems] = useState<ReplacementPreviewItem[]>([]);

  useEffect(() => {
    if (!session || session.current_step !== 'export_patch') return;
    fetchReplacementPreview(session.id).then((data) => setPreviewItems(data.items || [])).catch(() => setPreviewItems([]));
  }, [session]);

  if (!session) return <Typography.Text type="secondary">请选择待发布勘误包并创建发布会话</Typography.Text>;

  const handleGenerate = async () => {
    setLoading(true);
    try {
      const next = await generateSessionSheets(session.id);
      onSessionChange(next);
      message.success('精灵图已生成');
    } catch (error: any) {
      message.error(error?.response?.data?.detail || '生成精灵图失败');
    } finally {
      setLoading(false);
    }
  };

  return (
    <Space direction="vertical" style={{ width: '100%' }} size={16}>
      <Steps current={stepIndex[session.current_step] || 0} items={[{ title: '选择包' }, { title: '精灵图' }, { title: 'URL' }, { title: '补丁包' }, { title: '完成' }]} />
      <Card size="small" title={`发布会话 #${session.id} · ${session.status}`}>
        {session.current_step === 'select_package' && <Button type="primary" loading={loading} onClick={handleGenerate}>生成精灵图</Button>}
        {session.current_step === 'confirm_sheets' && <SheetPreviewPanel artifacts={session.artifacts} />}
        {session.current_step === 'export_patch' && <UrlMappingTable items={previewItems} />}
      </Card>
    </Space>
  );
}
