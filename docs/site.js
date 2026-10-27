const copyButton = document.querySelector('.copy-button');
const copyStatus = document.querySelector('#copy-status');

if (navigator.clipboard && copyButton) {
  copyButton.hidden = false;
  copyButton.addEventListener('click', async () => {
    try {
      await navigator.clipboard.writeText(document.querySelector('#install-commands').textContent);
      copyButton.textContent = 'Скопировано ✓';
      copyStatus.textContent = 'Команды установки скопированы.';
    } catch {
      copyStatus.textContent = 'Не удалось скопировать. Выделите команды в блоке и скопируйте их вручную.';
    }
  });
}
