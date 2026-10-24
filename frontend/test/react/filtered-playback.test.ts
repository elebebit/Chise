import { afterEach, describe, expect, it, vi } from 'vitest';
import { fetchQueue, nextPart, queueKey, queueRef } from '../../src/react/item-detail/item-detail';

const helpers = { mixRelated: vi.fn(), tagLabel: (value: string) => value };
afterEach(() => vi.unstubAllGlobals());

describe('主页筛选播放队列', () => {
  it('跨页沿用文件夹、标签和排序，排除图片并去重，保持返回顺序', async () => {
    const params = new URLSearchParams({ folder: 'R:\\Fixture', folder_recursive: '1', tag: '测试标签', sort: 'name', dir: 'asc', seed: 'fixed' }).toString();
    const fetcher = vi.fn(async (url: string) => {
      const query = new URL(url, 'http://peach.test').searchParams;
      const offset = Number(query.get('offset'));
      return { ok: true, status: 200, json: async () => offset === 0
        ? { total: 62, has_more: true, items: Array.from({ length: 60 }, (_, index) => ({ id: index + 1, medium: index === 4 ? 'image' : 'video' })) }
        : { has_more: false, items: [{ id: 60, medium: 'video' }, { id: 61, medium: 'video' }] } };
    });
    vi.stubGlobal('fetch', fetcher);
    const queue = await fetchQueue({ kind: 'catalog', params }, helpers, new AbortController().signal);
    expect(queue.items.map(row => row.id)).toEqual([...Array.from({ length: 60 }, (_, index) => index + 1).filter(id => id !== 5), 61]);
    expect(fetcher).toHaveBeenCalledTimes(2);
    for (const [url] of fetcher.mock.calls) {
      const query = new URL(url, 'http://peach.test').searchParams;
      for (const [key, value] of new URLSearchParams(params)) expect(query.get(key)).toBe(value);
    }
    expect(queueRef(queue)).toMatchObject({ kind: 'catalog', params });
    expect(nextPart(queue, 60)?.id).toBe(61);
    expect(nextPart(queue, 61)).toBeNull();
  });

  it('折叠规则与主页一致，筛选与排序各有独立队列身份', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => ({ ok: true, status: 200, json: async () => ({ total: 3, items: [
      { id: 1, part_group: { key: 'same' } }, { id: 2, part_group: { key: 'same' } }, { id: 3 },
    ] }) })));
    const queue = await fetchQueue({ kind: 'catalog', params: 'tag=A', groupCollapse: true }, helpers);
    expect(queue.items.map(row => row.id)).toEqual([1, 3]);
    expect(queueKey({ kind: 'catalog', params: 'tag=A' })).not.toEqual(queueKey({ kind: 'catalog', params: 'tag=B' }));
    expect(queueKey({ kind: 'catalog', params: 'sort=name' })).not.toEqual(queueKey({ kind: 'catalog', params: 'sort=dur' }));
  });

  it('取消时停止取后续页', async () => {
    const abort = new AbortController(); abort.abort();
    const fetcher = vi.fn(); vi.stubGlobal('fetch', fetcher);
    await expect(fetchQueue({ kind: 'catalog', params: 'tag=A' }, helpers, abort.signal)).rejects.toMatchObject({ name: 'AbortError' });
    expect(fetcher).not.toHaveBeenCalled();
  });
});
