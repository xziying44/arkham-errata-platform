import { Table, Tag } from 'antd';
import type { ColumnsType } from 'antd/es/table';
import type { PublishDirectoryPreset } from '../../types';

interface DirectoryPresetTableProps {
  presets: PublishDirectoryPreset[];
}

export default function DirectoryPresetTable({ presets }: DirectoryPresetTableProps) {
  const columns: ColumnsType<PublishDirectoryPreset> = [
    { title: '本地目录', dataIndex: 'local_dir_prefix', ellipsis: true },
    { title: '目标区域', dataIndex: 'target_area', width: 130, render: (value) => value === 'campaigns' ? 'Campaigns' : 'Player Cards' },
    { title: '目标 Bag', dataIndex: 'target_bag_path', ellipsis: true },
    { title: '对象目录', dataIndex: 'target_object_dir', width: 180 },
    { title: '状态', dataIndex: 'is_active', width: 90, render: (value) => <Tag color={value ? 'success' : 'default'}>{value ? '启用' : '停用'}</Tag> },
  ];
  return <Table rowKey="id" size="small" columns={columns} dataSource={presets} pagination={{ pageSize: 12 }} />;
}
