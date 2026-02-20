from typing import Optional, Dict, Any
from datetime import datetime, timedelta, timezone

STATE_TIMEOUT_SECONDS = 600


class StateStore:
    """ユーザー状態を管理するストア（in-memory）"""
    
    def __init__(self, ttl_hours: int = 24):
        """
        Args:
            ttl_hours: 状態の有効期限（時間）
        """
        self._store: Dict[str, Dict[str, Any]] = {}
        self.ttl_hours = ttl_hours
    
    def _is_expired(self, state: Dict[str, Any]) -> bool:
        """状態が期限切れかチェック（created_at + ttl_hours）"""
        if "created_at" not in state:
            return True
        created_at = datetime.fromisoformat(state["created_at"])
        if created_at.tzinfo is None:
            created_at = created_at.replace(tzinfo=timezone.utc)
        expiry = created_at + timedelta(hours=self.ttl_hours)
        return datetime.now(timezone.utc) > expiry
    
    def _is_timed_out(self, state: Dict[str, Any]) -> bool:
        """updated_at から STATE_TIMEOUT_SECONDS を超えているか"""
        if "updated_at" not in state:
            return True
        updated_at = datetime.fromisoformat(state["updated_at"])
        if updated_at.tzinfo is None:
            updated_at = updated_at.replace(tzinfo=timezone.utc)
        elapsed = (datetime.now(timezone.utc) - updated_at).total_seconds()
        return elapsed >= STATE_TIMEOUT_SECONDS
    
    def get_state(self, user_id: str) -> Optional[Dict[str, Any]]:
        """ユーザーの状態を取得。10分以上更新がなければ削除して None を返す。"""
        if user_id not in self._store:
            return None
        
        state = self._store[user_id]
        if self._is_timed_out(state):
            del self._store[user_id]
            return None
        if self._is_expired(state):
            del self._store[user_id]
            return None
        
        return state.copy()
    
    def set_state(self, user_id: str, state: Dict[str, Any]) -> None:
        """ユーザーの状態を設定"""
        now = datetime.now(timezone.utc)
        state["created_at"] = now.isoformat()
        state["updated_at"] = now.isoformat()
        self._store[user_id] = state
    
    def update_state(self, user_id: str, **kwargs) -> None:
        """ユーザーの状態を更新"""
        current = self.get_state(user_id) or {}
        current.update(kwargs)
        now = datetime.now(timezone.utc)
        current["updated_at"] = now.isoformat()
        if "created_at" not in current:
            current["created_at"] = now.isoformat()
        self._store[user_id] = current
    
    def clear_state(self, user_id: str) -> None:
        """ユーザーの状態をクリア"""
        if user_id in self._store:
            del self._store[user_id]
    
    def clear_expired(self) -> None:
        """期限切れの状態をクリア"""
        expired_users = [
            user_id for user_id, state in self._store.items()
            if self._is_expired(state)
        ]
        for user_id in expired_users:
            del self._store[user_id]

# グローバルインスタンス
state_store = StateStore()
