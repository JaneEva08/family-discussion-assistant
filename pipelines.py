import os
os.environ.setdefault('HAYSTACK_TELEMETRY_ENABLED', 'false')
from haystack import Pipeline
from components.discussion import MessageDocument, IndexMessages, RetrieveDiscussion, Discuss, ReadSession, Summarize


class DiscussionPipelines:
    def __init__(self, pc, host, chat, store):
        self.indexing = Pipeline()
        self.indexing.add_component('document', MessageDocument())
        self.indexing.add_component('write', IndexMessages(pc, host))
        self.indexing.connect('document.documents', 'write.documents')
        self.search = Pipeline()
        self.search.add_component('retrieve', RetrieveDiscussion(pc, host, store))
        self.search.add_component('discuss', Discuss(chat))
        self.search.connect('retrieve.context', 'discuss.context')
        self.summarization = Pipeline()
        self.summarization.add_component('read', ReadSession(store))
        self.summarization.add_component('summarize', Summarize(chat))
        self.summarization.connect('read.messages', 'summarize.messages')

    def index(self, chat, session, message):
        return self.indexing.run({'document': {'chat': str(chat), 'session': session, 'message': message}})['write']

    def answer(self, chat, session, question):
        return self.search.run({'retrieve': {'chat': str(chat), 'session': session, 'question': question},
                                'discuss': {'question': question}}, include_outputs_from={'retrieve'})

    def summary(self, chat, session):
        return self.summarization.run({'read': {'chat': str(chat), 'session': session}})['summarize']['answer']
