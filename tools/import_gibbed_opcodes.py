"""Import operand lengths from pinned original Gibbed format definitions.

This is an adapted metadata importer; retain the upstream zlib notice.
The source definitions are research inputs, not downloaded game content.
"""
from pathlib import Path
import json
import re

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT/'research/gibbed-script-format'
text = (SOURCE/'Opcode.cs').read_text()
names = [m[1] for line in text.splitlines() if (m:=re.match(r'\s+([A-Za-z_0-9]+),',line))]
helpers = (SOURCE/'OpcodeHelpers.cs').read_text()
classic = helpers.split('private static int GetClassicSize',1)[1].split('private static int GetEnhancedSize',1)[0]
enhanced = helpers.split('private static int GetEnhancedSize',1)[1]
def sizes(block):
    return {name:int(size) for name,size in re.findall(r'Opcode\.(\w+) => (-?\d+)',block)}
base = sizes(classic)
base['UnknownE6'] = -1  # Explicitly dynamic in the upstream format.
updated = sizes(enhanced)
rows = {str(index):dict(name=name,classic=base[name],enhanced=base[name]+updated.get(name,0))
        for index,name in enumerate(names)}
target = ROOT/'fftic/data/gibbed-opcode-lengths.json'
target.write_text(json.dumps(rows,indent=2)+'\n',encoding='utf-8')
(ROOT/'fftic/data/GIBBED-LICENSE.txt').write_bytes((SOURCE/'LICENSE.txt').read_bytes())
print('Imported',len(rows),'opcode lengths from Gibbed commit8f200e2902dab52dd36b5933df456ebb57173658')
