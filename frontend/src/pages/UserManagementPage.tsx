import { useEffect, useState } from 'react';
import { Button, Card, Form, Input, message, Modal, Select, Space, Switch, Table, Tag } from 'antd';
import type { ColumnsType } from 'antd/es/table';
import { createUser, fetchUsers, resetPassword, updateUser } from '../api/auth';
import type { User, UserRole } from '../types';

const roleOptions: UserRole[] = ['勘误员', '审核员', '管理员'];

export default function UserManagementPage() {
  const [users, setUsers] = useState<User[]>([]);
  const [loading, setLoading] = useState(false);
  const [createOpen, setCreateOpen] = useState(false);
  const [resetUser, setResetUser] = useState<User | null>(null);
  const [editingNoteUser, setEditingNoteUser] = useState<User | null>(null);
  const [form] = Form.useForm();
  const [resetForm] = Form.useForm();
  const [noteForm] = Form.useForm();

  const load = async () => {
    setLoading(true);
    try {
      setUsers(await fetchUsers());
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { load(); }, []);

  const columns: ColumnsType<User> = [
    { title: '账号', dataIndex: 'username' },
    {
      title: '备注',
      dataIndex: 'note',
      render: (note: string) => note || <span style={{ color: '#999' }}>未备注</span>,
    },
    {
      title: '角色',
      dataIndex: 'role',
      render: (role: UserRole, record) => (
        <Select
          value={role}
          style={{ width: 120 }}
          options={roleOptions.map((value) => ({ value, label: value }))}
          onChange={async (value) => {
            await updateUser(record.id, { role: value });
            message.success('角色已更新');
            load();
          }}
        />
      ),
    },
    {
      title: '状态',
      dataIndex: 'is_active',
      render: (active: boolean, record) => (
        <Space>
          <Tag color={active ? 'success' : 'default'}>{active ? '启用' : '禁用'}</Tag>
          <Switch
            checked={active}
            onChange={async (checked) => {
              await updateUser(record.id, { is_active: checked });
              message.success('状态已更新');
              load();
            }}
          />
        </Space>
      ),
    },
    {
      title: '操作',
      render: (_, record) => (
        <Space>
          <Button onClick={() => { setEditingNoteUser(record); noteForm.setFieldsValue({ note: record.note }); }}>编辑备注</Button>
          <Button onClick={() => setResetUser(record)}>重置密码</Button>
        </Space>
      ),
    },
  ];

  return (
    <Card title="用户管理" extra={<Button type="primary" onClick={() => setCreateOpen(true)}>创建用户</Button>}>
      <Table rowKey="id" loading={loading} columns={columns} dataSource={users} />
      <Modal
        title="创建用户"
        open={createOpen}
        onCancel={() => setCreateOpen(false)}
        onOk={async () => {
          const values = await form.validateFields();
          await createUser(values);
          message.success('用户已创建');
          setCreateOpen(false);
          form.resetFields();
          load();
        }}
      >
        <Form form={form} layout="vertical" initialValues={{ role: '勘误员' }}>
          <Form.Item name="username" label="账号" rules={[{ required: true, message: '请输入账号' }]}><Input /></Form.Item>
          <Form.Item name="password" label="密码" rules={[{ required: true, message: '请输入密码' }]}><Input.Password /></Form.Item>
          <Form.Item name="role" label="角色" rules={[{ required: true }]}>
            <Select options={roleOptions.map((value) => ({ value, label: value }))} />
          </Form.Item>
          <Form.Item name="note" label="备注">
            <Input.TextArea rows={3} placeholder="例如：张三使用 / 二校账号 / 联系方式备注" />
          </Form.Item>
        </Form>
      </Modal>

      <Modal
        title={`编辑备注：${editingNoteUser?.username || ''}`}
        open={Boolean(editingNoteUser)}
        onCancel={() => setEditingNoteUser(null)}
        onOk={async () => {
          const values = await noteForm.validateFields();
          if (!editingNoteUser) return;
          await updateUser(editingNoteUser.id, { note: values.note || '' });
          message.success('备注已更新');
          setEditingNoteUser(null);
          noteForm.resetFields();
          load();
        }}
      >
        <Form form={noteForm} layout="vertical">
          <Form.Item name="note" label="备注">
            <Input.TextArea rows={4} placeholder="记录这个账号是谁在用" />
          </Form.Item>
        </Form>
      </Modal>
      <Modal
        title={`重置密码：${resetUser?.username || ''}`}
        open={Boolean(resetUser)}
        onCancel={() => setResetUser(null)}
        onOk={async () => {
          const values = await resetForm.validateFields();
          if (!resetUser) return;
          await resetPassword(resetUser.id, values.password);
          message.success('密码已重置');
          setResetUser(null);
          resetForm.resetFields();
        }}
      >
        <Form form={resetForm} layout="vertical">
          <Form.Item name="password" label="新密码" rules={[{ required: true, message: '请输入新密码' }]}><Input.Password /></Form.Item>
        </Form>
      </Modal>
    </Card>
  );
}
