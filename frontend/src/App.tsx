import { Suspense, useCallback, useEffect, useState } from 'react';
import { Button, Card, Layout, Switch, Tag, Typography } from 'antd';
import { routeFromPath, routeItems, TraceGraphPage, QualityReviewPage, TemplateViewPage, ExperimentPage } from './app/routeConfig';
import type { AppRoute, RouteKey } from './app/routeConfig';
import { useAuthSession } from './features/auth/useAuthSession';
import { PlanPage } from './features/plan/PlanPage';
import { usePlanPipeline } from './features/plan/usePlanPipeline';
import { LoginPage } from './pages/LoginPage';

const { Header, Content } = Layout;
const MODE_TAGS_VISIBLE_KEY = 'llmkg_mode_tags_visible_v1';
const COMPACT_LAYOUT_KEY = 'llmkg_compact_layout_v1';
const DARK_MODE_KEY = 'llmkg_dark_mode_v1';

function loadModeTagsVisible() {
  if (typeof window === 'undefined') return true;
  const raw = window.localStorage.getItem(MODE_TAGS_VISIBLE_KEY);
  if (raw == null) return true;
  return raw !== '0';
}

function loadCompactLayout() {
  if (typeof window === 'undefined') return false;
  const raw = window.localStorage.getItem(COMPACT_LAYOUT_KEY);
  if (raw == null) return false;
  return raw === '1';
}

function loadDarkMode() {
  if (typeof window === 'undefined') return false;
  const raw = window.localStorage.getItem(DARK_MODE_KEY);
  if (raw == null) return false;
  return raw === '1';
}

export default function App() {
  const [route, setRoute] = useState<AppRoute>(() =>
    typeof window === 'undefined' ? 'login' : routeFromPath(window.location.pathname)
  );
  const [showModeTags, setShowModeTags] = useState(loadModeTagsVisible);
  const [showCompactLayout, setShowCompactLayout] = useState(loadCompactLayout);
  const [darkMode, setDarkMode] = useState(loadDarkMode);

  const auth = useAuthSession();

  const handleUnauthorized = useCallback(() => {
    auth.setLoggedOut();
    if (typeof window !== 'undefined') {
      window.history.replaceState(null, '', '/login');
    }
    setRoute('login');
  }, [auth]);

  const plan = usePlanPipeline({ onUnauthorized: handleUnauthorized });

  useEffect(() => {
    if (typeof window === 'undefined') return;
    const onPopState = () => {
      setRoute(routeFromPath(window.location.pathname));
    };

    window.addEventListener('popstate', onPopState);
    return () => window.removeEventListener('popstate', onPopState);
  }, []);

  useEffect(() => {
    if (typeof window === 'undefined') return;
    window.localStorage.setItem(MODE_TAGS_VISIBLE_KEY, showModeTags ? '1' : '0');
  }, [showModeTags]);

  useEffect(() => {
    if (typeof window === 'undefined') return;
    window.localStorage.setItem(COMPACT_LAYOUT_KEY, showCompactLayout ? '1' : '0');
  }, [showCompactLayout]);

  useEffect(() => {
    if (typeof window === 'undefined') return;
    window.localStorage.setItem(DARK_MODE_KEY, darkMode ? '1' : '0');
    document.body.classList.toggle('theme-dark', darkMode);
  }, [darkMode]);

  useEffect(() => {
    if (typeof window === 'undefined' || auth.authStatus === 'checking') return;

    if (auth.authStatus === 'unauthenticated') {
      if (window.location.pathname !== '/login') {
        window.history.replaceState(null, '', '/login');
      }
      setRoute('login');
      return;
    }

    if (window.location.pathname === '/' || window.location.pathname === '/login') {
      window.history.replaceState(null, '', '/plan');
      setRoute('plan');
      return;
    }

    setRoute(routeFromPath(window.location.pathname));
  }, [auth.authStatus]);

  const navigateRoute = (nextRoute: RouteKey) => {
    if (auth.authStatus !== 'authenticated') return;
    const target = routeItems.find((item) => item.key === nextRoute);
    if (!target || typeof window === 'undefined') return;
    if (window.location.pathname !== target.path) {
      window.history.pushState(null, '', target.path);
    }
    setRoute(nextRoute);
  };

  const handleLogin = async (username: string, password: string) => {
    const ok = await auth.handleLogin(username, password);
    if (!ok) return;
    if (typeof window !== 'undefined') {
      window.history.replaceState(null, '', '/plan');
    }
    setRoute('plan');
  };

  const handleLogout = async () => {
    await auth.handleLogout();
    if (typeof window !== 'undefined') {
      window.history.replaceState(null, '', '/login');
    }
    setRoute('login');
  };

  return (
    <Layout className={`app-shell ${darkMode ? 'app-shell--dark' : ''}`}>
      <Header className="app-header">
        <div className="app-header__inner">
          <div>
            <Typography.Title level={3} className="app-title">
              电力设备智能预案生成系统
            </Typography.Title>
          </div>
          {auth.authStatus === 'authenticated' ? (
            <div className="app-header__controls">
              <div className="app-user-bar">
                <div className="app-user-toggle">
                  <Typography.Text className="app-user-toggle__label">夜间模式</Typography.Text>
                  <Switch size="small" checked={darkMode} onChange={setDarkMode} />
                </div>
                <Tag color="blue">
                  当前用户：{auth.currentUsername} · 用户组：{auth.currentUserGroup}
                </Tag>
                <Button size="small" onClick={handleLogout}>
                  登出
                </Button>
              </div>
              <div className="app-route-bar">
                <div className="app-mode-toggle">
                  <div className="app-mode-toggle__item">
                    <Typography.Text className="app-mode-toggle__label">显示标签</Typography.Text>
                    <Switch size="small" checked={showModeTags} onChange={setShowModeTags} />
                  </div>
                  <div className="app-mode-toggle__item">
                    <Typography.Text className="app-mode-toggle__label">紧凑布局</Typography.Text>
                    <Switch size="small" checked={showCompactLayout} onChange={setShowCompactLayout} />
                  </div>
                </div>
                <div className="app-route-tabs">
                  {routeItems.map((item) => (
                    <button
                      key={item.key}
                      type="button"
                      className={`app-route-tab ${route === item.key ? 'app-route-tab--active' : ''}`}
                      onClick={() => navigateRoute(item.key)}
                    >
                      {item.label}
                    </button>
                  ))}
                </div>
              </div>
            </div>
          ) : null}
        </div>
      </Header>
      <Content className="app-content">
        {auth.authStatus === 'checking' ? (
          <Card className="panel-card chapter-empty-card auth-wait-card">
            <Typography.Text type="secondary">正在校验登录状态，请稍候。</Typography.Text>
          </Card>
        ) : null}
        {auth.authStatus === 'unauthenticated' && route === 'login' ? (
          <LoginPage loading={auth.loginLoading} errorMessage={auth.loginErrorMessage} onSubmit={handleLogin} />
        ) : null}
        {auth.authStatus === 'authenticated' && route === 'plan' ? (
          <PlanPage plan={plan} showModeTags={showModeTags} showCompactLayout={showCompactLayout} />
        ) : null}
        {auth.authStatus === 'authenticated' && route === 'trace' ? (
          <Suspense
            fallback={
              <Card className="panel-card chapter-empty-card auth-wait-card">
                <Typography.Text type="secondary">正在加载图谱溯源页面，请稍候。</Typography.Text>
              </Card>
            }
          >
            <TraceGraphPage pipeline={plan.pipeline} darkMode={darkMode} />
          </Suspense>
        ) : null}
        {auth.authStatus === 'authenticated' && route === 'quality' ? (
          <Suspense
            fallback={
              <Card className="panel-card chapter-empty-card auth-wait-card">
                <Typography.Text type="secondary">正在加载格式优化与质量评估页面，请稍候。</Typography.Text>
              </Card>
            }
          >
            <QualityReviewPage
              currentUserGroup={auth.currentUserGroup}
              showModeTags={showModeTags}
              compactLayout={showCompactLayout}
            />
          </Suspense>
        ) : null}
        {auth.authStatus === 'authenticated' && route === 'template' ? (
          <Suspense
            fallback={
              <Card className="panel-card chapter-empty-card auth-wait-card">
                <Typography.Text type="secondary">正在加载模板查看页面，请稍候。</Typography.Text>
              </Card>
            }
          >
            <TemplateViewPage currentUserGroup={auth.currentUserGroup} />
          </Suspense>
        ) : null}
        {auth.authStatus === 'authenticated' && route === 'experiment' ? (
          <Suspense
            fallback={
              <Card className="panel-card chapter-empty-card auth-wait-card">
                <Typography.Text type="secondary">正在加载对比实验页面，请稍候。</Typography.Text>
              </Card>
            }
          >
            <ExperimentPage />
          </Suspense>
        ) : null}
      </Content>
    </Layout>
  );
}
