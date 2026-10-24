import { notifyManager, QueryClientProvider } from '@tanstack/react-query';
import { act } from 'react';
import { afterEach, describe, expect, it, vi } from 'vitest';

import { EntityReleases } from '../../src/react/entity-page/entity-releases';
import { queryClient } from '../../src/react/query';
import { buttonNamed, click, mount } from './render';

afterEach(() => queryClient.clear());
notifyManager.setScheduler(notify => notify());
const flush = async () => { for (let i = 0; i < 3; i++) await act(async () => { await new Promise(resolve => setTimeout(resolve, 0)) }) };
const film = (code: string, date: string, asset: number | null = null) => ({ code, title: '测试影片', release_date: date, asset_id: asset, url: `https://www.javbus.com/${code}` });
const answer = (extra: object = {}) => ({ items: [], actors: [], actor: '/star/a', next_page: null, source_url: 'https://www.javbus.com/star/a', ...extra });

describe('人物页最新影片', () => {
  it('展开后读取，续页保留演员身份并去重，收起和恢复保留结果', async () => {
    const fetcher = vi.fn().mockResolvedValueOnce({ ok: true, json: async () => answer({ items: [film('ABC-001', '2026-10-01', 1)], next_page: 2 }) })
      .mockResolvedValueOnce({ ok: true, json: async () => answer({ items: [film('ABC-002', '2026-09-01'), film('ABC-001', '2026-10-01', 1)] }) });
    vi.stubGlobal('fetch', fetcher);
    const host = await mount(<QueryClientProvider client={queryClient}><EntityReleases id={1} /></QueryClientProvider>);
    expect(fetcher).not.toHaveBeenCalled();
    await click(buttonNamed('最新影片', host));
    await flush();
    expect(host.textContent).toContain('已收藏');
    await click(buttonNamed('加载更多影片', host));
    await flush();
    const params = new URL(String(fetcher.mock.calls[1]![0]), 'https://example.test').searchParams;
    expect(params.get('page')).toBe('2');
    expect(params.get('actor')).toBe('/star/a');
    expect(host.querySelectorAll('li')).toHaveLength(2);
    expect(host.textContent).toContain('未收藏');
    await click(buttonNamed('收起最新影片', host));
    expect(host.querySelector('ul')).toBeNull();
    await click(buttonNamed('最新影片', host));
    await flush();
    expect(host.querySelectorAll('li')).toHaveLength(2);
    expect(fetcher).toHaveBeenCalledTimes(2);
  });

  it('来源验证失败留在原位并提供重试', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => ({ ok: true, json: async () => ({ error: 'JavBus 需要验证' }) })));
    const host = await mount(<QueryClientProvider client={queryClient}><EntityReleases id={2} /></QueryClientProvider>);
    await click(buttonNamed('最新影片', host));
    await flush();
    expect(host.textContent).toContain('JavBus 需要验证');
    expect(host.textContent).toContain('重试');
    expect(host.textContent).not.toContain('暂无影片');
  });

  it('同名候选经选择后读取对应作品', async () => {
    const fetcher = vi.fn().mockResolvedValueOnce({ ok: true, json: async () => answer({ actor: '', actors: [{ path: '/star/b', name: '测试艺名', url: 'https://www.javbus.com/star/b' }] }) })
      .mockResolvedValueOnce({ ok: true, json: async () => answer({ actor: '/star/b', items: [film('DEF-001', '2026-10-02')] }) });
    vi.stubGlobal('fetch', fetcher);
    const host = await mount(<QueryClientProvider client={queryClient}><EntityReleases id={3} /></QueryClientProvider>);
    await click(buttonNamed('最新影片', host));
    await flush();
    await click(buttonNamed('测试艺名', host));
    await flush();
    expect(String(fetcher.mock.calls[1]![0])).toContain('actor=%2Fstar%2Fb');
    expect(host.textContent).toContain('DEF-001');
    expect(buttonNamed('重新选择演员', host)).not.toBeNull();
  });
});
