import { QueryClientProvider } from '@tanstack/react-query';
import { act } from 'react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { CatalogGridPage } from '../../src/react/catalog-grid/catalog-grid-page';
import { setCatalogView } from '../../src/react/catalog-grid/catalog-view';
import type { CatalogGridProps, MediaCardActions } from '../../src/react/catalog-grid/types';
import { queryClient } from '../../src/react/query';
import { click, mount } from './render';

afterEach(() => { queryClient.clear(); localStorage.removeItem('peach.catalog-view.v1') });

describe('主页打开视频的筛选上下文', () => {
  for (const view of ['cards', 'list'] as const) {
    it(`${view} 视图把文件夹、标签与排序交给当前队列入口`, async () => {
      setCatalogView(view);
      const target = { id: 41, name: '测试视频', medium: 'video', duration: 300, size: 100 };
      vi.stubGlobal('fetch', vi.fn(async () => ({ ok: true, status: 200, json: async () => ({ items: [target], total: 1 }) })));
      const openCatalog = vi.fn();
      const actions: MediaCardActions = {
        open: vi.fn(), openCatalog, openResource: vi.fn(), openShort: vi.fn(), openShorts: vi.fn(), openMix: vi.fn(),
        openEntity: vi.fn(), openUnowned: vi.fn(), toggleTag: vi.fn(), toggleSelection: vi.fn(),
        watchLater: vi.fn(async () => {}), resourceOperation: vi.fn(async () => {}), mixRelated: vi.fn(async () => []), canFlip: () => true,
      };
      const props: CatalogGridProps = {
        mode: 'catalog', actions, helpers: { badgeHtml: () => '', titleHtml: (_item, raw) => raw, displayName: (_item, raw) => raw, tagLabel: value => value },
        layout: { active: false, size: 'small', portrait: false, javImage: 'cover' }, selectMode: false, selected: new Set(), seekSeconds: 10,
        revision: 0, skeletonHtml: () => '', wireDrag: () => {}, groupCollapse: true,
        filters: { folder: 'R:\\Fixture', folder_recursive: '1', tag: '测试标签', sort: 'name', dir: 'asc' },
      };
      const host = await mount(<QueryClientProvider client={queryClient}><CatalogGridPage {...props} /></QueryClientProvider>);
      for (let i = 0; i < 4; i++) await act(async () => { await new Promise(resolve => setTimeout(resolve, 0)) });
      await click(host.querySelector(view === 'cards' ? '[data-media-open]' : '[data-list-open]'));
      expect(openCatalog).toHaveBeenCalledOnce();
      const params = new URLSearchParams(openCatalog.mock.calls[0]![2]);
      expect(params.get('folder')).toBe('R:\\Fixture');
      expect(params.get('tag')).toBe('测试标签');
      expect(params.get('sort')).toBe('name');
      expect(openCatalog.mock.calls[0]![3]).toBe(view === 'cards');
      expect(actions.open).not.toHaveBeenCalled();
    });
  }
});
