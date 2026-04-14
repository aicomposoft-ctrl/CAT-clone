import { useState } from 'react'
import { Layout, Menu, Badge, Avatar, Dropdown, theme } from 'antd'
import {
  DashboardOutlined,
  FileTextOutlined,
  ShopOutlined,
  DollarOutlined,
  StarOutlined,
  BellOutlined,
  SettingOutlined,
  LogoutOutlined,
  UserOutlined,
} from '@ant-design/icons'
import { useNavigate, useLocation, Outlet } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { useAuthStore } from '../store/authStore'
import { authApi } from '../api/auth'
import { alertsApi } from '../api/alerts'

const { Sider, Content, Header } = Layout

export const AppLayout: React.FC = () => {
  const [collapsed, setCollapsed] = useState(false)
  const navigate = useNavigate()
  const location = useLocation()
  const user = useAuthStore((s) => s.user)
  const { token } = theme.useToken()

  const { data: alertsData } = useQuery({
    queryKey: ['alerts-count'],
    queryFn: () => alertsApi.list({ is_sent: false, size: 1 }),
    staleTime: 5 * 60 * 1000,
    refetchInterval: 5 * 60 * 1000,
  })

  const activeAlerts = alertsData?.total ?? 0

  const navItems = [
    { key: '/dashboard', icon: <DashboardOutlined />, label: 'Дашборд' },
    { key: '/content', icon: <FileTextOutlined />, label: 'Контент' },
    { key: '/stock', icon: <ShopOutlined />, label: 'Дистрибуция' },
    { key: '/prices', icon: <DollarOutlined />, label: 'Цены' },
    { key: '/reviews', icon: <StarOutlined />, label: 'Отзывы' },
    {
      key: '/alerts',
      icon: (
        <Badge count={activeAlerts} size="small" offset={[4, 0]}>
          <BellOutlined />
        </Badge>
      ),
      label: 'Алерты',
    },
    { key: '/settings/skus', icon: <SettingOutlined />, label: 'Настройки' },
  ]

  const userMenuItems = [
    {
      key: 'logout',
      icon: <LogoutOutlined />,
      label: 'Выйти',
      onClick: authApi.logout,
    },
  ]

  return (
    <Layout style={{ minHeight: '100vh' }}>
      <Sider
        collapsible
        collapsed={collapsed}
        onCollapse={setCollapsed}
        theme="light"
        width={220}
        style={{ borderRight: `1px solid ${token.colorBorderSecondary}` }}
      >
        <div
          style={{
            padding: '16px',
            fontWeight: 700,
            fontSize: collapsed ? 12 : 16,
            color: token.colorPrimary,
            whiteSpace: 'nowrap',
            overflow: 'hidden',
          }}
        >
          {collapsed ? 'CAT' : 'CAT Analytics'}
        </div>
        <Menu
          mode="inline"
          selectedKeys={[location.pathname]}
          items={navItems}
          onClick={({ key }) => navigate(key)}
          style={{ borderRight: 0 }}
        />
      </Sider>

      <Layout>
        <Header
          style={{
            background: token.colorBgContainer,
            borderBottom: `1px solid ${token.colorBorderSecondary}`,
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'flex-end',
            padding: '0 24px',
          }}
        >
          <Dropdown menu={{ items: userMenuItems }} placement="bottomRight">
            <div style={{ cursor: 'pointer', display: 'flex', alignItems: 'center', gap: 8 }}>
              <Avatar icon={<UserOutlined />} size="small" />
              <span style={{ fontSize: 13 }}>{user?.email}</span>
            </div>
          </Dropdown>
        </Header>

        <Content style={{ padding: 24, background: token.colorBgLayout }}>
          <Outlet />
        </Content>
      </Layout>
    </Layout>
  )
}
