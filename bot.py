"""python bot.py — explicit listening, three Haystack pipelines, bounded sessions."""
import logging
import os
import re
import time
from pathlib import Path
from transport import load_env, Telegram, ChatClient
from pinecone_client import Pinecone, DIMENSION
from store import Store
from pipelines import DiscussionPipelines

ROOT = Path(__file__).resolve().parent
HELP = '''Помощник семейной учебной группы.
/listen — начать новое обсуждение (повторная команда сохраняет текущую сессию)
/stop — остановить запись и подвести итог
/summary — итог текущего/последнего обсуждения
/ask вопрос — найти в обсуждении и ответить
/status — состояние записи

После /listen обычные сообщения участников сохраняются в SQLite и Pinecone
и передаются модели для ответа. Не присылайте личные секреты.
«Что думаешь?» или @имя_бота вопрос — ответ по контексту обсуждения.
В группе /listen и /stop доступны её администраторам. Бот не оценивает
успеваемость и не принимает решения за семью.
'''


def trigger(text, username):
    normalized = text.casefold().strip().rstrip('?! .')
    if normalized in {'что думаешь', 'что ты думаешь'}: return 'Что думаешь об этом обсуждении?'
    mention = '@' + username.casefold()
    if re.search(re.escape(mention) + r'\b', text.casefold()):
        return re.sub(re.escape(mention) + r'\b', '', text, flags=re.I).strip() or 'Что думаешь об этом обсуждении?'
    if text.casefold().startswith('/ask '): return text.split(' ', 1)[1].strip()
    return None


class Bot:
    def __init__(self, store, pipelines, telegram, me, allowed=None):
        self.store, self.p, self.tg, self.me = store, pipelines, telegram, me
        self.allowed = allowed or set()

    def admin(self, message):
        if message['chat']['type'] == 'private': return True
        try:
            member = self.tg.call('getChatMember', chat_id=message['chat']['id'], user_id=message['from']['id'])
            return member.get('status') in {'creator', 'administrator'}
        except RuntimeError: return False

    def handle(self, message):
        if message.get('from', {}).get('is_bot') or message['chat']['type'] not in {'private','group','supergroup'}: return
        user, chat = message['from'], message['chat']['id']
        if self.allowed and user['id'] not in self.allowed:
            # The private-chat allowlist must not suppress other participants
            # once an authorized user has explicitly enabled this group.
            if message['chat']['type'] == 'private' or not self.store.room(chat)['session']:
                return
        text = message.get('text', '').strip()
        if not text: return
        if len(text) > 2000:
            self.tg.send(chat, 'Сообщение слишком длинное для этого прототипа: до 2000 символов.')
            return
        cmd = text.split()[0].split('@')[0].casefold()
        if cmd in {'/start','/help'}: self.tg.send(chat, HELP); return
        if cmd in {'/listen','/stop'} and not self.admin(message):
            self.tg.send(chat, 'Начать или остановить запись может администратор группы.'); return
        if cmd == '/listen':
            active = self.store.room(chat)['listening']
            self.store.start(chat)
            self.tg.send(chat, 'Запись уже идёт; текущая сессия сохранена.' if active else
                         'Запись обсуждения включена. Следующие сообщения сохраняются в SQLite и Pinecone '
                         'и передаются модели при запросе. Завершение и итог — /stop.'); return
        room = self.store.room(chat)
        messages = self.store.messages(chat, room['session']) if room['session'] else []
        if cmd == '/status':
            self.tg.send(chat, f"Запись {'включена' if room['listening'] else 'выключена'}. "
                         f"Сообщений в последнем обсуждении: {len(messages)}; в Pinecone: {sum(x['indexed'] for x in messages)}."); return
        if cmd == '/stop':
            self.store.stop(chat)
            self.tg.send(chat, 'Запись остановлена. ' + self.p.summary(chat, room['session'])); return
        if cmd == '/summary': self.tg.send(chat, self.p.summary(chat, room['session'])); return
        question = trigger(text, self.me['username'])
        if question:
            result = self.p.answer(chat, room['session'], question)
            self.tg.send(chat, result['discuss']['answer']); return
        if text.startswith('/'): self.tg.send(chat, 'Команды: /help'); return
        if not room['listening']:
            if message['chat']['type'] == 'private': self.tg.send(chat, 'Запись выключена. Начните обсуждение: /listen')
            return
        if len(messages) >= 60 and not any(x['mid'] == message['message_id'] for x in messages):
            self.store.stop(chat)
            self.tg.send(chat, 'Достигнут предел 60 сообщений. Запись остановлена; это сообщение не сохранено. '
                         'Получить итог: /summary. Новое обсуждение: /listen.'); return
        item = {'mid': message['message_id'], 'author': user.get('first_name', 'Участник')[:80],
                'author_id': str(user['id']), 'text': text, 'date': message.get('date', int(time.time()))}
        self.store.add(chat, room['session'], item)
        try:
            self.p.index(chat, room['session'], item)
            self.store.indexed(chat, room['session'], item['mid'])
        except RuntimeError:
            self.tg.send(chat, 'Сообщение сохранено локально; запись в Pinecone не подтверждена. '
                         'Оно останется в полном резюме. Проверьте /status.')


def services():
    load_env(ROOT / '.env')
    pc = Pinecone(os.environ['PINECONE_API_KEY'])
    info = pc.request('https://api.pinecone.io', '/indexes/' + os.getenv('PINECONE_INDEX','algebra-tutor-search'))
    if info['dimension'] != DIMENSION or info['metric'] != 'cosine': raise ValueError('Нужен индекс 1024/cosine.')
    host = 'https://' + info['host'].removeprefix('https://')
    chat = ChatClient(os.environ['OPENAI_API_KEY'], os.environ['OPENAI_BASE_URL'], os.getenv('CHAT_MODEL','gpt-6-luna'))
    return pc, host, chat


def main():
    pc, host, chat = services()
    tg = Telegram(os.environ['BOT_TOKEN'])
    me = tg.call('getMe')
    if tg.call('getWebhookInfo').get('url'): raise RuntimeError('У бота активен webhook. Polling не запущен.')
    store = Store(ROOT / 'data/discussions.sqlite3')
    if store.get('bot_id') != str(me['id']):
        store.put('offset', 0); store.put('bot_id', me['id'])
    bot = Bot(store, DiscussionPipelines(pc, host, chat, store), tg, me,
              {int(x) for x in os.getenv('ALLOWED_USER_IDS','').split(',') if x.strip()})
    logging.info('Family discussion bot polling started')
    while True:
        try:
            for update in tg.call('getUpdates', offset=int(store.get('offset')), timeout=25, allowed_updates=['message']):
                if 'message' in update:
                    try: bot.handle(update['message'])
                    except Exception:
                        logging.error('Message operation failed; content and credentials omitted')
                        tg.send(update['message']['chat']['id'], 'Не удалось завершить операцию. Повторите запрос; /status покажет состояние записи.')
                store.put('offset', update['update_id'] + 1)
        except RuntimeError as exc:
            logging.warning('%s', exc); time.sleep(3)


if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(message)s')
    try: main()
    except KeyboardInterrupt: pass
