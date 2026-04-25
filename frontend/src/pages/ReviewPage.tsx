import { useState, useEffect } from 'react';
import { Card, Table, Button, Space, Modal, Input, message, Tag } from 'antd';
import { fetchPendingReviews, batchApprove, batchReject } from '../api/admin';
import type { Errata } from '../types';

/** 勘误审核页面：管理员批量审核勘误 */
export default function ReviewPage() {
  const [items, setItems] = useState<Errata[]>([]);
  const [selected, setSelected] = useState<number[]>([]);
  const [loading, setLoading] = useState(false);
  const [rejectVisible, setRejectVisible] = useState(false);
  const [rejectNote, setRejectNote] = useState('');

  const load = async () => {
    setLoading(true);
    const data = await fetchPendingReviews();
    setItems(data.items);
    setLoading(false);
  };

  useEffect(() => {
    load();
  }, []);

  const handleApprove = async () => {
    await batchApprove(selected);
    message.success(`已通过 ${selected.length} 条勘误`);
    setSelected([]);
    load();
  };

  const handleReject = async () => {
    await batchReject(selected, rejectNote);
    message.success(`已驳回 ${selected.length} 条勘误`);
    setRejectVisible(false);
    setRejectNote('');
    setSelected([]);
    load();
  };

  const columns = [
    { title: '编号', dataIndex: 'arkhamdb_id', width: 100 },
    { title: '提交者', dataIndex: 'user_id', width: 80 },
    {
      title: '状态',
      dataIndex: 'status',
      width: 80,
      render: (s: string) => (
        <Tag color={s === '待审核' ? 'orange' : 'default'}>{s}</Tag>
      ),
    },
    { title: '提交时间', dataIndex: 'created_at', width: 180 },
  ];

  return (
    <Card
      title="勘误审核"
      extra={
        <Space>
          <Button
            type="primary"
            onClick={handleApprove}
            disabled={selected.length === 0}
          >
            批量通过 ({selected.length})
          </Button>
          <Button
            danger
            onClick={() => setRejectVisible(true)}
            disabled={selected.length === 0}
          >
            批量驳回
          </Button>
        </Space>
      }
    >
      <Table
        dataSource={items}
        columns={columns}
        loading={loading}
        rowKey="id"
        rowSelection={{
          selectedRowKeys: selected,
          onChange: (keys) => setSelected(keys as number[]),
        }}
      />
      <Modal
        title="填写驳回原因"
        open={rejectVisible}
        onOk={handleReject}
        onCancel={() => setRejectVisible(false)}
      >
        <Input.TextArea
          value={rejectNote}
          onChange={(e) => setRejectNote(e.target.value)}
          placeholder="驳回原因..."
        />
      </Modal>
    </Card>
  );
}
