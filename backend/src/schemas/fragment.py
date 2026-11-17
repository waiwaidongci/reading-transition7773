from typing import Optional
from pydantic import BaseModel,Field
class FragmentOp(BaseModel):
    position:int=Field(ge=0,le=100000)
    revision:int=Field(ge=1)
    chapter:Optional[str]=Field(default=None,max_length=600)
    tombstone:bool=False
class FragmentBatch(BaseModel):
    session:str=Field(min_length=1,max_length=160)
    operations:list[FragmentOp]=Field(min_length=1,max_length=2000)
    idempotency_key:Optional[str]=Field(default=None,max_length=200)
class SessionPublish(BaseModel):
    session:str=Field(min_length=1,max_length=160)
