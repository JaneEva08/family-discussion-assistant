import json
import tempfile
import time
import uuid
from pathlib import Path
from bot import services
from store import Store
from pipelines import DiscussionPipelines

ROOT = Path(__file__).resolve().parent


def main():
    pc, host, chat = services()
    with tempfile.TemporaryDirectory() as tmp:
        store = Store(Path(tmp) / 'probe.sqlite3')
        p = DiscussionPipelines(pc, host, chat, store)
        chat_id = 'probe-' + uuid.uuid4().hex[:12]
        session = store.start(chat_id)['session']
        examples = [('Родитель', 'Предлагаю заниматься уравнениями в 18:00 каждый день.'),
                    ('Ученица 1', 'Мне трудно раскрывать скобки. В 18:00 у меня другое занятие.'),
                    ('Ученица 2', 'Я могу после 19:00, но сначала хочу повторить раскрытие скобок.'),
                    ('Родитель', 'Уточняю: каждый день заниматься не будем. Договорились начать в субботу в 19:00 с раскрытия скобок, затем уравнения.')]
        for mid, (author, text) in enumerate(examples, 1):
            message = {'mid': mid, 'author': author, 'author_id': str(mid), 'text': text, 'date': 1793660000 + mid}
            store.add(chat_id, session, message); p.index(chat_id, session, message)
            store.indexed(chat_id, session, mid)
        # Allow index visibility before recording semantic search evidence.
        time.sleep(3)
        qa = p.answer(chat_id, session, 'Что думаешь? Когда и с чего договорились начать?')
        summary = p.summary(chat_id, session)
        other = p.answer('other-' + chat_id, session, 'О чём договорились?')
        assert other['retrieve']['context'] == []
        assert '19' in qa['discuss']['answer'] and 'скоб' in summary.lower()
        assert len(store.messages(chat_id, session)) == 4
        result = {'author_material': examples, 'search': qa, 'summary': summary, 'other_chat': other,
                  'namespace_isolation': True, 'pipelines': ['indexing', 'search', 'summarization']}
        (ROOT / 'results/service-checks.json').write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
        print('Real indexing, search, summary and isolation checks passed.')


if __name__ == '__main__': main()
