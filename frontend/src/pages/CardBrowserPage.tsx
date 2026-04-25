import { useState, useEffect, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import { Table, Select, Input, Tag, Space, Card } from 'antd';
import { fetchCards, fetchFilters } from '../api/cards';
import type { CardIndex } from '../types';

export default function CardBrowserPage() {
  const [cards, setCards] = useState<CardIndex[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(false);
  const [page, setPage] = useState(1);
  const [filters, setFilters] = useState<{ categories: string[]; cycles: string[] }>({ categories: [], cycles: [] });
  const [category, setCategory] = useState<string | undefined>();
  const [cycle, setCycle] = useState<string | undefined>();
  const [keyword, setKeyword] = useState('');
  const navigate = useNavigate();

  const load = useCallback(async () => {
    setLoading(true);
    const data = await fetchCards({ category, cycle, keyword: keyword || undefined, page, page_size: 50 });
    setCards(data.items);
    setTotal(data.total);
    setLoading(false);
  }, [category, cycle, keyword, page]);

  useEffect(() => { fetchFilters().then(setFilters); }, []);
  useEffect(() => { load(); }, [load]);

  const statusColor: Record<string, string> = { '已确认': 'green', '待确认': 'orange', '映射异常': 'red' };

  const columns = [
    { title: '编号', dataIndex: 'arkhamdb_id', width: 100 },
    { title: '中文名', dataIndex: 'name_zh', width: 180 },
    { title: '英文名', dataIndex: 'name_en', width: 200 },
    { title: '类型', dataIndex: 'category', width: 80 },
    { title: '循环', dataIndex: 'cycle', width: 140 },
    { title: '映射状态', dataIndex: 'mapping_status', width: 100, render: (s: string) => <Tag color={statusColor[s] || 'default'}>{s}</Tag> },
  ];

  return (
    <Card title="卡牌浏览">
      <Space style={{ marginBottom: 16 }}>
        <Select allowClear placeholder="分类" style={{ width: 120 }} value={category} onChange={setCategory} options={filters.categories.map(c => ({ value: c, label: c }))} />
        <Select allowClear placeholder="循环" style={{ width: 160 }} value={cycle} onChange={setCycle} options={filters.cycles.map(c => ({ value: c, label: c }))} />
        <Input.Search placeholder="搜索卡牌名..." style={{ width: 240 }} value={keyword} onChange={e => setKeyword(e.target.value)} onSearch={() => { setPage(1); load(); }} />
      </Space>
      <Table dataSource={cards} columns={columns} loading={loading} rowKey="arkhamdb_id" pagination={{ current: page, total, pageSize: 50, onChange: setPage }} onRow={(record) => ({ onClick: () => navigate(`/errata/${record.arkhamdb_id}`), style: { cursor: 'pointer' } })} />
    </Card>
  );
}
