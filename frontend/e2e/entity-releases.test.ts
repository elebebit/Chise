import assert from 'node:assert/strict';
import { after, before, describe, it } from 'node:test';
import type { Browser } from 'playwright-core';
import { launch, layout, settle, visit, VIEWPORTS } from './harness.ts';

describe('人物页最新影片', () => {
  let browser: Browser;
  before(async () => { browser = await launch() });
  after(async () => { await browser.close() });
  for (const viewport of VIEWPORTS) {
    it(`${viewport.name} 按需展开、收藏状态与长标题保持在视口内`, { timeout: 60_000 }, async () => {
      const opened = await visit(browser, '/', viewport);
      const { page } = opened;
      let calls = 0;
      await page.route(url => url.pathname === '/api/entity', route => route.fulfill({ json: {
        id: 90801, kind: 'performer', canonical_name: '测试女优', aliases: [], display_aliases: [],
        asset_count: 1, tags: [], related_performers: [], links: [], external_refs: [], metadata: {},
      } }));
      await page.route(url => url.pathname === '/api/items', route => route.fulfill({ json: { items: [], total: 0 } }));
      await page.route(url => url.pathname === '/api/photos', route => route.fulfill({ json: { items: [], sets: [], total: 0, sample_total: 0 } }));
      await page.route(url => url.pathname === '/api/feeds/discoveries', route => route.fulfill({ json: { items: [] } }));
      await page.route(url => url.pathname === '/api/entity/releases', route => {
        calls += 1;
        return route.fulfill({ json: { actors: [], actor: '/star/a', next_page: null,
          source_url: 'https://www.javbus.com/star/a', items: [
            { code: 'ABC-001', title: '无空格影片标题'.repeat(25), release_date: '2026-10-23', asset_id: 1, url: 'https://www.javbus.com/ABC-001' },
            { code: 'ABC-002', title: '测试影片', release_date: '2026-10-22', asset_id: null, url: 'https://www.javbus.com/ABC-002' },
          ] } });
      });
      try {
        await page.goto(new URL('/performers/测试女优', page.url()).href);
        const trigger = page.getByRole('button', { name: '最新影片', exact: true });
        await trigger.waitFor();
        assert.equal(calls, 0);
        await trigger.click();
        await page.locator('[data-entity-releases] li').first().waitFor();
        await settle(page);
        const section = page.locator('[data-entity-releases]');
        assert.match(await section.innerText(), /已收藏/);
        assert.match(await section.innerText(), /未收藏/);
        assert.equal(calls, 1);
        const bounds = await layout(page);
        assert.equal(bounds.scrollWidth, bounds.viewportWidth);
        assert.deepEqual(bounds.offenders, []);
        await page.getByRole('button', { name: '收起最新影片', exact: true }).click();
        assert.equal(await section.locator('li').count(), 0);
        await trigger.click();
        await section.locator('li').first().waitFor();
        assert.equal(calls, 1);
        assert.deepEqual(opened.problems, []);
      } finally { await opened.close() }
    });
  }
});
