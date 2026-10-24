import { useId, useState, type ReactNode } from 'react';

/** 播放器右边缘与列表共用悬停区域，键盘焦点也能展开列表。 */
export function FullscreenPlaylist({ children }: { children: ReactNode }) {
  const [open, setOpen] = useState(false);
  const id = useId();
  return <aside data-player-playlist="" onPointerEnter={() => setOpen(true)} onPointerLeave={() => setOpen(false)}
    onFocusCapture={() => setOpen(true)} onBlurCapture={event => {
      if (!event.currentTarget.contains(event.relatedTarget)) setOpen(false);
    }}>
    <button type="button" data-player-playlist-edge="" aria-label="播放列表" aria-expanded={open} aria-controls={id}
      onClick={() => setOpen(true)} />
    <div id={id} data-player-playlist-panel="" hidden={!open} aria-label="播放列表">
      <h2 data-player-playlist-title="">播放列表</h2>
      {children}
    </div>
  </aside>;
}
