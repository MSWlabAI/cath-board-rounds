#!/usr/bin/env python3
"""Rescore stored briefs from a runs CSV under the CURRENT scorer (no Switch, no model): proves a scorer change does not flag the real outputs, and what it now catches.
usage: rescore.py <day file> <answer key> <csv[,csv...]> [prompt-hash prefix]     e.g. rescore.py day.md expected.json runs.csv 8130"""
import csv,re,sys,os
day,exp,files,hashp=sys.argv[1],sys.argv[2],sys.argv[3].split(','),(sys.argv[4] if len(sys.argv)>4 else '')
os.environ['DAY_FILE']=day; os.environ['EXPECTED_FILE']=exp
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__))); import check
SPLIT=re.compile(r" \| (?=(?:@\w+ )*\*\*\[|\*\*[\w ()/-]+:\*\*|🚩|✅|🔁|MISSING:)")
n=bad=0
for f in files:
    for r in csv.DictReader(open(f)):
        if hashp and not r['prompt_hash'].startswith(hashp): continue
        if not r['brief']: continue
        m,_=check.score(int(r['case']),r['agent'],"\n".join(SPLIT.split(r['brief']))); n+=1
        if m: bad+=1; print(f,r['case'],r['agent'],m[:2])
print(day,n,'briefs rescored,',bad,'misses')
