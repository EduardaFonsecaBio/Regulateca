#!/usr/bin/env python3
"""REGULATECA - leitor de pautas, atas e extratos (INAEP e Anvisa/Dicol).

Uso: python3 regulateca_leitor.py PASTA_COM_PDFS [PASTA_SAIDA]
Gera: regulateca_itens.csv (cada item sinalizado) e regulateca_relogio.csv
(itens consolidados entre pauta e ata/extrato, prontos para o Relógio Regulatório).
"""
import csv, re, subprocess, sys, unicodedata
from pathlib import Path

# ---- Configuração: edite aqui as palavras e áreas de interesse ----
KEYWORDS = ["pesquisa clinica", "pesquisas clinicas", "pesquisa com seres humanos",
            "pesquisas com seres humanos", "seres humanos", "ensaio clinico", "ensaios clinicos",
            "estudo clinico", "estudos clinicos", "ddcm", "etica em pesquisa", "analise etica",
            "comite de etica", "protocolo de pesquisa", "bioequivalencia", "biodisponibilidade",
            "boas praticas clinicas", "biobanco", "caae"]
AREAS = ["GGMED", "GGBIO", "COPEC", "CATEPEC", "SCMED", "GGTES"]
# -------------------------------------------------------------------

PROC = re.compile(r"\d{5}\.\d{6}/\d{4}-\d{2}")
CAAE = re.compile(r"\d{8}\.\d\.\d{4}\.\d{3,4}")
ITEM = re.compile(r"^(\d{1,2}(?:\.\d{1,3}){1,4})\.?\s*(.*)$")
ROMAN = re.compile(r"^(I|II|III|IV|V|VI|VII|VIII)\.\s+(.+)$")
RUIDO = re.compile(r"(?:Pauta|Ata|Extrato)[^\n]{0,80}?SEI [\d.]+/\d{4}-\d{2} / pg\. \d+")  # rodapé de página
OK_REST = ("Retorno", "Assunto", "Diretor", "Recurso", "Membro", "Apresenta")
MESES = {m: i + 1 for i, m in enumerate("janeiro fevereiro março abril maio junho julho agosto setembro outubro novembro dezembro".split())}

def norm(s):
    return "".join(c for c in unicodedata.normalize("NFKD", s) if not unicodedata.combining(c)).lower()

def processo_reuniao(txt):
    """Processo SEI da reunião: o número que se repete nos rodapés de várias páginas."""
    from collections import Counter
    c = Counter(PROC.findall(txt)).most_common(1)
    return c[0][0] if c and c[0][1] >= 3 else ""

def texto_pdf(p):
    return subprocess.run(["pdftotext", "-enc", "UTF-8", str(p), "-"], capture_output=True, text=True).stdout

def cabecalho(txt, nome):
    t = txt[:3000]
    orgao = "INAEP" if "Instância Nacional de Ética" in t[:600] else "Anvisa (Dicol)"
    up = t[:700].upper()  # só o título: "data da reunião" no corpo não pode contar como ata
    tipo = "extrato" if "EXTRATO DE DELIBERA" in up else "pauta" if "PAUTA" in up else "ata" if "ATA DA REUNI" in up else "pauta"
    m = re.search(r"ROP\s*(\d+/\d{4})", t) or re.search(r"(\d+)ª\s*REUNIÃO ORDINÁRIA DA INAEP", t, re.I)
    reuniao = ("ROP " + m.group(1)) if orgao.startswith("Anvisa") and m else (f"{m.group(1)}ª RO INAEP" if m else nome)
    d = re.search(r"Data:\s*(\d{1,2}/\d{1,2}/\d{4})", t) or re.search(r"realizada nos? dias? ([\d e]+/\d{2}/\d{4})", t)
    if d: data = d.group(1)
    else:
        f = re.search(r"(\d{1,2})_de_(\w+)_de_(\d{4})", nome)
        data = f"{int(f.group(1)):02d}/{MESES.get(f.group(2),0):02d}/{f.group(3)}" if f else ""
    return orgao, tipo, reuniao, data

def dividir(txt):
    """Divide o texto em itens numerados, guardando seção e área de contexto."""
    txt = RUIDO.sub("", txt.split("Documento assinado eletronicamente")[0])
    itens, atual, secao, ctx = [], None, "", ""
    for ln in txt.splitlines():
        ln = ln.strip()
        if not ln: continue
        r = ROMAN.match(ln)
        if r:
            secao, ctx, atual = r.group(2).strip(": "), "", None
            continue
        m = ITEM.match(ln)
        if m and (not m.group(2) or m.group(2).startswith(OK_REST + ("Assuntos da", "DIRETOR"))):
            rest = m.group(2)
            a = re.match(r"Assuntos da (\w+)", rest)
            if a: ctx, atual = a.group(1), None; continue
            if rest.startswith("DIRETOR"): atual = None; continue
            atual = {"item": m.group(1), "secao": secao, "ctx": ctx, "linhas": [rest] if rest else []}
            itens.append(atual); continue
        if atual is not None: atual["linhas"].append(ln)
    return itens

def analisar(it, tipo, proc_reuniao=""):
    corpo = " ".join(it["linhas"])
    n = norm(corpo)
    kw = sorted({k for k in KEYWORDS if k in n})
    ar = re.search(r"Área:\s*(.+?)(?:\s+Agenda|\s+Excep|\s+Decis|$)", corpo)
    explicita = [a for a in AREAS if ar and re.search(rf"\b{a}\b", ar.group(1))]
    contexto = [it["ctx"]] if it["ctx"] in AREAS else []
    mencao = [a for a in AREAS if re.search(rf"\b{a}\b", corpo) and a not in explicita + contexto]
    gat = kw + [f"área {a}" for a in explicita] + [f"seção {a}" for a in contexto] + [f"menção {a}" for a in mencao]
    rel = "alta" if kw else "média" if explicita or contexto else "baixa" if mencao else ""
    a = re.search(r"Assuntos?:\s*(.+?)(?=\s(?:Área:|Agenda Regulatória|Excepcionalidade|Processos?:|Diretor|Diretora|Informe:|Deliberad|Recorrente|Área responsável)|$)", corpo)
    rec = re.search(r"Recorrente:\s*(.+?)\s+CNPJ", corpo)
    assunto = a.group(1) if a else ("Recurso de " + rec.group(1) if rec else corpo[:160])
    dec = ""
    if tipo != "pauta":
        d = re.search(r"((?:A Diretoria Colegiada|O Colegiado)[^.]{0,90}?\s(?:decidiu|deliberou|aprovou)|Deliberad[oa]:|Deliberação:)", corpo)
        if d: dec = corpo[d.start():d.start() + 320]
        elif "Item retirado de pauta" in corpo: dec = "Item retirado de pauta"
        elif it["secao"].startswith("ASSUNTOS PARA DISCUSS"): dec = "Informe (sem deliberação)"
    prazos = []
    for m in re.finditer(r"(\d+)\s*(?:\([a-zçã ]+\)\s*)?dias(?: úteis)?", corpo):
        ctxp = corpo[max(0, m.start() - 70):m.end() + 30]
        if re.search(r"consulta|prazo|em até|a contar", ctxp, re.I) and "antecedência" not in ctxp:
            prazos.append(f"{m.group(0)} ({ctxp.strip()[:100]})")
    if re.search(r"Dispensa[^.]{0,120}Consulta P[úu]blica|dispensa de Consulta", corpo, re.I): prazos.append("Dispensa de consulta pública")
    if re.search(r"Proposta de Consulta P[úu]blica", corpo): prazos.append("Proposta de abertura de consulta pública")
    return {"item": it["item"], "secao": it["secao"], "assunto": re.sub(r"\s+", " ", assunto)[:260],
            "processo": ([p for p in PROC.findall(corpo) if p != proc_reuniao] or [""])[0], "gatilhos": "; ".join(gat), "relevancia": rel,
            "decisao": re.sub(r"\s+", " ", dec), "prazos": " | ".join(prazos),
            "caaes": sorted(set(CAAE.findall(corpo)))}

def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    pasta = Path(args[0]); saida = Path(args[1] if len(args) > 1 else ".")
    linhas, caae_por, todas, pautas = [], {}, {}, {}
    for pdf in sorted(pasta.glob("*.pdf")):
        txt = texto_pdf(pdf)
        orgao, tipo, reuniao, data = cabecalho(txt, pdf.name)
        total = 0
        for it in dividir(txt):
            r = analisar(it, tipo, processo_reuniao(txt))
            r.update(orgao=orgao, tipo=tipo, reuniao=reuniao, data_reuniao=data, arquivo=pdf.name[:50])
            if tipo == "pauta": pautas[(reuniao, r["item"])] = f"{reuniao} item {r['item']} ({data})"
            if tipo != "pauta": todas[(reuniao, r["item"])] = r["decisao"]  # decisão de qualquer item, sinalizado ou não
            if not r["gatilhos"]: continue
            total += 1
            caae_por.setdefault((reuniao, tipo), set()).update(r["caaes"])
            linhas.append(r)
        print(f"{pdf.name[:55]:55} {orgao:15} {tipo:8} {reuniao:14} {data:10} sinalizados: {total}")
    campos = ["orgao", "reuniao", "data_reuniao", "tipo", "item", "secao", "assunto", "processo", "relevancia", "gatilhos", "decisao", "prazos", "arquivo"]
    with open(saida / "regulateca_itens.csv", "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, campos, extrasaction="ignore"); w.writeheader(); w.writerows(linhas)
    # consolidação pauta x ata/extrato: por processo SEI; sem processo, por reunião+item (INAEP)
    ordem = {"alta": 3, "média": 2, "baixa": 1, "": 0}
    grupos = {}
    for r in linhas:
        k = (r["orgao"], r["processo"]) if r["processo"] and r["orgao"] != "INAEP" else (r["orgao"], r["reuniao"], r["item"])
        g = grupos.setdefault(k, {"orgao": r["orgao"], "reuniao": r["reuniao"], "assunto": r["assunto"], "pauta": "", "decisao": "", "prazos": set(), "gatilhos": set(), "relevancia": "", "fontes": set()})
        if r["tipo"] == "pauta": g["pauta"] = f'{r["reuniao"]} item {r["item"]} ({r["data_reuniao"]})'
        else: g["decisao"] = g["decisao"] or r["decisao"]; g["reuniao"] = r["reuniao"]
        if r["orgao"] == "INAEP":
            g["decisao"] = g["decisao"] or todas.get((r["reuniao"], r["item"]), "")
            g["pauta"] = g["pauta"] or pautas.get((r["reuniao"], r["item"]), "")
        g["prazos"].update(filter(None, r["prazos"].split(" | "))); g["gatilhos"].update(r["gatilhos"].split("; "))
        g["fontes"].add(r["tipo"]); g["relevancia"] = max(g["relevancia"], r["relevancia"], key=lambda x: ordem[x])
    with open(saida / "regulateca_relogio.csv", "w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f); w.writerow(["órgão", "reunião", "assunto", "pauta", "ata/extrato: deliberação", "prazos detectados", "gatilhos", "relevância", "fontes", "validado"])
        for g in sorted(grupos.values(), key=lambda g: -ordem[g["relevancia"]]):
            w.writerow([g["orgao"], g["reuniao"], g["assunto"], g["pauta"], g["decisao"], " | ".join(sorted(g["prazos"])), "; ".join(sorted(g["gatilhos"])), g["relevancia"], ", ".join(sorted(g["fontes"])), ""])
    alertas = []
    for (reuniao, tipo), s in caae_por.items():  # alerta de divergência de CAAEs entre pauta e extrato
        o = caae_por.get((reuniao, "extrato" if tipo == "pauta" else None))
        if tipo == "pauta" and o is not None and s != o:
            msg = f"{reuniao}: CAAEs diferem entre pauta e extrato (só na pauta: {', '.join(sorted(s - o))}; só no extrato: {', '.join(sorted(o - s))})"
            alertas.append(msg); print("ALERTA", msg)
    if "--json" in sys.argv:
        import datetime, json
        st = Path("coleta_status.json")
        coleta = json.loads(st.read_text(encoding="utf-8")).get("resumo", "") if st.exists() else ""
        itens = [{"orgao": g["orgao"], "reuniao": g["reuniao"], "assunto": g["assunto"], "pauta": g["pauta"], "decisao": g["decisao"],
                  "prazos": " | ".join(sorted(g["prazos"])), "gatilhos": "; ".join(sorted(g["gatilhos"])),
                  "relevancia": g["relevancia"], "fontes": ", ".join(sorted(g["fontes"]))}
                 for g in sorted(grupos.values(), key=lambda g: -ordem[g["relevancia"]])]
        agora = datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=-3))).strftime("%d/%m/%Y %H:%M")
        (saida / "dados.json").write_text(json.dumps({"atualizado": agora, "coleta": coleta, "alertas": alertas, "itens": itens}, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"{len(linhas)} itens sinalizados, {len(grupos)} linhas no relógio")

if __name__ == "__main__":
    main()
