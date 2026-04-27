import { Card, Modal, Space, Table, Tag, Typography } from 'antd';
import type { ColumnsType } from 'antd/es/table';
import { symbolReferenceSections } from './symbolReference';
import type { SymbolReferenceItem } from './symbolReference';

const { Text, Paragraph } = Typography;

interface SymbolReferenceHelpProps {
  open: boolean;
  onClose: () => void;
}

function splitSyntax(syntax: string): string[] {
  return syntax
    .split(/\s*(?:\/|或)\s*/)
    .map((item) => item.trim())
    .filter(Boolean);
}

const columns: ColumnsType<SymbolReferenceItem> = [
  {
    title: '写法',
    dataIndex: 'syntax',
    width: 230,
    render: (syntax: string) => (
      <Space size={[4, 4]} wrap>
        {splitSyntax(syntax).map((item) => (
          <Text key={item} code copyable style={{ marginInlineEnd: 0 }}>{item}</Text>
        ))}
      </Space>
    ),
  },
  {
    title: '含义',
    dataIndex: 'meaning',
    width: 150,
    render: (meaning: string) => <Text strong>{meaning}</Text>,
  },
  {
    title: '说明',
    dataIndex: 'note',
    render: (note?: string) => <Text type="secondary">{note || '—'}</Text>,
  },
];

export default function SymbolReferenceHelp({ open, onClose }: SymbolReferenceHelpProps) {
  return (
    <Modal
      title="符号参考表"
      open={open}
      onCancel={onClose}
      footer={null}
      width={980}
      styles={{ body: { maxHeight: '72vh', overflowY: 'auto' } }}
    >
      <Space direction="vertical" size={12} style={{ width: '100%' }}>
        <Paragraph type="secondary" style={{ marginBottom: 0 }}>
          点击任意写法可以单独复制；建议优先使用尖括号标签，避免直接 emoji 在不同字体或复制场景下不稳定。
        </Paragraph>
        {symbolReferenceSections.map((section) => (
          <Card
            key={section.title}
            size="small"
            title={<Space><span>{section.title}</span><Tag>{section.items.length}</Tag></Space>}
          >
            <Table
              size="small"
              pagination={false}
              rowKey={(item) => item.syntax}
              columns={columns}
              dataSource={section.items}
            />
          </Card>
        ))}
      </Space>
    </Modal>
  );
}
