# Образец структуры пайплайна

Официальный Haystack Extractive QA:
https://haystack.deepset.ai/tutorials/34_extractive_qa_pipeline

Notebook скачан 2026-11-03 из официального репозитория deepset-ai:
https://github.com/deepset-ai/haystack-tutorials/blob/main/tutorials/34_Extractive_QA_Pipeline.ipynb

Исходный notebook сохранён в корне как образец соединения компонентов Pipeline;
не запускался. Лицензия исходного репозитория сохранена в TUTORIAL-LICENSE.
Рабочая реализация использует генеративные ответы и суммаризацию обсуждения,
а не экстрактивный reader: это разные задачи. Код создан Codex вместо Cursor.
Переиспользованы согласованные API/base URL и E5-эмбеддинги Pinecone из предыдущих
этапов; это не OpenAI embeddings, отдельный индекс другой размерности не создавался.
