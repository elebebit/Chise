/** 人物页的 JavBus 最新影片，查询与展开状态按实体隔离。 */
import { useInfiniteQuery } from '@tanstack/react-query';
import { useState } from 'react';
import { api } from '@peach/legacy/core';

import { Button } from '@/components/base/buttons/button';
import { errorMessage } from '../../api';
import { EmptyState } from '../components/empty-state';
import { RetryNote } from '../components/grid-reveal';
import { spriteGlyph } from '../components/sprite-glyph';
import { busyProps } from '../settings/busy-props';

interface Release {
  code: string; title: string; release_date: string; url: string; asset_id: number | null;
}
interface Releases {
  items: Release[]; actors: { path: string; name: string; url: string }[];
  actor: string; next_page: number | null; source_url: string; error?: string;
}

export async function fetchEntityReleases(id: number, actor: string, page: number): Promise<Releases> {
  const params = new URLSearchParams({ id: String(id), page: String(page) });
  if (actor) params.set('actor', actor);
  const result = await api(`/api/entity/releases?${params}`) as Releases;
  if (result.error) throw Object.assign(new Error(result.error), { sourceUrl: result.source_url });
  return result;
}

export function EntityReleases({ id }: { id: number }) {
  const [open, setOpen] = useState(false);
  const [actor, setActor] = useState('');
  const query = useInfiniteQuery({
    queryKey: ['entity-releases', id, actor], enabled: open,
    initialPageParam: { page: 1, actor },
    queryFn: ({ pageParam }) => fetchEntityReleases(id, pageParam.actor, pageParam.page),
    getNextPageParam: (last) => last.next_page ? { page: last.next_page, actor: last.actor } : undefined,
    staleTime: 3600000, retry: false,
  });
  const first = query.data?.pages[0];
  const sourceUrl = first?.source_url || (query.error as (Error & { sourceUrl?: string }) | null)?.sourceUrl;
  const unique = new Map<string, Release>();
  query.data?.pages.forEach(page => page.items.forEach(item => unique.set(item.code, item)));
  const items = [...unique.values()].sort((a, b) => b.release_date.localeCompare(a.release_date) || a.code.localeCompare(b.code));
  return (
    <section data-entity-releases="" className="my-4 flex min-w-0 flex-col gap-3" aria-label="最新影片">
      <div className="flex flex-wrap items-center gap-3">
        <Button size="small" variant="secondary" aria-expanded={open} aria-controls={`entity-releases-${id}`}
          onClick={() => setOpen(!open)}>{open ? '收起最新影片' : '最新影片'}</Button>
        {open ? <span className="text-caption-1-regular text-text-secondary">JavBus</span> : null}
        {open && sourceUrl ? <a href={sourceUrl} target="_blank" rel="noreferrer"
          className="text-caption-1-regular underline">在 JavBus 查看</a> : null}
        {open && actor ? <Button size="small" variant="ghost" onClick={() => setActor('')}>重新选择演员</Button> : null}
      </div>
      {open ? <div id={`entity-releases-${id}`} className="flex min-w-0 flex-col gap-3">
        {query.isPending ? <div aria-busy="true" aria-label="正在读取最新影片" data-skeleton="releases"
          className="relative h-40 rounded-xl skeleton-sheen" /> : null}
        {query.isError ? <RetryNote message={errorMessage(query.error)} onRetry={() => { void query.refetch() }} /> : null}
        {first && !first.actor ? first.actors.length ? <div className="flex flex-col gap-2">
          <p className="text-body-2-regular text-text-secondary">选择 JavBus 中的演员</p>
          <div className="flex flex-wrap gap-2">{first.actors.map(person => <Button key={person.path} size="small" variant="secondary"
            onClick={() => setActor(person.path)}>{person.name}</Button>)}</div>
        </div> : <EmptyState icon={spriteGlyph('search')} title="未找到这位演员" shell="plain">
          可以在 JavBus 中换一个名字搜索。
        </EmptyState> : null}
        {first?.actor && !items.length ? <EmptyState icon={spriteGlyph('film')} title="暂无影片" shell="plain">
          JavBus 暂未列出这位演员的作品。
        </EmptyState> : null}
        {items.length ? <ul className="flex min-w-0 flex-col divide-y divide-separator-border">{items.map(item => <li key={item.code}
          className="flex min-w-0 flex-wrap items-baseline gap-x-3 gap-y-1 py-3">
          <a href={item.url} target="_blank" rel="noreferrer" className="min-w-0 flex-1 text-body-2-regular wrap-anywhere hover:underline">
            <strong className="font-medium">{item.code}</strong> {item.title}
          </a>
          <span className="text-caption-1-regular text-text-secondary">{item.asset_id ? '已收藏' : '未收藏'}</span>
          <time className="text-caption-1-regular text-text-secondary">{item.release_date || '日期未知'}</time>
        </li>)}</ul> : null}
        {query.hasNextPage ? <Button size="small" variant="secondary" {...busyProps(query.isFetchingNextPage)}
          onClick={() => { if (!query.isFetchingNextPage) void query.fetchNextPage() }}>加载更多影片</Button> : null}
      </div> : null}
    </section>
  );
}
