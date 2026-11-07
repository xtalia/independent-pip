# Архитектура Independent PiP

## Решение
Лёгкий модульный монолит по функциям с явными зависимостями и контрактами. DDD не применяется: пока нет сложных доменных правил, агрегатов или независимых bounded contexts. PDD не вводится как фреймворк; evidence-first цикл и критерии готовности описаны в [AGENTS.md](../AGENTS.md).

Никакой сборки, контейнера DI и внешних runtime-зависимостей. Worker загружает обычные локальные скрипты через `importScripts`; внедряемые в страницу скрипты работают в ISOLATED world. Каждый модуль изолирует внутреннее состояние в IIFE и отдаёт замороженный namespace/factory.

## Модули и направление зависимостей
- `protocol.js` — контракт сообщений, UUID-валидация, порядок инъекции. Не вызывает Chrome API.
- `background.js` — composition root: создаёт зависимости, регистрирует listeners, не содержит логику поиска/drag/UI.
- `background/windows.js` — владение PiP-окном, session bindings, последовательность жестов; не ищет видео.
- `background/discovery.js` — доступные вкладки, ограниченный по времени поиск, сортировка результатов; не запускает видео.
- `background/playback.js` — запуск PiP и явное открытие picker; зависит от window ownership и контракта инъекции.
- `background/messages.js` — единственный runtime router; зависит от discovery/playback/windows.
- `background/menus.js` — native action menu, зависит только от playback и Chrome API настроек.
- `media.js` — обход DOM/open shadow/same-origin iframe, допустимость видео, WeakMap UUID.
- `pip-view.js` — DOM/стили; `pip-drag.js` — жесты/очередь; `pip.js` — захват, source controls, обновления, cleanup.
- `picker-client.js` — транспорт сообщений; `picker.js` — DOM, статусы, выбор пользователя.
- `settings.js` — нормализация/валидация настроек; `options.*` — форма редактирования.

Циклические зависимости запрещены. Chrome API передаётся worker-модулям явно. Единственный worker namespace для собранных возможностей — `IndependentPiPWorker`; внутренние Map и локальные handlers не становятся ambient globals.

## Потоки
1. Toolbar / Alt+Shift+P → playback → синхронно начатый executeScript → media → pip → view/drag. Старт API нельзя откладывать за await или Promise.then: нужна transient user activation.
2. Нет подходящего играющего видео → переиспользуемый picker. ПКМ на значке → «Выбор видео» открывает его явно, независимо от playback, не закрывая существующий PiP. «Настройки» вызывает openOptionsPage.
3. Picker list → client → messages → discovery → определения injected modules + список media. Поиск не включает play/PiP.
4. Picker select → немедленный sendMessage → messages → playback.openTab → конкретный UUID. Устаревший выбор не переключает на другое видео и не закрывает рабочее окно до валидации.
5. Pointer drag → PiP requestAnimationFrame → latest-position coalescing → сериализованный worker windows → проверенное chrome.windows.update. Start/end — барьеры, release отправляет конечную позицию. Playback rate не меняется.

## Lifecycle и ошибки picker
MV3 worker может остановиться в любой момент. Глобальные переменные не считаются durable storage. Binding своего PiP — в storage.session; настройки — в storage.local; нет искусственного keepalive.

Поиск ведётся максимум шестью concurrent workers, до двух секунд на вкладку и с общим бюджетом шесть секунд. Текущая вкладка и audible-вкладки идут первыми. Недоступная/замороженная/закрытая вкладка не блокирует здоровые; неполный результат помечается `incomplete`. Таймаут не отменяет Chrome executeScript: поздний результат игнорируется, инъекция только определяет функции и не начинает playback.

После закрытия message channel клиент один раз повторяет только list. После повторного сбоя показывает понятное восстановительное действие, а не сырой текст Chrome. Select/open/toggle не повторяются: ответ мог потеряться уже после выполнения команды. Каждый принятый router запрос завершается `{ok:true,...}` или `{ok:false,message}`; неизвестные и чужие сообщения возвращают false.

## Безопасность и неизменные ограничения
- Исходный video не отсоединяется, src не загружается во второй декодер, аудио остаётся у сайта. Mirror muted и содержит только video tracks. Cleanup закрывает только собственные ресурсы.
- Required: activeTab, scripting, storage, contextMenus. Меню добавляется только в контекст action, не на сайты. HTTP/HTTPS host access остаётся optional, с отдельным пользовательским согласием.
- Проверяются sender.id/URL, nonce/gesture/sequence, child-tab opener и принадлежность нового window. Нельзя двигать исходные/посторонние окна.
- Нет DRM/policy/opt-out bypass. Cross-origin iframe и closed shadow исключены. Document PiP требует secure context и поддержку API; native fallback не обещает custom controls/captions.
- Заголовки/стандартные VTT cues вставляются как текст. DOM-субтитры сайтов и VOT — отдельные будущие задачи.

## Доказательства
Node unit tests проверяют модульные контракты и ограничение повторов. Реальные Chrome integration tests проверяют video/PiP, жесты, lifecycle и остановку worker во время list; frozen renderer воспроизводится через CDP Page.setWebLifecycleState. Native menu registration и реальные эффекты callbacks проверяются отдельно от физического клика по меню Windows.

Точные версии, результаты и SHA-256 — в version-specific verification JSON. Headless не доказывает физическую плавность, меню Windows или global hotkey. Изолированный тестовый профиль не заменяет Reload установленного расширения в пользовательском Chrome.

Справка: [Document PiP](https://developer.chrome.com/docs/web-platform/document-picture-in-picture), [MV3 lifecycle](https://developer.chrome.com/docs/extensions/develop/concepts/service-workers/lifecycle), [contextMenus](https://developer.chrome.com/docs/extensions/reference/api/contextMenus).