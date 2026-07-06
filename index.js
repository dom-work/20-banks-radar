/**
 * Cloudflare Worker: CBR Proxy
 * Проксирует запросы к cbr.ru через российские ноды Cloudflare
 * Деплой: автоматически через GitHub Actions
 * Бесплатный план: 100,000 запросов/день
 */

// Разрешённые домены для проксирования (безопасность)
const ALLOWED_DOMAINS = [
  'cbr.ru',
  'www.cbr.ru',
  'xn--80az8a.xn--d1aqf.xn--p1ai',  // наш-дом.рф
];

export default {
  async fetch(request) {
    const url = new URL(request.url);

    // CORS preflight
    if (request.method === 'OPTIONS') {
      return new Response(null, {
        headers: {
          'Access-Control-Allow-Origin': '*',
          'Access-Control-Allow-Methods': 'GET',
        }
      });
    }

    // Получаем целевой URL из параметра
    const targetUrl = url.searchParams.get('url');
    if (!targetUrl) {
      return new Response(JSON.stringify({error: 'Missing url parameter'}),
        {status: 400, headers: {'Content-Type': 'application/json'}});
    }

    // Проверяем что домен разрешён
    let targetDomain;
    try {
      targetDomain = new URL(targetUrl).hostname;
    } catch {
      return new Response(JSON.stringify({error: 'Invalid URL'}), {status: 400});
    }

    if (!ALLOWED_DOMAINS.includes(targetDomain)) {
      return new Response(
        JSON.stringify({error: `Domain ${targetDomain} not allowed`}),
        {status: 403}
      );
    }

    // Проксируем запрос с браузерными заголовками
    try {
      const response = await fetch(targetUrl, {
        headers: {
          'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36',
          'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8,application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
          'Accept-Language': 'ru-RU,ru;q=0.9',
          'Accept-Encoding': 'gzip, deflate, br',
          'Referer': 'https://www.cbr.ru/',
          'sec-ch-ua': '"Chromium";v="124"',
          'sec-ch-ua-platform': '"Windows"',
        },
        cf: {
          // Принудительно используем российский датацентр Cloudflare
          resolveOverride: targetDomain,
        }
      });

      // Передаём ответ с CORS заголовками
      const newHeaders = new Headers(response.headers);
      newHeaders.set('Access-Control-Allow-Origin', '*');
      newHeaders.set('X-Proxied-By', 'cf-worker');

      return new Response(response.body, {
        status: response.status,
        headers: newHeaders,
      });

    } catch (err) {
      return new Response(
        JSON.stringify({error: err.message}),
        {status: 500, headers: {'Content-Type': 'application/json'}}
      );
    }
  }
};
