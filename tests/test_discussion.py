import tempfile
import unittest
from pathlib import Path
from bot import Bot, trigger
from store import Store
from components.discussion import namespace


class TelegramFake:
    def __init__(self, admin=True): self.sent, self.is_admin = [], admin
    def send(self, chat, text): self.sent.append(text)
    def call(self, method, **kwargs): return {'status': 'administrator' if self.is_admin else 'member'}


class PipelinesFake:
    def __init__(self): self.indexed = []
    def index(self, chat, session, message): self.indexed.append(message)
    def summary(self, chat, session): return 'Итог обсуждения'
    def answer(self, chat, session, question): return {'discuss': {'answer': 'Ответ по контексту'}}


class DiscussionTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.store = Store(Path(self.tmp.name) / 'db.sqlite3')
        self.tg, self.p = TelegramFake(), PipelinesFake()
        self.bot = Bot(self.store, self.p, self.tg, {'username': 'study_repo_bot'})
        self.mid = 0

    def tearDown(self): self.tmp.cleanup()

    def send(self, text, chat=-1, bot=False):
        self.mid += 1
        self.bot.handle({'chat': {'id': chat, 'type': 'group'}, 'from': {'id': 1, 'first_name': 'Участник', 'is_bot': bot},
                         'message_id': self.mid, 'date': self.mid, 'text': text})

    def test_only_explicit_listening_records_messages(self):
        self.send('До старта'); self.assertEqual(self.p.indexed, [])
        self.send('/listen'); self.send('Учимся в субботу'); self.send('/stop'); self.send('После стопа')
        self.assertEqual(len(self.p.indexed), 1)
        self.assertFalse(self.store.room(-1)['listening'])

    def test_start_stop_require_group_admin(self):
        self.tg.is_admin = False; self.send('/listen')
        self.assertFalse(self.store.room(-1)['listening'])
        self.tg.is_admin = True; self.send('/listen')
        self.tg.is_admin = False; self.send('/stop')
        self.assertTrue(self.store.room(-1)['listening'])

    def test_triggers_and_bot_replies_are_not_indexed(self):
        self.send('/listen'); self.send('Что думаешь?'); self.send('@study_repo_bot Какой итог?'); self.send('Ответ', bot=True)
        self.assertEqual(self.p.indexed, [])
        self.assertIn('Ответ по контексту', self.tg.sent)

    def test_repeated_start_preserves_active_session(self):
        self.send('/listen'); first = self.store.room(-1)['session']
        self.send('/listen'); self.assertEqual(first, self.store.room(-1)['session'])
        self.send('/stop'); self.send('/listen')
        self.assertNotEqual(first, self.store.room(-1)['session'])

    def test_chat_and_session_isolation(self):
        self.send('/listen'); self.send('Секрет текущей комнаты')
        old = self.store.room(-1)['session']
        self.assertEqual(self.store.messages(-2, old), [])
        self.send('/stop'); self.send('/listen')
        self.assertEqual(self.store.messages(-1, self.store.room(-1)['session']), [])
        self.assertNotEqual(namespace(-1), namespace(-2))

    def test_duplicate_telegram_update_does_not_duplicate_local_message(self):
        session = self.store.start(-1)['session']
        message = {'mid': 1, 'author': 'A', 'author_id': '1', 'text': 'abc', 'date': 1}
        self.store.add(-1, session, message); self.store.add(-1, session, message)
        self.assertEqual(len(self.store.messages(-1, session)), 1)

    def test_author_metadata_and_persistence(self):
        self.send('/listen'); self.send('Сначала скобки')
        other = Store(self.store.path)
        rows = other.messages(-1, other.room(-1)['session'])
        self.assertEqual(rows[0]['author'], 'Участник')
        self.assertEqual(rows[0]['text'], 'Сначала скобки')
        self.assertEqual(rows[0]['indexed'], 1)

    def test_message_limit_stops_recording(self):
        self.send('/listen')
        for i in range(61): self.send(f'Реплика {i}')
        self.assertEqual(len(self.p.indexed), 60)
        self.assertFalse(self.store.room(-1)['listening'])

    def test_group_records_other_participant_after_authorized_start(self):
        self.bot.allowed = {1}
        self.send('/listen')
        self.bot.handle({'chat': {'id': -1, 'type': 'group'},
                         'from': {'id': 2, 'first_name': 'Второй участник'},
                         'message_id': 20, 'date': 20, 'text': 'Согласна, в субботу в 19:00 удобно.'})
        rows = self.store.messages(-1, self.store.room(-1)['session'])
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]['author_id'], '2')

    def test_allowlist_still_protects_private_chat_and_new_group(self):
        self.bot.allowed = {1}
        for kind, chat in [('private', 2), ('group', -2)]:
            self.bot.handle({'chat': {'id': chat, 'type': kind},
                             'from': {'id': 2, 'first_name': 'Другой участник'},
                             'message_id': 1, 'date': 1, 'text': '/listen'})
            self.assertFalse(self.store.room(chat)['listening'])


if __name__ == '__main__': unittest.main()
