#!/usr/bin/env python3
"""REGULATECA - coletor diário.
Baixa para a pasta pdfs/ as pautas, atas e extratos novos da INAEP e da Anvisa (Dicol).
Se um portal não responder, registra a falha em coleta_status.json e segue (nunca derruba o robô)."""
import datetime, json, re, time
from pathlib import Path
from urllib.parse import urljoin, urlparse
import requests

ANO = datetime.date.today().year
ANVISA = "https://www.gov.br/anvisa/pt-br/composicao/diretoria-colegiada/reunioes-da-diretoria"
INAEP = "https://www.gov.br/saude/pt-br/composicao/orgaos-colegiados/inaep/reunioes"
# (nome, páginas de listagem, padrão que identifica os links dos documentos)
LISTAGENS = [
    ("anvisa_pauta", [f"{ANVISA}/pautas/{ANO}", f"{ANVISA}/pautas"], rf"/pautas/{ANO}/pauta-"),
    ("anvisa_ata", [f"{ANVISA}/atas/{ANO}", f"{ANVISA}/atas"], rf"/atas/{ANO}/ata-"),
    ("inaep", [INAEP, f"{INAEP}/pautas", f"{INAEP}/extratos"], r"/inaep/reunioes/.+\.pdf$"),
]
S = requests.Session()
S.headers["User-Agent"] = "Mozilla/5.0 (compatible; REGULATECA/1.0; monitoramento de pautas públicas)"

def get(url):
    for _ in range(2):
        try:
            time.sleep(0.7)  # educação com o servidor
            return S.get(url, timeout=30)
        except requests.RequestException:
            time.sleep(2)
    return None

def normaliza(u):
    u = u.split("#")[0].split("?")[0].rstrip("/")
    for fim in ("/view", "/@@download/file"):
        if u.endswith(fim): u = u[: -len(fim)]
    return u

def links(html, base, padrao):
    achados = {normaliza(urljoin(base, h)) for h in re.findall(r"href=[\"']([^\"']+)[\"']", html)}
    return sorted(u for u in achados if re.search(padrao, u) and "gov.br" in urlparse(u).netloc)

def baixar(url, destino):
    for tentativa in (url, url + "/@@download/file"):
        r = get(tentativa)
        if r is not None and r.ok and r.content[:4] == b"%PDF":
            destino.write_bytes(r.content)
            return True
    return False

def main():
    pdfs = Path("pdfs"); pdfs.mkdir(exist_ok=True)
    novos, falhas, alvos = [], [], {}
    for nome, paginas, padrao in LISTAGENS:
        for pg in paginas:
            r = get(pg)
            if r is None or not r.ok:
                falhas.append(f"{nome}: não abriu {pg} (HTTP {r.status_code if r is not None else 'sem resposta'})"); continue
            for u in links(r.text, pg, padrao):
                alvos[u] = nome
    # INAEP: os extratos seguem um padrão previsível de endereço, então também tentamos por número
    seguidas = 0
    for n in range(1, 41):
        u = f"{INAEP}/extratos/extrato-de-deliberacao-da-inaep-{n}a-reuniao-ordinaria-{ANO}.pdf"
        if (pdfs / f"inaep_extrato_{n}ro_{ANO}.pdf").exists() or u in alvos: seguidas = 0; continue
        r = get(u)
        if r is not None and r.ok and r.content[:4] == b"%PDF":
            (pdfs / f"inaep_extrato_{n}ro_{ANO}.pdf").write_bytes(r.content); novos.append(u); seguidas = 0
        else:
            seguidas += 1
            if seguidas >= 3: break
    for u, nome in alvos.items():
        arq = pdfs / f"{nome}_{Path(urlparse(u).path).stem}.pdf"
        if arq.exists(): continue
        if baixar(u, arq): novos.append(u)
        else: falhas.append(f"{nome}: não consegui baixar {u}")
    resumo = f"{len(novos)} documentos novos, {len(falhas)} falhas"
    Path("coleta_status.json").write_text(json.dumps({"data": datetime.datetime.now().isoformat(timespec="minutes"),
        "resumo": resumo, "novos": novos, "falhas": falhas}, ensure_ascii=False, indent=1), encoding="utf-8")
    print(resumo)
    for f in falhas[:15]: print(" -", f)

if __name__ == "__main__":
    main()
