import json
import sqlite3
import uuid
from contextlib import contextmanager
from pathlib import Path


class Store:
    def __init__(self, path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.db() as db:
            db.executescript('''
            CREATE TABLE IF NOT EXISTS rooms(chat TEXT PRIMARY KEY, session TEXT, listening INTEGER DEFAULT 0);
            CREATE TABLE IF NOT EXISTS messages(chat TEXT, session TEXT, mid INTEGER, author TEXT,
              author_id TEXT, text TEXT, date INTEGER, indexed INTEGER DEFAULT 0,
              PRIMARY KEY(chat,session,mid));
            CREATE TABLE IF NOT EXISTS runtime(key TEXT PRIMARY KEY,value TEXT);
            ''')

    @contextmanager
    def db(self):
        db = sqlite3.connect(self.path, timeout=20)
        db.row_factory = sqlite3.Row
        try:
            with db: yield db
        finally: db.close()

    def room(self, chat):
        with self.db() as db:
            row = db.execute('SELECT * FROM rooms WHERE chat=?', (str(chat),)).fetchone()
            return dict(row) if row else {'chat': str(chat), 'session': None, 'listening': 0}

    def start(self, chat):
        room = self.room(chat)
        if room['listening']: return room
        session = uuid.uuid4().hex[:16]
        with self.db() as db:
            db.execute('INSERT INTO rooms VALUES(?,?,1) ON CONFLICT(chat) DO UPDATE SET session=excluded.session,listening=1',
                       (str(chat), session))
        return self.room(chat)

    def stop(self, chat):
        with self.db() as db: db.execute('UPDATE rooms SET listening=0 WHERE chat=?', (str(chat),))

    def add(self, chat, session, message):
        with self.db() as db:
            db.execute('INSERT OR IGNORE INTO messages(chat,session,mid,author,author_id,text,date) VALUES(?,?,?,?,?,?,?)',
                       (str(chat), session, message['mid'], message['author'], str(message['author_id']),
                        message['text'], message['date']))

    def messages(self, chat, session):
        with self.db() as db:
            return [dict(r) for r in db.execute('SELECT * FROM messages WHERE chat=? AND session=? ORDER BY date,mid',
                                              (str(chat), session))]

    def indexed(self, chat, session, mid):
        with self.db() as db:
            db.execute('UPDATE messages SET indexed=1 WHERE chat=? AND session=? AND mid=?', (str(chat), session, mid))

    def get(self, key, default='0'):
        with self.db() as db:
            row = db.execute('SELECT value FROM runtime WHERE key=?', (key,)).fetchone()
            return row['value'] if row else default

    def put(self, key, value):
        with self.db() as db:
            db.execute('INSERT INTO runtime VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value',
                       (key, str(value)))
