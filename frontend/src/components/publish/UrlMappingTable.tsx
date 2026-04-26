import { Table, Tag, Typography } from 'antd';
import type { ColumnsType } from 'antd/es/table';
import type { ReplacementPreviewItem } from '../../types';

interface UrlMappingTableProps {
  items: ReplacementPreviewItem[];
}

export default function UrlMappingTable({ items }: UrlMappingTableProps) {
  const sorted = [...items].sort((left, right) => Number(right.blocking_errors.length > 0) - Number(left.blocking_errors.length > 0));
  const columns: ColumnsType<ReplacementPreviewItem> = [
    { title: '卡号', dataIndex: 'arkhamdb_id', width: 90 },
    { title: '名称', dataIndex: 'name_zh', width: 160 },
    { title: '动作', dataIndex: 'action', width: 80, render: (value) => <Tag color={value === '新增' ? 'blue' : 'green'}>{value}</Tag> },
    { title: '原路径', dataIndex: 'source_path', ellipsis: true, render: (value) => value || '-' },
    { title: '目标路径', dataIndex: 'target_path', ellipsis: true, render: (value) => value || '-' },
    { title: '新正面URL', dataIndex: 'new_face_url', ellipsis: true, render: (value) => <Typography.Text copyable>{value || '-'}</Typography.Text> },
    { title: '校验', dataIndex: 'blocking_errors', width: 220, render: (errors: string[]) => errors.length ? errors.map((error) => <Tag key={error} color="error">{error}</Tag>) : <Tag color="success">通过</Tag> },
  ];
  return <Table rowKey="arkhamdb_id" size="small" columns={columns} dataSource={sorted} pagination={{ pageSize: 20 }} />;
}
