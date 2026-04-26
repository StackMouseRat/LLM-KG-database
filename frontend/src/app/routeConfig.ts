import { lazy } from 'react';

export type RouteKey = 'plan' | 'trace' | 'quality' | 'template';
export type AppRoute = RouteKey | 'login';

export const routeItems: Array<{ key: RouteKey; label: string; path: string }> = [
  { key: 'plan', label: '预案生成', path: '/plan' },
  { key: 'trace', label: '图谱溯源', path: '/trace' },
  { key: 'quality', label: '格式优化与质量评估', path: '/quality' },
  { key: 'template', label: '模板查看', path: '/template' }
];

export function routeFromPath(pathname: string): AppRoute {
  if (pathname === '/login') return 'login';
  if (pathname === '/trace') return 'trace';
  if (pathname === '/quality') return 'quality';
  if (pathname === '/template') return 'template';
  return 'plan';
}

export const TraceGraphPage = lazy(() => import('../pages/TraceGraphPage').then((module) => ({ default: module.TraceGraphPage })));
export const QualityReviewPage = lazy(() =>
  import('../pages/QualityReviewPage').then((module) => ({ default: module.QualityReviewPage }))
);
export const TemplateViewPage = lazy(() =>
  import('../pages/TemplateViewPage').then((module) => ({ default: module.TemplateViewPage }))
);
