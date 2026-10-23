import { afterEach, beforeAll, describe, expect, it, vi } from 'vitest';
import { createV10Player } from '../src/player/v10-player';

const engine = () => ({ bandwidthEstimate: 8000000, currentLevel: -1,
  levels: [{ width: 1280, height: 720 }, { width: 1920, height: 1080 }], on: vi.fn() });

class TestMedia extends HTMLElement {
  source: unknown = null;
  engine = engine();
  adapter = { destroy: vi.fn() };
}
beforeAll(() => {
  if (!customElements.get('hlsjs-video')) customElements.define('hlsjs-video', TestMedia);
  if (!customElements.get('dash-video')) customElements.define('dash-video', class extends TestMedia {});
});
afterEach(() => {
  document.body.replaceChildren(); vi.restoreAllMocks();
  delete (window as Window & { chiseDesktop?: boolean }).chiseDesktop;
});

function mounted() {
  const video = document.createElement('video'); document.body.append(video);
  const player = createV10Player(video, { controls: false });
  const media = player.el().querySelector('hlsjs-video') as TestMedia;
  return { video, player, media };
}

describe('Video.js 10 播放会话', () => {
  it('App 全屏铺满窗口，按钮、Escape 与销毁保持状态一致', () => {
    (window as Window & { chiseDesktop?: boolean }).chiseDesktop = true;
    const video = document.createElement('video'); document.body.append(video);
    const player = createV10Player(video, { controls: true });
    const changed = vi.fn(); player.on('fullscreenchange', changed);
    const button = player.el().querySelector<HTMLButtonElement>('button.vjs-fullscreen-control')!;
    const request = vi.fn(); player.el().requestFullscreen = request;
    button.click();
    expect(player.isFullscreen()).toBe(true);
    expect(player.el().hasAttribute('data-window-fullscreen')).toBe(true);
    expect(button.getAttribute('aria-pressed')).toBe('true');
    expect(request).not.toHaveBeenCalled();
    const escape = new KeyboardEvent('keydown', { key: 'Escape', bubbles: true, cancelable: true });
    button.dispatchEvent(escape);
    expect(escape.defaultPrevented).toBe(true);
    expect(player.isFullscreen()).toBe(false);
    button.click(); button.click();
    expect(player.isFullscreen()).toBe(false);
    video.dispatchEvent(new MouseEvent('dblclick', { bubbles: true }));
    expect(player.isFullscreen()).toBe(true);
    player.dispose();
    expect(player.isFullscreen()).toBe(false);
    expect(changed).toHaveBeenCalledTimes(6);
  });

  it('浏览器沿用媒体元素的标准全屏控件', () => {
    const video = document.createElement('video'); document.body.append(video);
    const player = createV10Player(video, { controls: true });
    expect(player.el().querySelector('media-fullscreen-button')).not.toBeNull();
    expect(player.el().querySelector('button.vjs-fullscreen-control')).toBeNull();
    player.dispose();
  });
  it('片源交给异步 adapter 后立即播放，原生 play 使用已挂载的片源', async () => {
    const { video, player, media } = mounted();
    Object.defineProperty(media, 'source', { set: (value: { src: string }) => {
      queueMicrotask(() => { video.src = value.src });
    } });
    const play = vi.spyOn(video, 'play').mockImplementation(() => video.getAttribute('src')
      ? Promise.resolve() : Promise.reject(new DOMException('没有可播放的片源', 'NotSupportedError')));
    player.src({ src: '/example.mp4', type: 'video/mp4' });
    await expect(player.play()).resolves.toBeUndefined();
    expect(play).toHaveBeenCalledOnce();
    expect(video.src).toContain('/example.mp4');
    player.dispose();
  });

  it.each(['pause', 'source', 'dispose'] as const)('排队播放期间 %s 会取消该请求', async action => {
    const { video, player } = mounted();
    const play = vi.spyOn(video, 'play').mockResolvedValue(undefined);
    const pending = player.play();
    if (action === 'pause') player.pause();
    else if (action === 'source') player.src({ src: '/next.mp4', type: 'video/mp4' });
    else player.dispose();
    await expect(pending).rejects.toMatchObject({ name: 'AbortError' });
    expect(play).not.toHaveBeenCalled();
    player.dispose();
  });

  it('媒体错误可补充来源状态文案，展示错误不会再次触发错误处理', () => {
    const { player, media } = mounted();
    const callback = vi.fn(() => player.error({ code: 2, message: '媒体目录无法访问' }));
    player.on('error', callback);
    media.dispatchEvent(new Event('error'));
    expect(callback).toHaveBeenCalledOnce();
    expect(player.error()).toEqual({ code: 2, message: '媒体目录无法访问' });
    player.dispose();
  });

  it('固定清晰度和自动码率使用同一条 HLS 引擎，带宽读取实际估计', async () => {
    const { player, media } = mounted();
    player.src({ src: '/example.m3u8', type: 'application/vnd.apple.mpegurl' });
    const levels = player.qualityLevels!();
    expect(levels.length).toBe(2);
    videoMetadata(player.el()); videoMetadata(player.el());
    expect(media.engine.on).toHaveBeenCalledTimes(2);
    levels[0]!.enabled = false; levels[1]!.enabled = true;
    await Promise.resolve(); expect(media.engine.currentLevel).toBe(1);
    levels[0]!.enabled = true; levels[1]!.enabled = true;
    await Promise.resolve(); expect(media.engine.currentLevel).toBe(-1);
    expect(player.bandwidth!()).toBe(8000000);
    player.dispose();
  });

  it('清晰度选择排队后切换片源或销毁，不再写入旧引擎', async () => {
    const { player, media } = mounted();
    player.src({ src: '/first.m3u8', type: 'application/vnd.apple.mpegurl' });
    const levels = player.qualityLevels!();
    levels[0]!.enabled = false; levels[1]!.enabled = true;
    player.src({ src: '/second.m3u8', type: 'application/vnd.apple.mpegurl' });
    await Promise.resolve(); expect(media.engine.currentLevel).toBe(-1);
    levels[0]!.enabled = false; levels[1]!.enabled = true;
    player.dispose();
    await Promise.resolve(); expect(media.engine.currentLevel).toBe(-1);
  });

  it('HLS 与 DASH 切源保留原生视频和字幕，销毁停播并解除事件', () => {
    const { video, player, media } = mounted();
    const pause = vi.spyOn(video, 'pause').mockImplementation(() => {});
    const load = vi.spyOn(video, 'load').mockImplementation(() => {});
    const played = vi.fn(); player.on('play', played);
    video.dispatchEvent(new Event('play')); expect(played).toHaveBeenCalledOnce();
    const track = document.createElement('track'); track.label = '中文'; video.append(track);
    player.src({ src: '/example.mpd', type: 'application/dash+xml' });
    expect(media.adapter.destroy).toHaveBeenCalledOnce();
    expect(player.el().querySelector('dash-video > video')).toBe(video);
    expect(video.querySelector('track')).toBe(track);
    player.dispose(); player.dispose();
    expect(pause).toHaveBeenCalledOnce(); expect(load).toHaveBeenCalledOnce();
    video.dispatchEvent(new Event('play')); expect(played).toHaveBeenCalledOnce();
    expect(document.querySelector('.video-js')).toBeNull();
  });
});

function videoMetadata(root: HTMLElement) { root.querySelector('video')!.dispatchEvent(new Event('loadedmetadata')) }
