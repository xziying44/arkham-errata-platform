import { useEffect, useState } from 'react';
import { Card, Steps, Button, message, Upload, Space, Descriptions, Select, Tag } from 'antd';
import { UploadOutlined } from '@ant-design/icons';
import {
  step1GenerateSheets,
  step2Upload,
  step3ExportTTS,
  step5UploadTTSJson,
  step6ExportReplacements,
} from '../api/admin';
import { fetchPackages, unlockPackage } from '../api/packages';
import type { ErrataPackage } from '../types';
import CardWorkbench from '../components/workbench/CardWorkbench';

/** 发布管理页面：六步发布流程 */
export default function PublishPage() {
  const [current, setCurrent] = useState(0);
  const [batchId, setBatchId] = useState('');
  const [packages, setPackages] = useState<ErrataPackage[]>([]);
  const [sheets, setSheets] = useState<any[]>([]);
  const [sheetUrls, setSheetUrls] = useState<Record<string, string>>({});
  const [urlMapping, setUrlMapping] = useState<Record<string, unknown> | null>(null);
  const [exportedPatch, setExportedPatch] = useState(false);
  const [loading, setLoading] = useState(false);
  const selectedPackageId = batchId ? Number(batchId) : null;
  const selectedPackage = packages.find((item) => item.id === selectedPackageId) || null;

  const loadPackages = async () => {
    try {
      const data = await fetchPackages();
      setPackages(data.items || []);
      const active = (data.items || []).find((item) => item.status === '待发布' || item.status === '发布中');
      if (active && !batchId) setBatchId(String(active.id));
    } catch {
      setPackages([]);
    }
  };

  useEffect(() => { loadPackages(); }, []);

  /** 第一步：生成精灵图 */
  const handleStep1 = async () => {
    setLoading(true);
    try {
      const data = await step1GenerateSheets(batchId);
      setSheets(data.generated_sheets);
      message.success(
        `生成 ${data.total_sheets} 个精灵图，${data.total_cards} 张卡`
      );
      setCurrent(1);
    } catch (e: any) {
      message.error(e?.response?.data?.detail || '生成失败');
    } finally {
      setLoading(false);
    }
  };

  /** 第二步：上传到图床 */
  const handleStep2 = async () => {
    setLoading(true);
    try {
      const data = await step2Upload(sheets, { image_host: 'local' });
      setSheetUrls(data.urls || {});
      message.success('上传完成');
      setCurrent(2);
    } catch {
      message.error('上传失败');
    } finally {
      setLoading(false);
    }
  };

  /** 第三步：导出 TTS 存档 JSON 并下载 */
  const handleStep3 = async () => {
    setLoading(true);
    try {
      const sheetGrids = Object.fromEntries(
        sheets.map((sheet) => [
          sheet.sheet_name,
          { deck_key: sheet.sheet_name.replace(/\D/g, '').slice(0, 5) || '10000', width: 10, height: Math.ceil((sheet.card_ids?.length || 1) / 10) },
        ])
      );
      const blob = await step3ExportTTS(batchId, sheetUrls, sheetGrids);
      const url = URL.createObjectURL(blob);
      const link = document.createElement('a');
      link.href = url;
      link.download = '勘误发布包.json';
      link.click();
      URL.revokeObjectURL(url);
      message.success('TTS 存档已导出');
      setCurrent(3);
    } catch (e: any) {
      message.error(e?.response?.data?.detail || '导出失败');
    } finally {
      setLoading(false);
    }
  };

  /** 第五步：上传 TTS 导出 JSON 并提取 URL 映射 */
  const handleTTSJsonUpload = async (file: File) => {
    const data = await step5UploadTTSJson(file);
    setUrlMapping(data.url_mapping);
    message.success(`提取 ${data.total_cards} 张卡的 Steam URL`);
    setCurrent(4);
    return false; // 阻止默认上传行为
  };

  /** 第六步：导出 SCED-downloads PR 补丁包 */
  const handleStep6 = async () => {
    if (!urlMapping) return;
    setLoading(true);
    try {
      const blob = await step6ExportReplacements(urlMapping);
      const url = URL.createObjectURL(blob);
      const link = document.createElement('a');
      link.href = url;
      link.download = 'SCED-downloads-PR补丁包.zip';
      link.click();
      URL.revokeObjectURL(url);
      setExportedPatch(true);
      message.success('已导出 SCED-downloads PR 补丁包');
      setCurrent(5);
    } catch {
      message.error('导出补丁包失败');
    } finally {
      setLoading(false);
    }
  };

  const steps = [
    {
      title: '生成精灵图',
      content: (
        <Space direction="vertical" style={{ width: 520 }}>
          <Select
            placeholder="选择待发布勘误包"
            value={batchId || undefined}
            onChange={(value) => setBatchId(value)}
            options={packages.map((item) => ({
              value: String(item.id),
              label: `${item.package_no}（${item.status}）`,
            }))}
          />
          <Space size={4} wrap>
            {packages.map((item) => (
              <Tag key={item.id} color={item.status === '待发布' ? 'warning' : item.status === '已发布' ? 'success' : 'default'}>
                {item.package_no} · {item.status}
              </Tag>
            ))}
          </Space>
          <Space>
            <Button type="primary" onClick={handleStep1} loading={loading} disabled={!batchId}>
              开始生成
            </Button>
            <Button
              disabled={!batchId}
              onClick={async () => {
                await unlockPackage(Number(batchId), '管理员在发布页解锁');
                message.success('勘误包已解锁退回');
                setBatchId('');
                loadPackages();
              }}
            >
              解锁整包
            </Button>
          </Space>
        </Space>
      ),
    },
    {
      title: '上传图床',
      content: (
        <Button type="primary" onClick={handleStep2} loading={loading}>
          上传到图床
        </Button>
      ),
    },
    {
      title: '下载TTS存档',
      content: (
        <Button type="primary" onClick={handleStep3} loading={loading} disabled={Object.keys(sheetUrls).length === 0}>
          导出并下载 TTS 存档
        </Button>
      ),
    },
    {
      title: '上传替换后JSON',
      content: (
        <Upload beforeUpload={handleTTSJsonUpload} maxCount={1} accept=".json">
          <Button icon={<UploadOutlined />}>上传 TTS 导出 JSON</Button>
        </Upload>
      ),
    },
    {
      title: '导出PR补丁包',
      content: (
        <Button
          type="primary"
          onClick={handleStep6}
          loading={loading}
          disabled={!urlMapping}
        >
          导出 SCED-downloads PR 补丁包
        </Button>
      ),
    },
    {
      title: '完成',
      content: (
        <Descriptions column={1}>
          <Descriptions.Item label="补丁包">
            {exportedPatch ? '已下载' : '未生成'}
          </Descriptions.Item>
          <Descriptions.Item label="下一步">
            将压缩包内容复制到你的 SCED-downloads fork 仓库根目录，检查后提交 PR
          </Descriptions.Item>
        </Descriptions>
      ),
    },
  ];

  return (
    <Space direction="vertical" size={16} style={{ width: '100%' }}>
      <Card title="发布管理">
        <Steps
          current={current}
          items={steps.map((s) => ({ title: s.title }))}
          style={{ marginBottom: 32 }}
        />
        <Card>{steps[current].content}</Card>
      </Card>
      {selectedPackageId && selectedPackage && (
        <Card
          title={`发布前审阅：${selectedPackage.package_no}`}
          extra={<Tag color={selectedPackage.status === '待发布' ? 'warning' : 'default'}>{selectedPackage.status}</Tag>}
        >
          <CardWorkbench mode="package-review" packageId={selectedPackageId} />
        </Card>
      )}
    </Space>
  );
}
