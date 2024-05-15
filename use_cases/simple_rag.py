from typing import Any, List, Union, Optional
import dotenv


from core.openai_client import OpenAIClient
from core.generator import Generator
from core.embedder import Embedder
from core.data_components import (
    ToEmbedderResponse,
    RetrieverOutputToContextStr,
    ToEmbeddings,
)
from core.data_classes import Document

from core.document_splitter import DocumentSplitter
from core.string_parser import JsonParser
from core.component import Component, Sequential
from core.retriever import FAISSRetriever
from core.db import LocalDocumentDB

dotenv.load_dotenv(dotenv_path=".env", override=True)


# TODO: RAG can potentially be a component itsefl and be provided to the users
class RAG(Component):

    def __init__(self):
        super().__init__()

        self.vectorizer_settings = {
            "batch_size": 100,
            "model_kwargs": {
                "model": "text-embedding-3-small",
                "dimensions": 256,
                "encoding_format": "float",
            },
        }
        self.retriever_settings = {
            "top_k": 2,
        }
        self.generator_model_kwargs = {
            "model": "gpt-3.5-turbo",
            "temperature": 0.3,
            "stream": False,
        }
        self.text_splitter_settings = {  # TODO: change it to direct to spliter kwargs
            "split_by": "word",
            "chunk_size": 400,
            "chunk_overlap": 200,
        }

        vectorizer = Embedder(
            model_client=OpenAIClient(),
            # batch_size=self.vectorizer_settings["batch_size"],
            model_kwargs=self.vectorizer_settings["model_kwargs"],
            output_processors=Sequential(ToEmbedderResponse()),
        )
        # TODO: check document splitter, how to process the parent and order of the chunks
        text_splitter = DocumentSplitter(
            split_by=self.text_splitter_settings["split_by"],
            split_length=self.text_splitter_settings["chunk_size"],
            split_overlap=self.text_splitter_settings["chunk_overlap"],
        )
        data_transformer = Sequential(
            text_splitter,
            ToEmbeddings(
                vectorizer=vectorizer,
                batch_size=self.vectorizer_settings["batch_size"],
            ),
        )
        # initialize retriever, which depends on the vectorizer too
        retriever = FAISSRetriever(
            top_k=self.retriever_settings["top_k"],
            dimensions=self.vectorizer_settings["model_kwargs"]["dimensions"],
            vectorizer=vectorizer,
        )
        # TODO: currently retriever will be applied on transformed data. but its not very obvious design pattern
        self.db = LocalDocumentDB(
            retriever_transformer=data_transformer,  # prepare data for retriever to build index with
            retriever=retriever,
            retriever_output_processors=RetrieverOutputToContextStr(deduplicate=True),
        )

        # initialize generator
        self.generator = Generator(
            preset_prompt_kwargs={
                "task_desc_str": r"""
You are a helpful assistant.

Your task is to answer the query that may or may not come with context information.
When context is provided, you should stick to the context and less on your prior knowledge to answer the query.

Output JSON format:
{
    "answer": "The answer to the query",
}"""
            },
            model_client=OpenAIClient(),
            model_kwargs=self.generator_model_kwargs,
            output_processors=Sequential(JsonParser()),
        )
        self.tracking = {"vectorizer": {"num_calls": 0, "num_tokens": 0}}

    def build_index(self, documents: List[Document]):
        self.db.load_documents(documents)
        # transform the documents
        self.db()
        self.db.build_retrieve_index()

    def generate(self, query: str, context: Optional[str] = None) -> Any:
        if not self.generator:
            raise ValueError("Generator is not set")

        prompt_kwargs = {
            "context_str": context,
        }
        response = self.generator.call(input=query, prompt_kwargs=prompt_kwargs)
        return response

    def call(self, query: str) -> Any:
        context_str = self.db.retrieve(query)
        return self.generate(query, context=context_str)


if __name__ == "__main__":
    # NOTE: for the ouput of this following code, check text_lightrag.txt

    doc1 = Document(
        meta_data={"title": "Li Yin's profile"},
        text="My name is Li Yin, I love rock climbing" + "lots of nonsense text" * 500,
        id="doc1",
    )
    doc2 = Document(
        meta_data={"title": "Interviewing Li Yin"},
        text="lots of more nonsense text" * 250
        + "Li Yin is a software developer and AI researcher"
        + "lots of more nonsense text" * 250,
        id="doc2",
    )
    print(doc1)
    rag = RAG()
    print(rag)
    rag.build_index([doc1, doc2])
    print(rag.tracking)
    query = "What is Li Yin's hobby and profession?"

    response = rag.call(query)
    print(f"response: {response}")
