from fastapi import APIRouter,Depends
from ..config.database import db_session
from ..schemas.fragment import FragmentBatch,SessionPublish
from ..services.auth import current_user,writer
from ..controllers.fragments import FragmentsController as C
router=APIRouter()
@router.post('/sources/{id}/fragments')
def ingest(id:int,data:FragmentBatch,db=Depends(db_session),u=Depends(writer)):
    return C.ingest(db,u,id,data.model_dump())
@router.get('/sources/{id}/sessions')
def sessions(id:int,db=Depends(db_session),u=Depends(current_user)):
    return C.heads(db,id)
@router.get('/sources/{id}/sessions/{session_key}')
def detail(id:int,session_key:str,db=Depends(db_session),u=Depends(current_user)):
    return C.detail(db,id,session_key)
@router.post('/sources/{id}/sessions/publish')
def publish(id:int,data:SessionPublish,db=Depends(db_session),u=Depends(writer)):
    return C.publish(db,u,id,data.session)
@router.get('/sources/{id}/base-rates')
def base_rates(id:int,db=Depends(db_session),u=Depends(current_user)):
    return C.base_rates(db,id)
