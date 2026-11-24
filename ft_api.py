"""Клиент API France Travail «Offres d'emploi v2»."""
import re
import time

import httpx

TOKEN_URL = "https://entreprise.francetravail.fr/connexion/oauth2/access_token?realm=%2Fpartenaire"
SEARCH_URL = "https://api.francetravail.io/partenaire/offresdemploi/v2/offres/search"

# Коды ROME для HR: M1502 — développement des RH, M1503 — management des RH (вкл. C&B, HRBP, рекрутинг, формация)
ROME_HR = "M1502,M1503"
DEPARTMENTS = "06,83"  # Alpes-Maritimes, Var
REMOTE_RE = re.compile(
    r"(100\s?%\s*(en\s+)?t[ée]l[ée]travail|t[ée]l[ée]travail\s+(complet|total|int[ée]gral)|full[\s-]?remote|enti[èe]rement\s+[àa]\s+distance)",
    re.I,
)


class FranceTravail:
    def __init__(self, client_id, client_secret):
        self.cid, self.secret = client_id, client_secret
        self._token, self._exp = None, 0

    async def token(self, client):
        if self._token and time.time() < self._exp - 60:
            return self._token
        r = await client.post(
            TOKEN_URL,
            data={
                "grant_type": "client_credentials",
                "client_id": self.cid,
                "client_secret": self.secret,
                "scope": "api_offresdemploiv2 o2dsoffre",
            },
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
        r.raise_for_status()
        j = r.json()
        self._token, self._exp = j["access_token"], time.time() + int(j.get("expires_in", 1400))
        return self._token

    async def search(self, client, **params):
        tok = await self.token(client)
        r = await client.get(SEARCH_URL, params=params, headers={"Authorization": f"Bearer {tok}", "range": "0-149"})
        if r.status_code == 204:
            return []
        r.raise_for_status()
        return r.json().get("resultats", [])

    async def fresh_offers(self, days=1):
        """Новые HR-вакансии: Лазурный Берег (06, 83) + полностью удалённые по всей Франции."""
        async with httpx.AsyncClient(timeout=30) as client:
            local = await self.search(client, codeROME=ROME_HR, departement=DEPARTMENTS, publieeDepuis=days)
            national = await self.search(client, codeROME=ROME_HR, motsCles="télétravail", publieeDepuis=days)
        out, seen = [], set()
        for o in local:
            out.append(normalize(o, remote=False))
            seen.add(o["id"])
        for o in national:
            if o["id"] in seen:
                continue
            text = (o.get("intitule", "") + " " + o.get("description", ""))
            if REMOTE_RE.search(text):
                out.append(normalize(o, remote=True))
        return out


def normalize(o, remote=False):
    url = (o.get("origineOffre") or {}).get("urlOrigine") or f"https://candidat.francetravail.fr/offres/recherche/detail/{o['id']}"
    place = (o.get("lieuTravail") or {}).get("libelle", "")
    return {
        "id": "ft-" + str(o["id"]),
        "title": o.get("intitule", "").strip(),
        "company": (o.get("entreprise") or {}).get("nom", "") or "—",
        "place": ("Удалёнка · " if remote else "") + place,
        "contract": o.get("typeContratLibelle") or o.get("typeContrat", ""),
        "salary": (o.get("salaire") or {}).get("libelle", ""),
        "description": (o.get("description") or "")[:1500],
        "url": url,
    }
