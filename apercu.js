// Aperçus iPhone 14 (Safari, iOS 26) — see CLAUDE.md.
//   const { phone, shot } = require('./apercu.js');
//   const { page, close } = await phone({ landscape: false, dark: false });
//   ... drive the app ...
//   await shot(page, 'out.png');   // framed: status bar, Safari's address bar, home bar
//   await close();
// Portrait: 390 × 844 screen, the page gets 390 × 736 (status bar 47 pt, compact
// address bar 61 pt). Landscape: 844 × 390, page 844 × 369 (home bar).
// Chromium stands in for WebKit and Linux fonts for SF Pro: the layout and the
// sizes are the iPhone's, the type and the emoji look a little different.
const { chromium, devices } = require('playwright');

const P = { w: 390, h: 844, top: 47, bottom: 61 }, L = { w: 844, h: 390, top: 0, bottom: 21 };

async function phone({ landscape = false, dark = false, url = 'http://localhost:8765/index.html', skipNews = true } = {}) {
  const g = landscape ? L : P;
  const browser = await chromium.launch();
  const ctx = await browser.newContext({
    ...devices['iPhone 14'],
    viewport: { width: g.w, height: g.h - g.top - g.bottom },
    screen: { width: g.w, height: g.h },
    colorScheme: dark ? 'dark' : 'light',
  });
  const page = await ctx.newPage();
  page.__geom = g; page.__dark = dark; page.__url = url;
  await page.goto(url);
  if (skipNews) { await page.evaluate(() => localStorage.setItem('ankitrain_v1_news_seen', '999')); await page.reload(); }
  return { page, ctx, browser, close: () => browser.close() };
}

async function shot(page, out, { time = '17:08' } = {}) {
  const g = page.__geom, dark = page.__dark;
  const png = (await page.screenshot()).toString('base64');
  const fg = dark ? '#fff' : '#000', bar = dark ? 'rgba(30,30,32,.92)' : 'rgba(246,246,248,.92)';
  const host = new URL(page.__url).host;
  const html = `<html><body style="margin:0;background:${dark ? '#000' : '#fff'};font-family:-apple-system,'Inter','Helvetica Neue',Arial,sans-serif">
  <div style="position:relative;width:${g.w}px;height:${g.h}px;overflow:hidden;border-radius:${g === P ? 47 : 0}px">
    ${g.top ? `<div style="height:${g.top}px;display:flex;align-items:center;justify-content:space-between;padding:0 34px 0 46px;color:${fg};font-weight:600;font-size:16px;background:${dark ? '#111214' : '#fff'}">
      <span>${time}</span><span style="font-size:13px;letter-spacing:1px">▂▄▆ ᯤ ▭</span></div>` : ''}
    <img src="data:image/png;base64,${png}" style="display:block;width:${g.w}px">
    <div style="position:absolute;left:0;right:0;bottom:0;height:${g.bottom}px;background:${g === P ? bar : 'transparent'};display:flex;flex-direction:column;align-items:center;justify-content:flex-end;padding-bottom:7px;box-sizing:border-box">
      ${g === P ? `<div style="font-size:14px;color:${fg};margin-bottom:12px">🔒 ${host}</div>` : ''}
      <div style="width:134px;height:5px;border-radius:3px;background:${fg};opacity:.85"></div>
    </div>
  </div></body></html>`;
  const fp = await page.context().browser().newPage({ viewport: { width: g.w, height: g.h }, deviceScaleFactor: 2 });
  await fp.setContent(html);
  await fp.screenshot({ path: out, omitBackground: false });
  await fp.close();
}

module.exports = { phone, shot };
