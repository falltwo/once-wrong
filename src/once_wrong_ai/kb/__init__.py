"""填報手冊知識庫：把手冊切段存起來，審核時依檢核編號、欄位、表號找出相關段落給 AI。"""

from once_wrong_ai.kb.models import Passage, PassageKind
from once_wrong_ai.kb.search import Retriever

__all__ = ["Passage", "PassageKind", "Retriever"]
