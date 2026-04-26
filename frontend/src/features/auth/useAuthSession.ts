import { useEffect, useState } from 'react';
import { message } from 'antd';
import { fetchCurrentUser, login, logout } from '../../services/authApi';

export type AuthStatus = 'checking' | 'authenticated' | 'unauthenticated';
export type UserGroup = 'admin' | 'user';

export function useAuthSession() {
  const [authStatus, setAuthStatus] = useState<AuthStatus>('checking');
  const [currentUsername, setCurrentUsername] = useState('');
  const [currentUserGroup, setCurrentUserGroup] = useState<UserGroup>('user');
  const [loginLoading, setLoginLoading] = useState(false);
  const [loginErrorMessage, setLoginErrorMessage] = useState('');

  useEffect(() => {
    if (typeof window === 'undefined') return;

    const syncAuth = async () => {
      try {
        const session = await fetchCurrentUser();
        if (session?.username) {
          setCurrentUsername(session.username);
          setCurrentUserGroup(session.group);
          setAuthStatus('authenticated');
          return;
        }
        setCurrentUsername('');
        setCurrentUserGroup('user');
        setAuthStatus('unauthenticated');
      } catch (error) {
        setCurrentUsername('');
        setCurrentUserGroup('user');
        setAuthStatus('unauthenticated');
        message.error(error instanceof Error ? error.message : '登录状态校验失败');
      }
    };

    void syncAuth();
  }, []);

  const setLoggedOut = () => {
    setCurrentUsername('');
    setCurrentUserGroup('user');
    setAuthStatus('unauthenticated');
  };

  const handleLogin = async (username: string, password: string) => {
    if (!username || !password) {
      setLoginErrorMessage('请输入用户名和密码');
      message.warning('请输入用户名和密码');
      return false;
    }

    setLoginLoading(true);
    setLoginErrorMessage('');
    try {
      const session = await login(username, password);
      setCurrentUsername(session.username);
      setCurrentUserGroup(session.group);
      setAuthStatus('authenticated');
      message.success('登录成功');
      return true;
    } catch (error) {
      const nextMessage = error instanceof Error ? error.message : '登录失败';
      setLoginErrorMessage(nextMessage);
      message.error(nextMessage);
      return false;
    } finally {
      setLoginLoading(false);
    }
  };

  const handleLogout = async () => {
    try {
      await logout();
    } catch (error) {
      message.error(error instanceof Error ? error.message : '登出失败');
    } finally {
      setLoggedOut();
    }
  };

  return {
    authStatus,
    currentUsername,
    currentUserGroup,
    loginLoading,
    loginErrorMessage,
    handleLogin,
    handleLogout,
    setLoggedOut
  };
}
