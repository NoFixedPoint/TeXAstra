"""Read-only PE inspection of the installed BaKoMa compiler/preview interface.

Install pefile and capstone into .work/binary-tools. Does not load or execute DLLs.
Only selected interface functions and relevant strings are recorded.
"""
from pathlib import Path
import hashlib,json,re,sys
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'.work/binary-tools'))
import pefile,capstone

INSTALL=Path('C:/BaKoMa.TeX/BIN/Win64')
OUT=ROOT/'results/bakoma-binary';OUT.mkdir(parents=True,exist_ok=True)
SELECTED={'DVIBUF_Get','DVIBUF_Init','Set_DVI_Procs','Set_SaveState','StartTeX','ContinueTeX','InvalidatePages','RestartTeX','Set_FileReVersion_Proc','Set_Input_Procs','Set_Output_Procs'}
pattern=re.compile(r'^(?:tex\.|dvi\.)|(?:DVIBUF|ContinueTeX|InvalidatePages|Set_SaveState|Set_DVI_Procs|itex\.dll|ietex\.dll|DVI.?cache|DVI.?memory|TeX.?state|memory snapshot|save_state|save state|Compute_Dif|restore_diff|restore_files|load_state|Loading state|Restored.*states)',re.I)
report={}
for name in ['itex.dll','ietex.dll','texword.exe','dview.exe','postwx.exe']:
    path=INSTALL/name;data=path.read_bytes();pe=pefile.PE(data=data);base=pe.OPTIONAL_HEADER.ImageBase
    exports={s.name.decode():s.address for s in getattr(getattr(pe,'DIRECTORY_ENTRY_EXPORT',None),'symbols',[]) if s.name}
    imports={d.dll.decode():[{ 'name':s.name.decode() if s.name else f'ordinal:{s.ordinal}','iatRva':hex(s.address-base)} for s in d.imports] for d in pe.DIRECTORY_ENTRY_IMPORT}
    item={'path':str(path),'sha256':hashlib.sha256(data).hexdigest(),'bytes':len(data),'imageBase':hex(base),'machine':hex(pe.FILE_HEADER.Machine),'exports':{n:hex(r) for n,r in exports.items()},'imports':imports,'strings':[],'functions':{}}
    for match in re.finditer(rb'[\x20-\x7e]{5,}',data):
        value=match[0].decode()
        if len(value)<300 and pattern.search(value):item['strings'].append({'fileOffset':hex(match.start()),'rva':hex(pe.get_rva_from_offset(match.start())),'value':value})
    bounds={f.struct.BeginAddress:f.struct.EndAddress for f in getattr(pe,'DIRECTORY_ENTRY_EXCEPTION',[])}
    md=capstone.Cs(capstone.CS_ARCH_X86,capstone.CS_MODE_64)
    for symbol in sorted(SELECTED & exports.keys()):
        start=exports[symbol]
        end=bounds.get(start)
        if end is None:end=min([r for r in list(bounds)+list(exports.values()) if r>start]+[start+256])
        instructions=[]
        for i in md.disasm(pe.get_data(start,end-start),base+start):
            if i.mnemonic=='int3':break
            instructions.append(f'{i.address-base:08x}  {i.mnemonic} {i.op_str}')
        item['functions'][symbol]={'rva':hex(start),'extent':'PE unwind record' if start in bounds else 'leaf function, bounded by next entry/padding','instructions':instructions}
    report[name]=item
(OUT/'inspection.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
for name,item in report.items():
    print(name, item['sha256'], 'exports',len(item['exports']),'relevant strings',len(item['strings']))
print('Saved',OUT/'inspection.json')
