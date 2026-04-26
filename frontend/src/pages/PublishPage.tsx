import { useEffect, useState } from 'react';
import { Card, Space, Tabs, message } from 'antd';
import { createPublishSession, fetchDirectoryPresets, fetchPublishSession } from '../api/admin';
import { fetchPackages, unlockPackage } from '../api/packages';
import type { ErrataPackage, PublishDirectoryPreset, PublishSession } from '../types';
import CardWorkbench from '../components/workbench/CardWorkbench';
import DirectoryPresetTable from '../components/publish/DirectoryPresetTable';
import PackageTable from '../components/publish/PackageTable';
import PublishSessionWizard from '../components/publish/PublishSessionWizard';

export default function PublishPage() {
  const [packages, setPackages] = useState<ErrataPackage[]>([]);
  const [presets, setPresets] = useState<PublishDirectoryPreset[]>([]);
  const [selectedPackage, setSelectedPackage] = useState<ErrataPackage | null>(null);
  const [session, setSession] = useState<PublishSession | null>(null);
  const [loading, setLoading] = useState(false);

  const loadPackages = async () => {
    setLoading(true);
    try {
      const data = await fetchPackages();
      setPackages(data.items || []);
      if (!selectedPackage && data.items?.length) {
        const active = data.items.find((item) => item.status === '待发布') || data.items[0];
        setSelectedPackage(active);
      }
    } catch (error: any) {
      message.error(error?.response?.data?.detail || '加载勘误包失败');
    } finally {
      setLoading(false);
    }
  };

  const loadPresets = async () => {
    try {
      const data = await fetchDirectoryPresets();
      setPresets(data.items || []);
    } catch {
      setPresets([]);
    }
  };

  useEffect(() => {
    loadPackages();
    loadPresets();
  }, []);

  const handleOpenSession = async (pkg: ErrataPackage) => {
    try {
      const next = pkg.latest_session
        ? await fetchPublishSession(pkg.latest_session.id)
        : await createPublishSession(pkg.id);
      setSelectedPackage(pkg);
      setSession(next);
      message.success(pkg.latest_session ? '发布会话已加载' : '发布会话已创建');
      await loadPackages();
    } catch (error: any) {
      message.error(error?.response?.data?.detail || '打开发布会话失败');
    }
  };

  const handleUnlock = async (pkg: ErrataPackage) => {
    try {
      await unlockPackage(pkg.id, '管理员在发布页解锁');
      message.success('勘误包已解锁退回');
      setSession(null);
      await loadPackages();
    } catch (error: any) {
      message.error(error?.response?.data?.detail || '解锁失败');
    }
  };

  return (
    <Space direction="vertical" size={16} style={{ width: '100%' }}>
      <Card title="发布管理">
        <Tabs
          items={[
            {
              key: 'packages',
              label: '勘误包发布',
              children: (
                <Space direction="vertical" size={16} style={{ width: '100%' }}>
                  <PackageTable
                    packages={packages}
                    selectedPackageId={selectedPackage?.id || null}
                    loading={loading}
                    onSelect={setSelectedPackage}
                    onOpenSession={handleOpenSession}
                    onUnlock={handleUnlock}
                  />
                  <Card title="发布会话" size="small">
                    <PublishSessionWizard session={session} packageNo={selectedPackage?.package_no} onSessionChange={setSession} />
                  </Card>
                  <Card title={selectedPackage ? `发布前审阅：${selectedPackage.package_no}` : '发布前审阅'} size="small">
                    {selectedPackage ? <CardWorkbench mode="package-review" packageId={selectedPackage.id} /> : '请选择勘误包'}
                  </Card>
                </Space>
              ),
            },
            {
              key: 'presets',
              label: '发布目录索引',
              children: <DirectoryPresetTable presets={presets} />,
            },
          ]}
        />
      </Card>
    </Space>
  );
}
