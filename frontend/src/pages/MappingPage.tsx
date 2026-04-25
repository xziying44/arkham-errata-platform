import { useState, useEffect } from 'react';
import { Card, Table, Tag, Button } from 'antd';
import { fetchCards } from '../api/cards';
import type { CardIndex } from '../types';

/** 映射管理页面：浏览待确认映射状态的卡牌 */
export default function MappingPage() {
  const [items, setItems] = useState<CardIndex[]>([]);
  const [loading, setLoading] = useState(false);

  const load = async () => {
    setLoading(true);
    const data = await fetchCards({ mapping_status: '待确认', page_size: 100 });
    setItems(data.items);
    setLoading(false);
  };

  useEffect(() => {
    load();
  }, []);

  const statusColor: Record<string, string> = {
    '已确认': 'green',
    '待确认': 'orange',
    '映射异常': 'red',
  };

  const columns = [
    { title: '编号', dataIndex: 'arkhamdb_id', width: 100 },
    { title: '中文名', dataIndex: 'name_zh', width: 160 },
    { title: '类型', dataIndex: 'category', width: 80 },
    {
      title: '映射状态',
      dataIndex: 'mapping_status',
      width: 100,
      render: (s: string) => <Tag color={statusColor[s]}>{s}</Tag>,
    },
  ];

  return (
    <Card
      title="映射管理"
      extra={<Button onClick={load}>刷新</Button>}
    >
      <Table
        dataSource={items}
        columns={columns}
        loading={loading}
        rowKey="arkhamdb_id"
      />
    </Card>
  );
}
