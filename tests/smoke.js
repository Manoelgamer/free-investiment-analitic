const fs = require('fs');
const { JSDOM, VirtualConsole } = require('jsdom');

const html = fs.readFileSync(process.argv[2] || 'index.html', 'utf8');
const errors = [];
const vc = new VirtualConsole();
vc.on('jsdomError', e => errors.push('jsdomError: ' + (e.stack || e.message)));
vc.on('error', (...a) => errors.push('console.error: ' + a.join(' ')));

const dom = new JSDOM(html, {
  runScripts: 'dangerously',
  pretendToBeVisual: true,
  url: 'https://example.com/',
  virtualConsole: vc,
  beforeParse(win) {
    const noop = () => {};
    const ctx = new Proxy({}, {
      get(t, k) {
        if (k === 'createLinearGradient') return () => ({ addColorStop: noop });
        if (k === 'measureText') return () => ({ width: 50 });
        return t[k] || noop;
      },
      set(t, k, v) { t[k] = v; return true; }
    });
    win.HTMLCanvasElement.prototype.getContext = () => ctx;
    Object.defineProperty(win.HTMLCanvasElement.prototype, 'clientWidth', { get: () => 600 });
    win.HTMLCanvasElement.prototype.getBoundingClientRect = () => ({ left: 0, top: 0, width: 600, height: 290 });
    win.fetch = () => Promise.reject(new Error('offline smoke test'));
    win.alert = noop;
    win.confirm = () => true;
    win.scrollTo = noop;
    win.HTMLElement.prototype.scrollIntoView = noop;
  }
});

const w = dom.window, d = w.document;
const routes = [
  '#/acoes', '#/indices', '#/fis', '#/cripto', '#/cambio', '#/ativos',
  '#/ativo/PETR4', '#/ativo/MXRF11', '#/gestoras', '#/mapa-setores',
  '#/setor/Bancos', '#/calendario', '#/noticias', '#/arquivo-noticias',
  '#/noticia/n1', '#/tradeletter', '#/carta/tl1', '#/academy', '#/videos',
  '#/calculadoras', '#/simulador', '#/historico', '#/comparador',
  '#/busca', '#/sobre', '#/privacidade', '#/nao-existe'
];

setTimeout(() => {
  const checks = [];
  const ck = (name, ok) => checks.push([name, !!ok]);
  ck('ticker preenchido', d.querySelectorAll('#tickerTrack .tick').length > 0);
  ck('setores preenchidos', d.querySelectorAll('#sectorGrid .sector').length === 24);
  ck('noticias preenchidas', d.querySelectorAll('#newsList .news-item').length > 0);
  ck('calendario preenchido', d.querySelectorAll('#calTeaser .cal-row').length > 0);
  ck('skip-link presente', !!d.querySelector('.skip-link'));
  ck('noscript presente', !!d.querySelector('noscript'));
  ck('export/import presentes', !!d.querySelector('#exportBtn') && !!d.querySelector('#importBtn'));

  let i = 0;
  const next = () => {
    if (i >= routes.length) {
      console.log('\n=== RESULTADO ===');
      let fail = 0;
      for (const [n, ok] of checks) { if (!ok) fail++; console.log((ok ? 'PASS ' : 'FAIL ') + n); }
      console.log('\nErros capturados: ' + errors.length);
      errors.slice(0, 15).forEach(e => console.log('  ' + e.split('\n')[0]));
      console.log('\n' + (fail === 0 && errors.length === 0 ? 'SMOKE OK' : 'SMOKE COM PROBLEMAS'));
      process.exit(fail === 0 && errors.length === 0 ? 0 : 1);
    }
    const r = routes[i++];
    w.location.hash = r;
    w.dispatchEvent(new w.HashChangeEvent('hashchange'));
    setTimeout(() => {
      const view = d.querySelector('#view-dynamic');
      const espera404 = r === '#/nao-existe';
      ck('rota ' + r, view && view.innerHTML.length > 200 && (espera404 ? /Página não encontrada/.test(view.innerHTML) : !/Página não encontrada/.test(view.innerHTML)));
      next();
    }, 5);
  };
  next();
}, 100);
