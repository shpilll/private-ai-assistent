from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import ChatTurn, Conversation, PendingDeletion
from app.db.records import RecordMissing


class ChatStore:
    def __init__(self, db: Session):
        self.db = db

    def create(self):
        row = Conversation(title="Новый диалог")
        self.db.add(row)
        self.db.commit()
        return self.summary(row)

    @staticmethod
    def summary(row):
        return {"id": str(row.id), "title": row.title, "updated_at": row.updated_at.isoformat()}

    def conversations(self):
        return [self.summary(c) for c in self.db.scalars(select(Conversation).order_by(Conversation.updated_at.desc()))]

    def get(self, chat_id, lock=False):
        chat = self.db.get(Conversation, chat_id, with_for_update=lock)
        if chat is None:
            raise RecordMissing()
        return chat

    def turns(self, chat_id):
        return select(ChatTurn).where(ChatTurn.conversation_id == chat_id)

    def replay(self, chat_id, request_id):
        return self.db.scalar(self.turns(chat_id).where(ChatTurn.request_id == request_id))

    def context(self, chat_id):
        rows = list(self.db.scalars(self.turns(chat_id).order_by(ChatTurn.id.desc()).limit(8)))
        messages = []
        for row in reversed(rows):
            messages.append({"role": "user", "content": row.prompt[:1800]})
            facts = []
            for event in row.result["tools"]:
                record = event.get("result")
                if isinstance(record, dict) and "id" in record:
                    facts.append(f"{event['name']} id={record['id']}")
            messages.append({"role": "assistant", "content": row.result["answer"][:2400] + "\n" + ", ".join(facts)})
        return messages

    def view(self, row):
        result = dict(row.result)
        actions = []
        for item in result["confirmations"]:
            action = self.db.get(PendingDeletion, item["id"])
            state = "closed" if action is None else "pending"
            if action and action.expires_at <= datetime.now(timezone.utc):
                state = "expired"
            actions.append({**item, "state": state})
        result["confirmations"] = actions
        return {"request_id": str(row.request_id), "prompt": row.prompt, **result}

    def history(self, chat_id):
        chat = self.get(chat_id)
        rows = self.db.scalars(self.turns(chat_id).order_by(ChatTurn.id))
        return {**self.summary(chat), "turns": [self.view(row) for row in rows]}

    def save(self, chat, request_id, prompt, result):
        if chat.title == "Новый диалог":
            chat.title = prompt[:100]
        chat.updated_at = datetime.now(timezone.utc)
        row = ChatTurn(conversation_id=chat.id, request_id=request_id, prompt=prompt, result=result)
        self.db.add(row)
        self.db.flush()
        return self.view(row)
