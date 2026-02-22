/**
 * Ozon Cheque Downloader
 * 
 * Скрипт для массового скачивания электронных чеков с Ozon.
 * 
 * Использование:
 * 1. Откройте страницу "Электронные чеки" на ozon.ru (https://www.ozon.ru/my/cheques)
 * 2. Откройте консоль браузера (F12 → Console)
 * 3. Вставьте этот скрипт и нажмите Enter
 * 4. В диалоге выберите папку для сохранения
 * 5. Дождитесь завершения скачивания
 * 
 * Требования: Chrome/Edge (File System Access API)
 */
(async () => {
  // 1. Выбираем папку
  let dirHandle;
  try {
    dirHandle = await window.showDirectoryPicker({ mode: 'readwrite' });
  } catch (e) {
    console.log('Отменено пользователем');
    return;
  }

  // 2. Парсим ссылки на чеки из JSON-данных страницы
  const html = document.documentElement.innerHTML;
  const regex = /https?:\\u002F\\u002Fozon\.ru\\u002F_action\\u002FdownloadCheque\?id=([a-f0-9-]+)(?:\\u0026amp;|&amp;)rawdata=1(?:\\u0026amp;|&amp;)download=1/g;
  
  const links = new Set();
  let match;
  while ((match = regex.exec(html)) !== null) {
    let url = match[0].replace(/\\u002F/g, '/').replace(/\\u0026amp;/g, '&').replace(/&amp;/g, '&');
    url = url.replace('https://ozon.ru/', 'https://www.ozon.ru/');
    links.add(url);
  }

  const urls = [...links];
  console.log(`Найдено ${urls.length} чеков → папка: ${dirHandle.name}`);
  if (!urls.length) { console.error('Чеки не найдены. Убедитесь, что вы на странице "Электронные чеки"'); return; }

  // 3. Прогресс-бар
  const status = document.createElement('div');
  status.style.cssText = 'position:fixed;top:10px;right:10px;z-index:99999;background:#333;color:#0f0;padding:15px 20px;border-radius:8px;font-family:monospace;font-size:14px;';
  document.body.appendChild(status);

  let ok = 0, fail = 0;
  const DELAY = 1500; // мс между запросами

  for (let i = 0; i < urls.length; i++) {
    const url = urls[i];
    const id = url.match(/id=([^&]+)/)?.[1] || `cheque_${i}`;
    const orderNum = id.split('-').slice(0, 2).join('-');
    const filename = `ozon_cheque_${orderNum}_${id.slice(-8)}.pdf`;
    
    status.textContent = `⏳ ${i + 1}/${urls.length}: ${filename}`;

    try {
      const resp = await fetch(url, { credentials: 'include' });
      if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
      const blob = await resp.blob();

      // Пишем файл в выбранную папку
      const fileHandle = await dirHandle.getFileHandle(filename, { create: true });
      const writable = await fileHandle.createWritable();
      await writable.write(blob);
      await writable.close();
      
      ok++;
      console.log(`✅ ${filename}`);
    } catch (e) {
      console.error(`❌ ${filename}:`, e);
      fail++;
    }

    if (i < urls.length - 1) await new Promise(r => setTimeout(r, DELAY));
  }

  status.style.background = fail ? '#5c3a1a' : '#1a5c1a';
  status.textContent = `✅ Готово! Сохранено: ${ok}, ошибок: ${fail} → ${dirHandle.name}`;
  setTimeout(() => status.remove(), 10000);
})();
