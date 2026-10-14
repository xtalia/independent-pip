# Разработка и проверка

Расширение не требует npm-сборки или внешних runtime-зависимостей. Загружай папку `extension/` напрямую. Не меняй её путь при обновлении, если хочешь сохранить ID и настройки.

## Быстрые безопасные проверки

Нужны Python и Node.js:

```text
python -m unittest discover -s tests -p test_browser_lab.py -v
node --check extension/background.js
node --check extension/pip.js
node --check extension/settings.js
node --check extension/options.js
```

На Linux для импорта тестового стенда задай `TMPDIR` на существующую временную папку. CI делает это через `runner.temp`.

## Реальные browser integration tests — Windows

Текущий стенд рассчитан на установленный Chrome по пути `C:/Program Files/Google/Chrome/Application/chrome.exe`, Node.js с встроенным WebSocket и Python. Он использует отдельный профиль под `%LOCALAPPDATA%/hermes/cache/scratch/independent-pip-lab/`, а не обычный профиль Chrome. Нужна современная версия Chrome с CDP Extensions и Document PiP; исходная регрессия выполнена на Chrome 155.

1. Убедись, что порты 8766 и 9233 не заняты другими приложениями. **Не закрывай чужие процессы для освобождения портов.**
2. В отдельном терминале из корня проекта запусти fixture-сервер:

   ```text
   python -m http.server 8766 --bind 127.0.0.1 --directory tests/fixtures
   ```

3. Во втором терминале запусти собственный Chrome стенда:

   ```text
   python tools/browser_lab.py chrome
   ```

4. Открой тестовую страницу в этом же, проверенном браузере:

   ```text
   python -c "import sys; sys.path.insert(0,'tools'); from browser_lab import ensure_owned,rpc; b=ensure_owned('chrome'); print(rpc(b['webSocketDebuggerUrl'],[{'method':'Target.createTarget','params':{'url':'http://127.0.0.1:8766/'}}]))"
   ```

5. Запусти `python tools/verify.py`. Полные отчёты и screenshots создаются в исключённой из Git папке `reports/`. Это не автоматическая публикация релиза.
6. Заверши только собственный браузер и останови fixture-сервер через Ctrl+C:

   ```text
   python -c "import sys; sys.path.insert(0,'tools'); from browser_lab import ensure_owned,rpc; b=ensure_owned('chrome'); print(rpc(b['webSocketDebuggerUrl'],[{'method':'Browser.close'}]))"
   ```

Стенд не подключается повторно к занятому порту через `start()`. Перед установкой/удалением тестового расширения проверяются сохранённый browser WebSocket endpoint и live аргументы managed profile/debugging. Устаревший файл состояния сам по себе не доказывает принадлежность браузера.

## Релизы

GitHub Actions проверяет синтаксис, manifest, тесты принадлежности браузера и соответствие runtime SHA-256 браузерной проверке. Это не повторный запуск browser integration suite. Перед изменением runtime нужно выполнить реальные проверки и обновить version-specific evidence/hash gate; не подменяй проверенные SHA-256 только ради зелёного CI.

Локальные рабочие материалы и raw-отчёты исключены из Git. Стабильный GitHub release не означает публикацию в Chrome Web Store.
