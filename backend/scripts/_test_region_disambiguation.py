import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.llm import _match_region_by_name_and_context

for parent in ['南京市', '福州市', '徐州市']:
    print(parent, '->', _match_region_by_name_and_context('鼓楼区', parent, ''))
