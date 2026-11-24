"""Вызовы Claude API."""
import json
import os
import re

from anthropic import AsyncAnthropic

MODEL_FAST = os.getenv("MODEL_FAST", "claude-haiku-5-5")
MODEL_SMART = os.getenv("MODEL_SMART", "claude-sonnet-5-5")
WEB_SEARCH = {"type": "web_search_20250305", "name": "web_search", "max_uses": 5}

PROFILE = (
    "Кандидат: HR-специалист из России, живёт в Ницце. 13 лет опыта в организационном развитии (OD) "
    "и C&B (компенсации и льготы), сертификат GRP, изучает французское трудовое право. "
    "Французский — уровень A2+, английский рабочий. Ищет работу на Лазурном Берегу или удалённо."
)
LAW_DOMAINS = ["legifrance.gouv.fr", "code.travail.gouv.fr", "service-public.fr",
               "travail-emploi.gouv.fr", "urssaf.fr", "entreprendre.service-public.fr"]

_client = None


def client():
    global _client
    if _client is None:
        _client = AsyncAnthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
    return _client


def _text(resp):
    return "".join(b.text for b in resp.content if getattr(b, "type", "") == "text").strip()


async def ask(system, messages, model=None, max_tokens=1200, tools=None):
    kw = dict(model=model or MODEL_FAST, max_tokens=max_tokens, system=system, messages=messages)
    if tools:
        kw["tools"] = tools
    resp = await client().messages.create(**kw)
    return _text(resp)


def _json(text, default):
    m = re.search(r"[\[{].*[\]}]", text, re.S)
    if not m:
        return default
    try:
        return json.loads(m.group(0))
    except json.JSONDecodeError:
        return default


# --- вакансии ---
async def score_offers(offers):
    """Оценка 1–5 и одна строка по-русски для каждой вакансии."""
    if not offers:
        return offers
    items = [{"i": i, "title": o["title"], "company": o["company"], "place": o["place"],
              "contract": o.get("contract", ""), "salary": o.get("salary", ""),
              "description": o.get("description", "")[:900]} for i, o in enumerate(offers)]
    system = (PROFILE + "\nОцени каждую вакансию по соответствию профилю от 1 (не подходит) до 5 (отлично). "
              "Для каждой дай одну короткую фразу по-русски: суть роли и важный нюанс (уровень французского, "
              "контракт, зарплата). Ответь только JSON-массивом [{\"i\":0,\"score\":4,\"summary\":\"...\"}].")
    out = await ask(system, [{"role": "user", "content": json.dumps(items, ensure_ascii=False)}], max_tokens=2500)
    data = {d.get("i"): d for d in _json(out, []) if isinstance(d, dict)}
    for i, o in enumerate(offers):
        d = data.get(i, {})
        o["score"] = int(d.get("score", 3) or 3)
        o["summary"] = d.get("summary", "")
    return offers


async def other_sites_digest():
    system = (PROFILE + "\nНайди в интернете свежие (за последние 7 дней) HR-вакансии уровня middle/senior "
              "(organisational development, rémunération / C&B, HRBP, talents, formation, responsable RH) "
              "в Ницце, Каннах, Антибе, Софии-Антиполис, Монако или полностью удалённые во Франции. "
              "Ищи на APEC, LinkedIn, Welcome to the Jungle, Indeed, HelloWork и сайтах работодателей. "
              "Выведи до 8 вакансий по-русски: название (как в оригинале), компания, город, одна фраза почему подходит, "
              "ссылка. Только реальные найденные ссылки, ничего не выдумывай. Без вступлений.")
    return await ask(system, [{"role": "user", "content": "Подбери вакансии за неделю."}],
                     model=MODEL_SMART, max_tokens=2500, tools=[WEB_SEARCH])


# --- французский для HR ---
async def french_task():
    system = ("Ты преподаватель делового французского для HR-специалиста уровня A2+/B1. "
              "Дай одно короткое задание по лексике или ситуации из HR (рекрутинг, contrat de travail, "
              "entretien annuel, rémunération, formation, onboarding, congés). Формат: заголовок, 3–5 слов с переводом, "
              "затем задание (перевести 2 фразы, вставить слово или написать 2–3 предложения). "
              "Объяснения по-русски, сами задания по-французски. Не давай ответов.")
    return await ask(system, [{"role": "user", "content": "Новое задание."}], max_tokens=700)


async def french_check(task, answer):
    system = ("Ты преподаватель французского. Проверь ответ ученицы (A2+/B1) на задание. По-русски: "
              "что верно, ошибки с исправлением и коротким объяснением, правильный вариант. Доброжелательно и кратко.")
    return await ask(system, [{"role": "user", "content": f"Задание:\n{task}\n\nОтвет:\n{answer}"}], max_tokens=900)


INTERVIEW_SYS = (PROFILE + "\nТы рекрутер французской компании и проводишь собеседование на позицию в HR "
                 "(chargée de développement RH / responsable C&B). Говори только по-французски, простыми фразами "
                 "(уровень A2+/B1), задавай по одному вопросу за раз и реагируй на ответы. Не исправляй ошибки во время интервью.")


async def interview_reply(history):
    return await ask(INTERVIEW_SYS, history, model=MODEL_SMART, max_tokens=500)


async def interview_feedback(history):
    transcript = "\n".join(f"{'Рекрутер' if m['role']=='assistant' else 'Кандидат'}: {m['content']}" for m in history)
    system = ("Ты коуч по собеседованиям и преподаватель французского. По-русски дай разбор интервью: "
              "сильные стороны ответов, что улучшить по содержанию, главные языковые ошибки с исправлениями, "
              "3 полезные фразы на будущее. Кратко и по делу.")
    return await ask(system, [{"role": "user", "content": transcript}], model=MODEL_SMART, max_tokens=1500)


# --- трудовое право ---
LAW_SYS = ("Ты консультант по французскому трудовому праву (Code du travail, conventions collectives, URSSAF). "
           "Отвечай по-русски, структурированно и кратко, французские термины давай в скобках. "
           "Опирайся только на официальные источники, найденные поиском, и в конце дай список ссылок. "
           "Если ответ зависит от конвенции или ситуации — скажи об этом. В конце одна строка: "
           "«Это справочная информация, не юридическая консультация».")


async def law_answer(history):
    tool = dict(WEB_SEARCH, allowed_domains=LAW_DOMAINS)
    return await ask(LAW_SYS, history, model=MODEL_SMART, max_tokens=2000, tools=[tool])


# --- ассистент ---
ASSIST_SYS = ("Ты личный помощник, отвечаешь по-русски, кратко и по делу. Можешь искать в интернете, "
              "если вопрос о текущих фактах. Сегодня {now} (Европа/Париж).")


async def assistant_reply(history, now):
    return await ask(ASSIST_SYS.format(now=now), history, model=MODEL_SMART, max_tokens=1500, tools=[WEB_SEARCH])


async def parse_reminder(text, now):
    system = (f"Сейчас {now} (Europe/Paris). Извлеки из сообщения напоминание. Ответь только JSON "
              "{\"at\":\"YYYY-MM-DDTHH:MM\",\"text\":\"что напомнить\"}. Если время не указано — 09:00 ближайшего подходящего дня. "
              "Если это не напоминание — {\"at\":null}.")
    out = await ask(system, [{"role": "user", "content": text}], max_tokens=200)
    return _json(out, {"at": None})
