"""extractor 패키지 pytest 설정.

shared 패키지 (workspace root 아래) 를 sys.path 에 추가해
extractor 패키지 단위 테스트에서 `import shared` 가 동작하도록 한다.

uv workspace editable install 이 완전히 동작하지 않는 환경 대비 — apps/api/tests/conftest.py
와 동일한 패턴.
"""

from __future__ import annotations

import sys
from pathlib import Path

# workspace root = packages/extractor/tests/../../.. = english-worksheet-tool/
_workspace_root = Path(__file__).parent.parent.parent.parent
if str(_workspace_root) not in sys.path:
    sys.path.insert(0, str(_workspace_root))

# packages/extractor/src 도 추가 (editable install 환경 외)
_extractor_src = Path(__file__).parent.parent / "src"
if str(_extractor_src) not in sys.path:
    sys.path.insert(0, str(_extractor_src))

# packages/llm/src 도 추가
_llm_src = Path(__file__).parent.parent.parent / "llm" / "src"
if str(_llm_src) not in sys.path:
    sys.path.insert(0, str(_llm_src))
