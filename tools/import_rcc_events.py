"""Import the user's pinned RCC source methods into the native-data adapter."""
import ast
from pathlib import Path
import re
import textwrap

ROOT=Path(__file__).resolve().parents[1]
SOURCE=Path('I:/rumble_chaos_crashdown/randomizer.py')
lines=SOURCE.read_text(encoding='utf-8').splitlines()

def extract(name,owner=None):
    start=next(i for i,line in enumerate(lines) if line.startswith(f'class {owner}(')) if owner else 0
    indent=4 if owner else 0
    begin=next(i for i in range(start,len(lines)) if lines[i].startswith(' '*indent+f'def {name}('))
    end=begin+1
    while end<len(lines):
        line=lines[end]
        if line.strip() and not line.lstrip().startswith('#') and len(line)-len(line.lstrip())<=indent:
            break
        end+=1
    source=textwrap.dedent('\n'.join(lines[begin:end]))
    source=re.sub(r'(?m)^(\s*)print .+$',r'\1pass',source)
    source=source.replace('xrange(','range(')
    return source

selected=[('generate_formations','EncounterObject'),('randomize_enemy_formations',None),
          ('mutate_units_special',None),('generate_balmafula',None)]
output=ROOT/'fftic/data/rcc-event-methods.py'
output.write_text('# RCC version27, commit ce9aafa1aaf7d05711cd33d8b49a062dc8a8a070.\n'
                  '# Original algorithms by abyssonym. Python2 print/xrange adapted.\n\n'+
                  '\n\n'.join(extract(name,owner) for name,owner in selected)+'\n',encoding='utf-8')
ast.parse(output.read_text(encoding='utf-8'))
print(output)
