import asyncio, json, os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
import pytest
import db, ai, ft_api, bot as B

@pytest.fixture(autouse=True)
def tmpdb(tmp_path):
    db.set_path(str(tmp_path/"t.db")); db.init(); db.allow([1]); yield

def test_db_basics():
    assert db.is_allowed(1) and not db.is_allowed(2)
    assert db.user(1)["digest_time"] == "08:00"
    db.add_msg(1,"as","assistant","x"); db.add_msg(1,"as","user","hi"); db.add_msg(1,"as","assistant","yo")
    assert db.get_msgs(1,"as")[0]["role"] == "user"
    db.add_reminder(1,"2026-01-01T09:00","t"); assert len(db.due_reminders("2026-01-01T09:00"))==1

def test_remote_filter_and_normalize():
    o={"id":"123A","intitule":"Responsable RH","description":"Poste en 100% télétravail","entreprise":{"nom":"ACME"},"lieuTravail":{"libelle":"75 - Paris"}}
    assert ft_api.REMOTE_RE.search(o["description"])
    assert not ft_api.REMOTE_RE.search("2 jours de télétravail par semaine")
    n=ft_api.normalize(o, remote=True); assert n["id"]=="ft-123A" and n["place"].startswith("Удалёнка") and "123A" in n["url"]

def test_fresh_offers(monkeypatch):
    f=ft_api.FranceTravail("a","b")
    async def tok(c): return "T"
    calls=[]
    async def search(c, **p):
        calls.append(p)
        if "departement" in p: return [{"id":"1","intitule":"Chargé RH Nice","description":"","lieuTravail":{"libelle":"06 - Nice"}}]
        return [{"id":"1","intitule":"dup","description":"100% télétravail"},{"id":"2","intitule":"HRBP","description":"full remote"},{"id":"3","intitule":"RH","description":"sur site"}]
    monkeypatch.setattr(f,"token",tok); monkeypatch.setattr(f,"search",search)
    out=asyncio.run(f.fresh_offers())
    assert [o["id"] for o in out]==["ft-1","ft-2"] and calls[0]["departement"]=="06,83"

def test_score_json(monkeypatch):
    async def fake(system, messages, **kw): return 'Вот: [{"i":0,"score":5,"summary":"OD роль"},{"i":1,"score":2,"summary":"ассистент"}]'
    monkeypatch.setattr(ai,"ask",fake)
    offers=[{"title":"a","company":"c","place":"p"},{"title":"b","company":"c","place":"p"}]
    r=asyncio.run(ai.score_offers(offers)); assert r[0]["score"]==5 and r[1]["summary"]=="ассистент"

class FakeBot:
    def __init__(s): s.sent=[]
    async def send_message(s, chat, text, **kw): s.sent.append(text)

def test_digest_dedup(monkeypatch):
    class FT:
        async def fresh_offers(self, days=1):
            return [{"id":"ft-1","title":"Chargée de développement RH","company":"X","place":"Nice","url":"http://u","contract":"CDI","salary":""}]
    async def score(o):
        for x in o: x["score"]=4; x["summary"]="ok"
        return o
    monkeypatch.setattr(ai,"score_offers",score)
    b=FakeBot(); asyncio.run(B.run_digest(b,1,FT()))
    assert "Новых HR-вакансий" in b.sent[0] and "★★★★☆" in b.sent[1]
    b2=FakeBot(); asyncio.run(B.run_digest(b2,1,FT()))
    assert "не появилось" in b2.sent[0]

def test_parse_reminder(monkeypatch):
    async def fake(system, messages, **kw): return '{"at":"2026-11-25T10:00","text":"позвонить"}'
    monkeypatch.setattr(ai,"ask",fake)
    assert asyncio.run(ai.parse_reminder("напомни завтра в 10 позвонить","x"))["at"]=="2026-11-25T10:00"

def test_router_builds():
    from aiogram import Dispatcher
    dp=Dispatcher(); dp.include_router(B.router)
