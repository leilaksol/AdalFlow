"""
The data classes used to support core components.
We use dataclass which provides a decorator that automatically adds special methods to classes, such as __init__, __repr__, and __eq__, among others:
"""

from enum import Enum, auto
from typing import List, Dict, Any, Optional, Union
from collections import OrderedDict
from dataclasses import dataclass, field, InitVar
from uuid import UUID


from datetime import datetime
import uuid

from core.tokenizer import Tokenizer

# if sys.version_info >= (3, 10, 1):
#     Literal = typing.Literal
# else:
#     raise ImportError("Please upgrade to Python 3.10.1 or higher to use Literal")


class ModelType(Enum):
    EMBEDDER = auto()
    LLM = auto()
    UNDEFINED = auto()


@dataclass
class Embedding:
    """
    In sync with api spec, same as openai/types/embedding.py
    """

    embedding: List[float]
    index: int  # match with the index of the input


@dataclass
class Usage:
    """
    In sync with api spec, same as openai/types/create_embedding_response.py
    """

    prompt_tokens: int
    total_tokens: int


@dataclass
class EmbedderResponse:
    data: List[Embedding]
    model: str
    usage: Usage


@dataclass
class UserQuery:
    query_str: str
    metadata: Optional[Dict[str, Any]] = None


@dataclass
class AssistantResponse:
    response_str: str
    metadata: Optional[Dict[str, Any]] = None


# TODO: the data class can also be a component?
@dataclass
class DialogTurn:
    r"""A turn consists of a user query and the assistant response, \
    or potentially with more other roles in a multi-party conversation.

    Here we only consider the user query and the assistant response. If you want multiple parties
    you can extend this class or create a new class.
    Examples:
    - User: Hi, how are you?
    - Assistant: I'm fine, thank you!
    DialogTurn(id=uuid4(), user_query=UserQuery("Hi, how are you?"), assistant_response=AssistantResponse("I'm fine, thank you!"))
    """

    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    user_id: Optional[str] = None
    session_id: Optional[str] = None
    order: Optional[int] = (
        None  # the order of the turn in the Dialog Session, starts from 0
    )
    user_query: Optional[UserQuery] = None
    assistant_response: Optional[AssistantResponse] = None
    user_query_timestamp: Optional[datetime] = None
    assistant_response_timestamp: Optional[datetime] = None
    metadata: Optional[Dict[str, Any]] = None  # additional metadata

    def set_user_query(
        self, user_query: UserQuery, user_query_timestamp: Optional[datetime] = None
    ):
        self.user_query = user_query
        if not user_query_timestamp:
            user_query_timestamp = datetime.now()
        self.user_query_timestamp = user_query_timestamp

    def set_assistant_response(
        self,
        assistant_response: AssistantResponse,
        assistant_response_timestamp: Optional[datetime] = None,
    ):
        self.assistant_response = assistant_response
        if not assistant_response_timestamp:
            assistant_response_timestamp = datetime.now()
        self.assistant_response_timestamp = assistant_response_timestamp


@dataclass
class DialogSession:
    r"""A dialog session consists of multiple dialog turns, \
    and potentially with more other roles in a multi-party conversation.

    Here we only consider the dialog turns. If you want multiple parties
    you can extend this class or create a new class.
    """

    id: str = field(default_factory=lambda: str(uuid.uuid4()))  # the id of the session
    user_id: Optional[str] = None
    dialog_turns: OrderedDict[int, DialogTurn] = field(default_factory=OrderedDict)
    # int is the order of the turn, starts from 0
    metadata: Optional[Dict[str, Any]] = None
    session_start_timestamp: Optional[datetime] = field(default_factory=datetime.now)

    # InitVar type annotation is used for parameters that are used in __post_init__
    # but not meant to be fields in the dataclass.
    dialog_turns_input: InitVar[
        Optional[Union[OrderedDict[int, DialogTurn], List[DialogTurn]]]
    ] = None

    def __post_init__(
        self,
        dialog_turns_input: Optional[
            Union[OrderedDict[int, DialogTurn], List[DialogTurn]]
        ] = None,
    ):
        if dialog_turns_input:
            if isinstance(dialog_turns_input, list):
                # Assume the list is of DialogTurn objects and needs to be added to an OrderedDict
                for order, dialog_turn in enumerate(dialog_turns_input):
                    self.append_dialog_turn(dialog_turn)
            elif isinstance(dialog_turns_input, OrderedDict):
                self.dialog_turns = dialog_turns_input
            else:
                raise ValueError(
                    "dialog_turns should be a list of DialogTurn or an OrderedDict"
                )

    def get_next_order(self):
        return len(self.dialog_turns)

    def append_dialog_turn(self, dialog_turn: DialogTurn):
        next_order = self.get_next_order()
        if dialog_turn.order is None:
            dialog_turn.order = next_order
        else:
            assert dialog_turn.order == next_order, f"order should be {next_order}"
        self.dialog_turns[next_order] = dialog_turn

    def get_dialog_turns(self) -> OrderedDict[int, DialogTurn]:
        return self.dialog_turns

    def get_chat_history_str(self) -> str:
        chat_history_str = ""
        for order, dialog_turn in self.dialog_turns.items():
            chat_history_str += f"User: {dialog_turn.user_query.query_str}\n"
            chat_history_str += (
                f"Assistant: {dialog_turn.assistant_response.response_str}\n"
            )
        return chat_history_str

    def delete_dialog_turn(self, order: int):
        self.dialog_turns.pop(order)

    def update_dialog_turn(self, order: int, dialog_turn: DialogTurn):
        self.dialog_turns[order] = dialog_turn


@dataclass
class Document:
    r"""A document object is a text container with optional metadata and vector representation.
    It is the data structure to support functions like Retriever, DocumentSplitter, and LocalDocumentDB.
    """

    text: str = None

    meta_data: Optional[Dict[str, Any]] = None
    # can save data for filtering at retrieval time too
    vector: List[float] = field(default_factory=list)
    # the vector representation of the document

    id: Optional[str] = field(
        default_factory=lambda: str(uuid.uuid4())
    )  # unique id of the document
    order: Optional[int] = (
        None  # order of the chunked document in the original document
    )
    score: Optional[float] = None  # used in retrieved output
    parent_doc_id: Optional[Union[str, UUID]] = (
        None  # id of the Document where the chunk is from
    )
    estimated_num_tokens: Optional[int] = (
        None  # useful for cost and chunking estimation
    )

    def __post_init__(self):
        if self.estimated_num_tokens is None and self.text:
            tokenizer = Tokenizer()
            self.estimated_num_tokens = tokenizer.count_tokens(self.text)

    @staticmethod
    def from_dict(doc: Dict):
        assert "meta_data" in doc, "meta_data is required"
        assert "text" in doc, "text is required"
        # if "estimated_num_tokens" not in doc:
        #     tokenizer = Tokenizer()
        #     doc["estimated_num_tokens"] = tokenizer.count_tokens(doc["text"])
        if "id" not in doc:
            doc["id"] = uuid.uuid4()

        return Document(**doc)

    # def __repr__(self) -> str:
    #     # TODO: repr only those non empty fields
    #     return f"Document(id={self.id}, meta_data={self.meta_data}, text={self.text[0:50]}, estimated_num_tokens={self.estimated_num_tokens})"

    # def __str__(self):
    #     return self.__repr__()


@dataclass
class RetrieverOutput:
    r"""Mainly used to retrieve a list of documents with scores."""

    doc_indexes: List[int]  # either index or ids potentially
    doc_scores: Optional[List[float]] = None
    query: Optional[str] = None
    documents: Optional[List[Document]] = None
