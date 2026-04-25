import { useState } from 'react';
import { Card, Steps, Button, message, Upload, Space, Input, Descriptions } from 'antd';
import { UploadOutlined } from '@ant-design/icons';
import {
  step1GenerateSheets,
  step2Upload,
  step5UploadTTSJson,
  step6ReplaceUrls,
} from '../api/admin';

/** 发布管理页面：六步发布流程 */
export default function PublishPage() {
  const [current, setCurrent] = useState(0);
  const [batchId, setBatchId] = useState('');
  const [sheets, setSheets] = useState<any[]>([]);
  const [urlMapping, setUrlMapping] = useState<Record<string, unknown> | null>(null);
  const [modifiedCount, setModifiedCount] = useState(0);
  const [loading, setLoading] = useState(false);

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
      await step2Upload(sheets, { image_host: 'local' });
      message.success('上传完成');
      setCurrent(2);
    } catch {
      message.error('上传失败');
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

  /** 第六步：替换中文包中的图片 URL */
  const handleStep6 = async () => {
    if (!urlMapping) return;
    setLoading(true);
    try {
      const data = await step6ReplaceUrls(urlMapping);
      setModifiedCount(data.total_modified);
      message.success(`替换完成: ${data.total_modified} 个文件`);
      setCurrent(5);
    } catch {
      message.error('替换失败');
    } finally {
      setLoading(false);
    }
  };

  const steps = [
    {
      title: '生成精灵图',
      content: (
        <Space direction="vertical">
          <Input
            placeholder="批次ID"
            value={batchId}
            onChange={(e) => setBatchId(e.target.value)}
            style={{ width: 200 }}
          />
          <Button type="primary" onClick={handleStep1} loading={loading}>
            开始生成
          </Button>
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
        <Button type="primary" onClick={() => setCurrent(3)}>
          已下载，下一步
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
      title: '替换中文包URL',
      content: (
        <Button
          type="primary"
          onClick={handleStep6}
          loading={loading}
          disabled={!urlMapping}
        >
          执行替换
        </Button>
      ),
    },
    {
      title: '完成',
      content: (
        <Descriptions column={1}>
          <Descriptions.Item label="修改文件数">
            {modifiedCount}
          </Descriptions.Item>
          <Descriptions.Item label="状态">
            请在 SCED-downloads 目录检查变更并提交 PR
          </Descriptions.Item>
        </Descriptions>
      ),
    },
  ];

  return (
    <Card title="发布管理">
      <Steps
        current={current}
        items={steps.map((s) => ({ title: s.title }))}
        style={{ marginBottom: 32 }}
      />
      <Card>{steps[current].content}</Card>
    </Card>
  );
}
