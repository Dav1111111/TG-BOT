import os
import json
from datetime import datetime

class ChatHistory:
    def __init__(self, history_file='chat_history.json'):
        self.history_file = history_file
        self.history = self._load_history()

    def _load_history(self):
        if os.path.exists(self.history_file):
            try:
                with open(self.history_file, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except:
                return {}
        return {}

    def save_history(self):
        with open(self.history_file, 'w', encoding='utf-8') as f:
            json.dump(self.history, f, ensure_ascii=False, indent=2)

    def add_message(self, user_id: int, message: str, is_bot: bool):
        str_user_id = str(user_id)
        if str_user_id not in self.history:
            self.history[str_user_id] = []

        self.history[str_user_id].append({
            'timestamp': datetime.now().isoformat(),
            'message': message,
            'is_bot': is_bot
        })
        self.save_history()

    def get_user_history(self, user_id: int) -> list:
        return self.history.get(str(user_id), [])