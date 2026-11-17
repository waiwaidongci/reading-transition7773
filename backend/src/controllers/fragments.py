from ..services import fragments,rebuild
class FragmentsController:
    ingest=staticmethod(fragments.ingest)
    heads=staticmethod(fragments.list_session_heads)
    detail=staticmethod(fragments.session_detail)
    publish=staticmethod(fragments.publish)
    base_rates=staticmethod(rebuild.global_base_rates)
