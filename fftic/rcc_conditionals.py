"""Decode RCC two-level conditional programs and adapt verified native Nex ops."""
from collections import defaultdict
import copy
import difflib
import json
from pathlib import Path
import struct


BATTLE_ARITY = {1:2,4:1,5:2,6:2,7:2,8:2,11:1,22:0,24:4,25:1,28:1,
                29:1,30:1,31:1,32:1,33:1,34:1,35:1,37:4,39:2}
WORLD_ARITY = {0:0,1:2,4:1,25:2,26:8,29:1,30:3,31:2,32:2,33:2,34:1,35:1,36:1}
BATTLE_TERMINALS = {25,28}
WORLD_TERMINALS = {0,25,26,29,30,31,32,33,34,35,36}
CONDITIONAL_DATA = Path(__file__).with_name('data')/'rcc-conditionals.json'


def decode_program(data,offset,family):
    arity,terminals = (BATTLE_ARITY,BATTLE_TERMINALS) if family=='battle' else (WORLD_ARITY,WORLD_TERMINALS)
    ops = []
    for _ in range(512):
        if offset+2>len(data):
            raise ValueError('Truncated '+family+' conditional opcode')
        op = struct.unpack_from('<H',data,offset)[0]
        offset += 2
        if op not in arity:
            raise ValueError(f'Unverified {family} conditional opcode{op} at0x{offset-2:X}')
        size = arity[op]*2
        if offset+size>len(data):
            raise ValueError('Truncated '+family+' conditional operands')
        operands = list(struct.unpack_from('<'+'H'*arity[op],data,offset)) if arity[op] else []
        ops.append([op,*operands])
        offset += size
        if op in terminals:
            return ops,offset
    raise ValueError('Conditional exceeds verified512-word interpreter capacity')


def decode_table(data,family,count=None):
    """Read ushort first/second TOCs; programs use fixed-arity ushort operands."""
    if family not in ('battle','world') or len(data)<2:
        raise ValueError('Invalid conditional family/data')
    first = struct.unpack_from('<H',data)[0]
    inferred = first//2
    expected = 146 if family=='battle' else 44
    count = count if count is not None else expected
    if first%2 or inferred!=count or first>len(data):
        raise ValueError('Conditional first-level TOC count changed')
    offsets = struct.unpack_from('<'+'H'*count,data)
    groups = {}
    for key,offset in enumerate(offsets):
        if offset<first or offset%2 or offset+2>len(data):
            raise ValueError('Conditional second-level TOC pointer is invalid')
        programs = []
        for clause in range(64):
            if offset+2>len(data):
                raise ValueError('Truncated conditional second-level TOC')
            pointer = struct.unpack_from('<H',data,offset)[0]
            offset += 2
            if not pointer:
                break
            if pointer%2 or pointer<first or pointer>=len(data):
                raise ValueError('Conditional program pointer is invalid')
            ops,_ = decode_program(data,pointer,family)
            programs.append(ops)
        else:
            raise ValueError('Unterminated conditional second-level TOC')
        groups[key] = programs
    return groups


def native_battle_op(row,controls):
    op = row['UnkType4']
    array = json.loads(row['Unknown14']) if isinstance(row['Unknown14'],str) else row['Unknown14']
    unit = controls[row['CharaControlId']]['Unknown8'] if row['CharaControlId'] else 0
    if op in (1,39): return [op,row['UnknownC'],*array]
    if op in (4,11,29,33,34,35): return [op,unit]
    if op in (5,6,7,8,24,37): return [op,unit,*array]
    if op in (25,28): return [op,row['Unknown10']]
    if op==30: return [op,row['Unknown1C']]
    if op in (31,32): return [op,row['Unknown20']]
    return [op]


def native_world_op(row):
    op = row['Type']
    array = json.loads(row['Unknown8']) if isinstance(row['Unknown8'],str) else row['Unknown8']
    if op==1: return [op,row['Unknown10'],*array]
    if op in (4,25,26,29,30,31,43): return [op,*array]
    if op in (32,33): return [op,row['Unknown14'],row['Unknown18']]
    if op in (34,35,36,42): return [op,row['Unknown14']]
    if op==41: return [op,row['Unknown1C']]
    return [op]


def group_native_rows(rows):
    groups = defaultdict(dict)
    for key,row in sorted(rows.items()):
        groups[key[:2]][key[2]] = row
    return {key:list(values.values()) for key,values in groups.items()}


TABLES = {'battle':'EnhancedBattleEvent','world':'EnhancedWorldEvent'}
PRIVATE_ROWS = {'battle':'_RCCBattleConditions','world':'_RCCWorldConditions'}
BATTLE_COLUMNS = ('Key','Key2','Key3','DLCFlags','UnkType4','Unknown6',
    'CharaControlId','UnknownA','UnknownC','UnknownE','Unknown10','Unknown12',
    'Unknown14','Unknown1C','Unknown1E','Unknown20','Comment')
WORLD_COLUMNS = ('Key','Key2','Key3','DLCFlags','Type','Unknown8','Unknown10',
    'Unknown14','Unknown18','Unknown1C')


def load_deltas():
    return json.loads(CONDITIONAL_DATA.read_text(encoding='utf-8'))


def _terminal(ops,family):
    last = ops[-1]
    if family=='battle':
        return tuple(last)
    # Enhanced converts original map/cutscene OP26 into a cost condition
    # plus OP25 event dispatch. The event ID identifies that same clause.
    if last[0]==26: return ('event',last[2])
    if last[0]==25: return ('event',last[1])
    return tuple(last)


def _decode(rows,family,controls):
    decoder = (lambda row:native_battle_op(row,controls)) if family=='battle' else native_world_op
    return [decoder(row) for row in rows]


def _neutral_row(family,key):
    columns = BATTLE_COLUMNS if family=='battle' else WORLD_COLUMNS
    row = dict.fromkeys(columns,0)
    row.update(zip(('Key','Key2','Key3'),key))
    if family=='battle':
        row.update(Unknown14=[],Comment=None)
    else:
        row.update(Unknown8=[],Unknown14=47,Unknown18=47)
    return row


def encode_op(op,family,key,controls):
    """Encode only opcodes reconstructed by the verified native consumers."""
    arity = BATTLE_ARITY if family=='battle' else WORLD_ARITY
    if op[0] not in arity or len(op)!=arity[op[0]]+1:
        raise ValueError('Unverified source conditional operands: '+str(op))
    if any(not isinstance(value,int) or not 0<=value<=65535 for value in op):
        raise ValueError('Conditional operands exceed their native ushort range')
    row = _neutral_row(family,key)
    opcode = op[0]
    if family=='battle':
        row['UnkType4'] = opcode
        if opcode in (1,39):
            row.update(UnknownC=op[1],Unknown14=op[2:])
        elif opcode in (4,5,6,7,8,11,24,29,33,34,35,37):
            ids = [control for control,value in controls.items()
                   if control and value['Unknown8']==op[1]]
            if not ids:
                raise ValueError('No native CharaControlId for source unit '+str(op[1]))
            # A nonzero ID is required: zero means no control record. Unit0
            # therefore uses verified alias256, while retained rows keep
            # their existing Enhanced aliases rather than this default.
            row['CharaControlId'] = min(ids)
            row['Unknown14'] = op[2:]
        elif opcode in (25,28): row['Unknown10'] = op[1]
        elif opcode==30: row['Unknown1C'] = op[1]
        elif opcode in (31,32): row['Unknown20'] = op[1]
        elif opcode!=22: raise ValueError('Unsupported battle encoding')
    else:
        row['Type'] = opcode
        if opcode==1: row.update(Unknown10=op[1],Unknown8=op[2:])
        elif opcode in (0,4,25,26,29,30,31): row['Unknown8'] = op[1:]
        elif opcode in (32,33): row.update(Unknown14=op[1],Unknown18=op[2])
        elif opcode in (34,35,36): row['Unknown14'] = op[1]
        else: raise ValueError('Unsupported world encoding')
    return row


def _ops_changes(original,target):
    """Source pairs retain their dispatch; only the authored op edits apply."""
    if original[-1]!=target[-1]:
        raise ValueError('Authored paired conditional changes its dispatch')
    match = difflib.SequenceMatcher(a=list(map(tuple,original)),b=list(map(tuple,target)),autojunk=False)
    return [(list(map(list,original[a:b])),list(map(list,target[c:d])))
            for tag,a,b,c,d in match.get_opcodes() if tag!='equal']


def _adapt_clause(rows,original,target,family,controls,group):
    """Apply deleted/replaced source operands without flattening native extras."""
    rows = copy.deepcopy(rows)
    removed,added,already_absent = [],[],[]
    for old,new in _ops_changes(original,target):
        for operand in old:
            mapped = operand
            values = _decode(rows,family,controls)
            if family=='battle' and group==144 and operand==[1,128,0] and operand not in values:
                # Enhanced's ending routes specifically replace legacy
                # guard128 with509. This is not a global variable alias.
                mapped = [1,509,0]
            positions = [index for index,value in enumerate(values) if value==mapped]
            if not positions:
                already_absent.append(operand)
                continue
            index = positions[0]
            removed.append(dict(source=operand,native=mapped))
            rows.pop(index)
            if new:
                # Current authored paired insertion is exactly world18's
                # var159=1 -> var110=53, so insert at its removed guard.
                for offset,value in enumerate(new):
                    rows.insert(index+offset,encode_op(value,family,(group,rows[0]['Key2'],0),controls))
                    added.append(value)
                new = []
        if new:
            raise ValueError('Cannot anchor an authored conditional insertion to a native guard')
    for index,row in enumerate(rows): row['Key3'] = index
    return rows,dict(removed=removed,added=added,already_absent=already_absent)


def build_conditional_plan(before,family):
    """Return guarded two-key group replacements from the pinned source delta."""
    if family not in TABLES: raise ValueError('Invalid conditional family')
    rows = before[PRIVATE_ROWS[family]]
    controls = before.get('_RCCCharaControls',{})
    groups = group_native_rows(rows)
    changes = load_deltas()['families'][family]['changed_groups']
    plans,details = {},[]
    for raw_key,delta in changes.items():
        key = int(raw_key)
        source_before,source_after = delta['before'],delta['after']
        if len(source_after)<len(source_before):
            raise ValueError('Unexpected source clause deletion')
        native = {k:copy.deepcopy(v) for k,v in groups.items() if k[0]==key}
        if not native: raise ValueError('Missing native conditional group '+str(key))
        edits = defaultdict(list)
        for old,new in zip(source_before,source_after):
            if old!=new:
                edits[_terminal(old,family)].append((old,new))
        matched = set()
        for group,original_rows in sorted(native.items()):
            decoded = _decode(original_rows,family,controls)
            terminal = _terminal(decoded,family)
            pairs = edits.get(terminal,[])
            changed_rows = original_rows
            clause_audit = []
            for old,new in pairs:
                changed_rows,audit = _adapt_clause(changed_rows,old,new,family,controls,key)
                clause_audit.append(audit)
                matched.add(terminal)
            if family=='battle' and key==144 and terminal==(25,491):
                # These two modern branches split old event487 by ending
                # character availability. Remove its same mapped509 guard
                # while preserving the native33/34 controls and dispatch.
                old,new = [[1,128,0],[25,491]],[[25,491]]
                changed_rows,audit = _adapt_clause(changed_rows,old,new,family,controls,key)
                clause_audit.append(audit)
            if changed_rows!=original_rows:
                plans[group] = dict(expected=original_rows,rows=changed_rows)
            if clause_audit:
                details.append(dict(key=list(group),dispatch=list(terminal),edits=clause_audit,
                                    changed=changed_rows!=original_rows))
        missing = set(edits)-matched
        if missing: raise ValueError('Source conditional dispatch absent in Enhanced: '+str((key,missing)))
        next_clause = max(group[1] for group in native)+1
        for program in source_after[len(source_before):]:
            existing = [_decode(v,family,controls) for v in native.values()]
            if program in existing:
                details.append(dict(key=[key],added_program=program,already_present=True))
                continue
            group = (key,next_clause)
            encoded = [encode_op(op,family,(*group,index),controls) for index,op in enumerate(program)]
            plans[group] = dict(expected=[],rows=encoded)
            details.append(dict(key=list(group),added_program=program,already_present=False))
            native[group] = encoded
            next_clause += 1
        if family=='battle' and len(native)>16:
            raise ValueError('Enhanced battle conditionals exceed16 native clauses')
        if family=='battle':
            # The native loader has a512-word program buffer per battle.
            final = {**native,**{k:v['rows'] for k,v in plans.items() if k[0]==key}}
            word_count = sum(sum(len(op) for op in _decode(value,family,controls)) for value in final.values())
            if word_count>=512: raise ValueError('Enhanced battle conditionals reach512 native words')
    return plans,dict(family=family,changed_first_keys=sorted({key[0] for key in plans}),
                      replaced_clauses=sum(bool(v['expected']) for v in plans.values()),
                      added_clauses=sum(not v['expected'] for v in plans.values()),details=details)


def apply_conditionals(before,result,flags='',*,world=True):
    """Default overworld progression; z also applies RCC's ending battle table."""
    audit = dict(source_commit=load_deltas()['source_commit'],families={})
    for family in ('world','battle'):
        if family=='world' and not world or family=='battle' and 'z' not in flags: continue
        plans,report = build_conditional_plan(before,family)
        if plans:
            result.setdefault('_RCCConditionalReplacements',{})[TABLES[family]] = plans
            result[PRIVATE_ROWS[family]] = copy.deepcopy(before[PRIVATE_ROWS[family]])
            for group,plan in plans.items():
                result[PRIVATE_ROWS[family]] = {key:row for key,row in result[PRIVATE_ROWS[family]].items() if key[:2]!=group}
                result[PRIVATE_ROWS[family]].update({tuple(row[k] for k in ('Key','Key2','Key3')):row for row in copy.deepcopy(plan['rows'])})
        audit['families'][family] = report
    result['_RCCConditionalAudit'] = audit
    return audit


def validate_replacements(before,replacements):
    """Reject arbitrary row replacement outside the recomputed source plans."""
    for table,plans in replacements.items():
        family = next((family for family,name in TABLES.items() if name==table),None)
        if family is None: raise ValueError('Unsupported conditional Nex table')
        expected,_ = build_conditional_plan(before,family)
        if plans!=expected: raise ValueError('Conditional plan differs from verified authored source edits')
