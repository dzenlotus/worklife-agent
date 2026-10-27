const demoIcons = [
  'M3 10 12 3l9 7M5 9v12h5v-7h4v7h5V9',
  'M21 21l-6-6M17 10a7 7 0 1 1-14 0 7 7 0 0 1 14 0',
  'M5 5h14v16H4V5ZM4 10h16M8 3v5M16 3v5',
  'M9 3h6M10 3v7L4 20h16l-6-10V3M8 15h8',
  'M12 21S2 15 2 8a5 5 0 0 1 10-1A5 5 0 0 1 22 8c0 7-10 13-10 13Z',
  'M5 3h9l5 5v13H5ZM14 3v6h5M8 13h8M8 17h6',
  'M4 21V7h10v14M14 12h6v9M2 21h20M8 3h10v9M8 11h2M8 15h2',
  'm9 3-1 3-3 1-2 4 2 3 3 1 1 3h5l1-3 3-1 2-3-2-4-3-1-1-3ZM15 11a3 3 0 1 1-6 0 3 3 0 0 1 6 0'
];
document.querySelectorAll('.demo-nav > span').forEach((element,index) => {
  element.innerHTML = `<svg viewBox="0 0 24 24" aria-hidden="true"><path d="${demoIcons[index]}"/></svg>`;
});
const copyButton = document.querySelector('#copy-command');
copyButton?.addEventListener('click', async () => {
  const status = document.querySelector('#copy-status');
  try {
    await navigator.clipboard.writeText(document.querySelector('#install-command').textContent);
    copyButton.textContent = 'Скопировано ✓';
    status.textContent = 'Команда запуска скопирована.';
  } catch {
    const selection = window.getSelection();
    const range = document.createRange();
    range.selectNodeContents(document.querySelector('#install-command'));
    selection.removeAllRanges();
    selection.addRange(range);
    status.textContent = 'Команда выделена. Скопируйте её вручную.';
  }
});
