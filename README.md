# HR-помощник (Telegram)

Личный бот для поиска работы в HR во Франции. Четыре раздела:

- 💼 **Вакансии** — каждое утро в 8:00 новые HR-вакансии France Travail (Alpes-Maritimes, Var, полная удалёнка), с оценкой ★1–5 от Claude; по понедельникам подборка с APEC, LinkedIn, WTTJ и др.
- 🇫🇷 **Французский HR** — задания с проверкой и тренировка собеседований с разбором.
- ⚖️ **Трудовое право** — ответы по Code du travail со ссылками на официальные сайты.
- 🤖 **Ассистент** — вопросы, напоминания («напомни…»), заметки («заметка: …»).

## Установка на сервере

```
git clone https://github.com/ivansereda91-dotcom/hr-bot /opt/hr-bot && bash /opt/hr-bot/setup.sh
bash /opt/hr-bot/allow.sh <Telegram ID>
```

Обновление: `cd /opt/hr-bot && git pull && systemctl restart hr-bot`. Журнал: `journalctl -u hr-bot -n 30`.
