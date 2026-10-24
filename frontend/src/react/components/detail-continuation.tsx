import { useLayoutEffect, useRef, useState, type ReactNode } from 'react';
import { createPortal } from 'react-dom';
import { FullscreenPlaylist } from './fullscreen-playlist';

/** 详情底部：当前作品的分集队列与后续推荐共享一行。 */
export function DetailContinuation({ queue, children, editionCards }: { queue: ReactNode; children: ReactNode; editionCards?: number }) {
  const anchor = useRef<HTMLSpanElement>(null);
  const [player, setPlayer] = useState<HTMLElement | null>(null);
  useLayoutEffect(() => {
    const stage = anchor.current?.closest('[data-stage]');
    if (!stage) return;
    const sync = () => setPlayer(stage.querySelector<HTMLElement>('.video-js[data-window-fullscreen]'));
    const observer = new MutationObserver(sync);
    observer.observe(stage, { childList: true, subtree: true, attributes: true, attributeFilter: ['data-window-fullscreen'] });
    sync();
    return () => observer.disconnect();
  }, []);
  return <>
    <span ref={anchor} hidden />
    {player && (queue || children)
      ? createPortal(<FullscreenPlaylist>{queue || children}</FullscreenPlaylist>, player)
      : <div data-detail-continuation="" data-edition-cards={editionCards == null ? undefined : Math.min(3, editionCards)}>{queue}{children}</div>}
  </>;
}
