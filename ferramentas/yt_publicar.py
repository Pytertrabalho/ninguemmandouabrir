#!/usr/bin/env python3
"""Publica/agenda um Short no YouTube pela API oficial (YouTube Data API v3).

Uso:
  python3 -I yt_publicar.py --cred youtube.json --video caso-013.mp4 \
      --legenda-arquivo legenda.txt --publicar-em 2026-11-07T09:00:00-03:00
  python3 -I yt_publicar.py --cred youtube.json --checar      (só testa a chave e o canal)

A 1ª linha da legenda vira o título (máx. 100 caracteres); o resto, a descrição.
Saída: uma linha JSON {"ok":..., "video_id":..., "url":..., "status":..., "publicar_em":...}.
Nunca imprime a chave.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

CANAL_ESPERADO = "UCM-pHWbBdIn_PupTOWdAX-Q"
TIMEOUT = 60


def _json(req: urllib.request.Request) -> dict:
    with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
        return json.load(r)


def token_de_acesso(cred: dict) -> str:
    body = urllib.parse.urlencode({
        "client_id": cred["client_id"],
        "client_secret": cred["client_secret"],
        "refresh_token": cred["refresh_token"],
        "grant_type": "refresh_token",
    }).encode()
    return _json(urllib.request.Request(cred["token_uri"], data=body))["access_token"]


def canal(tok: str) -> dict:
    req = urllib.request.Request(
        "https://www.googleapis.com/youtube/v3/channels?part=snippet,statistics&mine=true",
        headers={"Authorization": f"Bearer {tok}"})
    itens = _json(req).get("items", [])
    return itens[0] if itens else {}


def enviar(tok: str, video: str, titulo: str, descricao: str, publicar_em: str | None, tags: list[str]) -> str:
    status = {"privacyStatus": "public", "selfDeclaredMadeForKids": False, "containsSyntheticMedia": True}
    if publicar_em:
        quando = dt.datetime.fromisoformat(publicar_em)
        if quando > dt.datetime.now(dt.timezone.utc) + dt.timedelta(minutes=15):
            status = {**status, "privacyStatus": "private",
                      "publishAt": quando.astimezone(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000Z")}
    meta = {"snippet": {"title": titulo[:100], "description": descricao[:4900], "tags": tags,
                        "categoryId": "24", "defaultLanguage": "pt-BR", "defaultAudioLanguage": "pt-BR"},
            "status": status}
    tamanho = os.path.getsize(video)
    ini = urllib.request.Request(
        "https://www.googleapis.com/upload/youtube/v3/videos?uploadType=resumable&part=snippet,status",
        data=json.dumps(meta).encode(),
        headers={"Authorization": f"Bearer {tok}", "Content-Type": "application/json; charset=UTF-8",
                 "X-Upload-Content-Type": "video/mp4", "X-Upload-Content-Length": str(tamanho)})
    with urllib.request.urlopen(ini, timeout=TIMEOUT) as r:
        destino = r.headers["Location"]
    for tentativa in range(3):
        try:
            with open(video, "rb") as f:
                put = urllib.request.Request(destino, data=f.read(), method="PUT",
                                             headers={"Content-Type": "video/mp4", "Content-Length": str(tamanho)})
                with urllib.request.urlopen(put, timeout=600) as r:
                    return json.load(r)["id"]
        except urllib.error.HTTPError as e:
            if e.code in (500, 502, 503, 504) and tentativa < 2:
                time.sleep(5 * (tentativa + 1))
                continue
            raise
    raise RuntimeError("envio falhou")


def conferir(tok: str, vid: str) -> dict:
    req = urllib.request.Request(
        f"https://www.googleapis.com/youtube/v3/videos?part=snippet,status,processingDetails&id={vid}",
        headers={"Authorization": f"Bearer {tok}"})
    itens = _json(req).get("items", [])
    return itens[0] if itens else {}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--cred", required=True)
    ap.add_argument("--video")
    ap.add_argument("--legenda-arquivo")
    ap.add_argument("--publicar-em", help="ISO com fuso, ex. 2026-11-07T09:00:00-03:00; vazio = público agora")
    ap.add_argument("--tags", default="terror,suspense,historias de terror,shorts")
    ap.add_argument("--checar", action="store_true")
    a = ap.parse_args()
    cred = json.load(open(a.cred, encoding="utf-8"))
    try:
        tok = token_de_acesso(cred)
        c = canal(tok)
        if c.get("id") != CANAL_ESPERADO:
            print(json.dumps({"ok": False, "erro": "canal_errado", "canal": c.get("id")}))
            return 2
        if a.checar:
            print(json.dumps({"ok": True, "canal": c["snippet"]["title"], "videos": c["statistics"].get("videoCount")},
                             ensure_ascii=False))
            return 0
        linhas = open(a.legenda_arquivo, encoding="utf-8").read().strip().split("\n")
        titulo, descricao = linhas[0].strip(), "\n".join(linhas[1:]).strip()
        vid = enviar(tok, a.video, titulo, descricao, a.publicar_em, [t.strip() for t in a.tags.split(",") if t.strip()])
        info = conferir(tok, vid)
        st = info.get("status", {})
        print(json.dumps({"ok": bool(info), "video_id": vid, "url": f"https://youtube.com/shorts/{vid}",
                          "status": st.get("privacyStatus"), "publicar_em": st.get("publishAt"),
                          "titulo": info.get("snippet", {}).get("title")}, ensure_ascii=False))
        return 0 if info else 1
    except urllib.error.HTTPError as e:
        corpo = e.read().decode(errors="replace")[:500]
        motivo = "limite_diario" if "uploadLimitExceeded" in corpo or "quotaExceeded" in corpo else "http"
        print(json.dumps({"ok": False, "erro": motivo, "codigo": e.code, "detalhe": corpo}, ensure_ascii=False))
        return 1


if __name__ == "__main__":
    sys.exit(main())
