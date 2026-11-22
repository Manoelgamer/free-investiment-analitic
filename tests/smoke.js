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
    win.fetch = url => {
      if (String(url).includes('/api/v2/currency')) {
        return Promise.resolve({
          status: 200,
          ok: true,
          headers: { get: () => null },
          json: () => Promise.resolve({ currency: [
            { fromCurrency: 'USD', toCurrency: 'BRL', bidPrice: '5,8889', askPrice: '5,9000', percentageChange: '1,35' },
            { fromCurrency: 'EUR', toCurrency: 'BRL', bidPrice: '6,4672', askPrice: '6,4800', percentageChange: '1,49' }
          ] })
        });
      }
      if (String(url).includes('brapi.dev')) {
        return Promise.resolve({
          status: 200,
          ok: true,
          headers: { get: () => null },
          json: () => Promise.resolve({ results: [{
            symbol: 'PETR4',
            data: { regularMarketPrice: 99.99, regularMarketChangePercent: 1.23, shortName: 'PETR4 ao vivo' }
          }] })
        });
      }
      return Promise.reject(new Error('offline smoke test'));
    };
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
  ck('manifest PWA presente', !!d.querySelector('link[rel="manifest"]'));
  ck('painel da chave Brapi presente', !!d.querySelector('#brapiPanel #brapiTokenInput') && !!d.querySelector('#brapiSave'));
  const slideTexts = [...d.querySelectorAll('#slides .slide:not(.clone)')].map(s => s.textContent);
  ck('carrossel com 4 destaques', slideTexts.length === 4);
  ck('clones para loop infinito', d.querySelectorAll('#slides .slide.clone').length === 2);
  ck('destaque de quedas', /mais caíram/.test(slideTexts[0] || ''));
  ck('destaque de Graham', /Graham/.test(slideTexts[1] || ''));
  ck('descontos segundo players', /Players do mercado/.test(slideTexts[2] || '') && /preço-alvo/.test(slideTexts[2] || ''));
  ck('ranking de casas', /Casas de análise/.test(slideTexts[3] || ''));
  ck('barras interativas', d.querySelectorAll('#slides [data-bar]').length >= 12);

  const finish = () => {
    console.log('\n=== RESULTADO ===');
    let fail = 0;
    for (const [n, ok] of checks) { if (!ok) fail++; console.log((ok ? 'PASS ' : 'FAIL ') + n); }
    console.log('\nErros capturados: ' + errors.length);
    errors.slice(0, 15).forEach(e => console.log('  ' + e.split('\n')[0]));
    console.log('\n' + (fail === 0 && errors.length === 0 ? 'SMOKE OK' : 'SMOKE COM PROBLEMAS'));
    process.exit(fail === 0 && errors.length === 0 ? 0 : 1);
  };

  // Cenário da chave Brapi + câmbio ao vivo
  const testarChaveECambio = () => {
    d.querySelector('#brapiTokenInput').value = 'token_de_teste';
    d.querySelector('#brapiSave').click();
    setTimeout(() => {
      ck('chave salva no painel', /Chave salva/.test(d.querySelector('#brapiStatus').textContent));
      ck('dólar ao vivo no ticker', /5,8889/.test(d.querySelector('#tickerTrack').textContent));
      w.location.hash = '#/cambio';
      w.dispatchEvent(new w.HashChangeEvent('hashchange'));
      setTimeout(() => {
        ck('câmbio ao vivo na tabela', /5,8889/.test(d.querySelector('#marketRows').textContent));
        ck('status do câmbio', /Câmbio ao vivo/.test(d.querySelector('#liveStatus').textContent));
        finish();
      }, 80);
    }, 100);
  };

  let i = 0;
  const next = () => {
    if (i >= routes.length) { testarChaveECambio(); return; }
    const r = routes[i++];
    w.location.hash = r;
    w.dispatchEvent(new w.HashChangeEvent('hashchange'));
    setTimeout(() => {
      const view = d.querySelector('#view-dynamic');
      const espera404 = r === '#/nao-existe';
      ck('rota ' + r, view && view.innerHTML.length > 200 && (espera404 ? /Página não encontrada/.test(view.innerHTML) : !/Página não encontrada/.test(view.innerHTML)));
      if (r === '#/acoes') {
        const btn = d.querySelector('[data-act="live-quotes"]');
        ck('botão de cotações ao vivo', !!btn);
        if (btn) {
          btn.click();
          setTimeout(() => {
            const st = d.querySelector('#liveStatus');
            ck('status ao vivo atualizado', st && /ao vivo/.test(st.textContent));
            ck('preço ao vivo na tabela', /99,99/.test(d.querySelector('#marketRows').textContent));
            next();
          }, 80);
          return;
        }
      }
      next();
    }, 5);
  };
  next();
}, 100);
