"""HR-помощник: вакансии, французский для HR, трудовое право, личный ассистент."""
import asyncio
import html
import logging
import os
from datetime import datetime
from zoneinfo import ZoneInfo

from aiogram import Bot, Dispatcher, F, Router
from aiogram.client.default import DefaultBotProperties
from aiogram.filters import Command, CommandStart
from aiogram.types import (CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, KeyboardButton, Message,
                           ReplyKeyboardMarkup)

import ai
import db
from ft_api import FranceTravail

TZ = ZoneInfo("Europe/Paris")
log = logging.getLogger("hr-bot")
router = Router()

B_JOBS, B_FR, B_LAW, B_ASSIST = "💼 Вакансии", "🇫🇷 Французский HR", "⚖️ Трудовое право", "🤖 Ассистент"
MENU = ReplyKeyboardMarkup(keyboard=[[KeyboardButton(text=B_JOBS), KeyboardButton(text=B_FR)],
                                     [KeyboardButton(text=B_LAW), KeyboardButton(text=B_ASSIST)]],
                           resize_keyboard=True)


def ikb(rows):
    return InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text=t, callback_data=d) for t, d in r] for r in rows])


def now():
    return datetime.now(TZ)


def esc(s):
    return html.escape(s or "")


def chunks(text, n=3900):
    while text:
        yield text[:n]
        text = text[n:]


async def send_long(msg_or_bot, chat_id, text, **kw):
    for part in chunks(text or "—"):
        if isinstance(msg_or_bot, Bot):
            await msg_or_bot.send_message(chat_id, part, parse_mode=None, disable_web_page_preview=True, **kw)
        else:
            await msg_or_bot.answer(part, parse_mode=None, disable_web_page_preview=True, **kw)


async def thinking(m: Message):
    await m.bot.send_chat_action(m.chat.id, "typing")


# ---------- доступ ----------
@router.message(~F.from_user.id.func(lambda i: db.is_allowed(i)))
async def deny(m: Message):
    await m.answer(f"Бот личный. Ваш Telegram ID: <code>{m.from_user.id}</code>")


@router.callback_query(~F.from_user.id.func(lambda i: db.is_allowed(i)))
async def deny_cb(c: CallbackQuery):
    await c.answer("Нет доступа", show_alert=True)


# ---------- меню ----------
@router.message(CommandStart())
@router.message(Command("menu"))
async def start(m: Message):
    db.set_user(m.from_user.id, mode="menu")
    u = db.user(m.from_user.id)
    await m.answer(
        "Привет! Я твой HR-помощник.\n\n"
        f"{B_JOBS} — новые вакансии каждое утро в {u['digest_time']} (Лазурный Берег и удалёнка)\n"
        f"{B_FR} — задания и тренировка собеседований\n"
        f"{B_LAW} — вопросы о Code du travail со ссылками на источники\n"
        f"{B_ASSIST} — напоминания, заметки и любые вопросы",
        reply_markup=MENU)


# ---------- вакансии ----------
JOBS_KB = ikb([[("🔄 Показать новые сейчас", "jobs:now")],
               [("⭐ Сохранённые", "jobs:saved"), ("🌐 Другие сайты", "jobs:web")],
               [("⏰ Время рассылки", "jobs:time")]])


@router.message(F.text == B_JOBS)
async def jobs_menu(m: Message):
    db.set_user(m.from_user.id, mode="jobs")
    u = db.user(m.from_user.id)
    await m.answer(f"💼 <b>Вакансии</b>\nКаждое утро в {u['digest_time']} присылаю новые HR-вакансии с France Travail: "
                   "Alpes-Maritimes, Var и полностью удалённые по Франции. По понедельникам — подборка с APEC, "
                   "LinkedIn, Welcome to the Jungle и других сайтов.", reply_markup=JOBS_KB)


def offer_card(o):
    stars = "★" * o.get("score", 0) + "☆" * (5 - o.get("score", 0))
    lines = [f"{stars} <b>{esc(o['title'])}</b>", f"🏢 {esc(o['company'])} · 📍 {esc(o['place'])}"]
    extra = " · ".join(x for x in (o.get("contract"), o.get("salary")) if x)
    if extra:
        lines.append(f"📄 {esc(extra)}")
    if o.get("summary"):
        lines.append(f"💬 {esc(o['summary'])}")
    lines.append(f'<a href="{esc(o["url"])}">Открыть вакансию</a>')
    return "\n".join(lines)


def offer_kb(oid):
    return ikb([[("⭐ Сохранить", f"of:save:{oid}"), ("🙈 Скрыть", f"of:hide:{oid}")]])


async def run_digest(bot: Bot, uid, ft: FranceTravail, days=1, manual=False):
    if not ft:
        await bot.send_message(uid, "Поиск вакансий ещё не подключён: нет ключей France Travail в настройках.")
        return
    try:
        offers = await ft.fresh_offers(days=days)
    except Exception as e:  # noqa: BLE001
        log.exception("France Travail")
        await bot.send_message(uid, f"Не удалось получить вакансии с France Travail: {esc(str(e))[:200]}")
        return
    new = [o for o in offers if not db.offer_known(uid, o["id"])]
    if not new:
        if manual:
            await bot.send_message(uid, "Новых вакансий пока нет.")
        else:
            await bot.send_message(uid, "☀️ Доброе утро! За сутки новых HR-вакансий не появилось.")
        return
    new = new[:25]
    try:
        new = await ai.score_offers(new)
    except Exception:  # noqa: BLE001
        log.exception("score")
    new.sort(key=lambda o: o.get("score", 0), reverse=True)
    for o in new:
        db.add_offer(uid, o)
    head = "☀️ Доброе утро! " if not manual else ""
    await bot.send_message(uid, f"{head}Новых HR-вакансий: <b>{len(new)}</b>. Сначала самые подходящие.")
    for o in new[:10]:
        await bot.send_message(uid, offer_card(o), reply_markup=offer_kb(o["id"]), disable_web_page_preview=True)
    if len(new) > 10:
        await bot.send_message(uid, f"Ещё {len(new) - 10} менее подходящих — их не показываю, чтобы не засорять чат.")


@router.callback_query(F.data == "jobs:now")
async def jobs_now(c: CallbackQuery, ft: FranceTravail):
    await c.answer("Ищу…")
    await run_digest(c.bot, c.from_user.id, ft, days=3, manual=True)


@router.callback_query(F.data == "jobs:saved")
async def jobs_saved(c: CallbackQuery):
    await c.answer()
    items = db.saved_offers(c.from_user.id)
    if not items:
        await c.message.answer("Сохранённых вакансий пока нет. Нажимай ⭐ под интересными.")
        return
    text = "⭐ <b>Сохранённые</b>\n\n" + "\n\n".join(
        f"• <b>{esc(o['title'])}</b> — {esc(o['company'])}, {esc(o['place'])}\n<a href=\"{esc(o['url'])}\">ссылка</a>"
        for o in items)
    for part in chunks(text):
        await c.message.answer(part, disable_web_page_preview=True)


@router.callback_query(F.data == "jobs:web")
async def jobs_web(c: CallbackQuery):
    await c.answer("Ищу на других сайтах, это займёт до минуты…")
    await c.bot.send_chat_action(c.message.chat.id, "typing")
    try:
        await send_long(c.message, None, await ai.other_sites_digest())
    except Exception as e:  # noqa: BLE001
        log.exception("web jobs")
        await c.message.answer(f"Ошибка поиска: {esc(str(e))[:200]}")


@router.callback_query(F.data == "jobs:time")
async def jobs_time(c: CallbackQuery):
    await c.answer()
    db.set_user(c.from_user.id, mode="jobs_time")
    await c.message.answer("Во сколько присылать вакансии? Напиши время, например <code>8:00</code>.")


@router.callback_query(F.data.startswith("of:"))
async def offer_action(c: CallbackQuery):
    _, act, oid = c.data.split(":", 2)
    db.set_offer_status(c.from_user.id, oid, "saved" if act == "save" else "hidden")
    if act == "save":
        await c.answer("Сохранено ⭐")
        await c.message.edit_reply_markup(reply_markup=ikb([[("✅ Сохранено", "noop")]]))
    else:
        await c.answer("Скрыто")
        await c.message.delete()


@router.callback_query(F.data == "noop")
async def noop(c: CallbackQuery):
    await c.answer()


# ---------- французский ----------
FR_KB = ikb([[("📝 Задание", "fr:task"), ("🎤 Собеседование", "fr:iv")]])


@router.message(F.text == B_FR)
async def fr_menu(m: Message):
    db.set_user(m.from_user.id, mode="fr")
    await m.answer("🇫🇷 <b>Французский для HR</b>\n📝 Задание — лексика и ситуации из HR, я проверю ответ.\n"
                   "🎤 Собеседование — я рекрутер, говорим по-французски, в конце разбор по-русски.", reply_markup=FR_KB)


@router.callback_query(F.data == "fr:task")
async def fr_task(c: CallbackQuery):
    await c.answer()
    await c.bot.send_chat_action(c.message.chat.id, "typing")
    task = await ai.french_task()
    db.kv_set(f"task:{c.from_user.id}", task)
    db.set_user(c.from_user.id, mode="fr_answer")
    await send_long(c.message, None, task + "\n\n✍️ Напиши ответ одним сообщением.")


@router.callback_query(F.data == "fr:iv")
async def fr_interview(c: CallbackQuery):
    await c.answer()
    uid = c.from_user.id
    db.clear_msgs(uid, "iv")
    db.set_user(uid, mode="iv")
    db.add_msg(uid, "iv", "user", "Bonjour, je suis prête pour l'entretien.")
    await c.bot.send_chat_action(c.message.chat.id, "typing")
    reply = await ai.interview_reply(db.get_msgs(uid, "iv"))
    db.add_msg(uid, "iv", "assistant", reply)
    await send_long(c.message, None, reply, reply_markup=ikb([[("🏁 Завершить и получить разбор", "fr:ivend")]]))


@router.callback_query(F.data == "fr:ivend")
async def fr_interview_end(c: CallbackQuery):
    await c.answer("Готовлю разбор…")
    uid = c.from_user.id
    hist = db.get_msgs(uid, "iv", limit=60)
    db.set_user(uid, mode="fr")
    if len(hist) < 3:
        await c.message.answer("Интервью было слишком коротким для разбора.", reply_markup=FR_KB)
        return
    await c.bot.send_chat_action(c.message.chat.id, "typing")
    await send_long(c.message, None, "📋 Разбор собеседования\n\n" + await ai.interview_feedback(hist))
    db.clear_msgs(uid, "iv")
    await c.message.answer("Что дальше?", reply_markup=FR_KB)


# ---------- право ----------
@router.message(F.text == B_LAW)
async def law_menu(m: Message):
    db.set_user(m.from_user.id, mode="law")
    db.clear_msgs(m.from_user.id, "law")
    await m.answer("⚖️ <b>Трудовое право Франции</b>\nЗадай вопрос по-русски — отвечу по Code du travail со ссылками на "
                   "Légifrance, code.travail.gouv.fr и service-public.fr. Например: «Какой испытательный срок у cadre в CDI?»",
                   reply_markup=ikb([[("🧹 Новая тема", "law:new")]]))


@router.callback_query(F.data == "law:new")
async def law_new(c: CallbackQuery):
    db.clear_msgs(c.from_user.id, "law")
    await c.answer("Начинаем заново")


# ---------- ассистент ----------
AS_KB = ikb([[("⏰ Напоминания", "as:rem"), ("🗒 Заметки", "as:notes")], [("🧹 Новый разговор", "as:new")]])


@router.message(F.text == B_ASSIST)
async def as_menu(m: Message):
    db.set_user(m.from_user.id, mode="assist")
    await m.answer("🤖 <b>Ассистент</b>\nПиши что угодно — отвечу. Начни с «напомни…», чтобы поставить напоминание "
                   "(«напомни завтра в 10 позвонить в мэрию»), или с «заметка:», чтобы сохранить заметку.",
                   reply_markup=AS_KB)


@router.callback_query(F.data == "as:new")
async def as_new(c: CallbackQuery):
    db.clear_msgs(c.from_user.id, "as")
    await c.answer("Начинаем новый разговор")


@router.callback_query(F.data == "as:rem")
async def as_rem(c: CallbackQuery):
    await c.answer()
    items = db.pending_reminders(c.from_user.id)
    if not items:
        await c.message.answer("Активных напоминаний нет.")
        return
    for r in items:
        when = datetime.fromisoformat(r["at"]).strftime("%d.%m %H:%M")
        await c.message.answer(f"⏰ {when} — {esc(r['text'])}", reply_markup=ikb([[("Удалить", f"rem:del:{r['id']}")]]))


@router.callback_query(F.data.startswith("rem:del:"))
async def rem_del(c: CallbackQuery):
    db.del_reminder(c.from_user.id, int(c.data.split(":")[2]))
    await c.answer("Удалено")
    await c.message.delete()


@router.callback_query(F.data == "as:notes")
async def as_notes(c: CallbackQuery):
    await c.answer()
    items = db.notes(c.from_user.id)
    if not items:
        await c.message.answer("Заметок пока нет. Напиши «заметка: …».")
        return
    for n in items:
        await c.message.answer(f"🗒 {esc(n['text'])}", reply_markup=ikb([[("Удалить", f"note:del:{n['id']}")]]))


@router.callback_query(F.data.startswith("note:del:"))
async def note_del(c: CallbackQuery):
    db.del_note(c.from_user.id, int(c.data.split(":")[2]))
    await c.answer("Удалено")
    await c.message.delete()


# ---------- свободный текст по режимам ----------
@router.message(F.text)
async def text_router(m: Message):
    uid, text = m.from_user.id, m.text.strip()
    mode = db.user(uid)["mode"]
    try:
        if mode == "jobs_time":
            t = text.replace(".", ":").replace("h", ":")
            try:
                hh, mm = (t.split(":") + ["0"])[:2]
                val = f"{int(hh):02d}:{int(mm or 0):02d}"
                datetime.strptime(val, "%H:%M")
            except ValueError:
                await m.answer("Не поняла время. Напиши, например, 8:00.")
                return
            db.set_user(uid, digest_time=val, mode="jobs")
            await m.answer(f"Готово: вакансии будут приходить каждый день в {val}.")
        elif mode == "fr_answer":
            await thinking(m)
            task = db.kv_get(f"task:{uid}", "")
            db.set_user(uid, mode="fr")
            await send_long(m, None, await ai.french_check(task, text))
            await m.answer("Ещё?", reply_markup=FR_KB)
        elif mode == "iv":
            db.add_msg(uid, "iv", "user", text)
            await thinking(m)
            reply = await ai.interview_reply(db.get_msgs(uid, "iv", limit=40))
            db.add_msg(uid, "iv", "assistant", reply)
            await send_long(m, None, reply, reply_markup=ikb([[("🏁 Завершить и получить разбор", "fr:ivend")]]))
        elif mode == "law":
            db.add_msg(uid, "law", "user", text)
            await thinking(m)
            reply = await ai.law_answer(db.get_msgs(uid, "law", limit=10))
            db.add_msg(uid, "law", "assistant", reply)
            await send_long(m, None, reply)
        elif mode == "assist" or mode in ("menu", "jobs", "fr"):
            await assistant_text(m, uid, text)
    except Exception as e:  # noqa: BLE001
        log.exception("text")
        await m.answer(f"Что-то пошло не так: {esc(str(e))[:200]}. Попробуй ещё раз.")


async def assistant_text(m, uid, text):
    low = text.lower()
    if low.startswith("заметка"):
        note = text.split(":", 1)[1].strip() if ":" in text else text[7:].strip()
        if note:
            db.add_note(uid, note)
            await m.answer("🗒 Заметка сохранена.")
        return
    if low.startswith("напомни"):
        await thinking(m)
        r = await ai.parse_reminder(text, now().strftime("%Y-%m-%d %H:%M, %A"))
        if r.get("at"):
            at = datetime.fromisoformat(r["at"]).replace(tzinfo=None)
            db.add_reminder(uid, at.strftime("%Y-%m-%dT%H:%M"), r.get("text") or text)
            await m.answer(f"⏰ Напомню {at.strftime('%d.%m в %H:%M')}: {esc(r.get('text') or text)}")
            return
    db.add_msg(uid, "as", "user", text)
    await thinking(m)
    reply = await ai.assistant_reply(db.get_msgs(uid, "as", limit=12), now().strftime("%Y-%m-%d %H:%M, %A"))
    db.add_msg(uid, "as", "assistant", reply)
    await send_long(m, None, reply)


# ---------- планировщик ----------
async def scheduler(bot: Bot, ft):
    while True:
        try:
            t = now()
            hm, today = t.strftime("%H:%M"), t.strftime("%Y-%m-%d")
            for uid in db.allowed_ids():
                u = db.user(uid)
                if u["digest_time"] <= hm and u["last_digest"] != today:
                    db.set_user(uid, last_digest=today)
                    await run_digest(bot, uid, ft, days=1)
                    if t.weekday() == 0:
                        try:
                            await bot.send_message(uid, "🌐 Недельная подборка с других сайтов:")
                            await send_long(bot, uid, await ai.other_sites_digest())
                        except Exception:  # noqa: BLE001
                            log.exception("weekly web")
            for r in db.due_reminders(t.strftime("%Y-%m-%dT%H:%M")):
                db.mark_sent(r["id"])
                await bot.send_message(r["user_id"], f"⏰ Напоминание: {esc(r['text'])}")
        except Exception:  # noqa: BLE001
            log.exception("scheduler")
        await asyncio.sleep(30)


async def main():
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    db.set_path(os.getenv("DB_PATH", "hr-bot.db"))
    db.init()
    cid, sec = os.getenv("FT_CLIENT_ID"), os.getenv("FT_CLIENT_SECRET")
    ft = FranceTravail(cid, sec) if cid and sec else None
    bot = Bot(os.environ["BOT_TOKEN"], default=DefaultBotProperties(parse_mode="HTML"))
    dp = Dispatcher()
    dp["ft"] = ft
    dp.include_router(router)
    asyncio.create_task(scheduler(bot, ft))
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
