import { Button, Card, Descriptions, Popconfirm, Space, Steps, Table, Typography, Upload, message } from 'antd';
import type { ColumnsType } from 'antd/es/table';
import { useEffect, useState } from 'react';
import {
  confirmSessionSheets,
  exportSessionPatch,
  exportSessionTTSBag,
  fetchReplacementPreview,
  fetchSessionSheetUrls,
  generateSessionSheets,
  rollbackPublishSessionStep,
  uploadSessionTTSJson,
} from '../../api/admin';
import type { PublishSession, ReplacementPreviewItem } from '../../types';
import SheetPreviewPanel from './SheetPreviewPanel';
import UrlMappingTable from './UrlMappingTable';
import { completePackage } from '../../api/packages';

interface PublishSessionWizardProps {
  session: PublishSession | null;
  packageNo?: string;
  onSessionChange: (session: PublishSession) => void;
  onPackageCompleted?: () => void;
}

interface SheetUrlItem {
  sheet_name: string;
  url: string;
  grid: Record<string, unknown>;
}

const stepIndex: Record<string, number> = {
  select_package: 0,
  confirm_sheets: 1,
  prepare_urls: 2,
  export_patch: 3,
  complete: 4,
};

function downloadBlob(blob: Blob, filename: string) {
  const url = URL.createObjectURL(blob);
  const link = document.createElement('a');
  link.href = url;
  link.download = filename;
  document.body.appendChild(link);
  link.click();
  link.remove();
  URL.revokeObjectURL(url);
}

export default function PublishSessionWizard({ session, packageNo, onSessionChange, onPackageCompleted }: PublishSessionWizardProps) {
  const [loading, setLoading] = useState(false);
  const [previewItems, setPreviewItems] = useState<ReplacementPreviewItem[]>([]);
  const [sheetUrlItems, setSheetUrlItems] = useState<SheetUrlItem[]>([]);

  useEffect(() => {
    if (!session || session.current_step !== 'export_patch') return;
    fetchReplacementPreview(session.id).then((data) => setPreviewItems(data.items || [])).catch(() => setPreviewItems([]));
  }, [session]);

  useEffect(() => {
    if (!session || session.current_step !== 'prepare_urls') {
      setSheetUrlItems([]);
      return;
    }
    fetchSessionSheetUrls(session.id).then((data) => setSheetUrlItems(data.items || [])).catch(() => setSheetUrlItems([]));
  }, [session]);

  if (!session) return <Typography.Text type="secondary">请选择待发布勘误包，点击“创建发布”或“继续发布”后，这里会显示发布步骤、精灵图和 URL 校验。</Typography.Text>;

  const activeArtifacts = session.artifacts.filter((artifact) => artifact.status === 'active' || artifact.status === 'confirmed');
  const patchZipArtifact = activeArtifacts.find((artifact) => artifact.kind === 'patch_zip');
  const reportArtifact = activeArtifacts.find((artifact) => artifact.kind === 'report');

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

  const handleRollback = async (targetStep: string, successText: string) => {
    setLoading(true);
    try {
      const next = await rollbackPublishSessionStep(session.id, targetStep);
      onSessionChange(next);
      message.success(successText);
    } catch (error: any) {
      message.error(error?.response?.data?.detail || '回退步骤失败');
    } finally {
      setLoading(false);
    }
  };

  const handleConfirmSheets = async () => {
    setLoading(true);
    try {
      const next = await confirmSessionSheets(session.id);
      onSessionChange(next);
      message.success('精灵图已确认，请导出 TTS 存档');
    } catch (error: any) {
      message.error(error?.response?.data?.detail || '确认精灵图失败');
    } finally {
      setLoading(false);
    }
  };

  const handleExportTTSBag = async () => {
    setLoading(true);
    try {
      const blob = await exportSessionTTSBag(session.id);
      downloadBlob(blob, `${packageNo || session.package_id}-TTS存档.json`);
      message.success('TTS 存档已导出');
    } catch (error: any) {
      message.error(error?.response?.data?.detail || '导出 TTS 存档失败');
    } finally {
      setLoading(false);
    }
  };

  const handleUploadTTSJson = async (file: File) => {
    setLoading(true);
    try {
      const next = await uploadSessionTTSJson(session.id, file);
      onSessionChange(next);
      message.success('已解析回传 TTS JSON，进入替换预览');
    } catch (error: any) {
      message.error(error?.response?.data?.detail || '解析回传 TTS JSON 失败');
    } finally {
      setLoading(false);
    }
    return Upload.LIST_IGNORE;
  };

  const handleExportPatch = async () => {
    const blockingCount = previewItems.filter((item) => item.blocking_errors.length > 0).length;
    if (blockingCount > 0) {
      message.error('替换预览仍有阻断问题，不能进入下一步');
      return;
    }
    setLoading(true);
    try {
      const next = await exportSessionPatch(session.id);
      onSessionChange(next);
      message.success('补丁报告已生成');
    } catch (error: any) {
      const detail = error?.response?.data?.detail;
      message.error(typeof detail === 'string' ? detail : detail?.message || '导出补丁失败');
    } finally {
      setLoading(false);
    }
  };

  const handleCompleteArchive = async () => {
    setLoading(true);
    try {
      await completePackage(session.package_id);
      message.success('发布完成，勘误副本已写回卡牌数据库并归档');
      onPackageCompleted?.();
    } catch (error: any) {
      message.error(error?.response?.data?.detail || '完成归档失败');
    } finally {
      setLoading(false);
    }
  };

  const sheetUrlColumns: ColumnsType<SheetUrlItem> = [
    { title: '精灵图', dataIndex: 'sheet_name', width: 220 },
    { title: 'URL', dataIndex: 'url', ellipsis: true, render: (value) => <Typography.Text copyable>{value}</Typography.Text> },
    { title: '网格', dataIndex: 'grid', width: 120, render: (grid) => `${grid.width || '-'} x ${grid.height || '-'}` },
  ];

  return (
    <Space direction="vertical" style={{ width: '100%' }} size={16}>
      <Steps current={stepIndex[session.current_step] || 0} items={[{ title: '选择包' }, { title: '精灵图' }, { title: 'TTS存档' }, { title: '替换预览' }, { title: '完成' }]} />
      <Card size="small" title={`发布会话 #${session.id} · ${session.status}`}>
        <Descriptions size="small" column={3} style={{ marginBottom: 16 }}>
          <Descriptions.Item label="勘误包">{packageNo || session.package_id}</Descriptions.Item>
          <Descriptions.Item label="当前步骤">{session.current_step}</Descriptions.Item>
          <Descriptions.Item label="当前产物">{activeArtifacts.length}</Descriptions.Item>
        </Descriptions>
        {session.current_step === 'select_package' && <Button type="primary" loading={loading} onClick={handleGenerate}>生成精灵图</Button>}
        {session.current_step === 'confirm_sheets' && (
          <Space direction="vertical" style={{ width: '100%' }} size={12}>
            <Space wrap>
              <Button type="primary" loading={loading} onClick={handleConfirmSheets}>确认精灵图，下一步</Button>
              <Button loading={loading} onClick={handleGenerate}>重新生成精灵图</Button>
            </Space>
            <SheetPreviewPanel artifacts={activeArtifacts} />
          </Space>
        )}
        {session.current_step === 'prepare_urls' && (
          <Space direction="vertical" style={{ width: '100%' }} size={12}>
            <Typography.Text type="secondary">下载 TTS 存档后导入 TTS 或上传到其他图床，拿到已替换图片 URL 的 TTS JSON 后再上传回平台。</Typography.Text>
            <Table rowKey="sheet_name" size="small" columns={sheetUrlColumns} dataSource={sheetUrlItems} pagination={false} />
            <Space wrap>
              <Button type="primary" loading={loading} onClick={handleExportTTSBag}>下载 TTS 存档 JSON</Button>
              <Upload accept=".json,application/json" beforeUpload={handleUploadTTSJson} showUploadList={false}>
                <Button loading={loading}>上传处理后的 TTS JSON，下一步</Button>
              </Upload>
              <Button loading={loading} onClick={() => handleRollback('confirm_sheets', '已返回精灵图确认步骤')}>返回上一步：精灵图</Button>
            </Space>
          </Space>
        )}
        {session.current_step === 'export_patch' && (
          <Space direction="vertical" style={{ width: '100%' }} size={12}>
            <Space wrap>
              <Button type="primary" loading={loading} onClick={handleExportPatch}>确认替换预览，生成补丁报告</Button>
              <Button loading={loading} onClick={() => handleRollback('prepare_urls', '已返回 TTS 存档步骤')}>返回上一步：TTS存档</Button>
              <Button loading={loading} onClick={() => handleRollback('confirm_sheets', '已返回精灵图确认步骤')}>返回精灵图重新生成</Button>
            </Space>
            <UrlMappingTable items={previewItems} />
          </Space>
        )}
        {session.current_step === 'complete' && (
          <Space direction="vertical" style={{ width: '100%' }} size={12}>
            <Typography.Text type="success">SCED-downloads 补丁包已生成。请下载 zip，复制到你的 SCED-downloads fork 仓库根目录后检查并提交 PR。</Typography.Text>
            <Space wrap>
              {patchZipArtifact?.public_url && <Button type="primary" href={patchZipArtifact.public_url}>下载 SCED-downloads 补丁 zip</Button>}
              {reportArtifact?.public_url && <Button href={reportArtifact.public_url}>下载校验报告</Button>}
              <Popconfirm
                title="确认完成发布并归档？"
                description="这会把勘误副本写回卡牌数据库，保留原始 base64 背景，并提交卡牌数据库 git 仓库。"
                okText="确认完成"
                cancelText="取消"
                onConfirm={handleCompleteArchive}
              >
                <Button danger type="primary" loading={loading}>完成并归档</Button>
              </Popconfirm>
              <Button loading={loading} onClick={() => handleRollback('prepare_urls', '已返回 TTS 存档步骤')}>返回 TTS 存档步骤</Button>
            </Space>
          </Space>
        )}
      </Card>
    </Space>
  );
}
