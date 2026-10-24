import { act } from 'react';
import { describe, expect, it, vi } from 'vitest';
import { DetailContinuation } from '../../src/react/components/detail-continuation';
import { click, mount, settle } from './render';

describe('铺满播放器的播放列表', () => {
  it('右侧悬停展开当前队列，点击沿用切换动作，移开收起，退出后恢复底部', async () => {
    const select = vi.fn();
    const host = await mount(<div data-stage="">
      <div className="video-js" data-window-fullscreen="" />
      <DetailContinuation queue={<button data-mix-item="" onClick={select}>队列条目</button>}>
        <button>推荐条目</button>
      </DetailContinuation>
    </div>);
    await settle();
    const player = host.querySelector('.video-js')!;
    const dock = player.querySelector('[data-player-playlist]')!;
    const panel = dock.querySelector<HTMLElement>('[data-player-playlist-panel]')!;
    expect(panel.hidden).toBe(true);
    expect(panel.textContent).toContain('队列条目');
    expect(panel.textContent).not.toContain('推荐条目');
    await act(async () => dock.dispatchEvent(new PointerEvent('pointerover', { bubbles: true })));
    expect(panel.hidden).toBe(false);
    await click(panel.querySelector('[data-mix-item]'));
    expect(select).toHaveBeenCalledOnce();
    await act(async () => dock.dispatchEvent(new PointerEvent('pointerout', { bubbles: true, relatedTarget: document.body })));
    expect(panel.hidden).toBe(true);
    await act(async () => player.removeAttribute('data-window-fullscreen'));
    await settle();
    expect(player.querySelector('[data-player-playlist]')).toBeNull();
    expect(host.querySelector('[data-detail-continuation]')?.textContent).toContain('推荐条目');
  });

  it('没有当前队列时显示推荐，按钮支持展开', async () => {
    const host = await mount(<div data-stage=""><div className="video-js" data-window-fullscreen="" />
      <DetailContinuation queue={null}><button>推荐条目</button></DetailContinuation></div>);
    await settle();
    await click(host.querySelector('[data-player-playlist-edge]'));
    const panel = host.querySelector<HTMLElement>('[data-player-playlist-panel]')!;
    expect(panel.hidden).toBe(false);
    expect(panel.textContent).toContain('推荐条目');
  });
});
