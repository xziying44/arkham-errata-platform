import { Button, Space, Table, Tag } from 'antd';
import type { ColumnsType } from 'antd/es/table';
import type { ErrataPackage } from '../../types';

interface PackageTableProps {
  packages: ErrataPackage[];
  selectedPackageId: number | null;
  loading?: boolean;
  onSelect: (pkg: ErrataPackage) => void;
  onOpenSession: (pkg: ErrataPackage) => void;
  onUnlock: (pkg: ErrataPackage) => void;
}

const statusColor: Record<string, string> = {
  待发布: 'warning',
  发布中: 'processing',
  已发布: 'success',
  已退回: 'default',
};

export default function PackageTable({ packages, selectedPackageId, loading, onSelect, onOpenSession, onUnlock }: PackageTableProps) {
  const columns: ColumnsType<ErrataPackage> = [
    { title: '包号', dataIndex: 'package_no', width: 160 },
    { title: '状态', dataIndex: 'status', width: 100, render: (value) => <Tag color={statusColor[value] || 'default'}>{value}</Tag> },
    { title: '卡牌数', dataIndex: 'card_count', width: 90 },
    { title: '创建人', dataIndex: 'created_by_username', width: 120, render: (value) => value || '-' },
    { title: '创建时间', dataIndex: 'created_at', width: 180, render: (value) => value ? new Date(value).toLocaleString() : '-' },
    { title: '最近会话', dataIndex: 'latest_session', render: (value) => value ? `${value.status} · ${value.current_step}` : '无' },
    {
      title: '操作',
      width: 260,
      render: (_, record) => (
        <Space>
          <Button size="small" onClick={() => onSelect(record)}>审阅</Button>
          <Button size="small" type="primary" disabled={record.status !== '待发布'} onClick={() => onOpenSession(record)}>{record.latest_session ? '继续发布' : '创建发布'}</Button>
          <Button size="small" disabled={record.status !== '待发布'} onClick={() => onUnlock(record)}>解锁整包</Button>
        </Space>
      ),
    },
  ];

  return (
    <Table
      rowKey="id"
      size="small"
      loading={loading}
      columns={columns}
      dataSource={packages}
      pagination={{ pageSize: 8 }}
      rowClassName={(record) => record.id === selectedPackageId ? 'ant-table-row-selected' : ''}
    />
  );
}
