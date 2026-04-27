import { Button, Form, Input, Select, Space, Table, Tag, message } from 'antd';
import type { ColumnsType } from 'antd/es/table';
import { createDirectoryPreset } from '../../api/admin';
import type { PublishDirectoryPreset } from '../../types';

interface DirectoryPresetTableProps {
  presets: PublishDirectoryPreset[];
  onChanged?: () => void;
}

export default function DirectoryPresetTable({ presets, onChanged }: DirectoryPresetTableProps) {
  const [form] = Form.useForm();

  const handleCreate = async (values: any) => {
    try {
      await createDirectoryPreset({ ...values, is_active: true });
      message.success('发布目录预设已创建');
      form.resetFields();
      onChanged?.();
    } catch (error: any) {
      message.error(error?.response?.data?.detail || '创建发布目录预设失败');
    }
  };

  const columns: ColumnsType<PublishDirectoryPreset> = [
    { title: '本地目录', dataIndex: 'local_dir_prefix', ellipsis: true },
    { title: '目标区域', dataIndex: 'target_area', width: 130, render: (value) => value === 'campaigns' ? 'Campaigns' : 'Player Cards' },
    { title: '目标 Bag', dataIndex: 'target_bag_path', ellipsis: true },
    { title: '对象目录', dataIndex: 'target_object_dir', width: 180 },
    { title: '状态', dataIndex: 'is_active', width: 90, render: (value) => <Tag color={value ? 'success' : 'default'}>{value ? '启用' : '停用'}</Tag> },
  ];
  return (
    <Space direction="vertical" size={12} style={{ width: '100%' }}>
      <Form form={form} layout="vertical" onFinish={handleCreate} initialValues={{ target_area: 'campaigns' }}>
        <Space align="end" wrap>
          <Form.Item label="本地目录" name="local_dir_prefix" rules={[{ required: true, message: '请输入本地目录' }]}>
            <Input style={{ width: 220 }} placeholder="剧本卡/09_绯红密钥" />
          </Form.Item>
          <Form.Item label="目标区域" name="target_area" rules={[{ required: true }]}>
            <Select style={{ width: 140 }} options={[{ value: 'campaigns', label: 'Campaigns' }, { value: 'player_cards', label: 'Player Cards' }]} />
          </Form.Item>
          <Form.Item label="目标 Bag 路径" name="target_bag_path" rules={[{ required: true, message: '请输入目标 Bag 路径' }]}>
            <Input style={{ width: 520 }} placeholder="decomposed/language-pack/.../TheScarletKeys.ab12cd.json" />
          </Form.Item>
          <Form.Item label="Bag GUID" name="target_bag_guid" rules={[{ required: true, message: '请输入 Bag GUID' }]}>
            <Input style={{ width: 120 }} placeholder="ab12cd" />
          </Form.Item>
          <Form.Item label="对象目录" name="target_object_dir" rules={[{ required: true, message: '请输入对象目录' }]}>
            <Input style={{ width: 220 }} placeholder="TheScarletKeys.ab12cd" />
          </Form.Item>
          <Form.Item label="显示名" name="label">
            <Input style={{ width: 220 }} placeholder="可选" />
          </Form.Item>
          <Form.Item>
            <Button type="primary" htmlType="submit">新增预设</Button>
          </Form.Item>
        </Space>
      </Form>
      <Table rowKey="id" size="small" columns={columns} dataSource={presets} pagination={{ pageSize: 12 }} />
    </Space>
  );
}
