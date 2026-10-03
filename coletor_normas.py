#!/usr/bin/env python3
"""REGULATECA - coletor de normas do Diário Oficial da União, via INLABS (etapa 1: registrar as normas).

Baixa as edições da Seção 1 (e extras), seleciona os atos dos órgãos de interesse que tratam de pesquisa clínica
e grava docs/normas.json com tipo, número, data, órgão, ementa e link.
Precisa dos secrets INLABS_EMAIL e INLABS_SENHA (cadastro gratuito no INLABS). Sem eles, o script apenas avisa e sai."""
import datetime, html, io, json, os, re, sys, time, zipfile
import xml.etree.ElementTree as ET
from pathlib import Path
import requests
from regulateca_leitor import KEYWORDS, AREAS, norm

EXTRA = ["inaep", "conep", "instancia nacional de etica", "sistema cep/conep"]
ORGAOS = ["Agência Nacional de Vigilância Sanitária", "Ministério da Saúde", "Conselho Nacional de Saúde", "Presidência da República"]
SECOES = ["DO1", "DO1E"]
JANELA_INICIAL, JANELA_REVISAO = 90, 7   # dias: primeira carga e revisões diárias
URL_LOGIN, URL_DOWN = "https://inlabs.in.gov.br/logar.php", "https://inlabs.in.gov.br/index.php"
TIPOS = [("instrucao normativa", "IN"), ("portaria", "Portaria"), ("decreto", "Decreto"), ("lei", "Lei"), ("despacho", "Despacho"),
         ("medida provisoria", "Medida Provisória"), ("carta circular", "Carta Circular"), ("consulta publica", "Consulta Pública"),
         ("resolucao", "Resolução")]

def plano(h):
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", html.unescape(h or ""))).strip()

def tipo_de(ident):
    n = norm(ident)
    if re.match(r"resolucao.*\brdc\b", n): return "RDC"
    if re.match(r"resolucao[- ]re\b", n): return "Resolução-RE"
    for chave, nome in TIPOS:
        if n.startswith(chave): return nome
    return None  # extrato, edital, aviso etc. não são normas

def avalia(art):
    cat = art.get("artCategory", "")
    if not any(o in cat for o in ORGAOS): return None
    b = art.find("body")
    if b is None: return None
    ident = (b.findtext("Identifica") or "").strip()
    tipo = tipo_de(ident)
    if not tipo: return None
    ementa = plano(b.findtext("Ementa")); texto = plano(b.findtext("Texto"))
    n = norm(f"{ident} {ementa} {texto}")
    gat = sorted({k for k in KEYWORDS + EXTRA if k in n}) + [f"área {a}" for a in AREAS if re.search(rf"\b{a}\b", f"{ident} {texto}")]
    if not gat: return None
    num = re.search(r"N[º°o]\.?\s*([\d.]+(?:/\d+)?)", ident, re.I)
    corpo = texto[len(ident):].strip() if texto.startswith(ident) else texto
    partes = cat.split("/")
    return {"id": art.get("idMateria") or art.get("id"), "tipo": tipo, "numero": num.group(1) if num else "",
            "titulo": ident[:220], "orgao": partes[0] + (" / " + partes[-1] if len(partes) > 1 else ""),
            "data": art.get("pubDate", ""), "secao": art.get("pubName", ""), "edicao": art.get("editionNumber", ""),
            "pagina": art.get("numberPage", ""), "ementa": (ementa or corpo)[:400], "gatilhos": "; ".join(gat),
            "link": ("https://www.in.gov.br/web/dou/-/" + art.get("urlTitle")) if art.get("urlTitle") else art.get("pdfPage", "")}

def ler_zip(conteudo):
    achados = []
    with zipfile.ZipFile(io.BytesIO(conteudo)) as z:
        for nome in z.namelist():
            if not nome.lower().endswith(".xml"): continue
            try:
                raiz = ET.fromstring(z.read(nome))
            except ET.ParseError:
                continue
            for art in raiz.iter("article"):
                r = avalia(art)
                if r: achados.append(r)
    return achados

def sessao(email, senha):
    s = requests.Session()
    s.headers["User-Agent"] = "Mozilla/5.0 (compatible; REGULATECA/1.0)"
    s.post(URL_LOGIN, data={"email": email, "password": senha}, timeout=30)
    return s if s.cookies.get("inlabs_session_cookie") else None

def baixar(s, dia, secao):
    time.sleep(1)
    try:
        r = s.get(URL_DOWN, params={"p": dia, "dl": f"{dia}-{secao}.zip"}, timeout=120)
    except requests.RequestException:
        return None
    return r.content if r.ok and r.content[:2] == b"PK" else None

def iso(d):  # dd/mm/aaaa -> aaaa-mm-dd, para ordenar
    p = d.split("/"); return f"{p[2]}-{p[1]}-{p[0]}" if len(p) == 3 else d

def main():
    saida = Path(sys.argv[1] if len(sys.argv) > 1 else "docs"); saida.mkdir(exist_ok=True)
    arq = saida / "normas.json"
    base = json.loads(arq.read_text(encoding="utf-8")) if arq.exists() else {"normas": [], "datas": []}
    normas = {n["id"]: n for n in base["normas"]}; feitas = set(base["datas"])
    email, senha = os.environ.get("INLABS_EMAIL"), os.environ.get("INLABS_SENHA")
    if not (email and senha):
        print("Sem credenciais do INLABS (secrets INLABS_EMAIL e INLABS_SENHA). Normas não atualizadas."); return
    s = sessao(email, senha)
    if not s:
        print("Login no INLABS não funcionou (confira e-mail e senha nos secrets)."); return
    hoje = datetime.date.today(); novas, falhas = 0, []
    for i in range(JANELA_REVISAO if feitas else JANELA_INICIAL):
        d = hoje - datetime.timedelta(days=i); dia = d.isoformat()
        if dia in feitas and i >= JANELA_REVISAO: continue
        obteve = False
        for secao in SECOES:
            z = baixar(s, dia, secao)
            if not z: continue
            obteve = True
            for r in ler_zip(z):
                if r["id"] not in normas: novas += 1
                normas[r["id"]] = r
        if obteve or d.weekday() >= 5 or i >= JANELA_REVISAO: feitas.add(dia)
        else: falhas.append(dia)
    lista = sorted(normas.values(), key=lambda n: iso(n["data"]), reverse=True)
    resumo = f"{novas} normas novas, {len(falhas)} dias sem edição baixada"
    agora = datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=-3))).strftime("%d/%m/%Y %H:%M")
    arq.write_text(json.dumps({"atualizado": agora, "coleta": resumo, "datas": sorted(feitas), "normas": lista}, ensure_ascii=False, indent=1), encoding="utf-8")
    print(resumo, f"| total: {len(lista)}")
    if falhas: print("Dias sem edição:", ", ".join(falhas[:10]))

if __name__ == "__main__":
    main()
