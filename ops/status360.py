#!/usr/bin/env python3
"""AOP Status 360 + ETA dashboard (semáforo, ETA/task, agente responsável).
Uso: python3 status360.py [--watch]   (--watch = refresh 60s)
Fonte: CHECKIN_OUT_GSD.md (ledger) + herdr pane list (estado vivo)."""
import re, sys, json, subprocess, time, os
from datetime import datetime, timezone

# Ledger canônico atual (override via env AOP_LEDGER). Default: CHECKIN_OUT.md na raiz do repo AOP.
LEDGER = os.environ.get(
    "AOP_LEDGER",
    os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "CHECKIN_OUT.md"),
)

# tag -> (descrição curta, agente responsável padrão)
SCOPE = {
 "P0":   ("Infra: HerdMaster FK/schema fix",        "CODEX_55#0"),
 "RECOV":("Infra: build/runtime recovery",          "CODEX"),
 "AG-1": ("Design System Indra HEX + Shell",        "CODEX_55#0"),
 "AG-2": ("Projects backend + UI",                  "CODEX"),
 "AG-3": ("Squad Builder + Agents",                 "AGY_OPUS46"),
 "AG-4": ("Seats + Sessions OAuth",                 "CODEX"),
 "AG-5": ("FinOps + Observability + Live",          "AGY_Gemini-PRO31"),
 "AG-6": ("Settings + Inbox + My-Issues + Search",  "AGY_Gemini-PRO31"),
 "F2":   ("Issues/Tasks tracker (/issues)",         "CODEX"),
 "QA":   ("QA E2E Contract Tests + UI Smoke",       "(a distribuir)"),
 "OTTL": ("Telemetry & Task Lifecycle (board)",     "(a distribuir)"),
 "F7":   ("E2E final + UI/Perf/A11y review",        "(a distribuir)"),
}
def tag_of(text):
    t=text.upper()
    if "HERDMASTER FK" in t or "FK FIX" in t: return "P0"
    if "RECOVERY" in t or "RUNTIME-RECOV" in t or "BUILD-RUNTIME" in t: return "RECOV"
    for k in ("AG-1","AG-2","AG-3","AG-4","AG-5","AG-6"):
        if k in t: return k
    if "PANE AG-6" in t: return "AG-6"
    if "ISSUE" in t: return "F2"
    if "E2E" in t and ("FINAL" in t or "F7" in t): return "F7"
    if "E2E" in t or "SMOKE" in t or " QA" in t: return "QA"
    if "TELEMETRY" in t or "OTTL" in t: return "OTTL"
    return None
def ts_parse(s):
    s=s.replace(" UTC","").strip()
    for f in ("%Y-%m-%dT%H:%M:%SZ","%Y-%m-%d %H:%M:%S","%Y-%m-%dT%H:%M:%S","%Y-%m-%d %H:%M"):
        try: return datetime.strptime(s,f).replace(tzinfo=timezone.utc)
        except: pass
    return None
def parse_ledger():
    rows=[]
    for ln in open(LEDGER,encoding="utf-8",errors="ignore"):
        if not ln.lstrip().startswith("|"): continue
        c=[x.strip() for x in ln.strip().strip("|").split("|")]
        if len(c)<6 or not re.match(r"^\d{4}-\d{2}-\d{2}",c[0]): continue
        rows.append(c)
    return rows
def build():
    rows=parse_ledger()
    st={k:"PENDENTE" for k in SCOPE}
    agent={k:SCOPE[k][1] for k in SCOPE}
    cin={}; elapsed={}; actual={}; durs=[]
    now=datetime.now(timezone.utc)
    for c in rows:
        ts,ag,typ,act,_,status=c[0],c[1],c[2],c[3],c[4],c[5]
        tag=tag_of(ag+" "+act)
        if not tag: continue
        if "CHECK-IN" in typ:
            cin[tag]=ts_parse(ts)
            if ag and ag.upper() not in ("KIRO","KIRO (PLANNER/ORQUESTRAÇÃO)"): agent[tag]=ag
            if st[tag]=="PENDENTE": st[tag]="RODANDO"
        elif "CHECK-OUT" in typ:
            su=status.upper()
            if "COMPLET" in su:
                st[tag]="COMPLETA"; t0=cin.get(tag); t1=ts_parse(ts)
                if t0 and t1 and t1>t0:
                    d=(t1-t0).total_seconds()/60; durs.append(d); actual[tag]=d
            elif "FAIL" in su: st[tag]="FALHA"
            elif "CANCEL" in su: st[tag]="CANCELADA"
    for tag,t0 in cin.items():
        if st[tag]=="RODANDO" and t0: elapsed[tag]=(now-t0).total_seconds()/60
    return st,agent,elapsed,actual,durs
def live():
    try:
        d=json.loads(subprocess.check_output(["herdr","pane","list"],text=True,stderr=subprocess.DEVNULL))
        return d["result"]["panes"]
    except Exception: return []
def render():
    st,agent,elapsed,actual,durs=build()
    panes=live()
    avg=sum(durs)/len(durs) if durs else 12.0
    workers=sum(1 for p in panes if p.get("agent") not in ("kiro","system",None)) or 1
    cnt={s:0 for s in ("RODANDO","COMPLETA","PENDENTE","FALHA","CANCELADA")}
    for v in st.values(): cnt[v]+=1
    total=len(st)
    remaining=cnt["PENDENTE"]*1.0+cnt["RODANDO"]*0.5+cnt["FALHA"]*0.7
    eta_all=(remaining*avg)/max(1,workers)
    now=datetime.now(timezone.utc).strftime("%H:%M:%S UTC")
    def light(tag):
        s=st[tag]
        if s=="COMPLETA": return "🟢"
        if s=="FALHA": return "🔴"
        if s=="RODANDO": return "🔴" if elapsed.get(tag,0)>avg*1.6 else "🟡"
        if s=="CANCELADA": return "⊘"
        return "⚪"  # pendente
    def eta(tag):
        s=st[tag]
        if s=="COMPLETA": return f"feito ({actual.get(tag,0):.0f}m)" if tag in actual else "feito"
        if s=="FALHA": return f"~{avg*0.5:.0f}m (rework)"
        if s=="RODANDO":
            el=elapsed.get(tag,0); r=avg-el
            return f"~{max(1,r):.0f}m" if r>0 else f"ATRASADO +{-r:.0f}m"
        return f"~{avg:.0f}m (fila)"
    pct=100*cnt["COMPLETA"]/total; bar="█"*int(pct/5)+"░"*(20-int(pct/5))
    W=78
    o=[]
    o.append("═"*W)
    o.append(f" AOP · STATUS 360 + ETA · {now} · refresh 60s")
    o.append("═"*W)
    o.append(f" 🟢 {cnt['COMPLETA']} concluídas   🟡 {cnt['RODANDO']} rodando   ⚪ {cnt['PENDENTE']} pendentes   🔴 {cnt['FALHA']} falha   ⊘ {cnt['CANCELADA']} canceladas")
    o.append(f" Progresso [{bar}] {pct:.0f}%")
    o.append(f" ETA p/ TERMINAR TUDO: ~{eta_all:.0f} min (~{eta_all/60:.1f} h)  ·  base: {len(durs)} feitas, média {avg:.0f}m/task, {workers} workers paralelos")
    o.append("─"*W)
    o.append(f" {'LUZ':<4}{'TASK':<38}{'AGENTE RESPONSÁVEL':<22}{'ETA'}")
    o.append("─"*W)
    order={"RODANDO":0,"FALHA":1,"PENDENTE":2,"COMPLETA":3,"CANCELADA":4}
    for tag in sorted(SCOPE,key=lambda k:(order[st[k]],k)):
        o.append(f" {light(tag)}  {SCOPE[tag][0][:36]:<37}{str(agent[tag])[:20]:<22}{eta(tag)}")
    o.append("═"*W)
    o.append(" 🟢 concluída  🟡 rodando no prazo  🔴 falha/atrasada  ⚪ pendente (fila)")
    return "\n".join(o)
if __name__=="__main__":
    if "--watch" in sys.argv:
        try:
            while True: print("\033[2J\033[H"+render(),flush=True); time.sleep(60)
        except KeyboardInterrupt: pass
    else: print(render())
