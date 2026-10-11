"""Record static code references to selected preview/state interface strings."""
from pathlib import Path
import bisect,json,sys
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'.work/binary-tools'))
import pefile,capstone
from capstone.x86_const import X86_OP_MEM,X86_REG_RIP
OUT=ROOT/'results/bakoma-binary'
inventory=json.loads((OUT/'inspection.json').read_text())
report={}
for name in ['ietex.dll','texword.exe']:
    item=inventory[name];pe=pefile.PE(item['path']);base=pe.OPTIONAL_HEADER.ImageBase
    targets={int(s['rva'],16):s['value'] for s in item['strings'] if any(t in s['value'] for t in ['DVIBUF_Get','DVIBUF_Init','Set_DVI_Procs','ContinueTeX','Set_SaveState','memory snapshot','save_state','Save State','Save state','Compute_Dif','restore_diff','Loading state','Restored'])}
    md=capstone.Cs(capstone.CS_ARCH_X86,capstone.CS_MODE_64);md.detail=True
    bounds={f.struct.BeginAddress:f.struct.EndAddress for f in pe.DIRECTORY_ENTRY_EXCEPTION};starts=sorted(bounds)
    hits=[]
    # Unwind boundaries avoid decoding jump tables as instructions and stopping
    # the scan at embedded data. Leaf functions without unwind entries are not
    # covered by this cross-reference pass.
    for entry,end in bounds.items():
        for ins in md.disasm(pe.get_data(entry,end-entry),base+entry):
            for op in ins.operands:
                if op.type!=X86_OP_MEM or op.mem.base!=X86_REG_RIP:continue
                target=ins.address+ins.size+op.mem.disp-base
                if target not in targets:continue
                rva=ins.address-base;index=bisect.bisect_right(starts,rva)-1
                start=starts[index] if index>=0 else None
                if start is not None and not(start<=rva<bounds[start]):start=None
                hits.append({'string':targets[target],'rva':hex(rva),'instruction':ins.mnemonic+' '+ins.op_str,'functionRva':hex(start) if start is not None else None})
    functions={}
    for start in sorted({int(h['functionRva'],16) for h in hits if h['functionRva']}):
        functions[hex(start)]=[f'{ins.address-base:08x}  {ins.mnemonic} {ins.op_str}' for ins in md.disasm(pe.get_data(start,bounds[start]-start),base+start)]
    report[name]={'scope':'Static references in PE unwind regions; some regions are fragments of a larger function. Leaf functions may be omitted.','references':hits,'containingFunctions':functions}
    if name=='ietex.dll' and item['sha256']=='8422ea6e01d1af2c10d8d2e656f14f0f73a3da2bf94f9c94c2bf715ab96cf3c7':
        instructions=[]
        for ins in md.disasm(pe.get_data(0x47df0,0x48220-0x47df0),base+0x47df0):
            if ins.mnemonic=='int3':break
            instructions.append({'rva':hex(ins.address-base),'instruction':ins.mnemonic+' '+ins.op_str})
        (OUT/'difference-helper.json').write_text(json.dumps({'binary':name,'sha256':item['sha256'],'startRva':'0x47df0','extent':'Through padding or next known routine at RVA 0x48220; spans multiple unwind fragments','instructions':instructions},indent=2),encoding='utf-8')
(OUT/'xrefs.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
for name,item in report.items():print(name,json.dumps(item['references'],indent=2))
